"""Fetch and prune the bot's word data into data/. Every source streams; nothing is stored whole.

    python -m rstlne.data fetch [source ...]
    python -m rstlne.data status

wordfreq, the word list itself, ships as a Python package. The rest:
cmudict for rhymes, Wiktionary multiword entries, Wikidata labels filtered by sitelinks,
fastText vectors for the vocabulary, for category fit, and word pair counts from Tatoeba's
English sentences and Simple English Wikipedia.
"""

from __future__ import annotations

import argparse
import bz2
import gzip
import html
import hashlib
import io
import json
import re
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from rstlne import settings
from rstlne.engine.puzzle import LETTERS, PUNCTUATION, normalize

DATA = settings.ROOT / "data"
CAP = 2.5e9  # bytes for everything under data/
AGENT = "rstlne/0.1"  # no personal details
MAX_WORDS = 8
MAX_CHARACTERS = 60
VOCABULARY = 100_000  # wordfreq words that get vectors, besides every word in the phrase lists
WIKIDATA_URL = "https://qlever.dev/api/wikidata"


@dataclass(frozen=True)
class Source:
    url: str
    license: str


SOURCES = {
    "cmudict": Source("https://raw.githubusercontent.com/cmusphinx/cmudict/master/cmudict.dict",
                      "BSD 2-clause, Carnegie Mellon University"),
    "wiktionary": Source("https://kaikki.org/dictionary/English/kaikki.org-dictionary-English.jsonl.gz",
                         "CC BY-SA 4.0 and GFDL, Wiktionary contributors, extracted by wiktextract (kaikki.org)"),
    "wikidata": Source(WIKIDATA_URL, "CC0, Wikidata"),
    "vectors": Source("https://dl.fbaipublicfiles.com/fasttext/vectors-crawl/cc.en.300.vec.gz",
                      "CC BY-SA 3.0, fastText (Facebook AI Research)"),
    "tatoeba": Source("https://downloads.tatoeba.org/exports/per_language/eng/eng_sentences.tsv.bz2",
                      "CC BY 2.0 FR, Tatoeba contributors"),
    "simplewiki": Source("https://dumps.wikimedia.org/simplewiki/latest/simplewiki-latest-pages-articles.xml.bz2",
                         "CC BY-SA 4.0, Simple English Wikipedia contributors"),
}
PAIR_MINIMUM = 2  # pairs seen fewer times than this are dropped
PAIR_PRUNE = 8_000_000  # while counting, past this many pairs, drop the ones seen once

# Wikidata classes to label, with the fewest Wikipedia language editions (sitelinks) a label needs.
# "kind of" patterns follow instance-of or subclass-of, for things Wikidata models as classes, like foods.
_INSTANCE = "wdt:P31"
_KIND_OF = "(wdt:P31|wdt:P279)/wdt:P279*"
WIKIDATA = {
    "person": (f"{_INSTANCE} wd:Q5", 40),
    "character": (f"{_KIND_OF} wd:Q95074", 15),
    "country": (f"{_INSTANCE} wd:Q6256", 0),
    "state": (f"{_INSTANCE} wd:Q35657", 0),
    "city": (f"{_KIND_OF} wd:Q515", 40),
    "landmark": (f"{_KIND_OF} wd:Q570116", 25),
    "structure": (f"{_KIND_OF} wd:Q811979", 40),  # bridges, towers, and buildings, like the Golden Gate Bridge
    "park": (f"{_KIND_OF} wd:Q46169", 15),
    "canyon": (f"{_KIND_OF} wd:Q150784", 10),
    "lake": (f"{_INSTANCE} wd:Q23397", 30),
    "mountain": (f"{_INSTANCE} wd:Q8502", 30),
    "river": (f"{_INSTANCE} wd:Q4022", 30),
    "island": (f"{_INSTANCE} wd:Q23442", 30),
    "film": (f"{_INSTANCE} wd:Q11424", 30),
    "tv": (f"{_INSTANCE} wd:Q5398426", 20),
    "book": (f"{_KIND_OF} wd:Q7725634", 20),
    "song": (f"{_KIND_OF} wd:Q7366", 20),
    "band": (f"{_KIND_OF} wd:Q215380", 30),
    "game": (f"{_KIND_OF} wd:Q11410", 15),
    "food": (f"{_KIND_OF} wd:Q2095", 10),
    "dish": (f"{_KIND_OF} wd:Q746549", 10),
    "drink": (f"{_KIND_OF} wd:Q40050", 10),
    "holiday": (f"{_KIND_OF} wd:Q1445650", 10),
    "team": (f"{_KIND_OF} wd:Q12973014", 30),
    "brand": (f"{_INSTANCE} wd:Q431289", 20),
    "animal": ("wdt:P1843 ?label", 30),  # taxa by their English common name, like bald eagle
}
_OWN_LABEL = {"animal"}


