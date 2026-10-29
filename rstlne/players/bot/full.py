"""The full reader: whole answers sampled from a chain over the board's word slots.

Each slot holds one of three kinds of state:
- a free word: its frequency times its category fit, linked to the word before it by word pair counts
- an unknown word, whose letters come from letter frequency
- a position inside a known phrase or name, which covers a run of slots with its own words

Forward filtering runs left to right; backward sampling draws whole answers from right to left.
Category rules: ING words for What Are You Doing?, shared first letters for Same Letter, rhymes for
Rhyme Time, phrases that overlap on a shared word for Before & After, and for Same Name and
Rhyme Time a reweighting of whole answers.
"""

from __future__ import annotations

import math
import random
import re
from dataclasses import dataclass

import numpy as np

from rstlne.engine.puzzle import LETTERS
from rstlne.engine.state import PublicView
from rstlne.players.bot.belief import Belief
from rstlne.players.bot.lexicon import Lexicon, Phrase, tokens
from rstlne.players.bot.reader import _SHARE, board_text, summarize
from rstlne.players.bot.seed import view_seed
from rstlne.players.bot.versions import Knobs

# Category words -> the kinds of phrase or name that fit it. Wikidata kinds and Wiktionary parts of speech.
_PLACES = {"city", "country", "state", "landmark", "structure", "park", "canyon", "lake", "mountain", "river", "island"}
CATEGORY_KINDS = [
    ("PERSON", {"person", "name"}), ("PEOPLE", {"person", "name"}), ("CHARACTER", {"character", "name"}),
    ("LANDMARK", {"landmark", "structure", "park", "canyon", "mountain", "name"}), ("MAP", _PLACES | {"name"}),
    ("PLACE", _PLACES | {"noun", "name"}), ("FOOD", {"food", "dish", "drink", "noun"}), ("KITCHEN", {"food", "dish", "noun"}),
    ("LIVING", {"animal", "noun"}), ("ANIMAL", {"animal", "noun"}), ("SHOW", {"film", "tv", "song", "band", "person"}),
    ("TITLE", {"film", "tv", "book", "song", "name"}), ("SONG", {"song", "band", "person"}), ("GAMES", {"game", "noun"}),
    ("EVENT", {"holiday", "noun"}), ("PHRASE", {"phrase", "proverb", "prep_phrase", "intj", "noun", "verb", "adj", "adv"}),
    ("DOING", {"verb", "noun"}), ("MAKING", {"verb", "noun", "dish", "food"}), ("WEARING", {"noun"}),
    ("THING", {"noun"}), ("HOUSE", {"noun"}), ("OCCUPATION", {"noun"}),
]
ING_CATEGORIES = ("DOING",)
STRUCTURAL = ("BEFORE", "SAME NAME", "RHYME", "SAME LETTER", "MEGAWORD")  # these name a shape, not a topic
ANY = "*"
_AND = {"&", "AND"}


def category_kinds(category: str) -> set[str]:
    upper = category.upper()
    if any(word in upper for word in STRUCTURAL):
        return {ANY}
    kinds: set[str] = set()
    for word, fit in CATEGORY_KINDS:
        if word in upper:
            kinds |= fit
    return kinds


@dataclass
class _Slot:
    pattern: str  # the board's word, `_` for hidden squares, punctuation in place
    words: list[str]  # free words that fit
    weight: np.ndarray  # each free word's odds before its neighbors
    ids: np.ndarray  # pair ids, -1 for words without pair counts
    unknown: float  # odds of a word the vocabulary doesn't know


@dataclass(frozen=True)
class _Match:
    phrase: Phrase
    start: int
    weight: float

    @property
    def end(self) -> int:
        return self.start + len(self.phrase.words) - 1


