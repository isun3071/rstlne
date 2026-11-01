"""The full reader's word data: words, phrases and names, word pairs, rhymes, and vectors.

Loaded once per process from data/, or built from small parts in tests. Phrases are stored compactly
by shape, and a Phrase is only built for one that fits a board. The first load compiles everything
into data/compiled-*.pickle, so later loads, one per tournament process, are quick.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import pickle
import re
import sqlite3
from collections import defaultdict
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import numpy as np

from rstlne import settings
from rstlne.engine.puzzle import LETTERS

FLOOR = 1e-9  # frequency of a word wordfreq doesn't know
COMPILED = 2  # bump when the compiled layout changes
_SEPARATOR = re.compile(r"([ -])")
# Wiktionary headwords use placeholders a board fills in
_PLACEHOLDERS = {"ONE'S": ("YOUR", "HIS", "HER", "MY", "THEIR", "OUR")}


def data_dir() -> Path:
    """data/, or RSTLNE_DATA when set, which tests use to keep the real data out."""
    return Path(os.environ.get("RSTLNE_DATA", settings.ROOT / "data"))


def tokens(text: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """`WELL-KNOWN FACT` -> (("WELL", "KNOWN", "FACT"), ("-", " ")): words, and what separates them."""
    parts = _SEPARATOR.split(text)
    return tuple(parts[0::2]), tuple(parts[1::2])


def shape(text: str) -> tuple:
    words, seps = tokens(text)
    return tuple(len(w) for w in words), seps


@dataclass(frozen=True)
class Phrase:
    words: tuple[str, ...]
    separators: tuple[str, ...]
    kinds: frozenset[str]
    weight: float  # sitelinks for a name, sense count for a Wiktionary entry
    popularity: float = 1.0  # weight and corpus use together; see Lexicon._index_phrases

    @property
    def text(self) -> str:
        return "".join(w + s for w, s in zip(self.words, (*self.separators, "")))


@dataclass
class _Shape:
    """Every phrase of one shape, in parallel lists."""

    texts: list[str] = field(default_factory=list)
    kinds: list[frozenset[str]] = field(default_factory=list)
    weight: list[float] = field(default_factory=list)
    popularity: list[float] = field(default_factory=list)


@dataclass
class Ngrams:
    """Version 5's word, pair, and triple counts from full English Wikipedia, as sorted integer keys."""

    ids: dict[str, int]  # uppercase word -> id
    unigrams: np.ndarray
    pair_keys: np.ndarray
    pair_counts: np.ndarray
    triple_keys: np.ndarray
    triple_counts: np.ndarray
    followers: np.ndarray  # distinct words seen after each word, for Witten-Bell smoothing

    @classmethod
    def build(cls, unigrams: Mapping[str, int], pairs: Mapping[tuple[str, str], int] | None = None,
              triples: Mapping[tuple[str, str, str], int] | None = None) -> Ngrams:
        """From plain counts, for tests."""
        words = sorted(set(unigrams) | {w for p in [*(pairs or {}), *(triples or {})] for w in p})
        ids = {w: i for i, w in enumerate(words)}
        def keyed(table, width):
            items = sorted((_key([ids[w] for w in k]), n) for k, n in (table or {}).items())
            return (np.array([k for k, _ in items], np.int64), np.array([n for _, n in items], np.int64))
        pk, pc = keyed(pairs, 2)
        tk, tc = keyed(triples, 3)
        counts = np.array([unigrams.get(w, 0) for w in words], np.int64)
        return cls._made(words, counts, pk, pc, tk, tc)

    @classmethod
    def load(cls, root: Path) -> Ngrams:
        """The fetched files, memory-mapped."""
        root = Path(root)
        words = (root / "enwiki-words.txt").read_text().split("\n")[:-1]
        arrays = [np.load(root / f"enwiki-{name}.npy", mmap_mode="r")
                  for name in ("unigrams", "pair-keys", "pair-counts", "triple-keys", "triple-counts")]
        return cls._made(words, *arrays)

    @classmethod
    def _made(cls, words, unigrams, pk, pc, tk, tc) -> Ngrams:
        followers = np.bincount(np.asarray(pk) >> NGRAM_BITS, minlength=len(words)) if len(pk) else np.zeros(len(words))
        ids: dict[str, int] = {}
        for i, w in enumerate(words):  # the dotless ı uppercases to I: of two such words, the commoner keeps the name
            if w.upper() not in ids or unigrams[i] > unigrams[ids[w.upper()]]:
                ids[w.upper()] = i
        return cls(ids, unigrams, pk, pc, tk, tc, followers)

    def ids_of(self, words: Iterable[str]) -> np.ndarray:
        return np.array([self.ids.get(w.strip("&,.'-!?").upper(), -1) for w in words], dtype=np.int64)

    def pair(self, first: np.ndarray, second: np.ndarray) -> np.ndarray:
        """Counts for every (first[i], second[j]) pair, -1 meaning unknown. Shape (len(first), len(second))."""
        known = (first[:, None] >= 0) & (second[None, :] >= 0)
        return np.where(known, _lookup(self.pair_keys, self.pair_counts, _key([first[:, None], second[None, :]])), 0)

    def triple(self, a: int, b: int, c: int) -> int:
        return int(_lookup(self.triple_keys, self.triple_counts, np.array([_key([a, b, c])]))[0])