class OverBudget(Exception):
    """data/ would grow past its cap."""


# Cleaning and parsing


def clean(text: str) -> str | None:
    """Uppercase board text, or None when it can't sit on a board: digits, accents, brackets, too long."""
    try:
        phrase = normalize(text)
    except ValueError:
        return None
    letters = sum(c in LETTERS for c in phrase)
    if letters < 2 or len(phrase.split(" ")) > MAX_WORDS or len(phrase) > MAX_CHARACTERS:
        return None
    if set(phrase) - LETTERS - PUNCTUATION - {" "}:
        return None
    return phrase


def wiktionary_phrases(lines: Iterable[str]) -> Iterator[tuple[str, str, float]]:
    """Multiword entries as (phrase, part of speech, sense count). Single words come from wordfreq."""
    for line in lines:
        entry = json.loads(line)
        word = entry.get("word", "")
        if " " not in word.strip():
            continue
        phrase = clean(word)
        if phrase:
            yield phrase, entry.get("pos", ""), float(max(1, len(entry.get("senses", ()))))


def wikidata_query(pattern: str, sitelinks: int, label: str | None = "rdfs:label ?label") -> str:
    """Labels of items matching `pattern`. `label=None` when the pattern itself binds ?label."""
    names = f" ; {label}" if label else ""
    return f"""PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX wikibase: <http://wikiba.se/ontology#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?label (MAX(?s) AS ?links) WHERE {{
  ?x {pattern}{names} ; wikibase:sitelinks ?s .
  FILTER(?s >= {sitelinks}) FILTER(LANG(?label) = "en")
}} GROUP BY ?label"""


def wikidata_labels(body: dict, kind: str) -> Iterator[tuple[str, str, float]]:
    for row in body["results"]["bindings"]:
        phrase = clean(row["label"]["value"])
        if phrase and not (phrase.startswith("Q") and phrase[1:].isdigit()):
            yield phrase, kind, float(row["links"]["value"])


def read_vectors(lines: Iterable[str], vocabulary: set[str]) -> tuple[list[str], np.ndarray]:
    """fastText text vectors for `vocabulary`, lowercased, first casing wins, scaled to unit length."""
    lines = iter(lines)
    next(lines)  # the header: count and dimension
    words, rows, seen = [], [], set()
    for line in lines:
        word, _, rest = line.rstrip("\n").partition(" ")
        key = word.lower()
        if key in vocabulary and key not in seen:
            vector = np.array(rest.split(" "), dtype=np.float32)
            norm = np.linalg.norm(vector)
            if norm > 0:
                seen.add(key)
                words.append(key)
                rows.append(vector / norm)
    return words, np.array(rows, dtype=np.float16)