class FullReader:
    name = "full"

    def __init__(self, lexicon: Lexicon, knobs: Knobs):
        self.lexicon = lexicon
        self.knobs = knobs

    def read(self, view: PublicView, refuted: frozenset[str] = frozenset(),
             suggested: tuple[str, float] | None = None) -> Belief:
        text = board_text(view.board)
        if "_" not in text:
            return Belief(letters={}, answers=((text, 1.0),), oov=0.0)
        used = set(view.used_letters)
        pool = sorted(LETTERS - used)
        words, seps = tokens(text)
        category = view.category.upper()
        kinds = category_kinds(category)
        slots = [self._slot(w, used, category) for w in words]
        matches = self._matches(words, seps, used, kinds)
        rng = random.Random(view_seed(view))
        samples, unknown = self._sample(slots, matches, category, rng, pool)
        if "SAME NAME" in category or "RHYME" in category:
            samples, unknown = self._reweight(samples, unknown, category, rng)
        answers = [self._join(s, seps) for s in samples]
        return summarize(answers, unknown, text, pool, self.knobs, refuted, suggested)

    # Slots and phrase matches

    def _slot(self, pattern: str, used: set[str], category: str) -> _Slot:
        lex, knobs = self.lexicon, self.knobs
        if "_" not in pattern:
            return _Slot(pattern, [pattern], np.array([lex.freq(pattern)]), np.array([lex.pair_ids.get(pattern, -1)]), 0.0)
        core = re.sub(r"^[^A-Z_']+|[^A-Z_']+$", "", pattern)  # punctuation around the word, like a comma
        lead, trail = pattern[: pattern.index(core)], pattern[pattern.index(core) + len(core):]
        fitting = []
        for w in lex.by_length.get(len(core), ()):
            if _fits(w, core, used):
                fitting.append(w)
        weight = np.array([lex.freq(w) for w in fitting])
        if fitting:
            weight = weight * np.exp(knobs.fit_weight * lex.fit(fitting, category))
            if any(c in category for c in ING_CATEGORIES):
                weight = weight * np.where([w.endswith("ING") for w in fitting], knobs.ing_boost, 1.0)
            keep = np.argsort(-weight, kind="stable")[: knobs.slot_candidates]
            fitting, weight = [fitting[i] for i in keep], weight[keep]
        open_square = sum(_SHARE[c] for c in LETTERS - used)
        unknown = knobs.unknown_word * _length_share(len(core))
        for c in core:
            unknown *= open_square if c == "_" else _SHARE.get(c, 1.0)
        full = [lead + w + trail for w in fitting]
        return _Slot(pattern, full, weight, np.array([lex.pair_ids.get(w, -1) for w in fitting], dtype=np.int64), unknown)

    def _matches(self, words, seps, used: set[str], kinds: set[str]) -> list[_Match]:
        lex, knobs = self.lexicon, self.knobs
        out = []
        for start in range(len(words)):
            for length in range(1, len(words) - start + 1):
                span = words[start:start + length]
                key = (tuple(len(w) for w in span), tuple(seps[start:start + length - 1]))
                entry = lex.shapes.get(key)
                if entry is None:
                    continue
                pattern = "".join(w + s for w, s in zip(span, (*seps[start:start + length - 1], "")))
                for i, text in enumerate(entry.texts):
                    if _fits(text, pattern, used):
                        phrase = lex.phrase(key, i)
                        out.append(_Match(phrase, start, self.match_weight(phrase, kinds)))
        return out

    def match_weight(self, phrase: Phrase, kinds: set[str]) -> float:
        """A known phrase over its run of slots: its prior odds against free words, times the free words'
        total mass over those lengths, times its share of popularity among phrases of the same shape."""
        lex, knobs = self.lexicon, self.knobs
        fits = ANY in kinds or bool(phrase.kinds & kinds)
        if len(phrase.words) == 1:
            odds = knobs.name_odds if fits else knobs.name_odds_other
        else:
            odds = knobs.phrase_odds if fits else knobs.phrase_odds_other
        mass = math.prod(lex.length_mass.get(len(w), 1e-6) for w in phrase.words)
        key = (tuple(len(w) for w in phrase.words), phrase.separators)
        return odds * mass * phrase.popularity / lex.shape_popularity[key]

    # Forward filtering, backward sampling

    def _links(self, a: _Slot, b: _Slot, category: str) -> np.ndarray:
        """How much each free word in `a` raises each free word in `b`'s odds, beyond b's own frequency."""
        knobs, lex = self.knobs, self.lexicon
        counts = lex.pair_count(a.ids, b.ids)
        first = lex.word_counts[a.ids.clip(0)] if len(lex.word_counts) else np.zeros(len(a.ids))
        first = np.where(a.ids >= 0, first, 0.0)
        own = np.array([lex.freq(w) for w in b.words])
        seen = np.where(a.ids >= 0, lex.distinct[a.ids.clip(0)], 0.0) if len(lex.distinct) else np.zeros(len(a.ids))
        with np.errstate(divide="ignore", invalid="ignore"):
            # Witten-Bell: P(b | a) / P(b). Unseen pairs cost more after a word with plenty of evidence.
            lift = (counts / own[None, :] + seen[:, None]) / (first[:, None] + seen[:, None])
        links = np.where(first[:, None] > 0, (1 - knobs.pair_weight) + knobs.pair_weight * lift, 1.0)
        if "SAME LETTER" in category:
            same = np.array([[x.strip("&,.'-")[:1] == y.strip("&,.'-")[:1] for y in b.words] for x in a.words])
            links = links * np.where(same, knobs.same_letter_boost, 1.0)
        if "RHYME" in category:
            links = links * np.array([[knobs.rhyme_boost if self._rhyme(x, y) else 1.0 for y in b.words] for x in a.words])
        return links

    def _sample(self, slots: list[_Slot], matches: list[_Match], category: str, rng: random.Random,
                pool: list[str]) -> tuple[list[list[str]], list[bool]]:
        n = len(slots)
        overlap = "BEFORE" in category and "AFTER" in category
        at = [[(m, k) for m in matches for k in range(len(m.phrase.words)) if m.start + k == i] for i in range(n)]
        index = [{state: j for j, state in enumerate(states)} for states in at]
        ends = [[j for j, (m, k) in enumerate(states) if k == len(m.phrase.words) - 1] for states in at]
        links = [self._links(slots[i], slots[i + 1], category) for i in range(n - 1)]
        free, unknown, phrase = [], [], []  # forward weights per slot, each slot scaled to sum to 1
        for i, slot in enumerate(slots):
            if i == 0:
                f, u = slot.weight.copy(), slot.unknown
                p = np.array([m.weight if k == 0 else 0.0 for m, k in at[0]])
            else:
                nonfree = unknown[-1] + phrase[-1][ends[i - 1]].sum()
                total = nonfree + free[-1].sum()
                f = slot.weight * (free[-1] @ links[i - 1] + nonfree)
                u = slot.unknown * total
                p = np.zeros(len(at[i]))
                for j, (m, k) in enumerate(at[i]):
                    if k == 0:
                        p[j] = m.weight * total
                    else:
                        p[j] = phrase[-1][index[i - 1][(m, k - 1)]]
                        if overlap and k == 1:
                            p[j] += sum(w for _, _, w in self._overlaps(m, slots[i - 1], at[i - 1], ends[i - 1],
                                                                       free[-1], phrase[-1]))
            scale = f.sum() + u + p.sum()
            if scale == 0:  # nothing fits: the unknown word carries the slot
                u, scale = 1.0, 1.0
            free.append(f / scale)
            unknown.append(u / scale)
            phrase.append(p / scale)

        # Backward sampling. At each slot, a state is ("free", j), ("unknown", None), or ("phrase", j).
        samples, oov = [], []
        weights = [_cdf(np.concatenate([free[i], [unknown[i]], phrase[i][ends[i]]])) for i in range(n)]
        share = [_SHARE[c] for c in pool]
        for _ in range(self.knobs.samples):
            words = [""] * n
            unknown_word = False
            state = self._from(rng, weights[-1], len(free[-1]), ends[-1])
            for i in range(n - 1, -1, -1):
                kind, j = state
                if kind == "free":
                    words[i] = slots[i].words[j]
                elif kind == "unknown":
                    unknown_word = True
                    words[i] = "".join(rng.choices(pool, share)[0] if c == "_" else c for c in slots[i].pattern)
                else:
                    m, k = at[i][j]
                    words[i] = m.phrase.words[k]
                if i == 0:
                    break
                if kind == "phrase" and at[i][j][1] > 0:
                    m, k = at[i][j]
                    state = ("phrase", index[i - 1][(m, k - 1)])
                    if overlap and k == 1:
                        before = [(state, phrase[i - 1][state[1]])] + [
                            ((what, where), w) for what, where, w in
                            self._overlaps(m, slots[i - 1], at[i - 1], ends[i - 1], free[i - 1], phrase[i - 1])]
                        state = rng.choices([b for b, _ in before], [w for _, w in before])[0]
                elif kind == "free":
                    cdf = _cdf(np.concatenate([free[i - 1] * links[i - 1][:, j], [unknown[i - 1]],
                                               phrase[i - 1][ends[i - 1]]]))
                    state = self._from(rng, cdf, len(free[i - 1]), ends[i - 1])
                else:
                    state = self._from(rng, weights[i - 1], len(free[i - 1]), ends[i - 1])
            samples.append(words)
            oov.append(unknown_word)
        return samples, oov

    def _overlaps(self, m: _Match, before: _Slot, states, ends, free: np.ndarray, phrase: np.ndarray):
        """Before & After: phrase m starts on the slot before, sharing its first word with what ends there.
        Yields (kind, index, weight); the shared word counts once."""
        shared = m.phrase.words[0]
        rest = m.weight / max(self.lexicon.freq(shared), 1e-12)
        for j in ends:
            if states[j][0].phrase.words[-1] == shared:
                yield "phrase", j, phrase[j] * rest
        for j, word in enumerate(before.words):
            if word == shared:
                yield "free", j, free[j] * rest

    @staticmethod
    def _from(rng: random.Random, cdf: np.ndarray, free_count: int, ends: list[int]):
        pick = int(np.searchsorted(cdf, rng.random() * cdf[-1], side="right"))
        pick = min(pick, len(cdf) - 1)
        if pick < free_count:
            return "free", pick
        if pick == free_count:
            return "unknown", None
        return "phrase", ends[pick - free_count - 1]

    # Whole answers

    def _reweight(self, samples, unknown, category, rng):
        """Resample whole answers by a category check the chain can't see: Same Name, or rhymes far apart."""
        weights = []
        for words in samples:
            w = 1.0
            if "SAME NAME" in category and self._same_name(words):
                w *= self.knobs.same_name_boost
            if "RHYME" in category and self._rhymes_anywhere(words):
                w *= self.knobs.rhyme_boost
            weights.append(w)
        picks = rng.choices(range(len(samples)), weights, k=len(samples))
        return [samples[i] for i in picks], [unknown[i] for i in picks]

    def _same_name(self, words: list[str]) -> bool:
        """`BIRTHDAY & WEDDING CAKE`: the left half plus the right half's ending is a known phrase too."""
        for i, w in enumerate(words):
            if w in _AND and 0 < i < len(words) - 1:
                left, right = words[:i], words[i + 1:]
                for cut in range(1, len(right)):
                    if " ".join(left + right[cut:]) in self.lexicon.texts and " ".join(right) in self.lexicon.texts:
                        return True
        return False

    def _rhymes_anywhere(self, words: list[str]) -> bool:
        content = [w for w in words if len(w) >= 3 and w not in _AND]
        return any(self._rhyme(a, b) for i, a in enumerate(content) for b in content[i + 1:])

    def _rhyme(self, a: str, b: str) -> bool:
        if a == b:
            return False
        return bool(self.lexicon.rhymes.get(a, frozenset()) & self.lexicon.rhymes.get(b, frozenset()))

    @staticmethod
    def _join(words: list[str], seps: tuple[str, ...]) -> str:
        return "".join(w + s for w, s in zip(words, (*seps, "")))


def _fits(word: str, pattern: str, used: set[str]) -> bool:
    if len(word) != len(pattern):
        return False
    for w, p in zip(word, pattern):
        if p == "_":
            if w not in LETTERS or w in used:
                return False
        elif w != p:
            return False
    return True


def _length_share(n: int) -> float:
    """Rough share of English words with n letters, for the unknown word."""
    return max(1e-4, math.exp(-((n - 6) ** 2) / 18) / 5.3)


def _cdf(weights: np.ndarray) -> np.ndarray:
    return np.cumsum(weights)