NGRAM_BITS = 18  # as rstlne.data.WORD_BITS: a word's share of a pair or triple key


def _key(ids):
    key = np.asarray(ids[0], np.int64)
    for i in ids[1:]:
        key = (key << NGRAM_BITS) | np.asarray(i, np.int64)
    return key


def _lookup(keys: np.ndarray, counts: np.ndarray, wanted: np.ndarray) -> np.ndarray:
    if not len(keys):
        return np.zeros(np.shape(wanted), np.int64)
    at = np.searchsorted(keys, wanted).clip(0, len(keys) - 1)
    return np.where(np.asarray(keys)[at] == wanted, np.asarray(counts)[at], 0)


@dataclass
class Lexicon:
    frequency: dict[str, float]  # word -> share of English words, from wordfreq
    by_length: dict[int, list[str]]  # vocabulary by length, commonest first
    shapes: dict[tuple, _Shape] = field(default_factory=dict)  # phrases by (word lengths, separators)
    texts: frozenset[str] = frozenset()  # every phrase's text, for whole-answer checks
    length_mass: dict[int, float] = field(default_factory=dict)  # total frequency of the vocabulary's words by length
    shape_popularity: dict[tuple, float] = field(default_factory=dict)  # total popularity of the phrases of each shape
    pair_ids: dict[str, int] = field(default_factory=dict)
    pair_keys: np.ndarray = field(default_factory=lambda: np.zeros(0, np.int64))  # first id * size + second id, sorted
    pair_counts: np.ndarray = field(default_factory=lambda: np.zeros(0, np.float64))
    word_counts: np.ndarray = field(default_factory=lambda: np.zeros(0, np.float64))  # by pair id
    distinct: np.ndarray = field(default_factory=lambda: np.zeros(0, np.float64))  # distinct words seen after each
    rhymes: dict[str, frozenset[str]] = field(default_factory=dict)
    vector_ids: dict[str, int] = field(default_factory=dict)
    vectors: np.ndarray = field(default_factory=lambda: np.zeros((0, 1), np.float16))
    name: str = "full"
    ngrams: Ngrams | None = None  # from version 5, attached at load, never pickled

    @classmethod
    def build(
        cls,
        words: Mapping[str, float],
        phrases: Iterable[tuple[str, str, float]] = (),
        pairs: Mapping[tuple[str, str], int] | None = None,
        counts: Mapping[str, int] | None = None,
        rhymes: Mapping[str, Iterable[str]] | None = None,
        vectors: Mapping[str, np.ndarray] | None = None,
        cased: bool = False,
    ) -> Lexicon:
        """From plain parts: words with frequencies, (text, kind, weight) phrases, pair and word counts."""
        lexicon = cls._words(words, cased)
        if pairs:
            lexicon._index_pairs(((a, b, n) for (a, b), n in pairs.items()), counts or {})
        lexicon._index_phrases(phrases)
        lexicon.rhymes = {w.upper(): frozenset(keys) for w, keys in (rhymes or {}).items()}
        if vectors:
            names = list(vectors)
            lexicon.vector_ids = {w.upper(): i for i, w in enumerate(names)}
            matrix = np.array([vectors[w] for w in names], dtype=np.float32)
            lexicon.vectors = (matrix / np.linalg.norm(matrix, axis=1, keepdims=True)).astype(np.float16)
        return lexicon

    @classmethod
    def _words(cls, words: Mapping[str, float], cased: bool = False) -> Lexicon:
        """Uppercased words and their frequencies. Two words can uppercase alike (the dotless ı becomes I): `cased`
        keeps the larger frequency, where version 4 and earlier kept whichever came last."""
        if cased:
            frequency: dict[str, float] = {}
            for w, f in words.items():
                frequency[w.upper()] = max(frequency.get(w.upper(), 0.0), f)
        else:
            frequency = {w.upper(): f for w, f in words.items()}
        by_length: dict[int, list[str]] = defaultdict(list)
        for w in sorted(frequency, key=lambda w: -frequency[w]):
            if all(c in LETTERS or c == "'" for c in w):
                by_length[len(w)].append(w)
        lexicon = cls(frequency, dict(by_length))
        lexicon.length_mass = {n: sum(frequency[w] for w in ws) for n, ws in by_length.items()}
        return lexicon

    def _index_pairs(self, rows: Iterable[tuple[str, str, int]], counts: Mapping[str, int]) -> None:
        """Pair counts as sorted int64 keys, straight from (first, second, count) rows."""
        ids: dict[str, int] = {}
        firsts, seconds, values = [], [], []
        for a, b, n in rows:
            firsts.append(ids.setdefault(a.upper(), len(ids)))
            seconds.append(ids.setdefault(b.upper(), len(ids)))
            values.append(n)
        for w in counts:
            ids.setdefault(w.upper(), len(ids))
        size = len(ids)
        keys = np.array(firsts, dtype=np.int64) * size + np.array(seconds, dtype=np.int64)
        order = np.argsort(keys)
        self.pair_ids = ids
        self.pair_keys = keys[order]
        self.pair_counts = np.array(values, dtype=np.float64)[order]
        self.word_counts = np.zeros(size)
        for w, n in counts.items():
            self.word_counts[ids[w.upper()]] = n
        self.distinct = np.bincount(self.pair_keys // size, minlength=size).astype(np.float64) if size else np.zeros(0)

    def _index_phrases(self, phrases: Iterable[tuple[str, str, float]]) -> None:
        """Merge sources and placeholder variants, then file each phrase under its shape.
        Popularity is its weight times how often its rarest word pair (or its one word) shows up in text."""
        merged: dict[str, tuple[set[str], float]] = {}
        for text, kind, weight in phrases:
            for variant in _variants(text.upper()):
                kinds, old = merged.get(variant, (set(), 0.0))
                kinds.add(kind)
                merged[variant] = (kinds, max(weight, old))
        interned: dict[frozenset, frozenset] = {}
        texts = list(merged)
        for text, used in zip(texts, self._uses(texts)):
            kinds, weight = merged[text]
            kinds = interned.setdefault(frozenset(kinds), frozenset(kinds))
            entry = self.shapes.setdefault(shape(text), _Shape())
            entry.texts.append(text)
            entry.kinds.append(kinds)
            entry.weight.append(weight)
            entry.popularity.append((1 + math.log1p(weight)) * (1 + math.log1p(used)))
        self.texts = frozenset(texts)
        self.shape_popularity = {k: sum(v.popularity) for k, v in self.shapes.items()}

    def _uses(self, texts: list[str]) -> np.ndarray:
        """Corpus use of each phrase: its rarest word pair's count, or a one-word name's own count."""
        use = np.zeros(len(texts))
        if not len(self.pair_keys):
            return use
        size = len(self.word_counts)
        owners, firsts, seconds = [], [], []
        for i, text in enumerate(texts):
            ids = [self.pair_ids.get(w, -1) for w in tokens(text)[0]]
            if len(ids) == 1:
                use[i] = self.word_counts[ids[0]] if ids[0] >= 0 else 0.0
                continue
            for a, b in zip(ids, ids[1:]):
                owners.append(i)
                firsts.append(a)
                seconds.append(b)
        if owners:
            owners, firsts, seconds = np.array(owners), np.array(firsts), np.array(seconds)
            keys = firsts * size + seconds
            at = np.searchsorted(self.pair_keys, keys).clip(0, len(self.pair_keys) - 1)
            found = np.where((firsts >= 0) & (seconds >= 0) & (self.pair_keys[at] == keys), self.pair_counts[at], 0.0)
            least = np.full(len(texts), np.inf)
            np.minimum.at(least, owners, found)
            multi = np.isfinite(least)
            use[multi] = least[multi]
        return use

    def phrases(self, key: tuple) -> Iterator[Phrase]:
        """Every phrase of this shape, built on demand."""
        entry = self.shapes.get(key)
        for i in range(len(entry.texts) if entry else 0):
            yield self.phrase(key, i)

    def phrase(self, key: tuple, i: int) -> Phrase:
        entry = self.shapes[key]
        words, seps = tokens(entry.texts[i])
        return Phrase(words, seps, entry.kinds[i], entry.weight[i], entry.popularity[i])

    def freq(self, word: str) -> float:
        return self.frequency.get(word, FLOOR)

    def pair_count(self, first: np.ndarray, second: np.ndarray) -> np.ndarray:
        """Counts for every (first[i], second[j]) pair of pair ids, -1 meaning unknown. Shape (len(first), len(second))."""
        size = len(self.word_counts)
        out = np.zeros((len(first), len(second)))
        if not len(self.pair_keys) or not len(first) or not len(second):
            return out
        known = (first[:, None] >= 0) & (second[None, :] >= 0)
        keys = (first[:, None] * size + second[None, :])
        at = np.searchsorted(self.pair_keys, keys).clip(0, len(self.pair_keys) - 1)
        hit = known & (self.pair_keys[at] == keys)
        out[hit] = self.pair_counts[at[hit]]
        return out

    def fit(self, words: list[str], category: str) -> np.ndarray:
        """Cosine of each word's vector with the category's, 0 for words without one."""
        out = np.zeros(len(words))
        target = self._category_vector(category)
        if target is None:
            return out
        rows = [self.vector_ids.get(w, -1) for w in words]
        have = [i for i, r in enumerate(rows) if r >= 0]
        if have:
            out[have] = self.vectors[[rows[i] for i in have]].astype(np.float32) @ target
        return out

    def closeness(self, first: list[str], second: list[str]) -> np.ndarray:
        """Cosine between every word of `first` and every word of `second`, 0 where either lacks a vector."""
        a = [self.vector_ids.get(w.strip("&,.'-!?"), -1) for w in first]
        b = [self.vector_ids.get(w.strip("&,.'-!?"), -1) for w in second]
        out = np.zeros((len(a), len(b)))
        ha, hb = [i for i, r in enumerate(a) if r >= 0], [j for j, r in enumerate(b) if r >= 0]
        if ha and hb:
            va = self.vectors[[a[i] for i in ha]].astype(np.float32)
            vb = self.vectors[[b[j] for j in hb]].astype(np.float32)
            out[np.ix_(ha, hb)] = va @ vb.T
        return out

    def _category_vector(self, category: str) -> np.ndarray | None:
        words = [w for w in re.findall(r"[A-Z]+", category.upper()) if w not in _CATEGORY_STOP]
        rows = [self.vector_ids[w] for w in words if w in self.vector_ids]
        if not rows:
            return None
        v = self.vectors[rows].astype(np.float32).mean(axis=0)
        return v / np.linalg.norm(v)


_CATEGORY_STOP = {"THE", "A", "AN", "AND", "ARE", "YOU", "WE", "WHAT", "IN", "ON", "OF"}


def _variants(text: str) -> list[str]:
    out = [text]
    for placeholder, fills in _PLACEHOLDERS.items():
        if placeholder in text.split(" "):
            out = [t.replace(placeholder, f) for t in out for f in fills] + out
    return out


def rhyme_key(phones: list[str]) -> str:
    """The sounds from the last stressed vowel on: CAT -> AE1 T."""
    for i in range(len(phones) - 1, -1, -1):
        if phones[i][-1] in "12":
            return " ".join(phones[i:])
    return " ".join(phones)


OPTIONAL_SOURCES = ("enwiki",)  # fetched only for later versions; a fingerprint covers them only when asked


def fingerprint(root: Path, vocabulary: int, extra: Iterable[str] = ()) -> str:
    """Names the data a lexicon came from: every fetched file's hash, and the vocabulary size. Optional sources
    count only when named in `extra`, so fetching one leaves earlier versions' fingerprints unchanged."""
    path = root / "manifest.json"
    manifest = json.loads(path.read_text()) if path.exists() else {}
    hashes = sorted({(f, e["sha256"]) for source, entry in manifest.items()
                     if source not in OPTIONAL_SOURCES or source in extra for f, e in entry["files"].items()})
    return hashlib.sha256(json.dumps([COMPILED, vocabulary, hashes]).encode()).hexdigest()[:12]


@lru_cache(maxsize=4)
def cache_path(root: Path, found: str, cased: bool) -> Path:
    """Where a compiled lexicon lives: one file per data fingerprint and lexicon variant."""
    return Path(root) / f"compiled-{found}{'-cased' if cased else ''}.pickle"


def load(path: str, vocabulary: int, cased: bool = False, ngrams: bool = False) -> Lexicon:
    """The full lexicon from data/, once per process, compiled to a pickle the first time."""
    root = Path(path)
    found = fingerprint(root, vocabulary)
    cache = cache_path(root, found, cased)
    if cache.exists():
        with open(cache, "rb") as f:
            lexicon = pickle.load(f)
    else:
        lexicon = _compile(root, vocabulary, cased)
        for old in root.glob("compiled-*.pickle"):
            if not old.name.startswith(f"compiled-{found}"):  # stale data; another variant's cache stays
                old.unlink()
        partial = cache.with_suffix(".partial")
        with open(partial, "wb") as f:
            pickle.dump(lexicon, f, protocol=pickle.HIGHEST_PROTOCOL)
        partial.replace(cache)  # whole or not at all, if two processes compile at once
    lexicon.vectors = np.load(root / "vectors.npy", mmap_mode="r")  # shared by every process on the machine
    lexicon.ngrams = Ngrams.load(root) if ngrams else None
    return lexicon


def _compile(root: Path, vocabulary: int, cased: bool = False) -> Lexicon:
    import wordfreq

    words = {w: wordfreq.word_frequency(w, "en") for w in wordfreq.top_n_list("en", vocabulary)}
    with sqlite3.connect(root / "lexicon.sqlite") as con:
        phrases = con.execute("SELECT text, kind, weight FROM phrases").fetchall()
    for text, _, _ in phrases:  # every word of a known name or phrase gets its real frequency
        for w in tokens(text)[0]:
            if w.lower() not in words:
                words[w.lower()] = wordfreq.word_frequency(w.lower(), "en") or FLOOR
    lexicon = Lexicon._words(words, cased)
    with sqlite3.connect(root / "pairs.sqlite") as con:
        counts = dict(con.execute("SELECT word, SUM(count) FROM words GROUP BY word"))
        lexicon._index_pairs(con.execute("SELECT first, second, SUM(count) FROM pairs GROUP BY first, second"), counts)
    lexicon._index_phrases(phrases)
    rhymes: dict[str, set[str]] = defaultdict(set)
    for line in (root / "cmudict.dict").read_text().splitlines():
        head, *phones = line.split("#")[0].split()
        rhymes[head.split("(")[0].upper()].add(rhyme_key(phones))
    lexicon.rhymes = {w: frozenset(k) for w, k in rhymes.items()}
    names = (root / "vectors.txt").read_text().split()
    lexicon.vector_ids = {w.upper(): i for i, w in enumerate(names)}
    return lexicon


def available(root: Path | None = None) -> bool:
    root = root or data_dir()
    return all((root / name).exists() for name in ("lexicon.sqlite", "pairs.sqlite", "cmudict.dict", "vectors.npy"))