_SENTENCE_END = re.compile(r"[.!?;:()\"]+")
_WORD = re.compile(r"[a-z]+(?:'[a-z]+)?")
_TEMPLATE = re.compile(r"\{\{[^{}]*\}\}")
_REF = re.compile(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>", re.S)
_TAG = re.compile(r"<[^>]+>")
_FILE_LINK = re.compile(r"\[\[(?:File|Image|Category):[^\]]*\]\]", re.I)
_LINK = re.compile(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]")
_SKIP = ("{|", "|", "!", "==", "*", "#", ":", ";", "{{", "}}")


def sentences(text: str) -> Iterator[list[str]]:
    """Lowercase words, one list per sentence."""
    for part in _SENTENCE_END.split(text.lower().replace("’", "'")):
        words = _WORD.findall(part)
        if words:
            yield words


def tatoeba_sentences(rows: Iterable[str]) -> Iterator[list[str]]:
    for row in rows:
        _, _, text = row.rstrip("\n").split("\t", 2)
        yield from sentences(text)


def wikitext_sentences(lines: Iterable[str]) -> Iterator[list[str]]:
    """Prose from a MediaWiki XML dump: links become their text; templates, tags, tables, and lists go."""
    inside, depth = False, 0
    for line in lines:
        if not inside:
            start = line.find("<text")
            if start < 0:
                continue
            inside = True
            line = line[line.find(">", start) + 1:]
        if "</text>" in line:
            inside = False
            line = line[: line.find("</text>")]
        line = html.unescape(line)
        depth += line.count("{{") - line.count("}}")
        if depth > 0 or line.lstrip().startswith(_SKIP):
            depth = max(depth, 0)
            continue
        depth = max(depth, 0)
        line = _REF.sub(" ", line)
        while _TEMPLATE.search(line):
            line = _TEMPLATE.sub(" ", line)
        line = _FILE_LINK.sub(" ", line)
        line = _LINK.sub(r"\1", line)
        line = _TAG.sub(" ", line).replace("\'\'\'", "").replace("\'\'", "")
        yield from sentences(line)


def count_pairs(stream: Iterable[list[str]], vocabulary: set[str], minimum: int = PAIR_MINIMUM,
                prune: int = PAIR_PRUNE) -> tuple[Counter, dict[tuple[str, str], int]]:
    """Word counts and neighbor pair counts, both inside the vocabulary. Rare pairs are dropped."""
    words, pairs = Counter(), Counter()
    for sentence in stream:
        known = [w if w in vocabulary else None for w in sentence]
        words.update(w for w in known if w)
        pairs.update((a, b) for a, b in zip(known, known[1:]) if a and b)
        if len(pairs) > prune:
            pairs = Counter({k: n for k, n in pairs.items() if n > 1})
    return words, {k: n for k, n in pairs.items() if n >= minimum}


# Storage


def store_phrases(db: Path, source: str, rows: Iterable[tuple[str, str, float]]) -> int:
    """Replace `source`'s phrases in the SQLite file. Returns how many it kept."""
    with sqlite3.connect(db) as con:
        con.execute("CREATE TABLE IF NOT EXISTS phrases (text TEXT, source TEXT, kind TEXT, weight REAL, "
                    "PRIMARY KEY (text, source, kind))")
        con.execute("DELETE FROM phrases WHERE source = ?", (source,))
        con.executemany("INSERT OR REPLACE INTO phrases VALUES (?, ?, ?, ?)",
                        ((text, source, kind, weight) for text, kind, weight in rows))
        return con.execute("SELECT COUNT(*) FROM phrases WHERE source = ?", (source,)).fetchone()[0]


def load_phrases(db: Path) -> list[tuple[str, str, str, float]]:
    with sqlite3.connect(db) as con:
        return con.execute("SELECT text, source, kind, weight FROM phrases").fetchall()


def store_pairs(db: Path, source: str, words: dict[str, int], pairs: dict[tuple[str, str], int]) -> None:
    """Replace `source`'s word and pair counts in the SQLite file."""
    with sqlite3.connect(db) as con:
        con.execute("CREATE TABLE IF NOT EXISTS words (word TEXT, source TEXT, count INTEGER, PRIMARY KEY (word, source)) WITHOUT ROWID")
        con.execute("CREATE TABLE IF NOT EXISTS pairs (first TEXT, second TEXT, source TEXT, count INTEGER, "
                    "PRIMARY KEY (first, second, source)) WITHOUT ROWID")
        con.execute("DELETE FROM words WHERE source = ?", (source,))
        con.execute("DELETE FROM pairs WHERE source = ?", (source,))
        con.executemany("INSERT INTO words VALUES (?, ?, ?)", ((w, source, n) for w, n in words.items()))
        con.executemany("INSERT INTO pairs VALUES (?, ?, ?, ?)", ((a, b, source, n) for (a, b), n in pairs.items()))


def load_pairs(db: Path) -> tuple[dict[str, int], dict[tuple[str, str], int]]:
    """Word and pair counts, summed across sources."""
    with sqlite3.connect(db) as con:
        words = dict(con.execute("SELECT word, SUM(count) FROM words GROUP BY word"))
        pairs = {(a, b): n for a, b, n in con.execute("SELECT first, second, SUM(count) FROM pairs GROUP BY first, second")}
    return words, pairs


def record(data_dir: Path, source: str, files: Sequence[str], cap: float = CAP) -> dict:
    """Note `source`'s files in manifest.json, and refuse if data/ is now past the cap."""
    total = total_bytes(data_dir)
    if total > cap:
        raise OverBudget(f"data/ holds {total / 1e9:.2f} GB, past the {cap / 1e9:.2f} GB cap")
    path = data_dir / "manifest.json"
    manifest = json.loads(path.read_text()) if path.exists() else {}
    entry = {
        "url": SOURCES[source].url,
        "license": SOURCES[source].license,
        "fetched": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "files": {name: {"bytes": (data_dir / name).stat().st_size,
                         "sha256": hashlib.sha256((data_dir / name).read_bytes()).hexdigest()} for name in files},
    }
    manifest[source] = entry
    path.write_text(json.dumps(manifest, indent=2) + "\n")
    return entry


# Network


def stream(url: str, timeout: float = 120):
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": AGENT}), timeout=timeout)


def lines(raw, gz: bool = False) -> Iterator[str]:
    """Decode a byte stream line by line, gunzipping on the way."""
    source = gzip.GzipFile(fileobj=raw) if gz else raw
    yield from io.TextIOWrapper(source, encoding="utf-8", errors="replace")


# Fetch steps


def fetch_cmudict(data_dir: Path, say) -> list[str]:
    with stream(SOURCES["cmudict"].url) as raw:
        (data_dir / "cmudict.dict").write_bytes(raw.read())
    return ["cmudict.dict"]


def fetch_wiktionary(data_dir: Path, say) -> list[str]:
    with stream(SOURCES["wiktionary"].url) as raw:
        kept = store_phrases(data_dir / "lexicon.sqlite", "wiktionary", wiktionary_phrases(lines(raw, gz=True)))
    say(f"  {kept:,} multiword entries")
    return ["lexicon.sqlite"]


def fetch_wikidata(data_dir: Path, say) -> list[str]:
    rows = []
    for kind, (pattern, sitelinks) in WIKIDATA.items():
        label = None if kind in _OWN_LABEL else "rdfs:label ?label"
        url = WIKIDATA_URL + "?" + urllib.parse.urlencode({"query": wikidata_query(pattern, sitelinks, label)})
        request = urllib.request.Request(url, headers={"User-Agent": AGENT, "Accept": "application/sparql-results+json"})
        try:
            with urllib.request.urlopen(request, timeout=180) as raw:
                found = list(wikidata_labels(json.load(raw), kind))
        except Exception as err:  # one class failing shouldn't sink the rest
            say(f"  {kind}: failed ({err}); rerun to retry")
            continue
        say(f"  {kind}: {len(found):,} labels")
        rows += found
    store_phrases(data_dir / "lexicon.sqlite", "wikidata", rows)
    return ["lexicon.sqlite"]


def vocabulary(data_dir: Path, size: int = VOCABULARY) -> set[str]:
    """wordfreq's most common words, plus every word in the phrase lists."""
    import wordfreq

    words = {w for w in wordfreq.top_n_list("en", size)}
    db = data_dir / "lexicon.sqlite"
    if db.exists():
        for text, *_ in load_phrases(db):
            words.update(w.lower() for w in text.replace("-", " ").split(" "))
    return words


def fetch_vectors(data_dir: Path, say) -> list[str]:
    with stream(SOURCES["vectors"].url, timeout=300) as raw:
        words, matrix = read_vectors(lines(raw, gz=True), vocabulary(data_dir))
    np.save(data_dir / "vectors.npy", matrix)
    (data_dir / "vectors.txt").write_text("\n".join(words) + "\n")
    say(f"  {len(words):,} word vectors")
    return ["vectors.npy", "vectors.txt"]


def _fetch_pairs(data_dir: Path, say, name: str, parse) -> list[str]:
    with stream(SOURCES[name].url, timeout=300) as raw:
        text = io.TextIOWrapper(bz2.BZ2File(raw), encoding="utf-8", errors="replace")
        words, pairs = count_pairs(parse(text), vocabulary(data_dir))
    store_pairs(data_dir / "pairs.sqlite", name, words, pairs)
    say(f"  {sum(words.values()):,} words read, {len(pairs):,} pairs kept")
    return ["pairs.sqlite"]


def fetch_tatoeba(data_dir: Path, say) -> list[str]:
    return _fetch_pairs(data_dir, say, "tatoeba", tatoeba_sentences)


def fetch_simplewiki(data_dir: Path, say) -> list[str]:
    return _fetch_pairs(data_dir, say, "simplewiki", wikitext_sentences)


STEPS = {"cmudict": fetch_cmudict, "wiktionary": fetch_wiktionary, "wikidata": fetch_wikidata, "vectors": fetch_vectors,
         "tatoeba": fetch_tatoeba, "simplewiki": fetch_simplewiki}


def fetch(names: Sequence[str], data_dir: Path = DATA, say=print) -> None:
    data_dir.mkdir(exist_ok=True)
    for name in names:
        say(f"{name}: streaming from {SOURCES[name].url}")
        start = time.monotonic()
        files = STEPS[name](data_dir, say)
        entry = record(data_dir, name, files)
        size = sum(f["bytes"] for f in entry["files"].values())
        say(f"  done in {time.monotonic() - start:.0f} s, {size / 1e6:.1f} MB")


def status(data_dir: Path = DATA, say=print) -> None:
    path = data_dir / "manifest.json"
    manifest = json.loads(path.read_text()) if path.exists() else {}
    for name in SOURCES:
        entry = manifest.get(name)
        if entry is None:
            say(f"{name}: not fetched")
            continue
        files = ", ".join(entry["files"])
        say(f"{name}: {files}, fetched {entry['fetched']}, {entry['license']}")
    say(f"total {total_bytes(data_dir) / 1e9:.2f} GB of the {CAP / 1e9:.1f} GB cap")


def total_bytes(data_dir: Path = DATA) -> int:
    """What data/ holds now, each file once."""
    return sum(p.stat().st_size for p in data_dir.iterdir() if p.is_file()) if data_dir.exists() else 0


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m rstlne.data", description="Fetch the bot's word data.")
    commands = parser.add_subparsers(dest="command", required=True)
    get = commands.add_parser("fetch", help="stream and prune sources into data/")
    get.add_argument("sources", nargs="*", default=list(STEPS), help=f"any of: {', '.join(STEPS)}")
    commands.add_parser("status", help="list what's fetched and how much space it takes")
    args = parser.parse_args(argv)
    if args.command == "status":
        status()
        return
    unknown = set(args.sources) - set(STEPS)
    if unknown:
        sys.exit(f"unknown sources: {', '.join(sorted(unknown))}")
    fetch(args.sources)


if __name__ == "__main__":
    main()
