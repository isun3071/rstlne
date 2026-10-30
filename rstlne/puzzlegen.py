"""Fresh puzzles on demand: a generator model writes answers, code checks them, and a judge model
confirms each fits its category. Nothing is ever reused.

    python -m rstlne.puzzlegen --main 40 --bonus 10 --seed 7 --out puzzles/generated/batch-7.json

Every request stands alone: a short system prompt and one request, never a growing conversation.
The prompts never mention the show, so the generator doesn't reach for puzzles it half remembers.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from collections import Counter, deque
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import openai

from rstlne import puzzle_examples
from rstlne import settings as project
from rstlne.engine.puzzle import LETTERS, Puzzle, normalize
from rstlne.llm.openrouter import EmptyResponse, OpenRouter, Usage
from rstlne.narrate import duration, line_output
from rstlne.players.bot import lexicon, versions
from rstlne.players.bot.lexicon import data_dir, rhyme_key

PROMPT_VERSION = 6  # 4: bonus requests ask for less common letters; 5: and for at least 10 letters;
# 6: real puzzles' length and style, few-shot examples, a judge for natural wording, sources for songs and titles,
# and bonus answers in everyday words
DEADLINE = 60  # seconds for one request: a batch of answers takes a few
MAX_FAILURES = 5  # requests failing in a row before a run stops and keeps what it has
FAMILIAR = 4  # the judge rates how familiar an answer is, 1 to 5; below this it's out
# Categories that need more than FAMILIAR. Rhyme Time needed 5 until a judge test on aired puzzles: 5 kept 9 of 31
# aired Rhyme Time puzzles, 4 kept 15, and both caught every made-up rhyme.
FAMILIAR_FOR: dict[str, int] = {}
SEEN = project.ROOT / "puzzles" / "generated" / "seen.txt"
_ARTICLES = {"A", "AN", "THE"}
_AND = {"&", "AND"}

SYSTEM = (
    "You write answers for a word puzzle game. An answer is natural English that a typical adult would understand "
    "at once, and it clearly belongs to its category: a well-known saying, name, or title, or a vivid everyday "
    "description whose words go together. Write each answer in plain capital letters, with spaces between words. "
    "Use only letters, spaces, hyphens, apostrophes, the ampersand (&), and now and then a question mark, "
    "exclamation point, or colon. No numbers. Reply with JSON only."
)

# What each category asks for, in plain terms. Structural categories spell out their rule.
DESCRIPTIONS = {
    "Phrase": "a common saying or idiom, or something people often say in everyday life",
    "Thing": ("a thing of any kind, often with a describing word: an object, or a quality, idea, feeling, or "
              "experience"),
    "Things": "a group of everyday things, in the plural, or a list of two or three",
    "Places": "kinds of places, in the plural, or a list of two or three",
    "People": "a group of people, in the plural, or a list of two or three kinds of people",
    "Place": "a kind of place, or a specific well-known place",
    "On the Map": "a specific city, country, region, or geographic feature",
    "Landmark": "a famous building, monument, or natural landmark",
    "Food & Drink": "a food, dish, or drink",
    "In the Kitchen": "something found or done in a kitchen",
    "Around the House": "something found around a home",
    "Living Thing": "an animal or plant",
    "Living Things": "animals or plants, in the plural",
    "Person": "a kind of person, or a famous real person",
    "Character": "a well-known fictional character",
    "Characters": "two or more fictional characters who belong together",
    "Proper Name": "a real, well-known person, team, or organization, often with a describing word",
    "Song Lyrics": ("a line from a real song: an album track or a lesser-known song by a well-known artist, "
                    "not one of the most famous hit singles"),
    "Song Title": "the title of a real song, preferably an album track or lesser-known song rather than a famous hit",
    "Song/Artist": ("a real song and its artist, written SONG BY ARTIST, preferably an album track or lesser-known "
                    "song rather than a famous hit"),
    "Movie Title": "the title of a real film",
    "Movie Quote": "a real line spoken in a film, preferably not one of the most quoted lines",
    "Quotation": "a real quotation from a known person, book, or speech",
    "Headline": "a newspaper-style headline about a real event",
    "Event": "an occasion, celebration, or happening",
    "Fun & Games": "a game, sport, toy, or pastime, or a fun activity or outing",
    "Show Biz": "something from film, television, music, or theater",
    "Title": "the title of a well-known film, book, song, or show",
    "Occupation": "a job or profession",
    "What Are You Wearing?": "an item of clothing or an accessory, often with a describing word",
    "What Are You Doing?": "an activity, starting with a verb that ends in ING, like WALKING THE DOG",
    "Before & After": ("two common phrases joined into one, where the last word of the first phrase is the first "
                       "word of the second and is written only once, like PIECE OF CAKE WALK"),
    "Same Name": "two things that end with the same word, written as FIRST & SECOND SHARED, like BIRTHDAY & WEDDING CAKE",
    "Rhyme Time": "a natural phrase or description in which two main words rhyme, like WEAR AND TEAR",
    "Same Letter": "a phrase in which every word starts with the same letter, like BIG BLUE BUBBLES",
}


SOURCED = {"Song Lyrics", "Song Title", "Song/Artist", "Movie Title", "Movie Quote", "Quotation", "Headline", "Title",
           "Character", "Characters"}  # answers that must be real: the generator names the source, the judge checks it


@dataclass(frozen=True)
class Settings:
    generator: str
    judge: str
    batch: int = 10  # answers asked for per generator request
    rows: tuple[int, ...] = (12, 14, 14, 12)  # board rows a main puzzle wraps into
    bonus_rows: tuple[int, ...] = (14, 14)  # rows a bonus puzzle must fit in
    max_requests: int = 200  # generator requests per run, so a weak generator can't run up a bill
    main_min_letters: int = 8  # a main puzzle needs at least this many letters
    judges: int = 4  # judge calls in flight at once
    providers: dict[str, str] = field(default_factory=dict)  # model -> the one host it runs on, from [providers]
    bonus_letters: str = "RSTLNE"  # what the bonus round gives every player
    bonus_picks: str = "CDMA"  # the picks a bonus puzzle is tested against, the most common ones
    bonus_min_hidden: float = 0.5  # share of letter squares still hidden after those letters show
    bonus_min_letters: int = 10  # a bonus puzzle is a phrase, not one short word

    @classmethod
    def from_config(cls, config: dict) -> Settings:
        c = config["puzzlegen"]
        pins = config.get("providers", {})
        return cls(c["generator"], c["judge"], c.get("batch", 10), tuple(c["rows"]), tuple(c["bonus_rows"]),
                   c.get("max_requests", 200), c.get("main_min_letters", 8), c.get("judges", 4),
                   {m: pins[m] for m in (c["generator"], c["judge"]) if m in pins},
                   "".join(config.get("bonus_letters", "RSTLNE")), c.get("bonus_picks", "CDMA"),
                   c.get("bonus_min_hidden", 0.5), c.get("bonus_min_letters", 10))


@dataclass
class Result:
    puzzles: list[Puzzle] = field(default_factory=list)
    rejected: Counter = field(default_factory=Counter)  # reason -> count
    judged_out: list[tuple[str, str, str]] = field(default_factory=list)  # (category, answer, the judge's reason)
    sources: dict[str, str] = field(default_factory=dict)  # answer -> the source the generator named, for SOURCED
    usage: Usage = field(default_factory=Usage)
    requests: int = 0
    stopped: bool = False  # too many requests failed in a row


# Checks in code


def fits_rows(answer: str, rows: Sequence[int]) -> bool:
    """Whether the words wrap into these rows, never splitting a word. A row may be left empty."""
    row, room = 0, rows[0]
    for word in answer.split(" "):
        need = len(word) if room == rows[row] else len(word) + 1  # a space before every word but a row's first
        while need > room:
            row += 1
            if row == len(rows):
                return False
            room, need = rows[row], len(word)
        room -= need
    return True


def unknown_words(answer: str, dictionary: frozenset[str]) -> list[str]:
    """The answer's words that no dictionary word or name holds, like WAKIKI for WAIKIKI."""
    words = [w for w in re.split(r"[ \-&]+", answer) if w]
    return [w for w in words if w not in dictionary and w.replace("'", "") not in dictionary]


@lru_cache(maxsize=1)
def load_dictionary() -> frozenset[str] | None:
    """Every word the bot's word data knows, from wordfreq and from its phrases and names; None without the data."""
    root = data_dir()
    if not lexicon.available(root):
        return None
    lex = lexicon.load(str(root), versions.knobs(versions.current(project.load_config())).vocabulary)
    words = set(lex.frequency)
    for text in lex.texts:
        words.update(w for w in re.split(r"[ \-&]+", text) if w)
    return frozenset(words)


def hidden_after_picks(answer: str, s: Settings) -> float:
    """The share of a bonus puzzle's letter squares still hidden once the given letters and the usual picks show."""
    shown = set(s.bonus_letters) | set(s.bonus_picks)
    letters = [c for c in answer if c in LETTERS]
    return sum(c not in shown for c in letters) / len(letters)


def structure_ok(category: str, answer: str, rhymes: dict[str, set[str]]) -> bool:
    """The rule a structural category names actually holds. Other categories pass; the judge has those."""
    words = answer.split(" ")
    plain = [re.sub(r"[^A-Z]", "", w) for w in words if re.sub(r"[^A-Z]", "", w)]
    match category:
        case "Same Letter":
            return len(set(plain)) >= 2 and len({w[0] for w in plain}) == 1
        case "Rhyme Time":
            content = [w for w in plain if w not in _AND and len(w) >= 3]
            return any(_rhyme(a, b, rhymes) for i, a in enumerate(content) for b in content[i + 1:])
        case "Same Name":  # FIRST & SECOND SHARED: two or more words after the &, so there's an ending to share
            return any(w in _AND and 0 < i < len(words) - 2 for i, w in enumerate(words))
        case "Before & After":
            return len(words) >= 3
        case "What Are You Doing?":
            return any(w.endswith("ING") for w in plain)
    return True


def parts_ok(category: str, answer: str, parts: Sequence[str]) -> bool:
    """For Before & After and Same Name, the judge names the two phrases, and they must rebuild the answer."""
    if category not in ("Before & After", "Same Name"):
        return True
    if len(parts) != 2:
        return False
    try:
        first, second = (re.split(r"[ -]", normalize(p)) for p in parts)
    except ValueError:
        return False
    words = re.split(r"[ -]", answer)  # a hyphen joins words: CATTLE DRIVE + DRIVE-THROUGH WINDOW
    if category == "Before & After":  # PIECE OF CAKE + CAKE WALK, the shared word written once
        if second[0] in _ARTICLES and len(second) > 2 and first[-1] == second[1]:
            second = second[1:]  # MORE THAN MEETS THE EYE + THE EYE DOCTOR
        return len(first) >= 2 and len(second) >= 2 and first[-1] == second[0] and first + second[1:] == words
    for i, w in enumerate(words):  # BIRTHDAY & WEDDING CAKE: BIRTHDAY CAKE and WEDDING CAKE
        if w in _AND:
            left, right = words[:i], words[i + 1:]
            if second == right and any(first == left + right[k:] for k in range(1, len(right))):
                return True
    return False


def _rhyme(a: str, b: str, rhymes: dict[str, set[str]]) -> bool:
    if a == b:
        return False
    if a in rhymes and b in rhymes:
        return bool(rhymes[a] & rhymes[b])
    return a[-3:] == b[-3:]  # neither in the dictionary: the same ending will do


_MINOR = _ARTICLES | _AND | {"OF"}  # words that don't make two answers different


def _stem(word: str) -> str:
    return word[:-1] if len(word) > 3 and word.endswith("S") and not word.endswith("SS") else word


@dataclass(frozen=True)
class NearKey:
    """An answer's main words, without punctuation, articles, or plurals, in order."""

    words: tuple[str, ...]

    @classmethod
    def of(cls, answer: str) -> NearKey:
        words = (_stem(re.sub(r"[^A-Z]", "", w)) for w in answer.upper().split())
        return cls(tuple(w for w in words if w and w not in _MINOR))


def near(a: NearKey, b: NearKey) -> bool:
    """The same main words in any order, or the shorter's words running inside the longer and covering
    at least half of them: LET SLEEPING DOGS in LET SLEEPING DOGS LIE, but not ON THE ROCKS in
    SEA LIONS SUNBATHING ON THE ROCKS."""
    if not a.words or not b.words:
        return a.words == b.words
    if set(a.words) == set(b.words):
        return True
    short, long = (a, b) if len(a.words) <= len(b.words) else (b, a)
    n = len(short.words)
    if n < 2 or n * 2 < len(long.words):
        return False
    return any(long.words[i:i + n] == short.words for i in range(len(long.words) - n + 1))


class NearIndex:
    """Answers so far, looked up by their main words, for near repeat checks."""

    def __init__(self, answers=()):
        self.by_word: dict[str, list[NearKey]] = {}
        for answer in answers:
            self.add(answer)

    def add(self, answer: str) -> None:
        key = NearKey.of(answer)
        for w in set(key.words) or {""}:
            self.by_word.setdefault(w, []).append(key)

    def has_near(self, answer: str) -> bool:
        key = NearKey.of(answer)
        candidates = {k for w in set(key.words) or {""} for k in self.by_word.get(w, ())}
        return any(near(key, k) for k in candidates)


_CONTRACTION = re.compile(
    r"\b(DONT|CANT|WONT|ISNT|ARENT|WASNT|WERENT|DOESNT|DIDNT|HASNT|HAVENT|HADNT|WOULDNT|COULDNT|SHOULDNT|MUSTNT"
    r"|IM|IVE|YOURE|YOUVE|YOULL|THEYRE|THEYVE|WEVE|THATS|WHATS|WHERES|THERES|HERES"
    r"|ITS (?:NOT|A|AN|THE|ALL|RAINING|TIME|ONLY|NEVER|ALWAYS|BEEN|GOING|OKAY|LIKE|SO|TOO|JUST|REALLY|ABOUT)"
    r"|LETS (?:GO|BE|TALK|DANCE|EAT|PLAY|SEE|GET|MAKE|DO|FACE))\b")


def missing_apostrophe(answer: str) -> bool:
    """A contraction written without its apostrophe, like DONT or ITS NOT."""
    return bool(_CONTRACTION.search(answer.upper()))


def parse_reply(text: str | None) -> tuple[list[str], list[str]]:
    """The answers from a reply and the sources beside them, through code fences and stray words around the JSON.
    Sources line up with answers by position; a missing one is empty."""
    if not text:
        return [], []
    for candidate in (text, *re.findall(r"\{.*\}", text, re.S)):
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        answers = data.get("answers") if isinstance(data, dict) else None
        if isinstance(answers, list):
            pairs = [(a, s) for a, s in zip(answers, [*data.get("sources", []), *[""] * len(answers)])
                     if isinstance(a, str)]
            return [a for a, _ in pairs], [s if isinstance(s, str) else "" for _, s in pairs]
    return [], []


def parse_answers(text: str | None) -> list[str]:
    return parse_reply(text)[0]


def split(count: int, weights: dict[str, float], rng: random.Random) -> list[tuple[str, int]]:
    """`count` puzzles over the categories by weight, remainders going to a seeded draw."""
    total = sum(weights.values())
    shares = {c: count * w / total for c, w in weights.items()}
    out = {c: int(s) for c, s in shares.items()}
    left = count - sum(out.values())
    order = sorted(shares, key=lambda c: (-(shares[c] - out[c]), rng.random()))
    for c in order[:left]:
        out[c] += 1
    return [(c, n) for c, n in out.items() if n]


def load_rhymes(path: Path) -> dict[str, set[str]]:
    rhymes: dict[str, set[str]] = {}
    if path.exists():
        for line in path.read_text().splitlines():
            head, *phones = line.split("#")[0].split()
            rhymes.setdefault(head.split("(")[0].upper(), set()).add(rhyme_key(phones))
    return rhymes


# Requests


_ANSWERS = {"type": "json_schema", "json_schema": {"name": "answers", "strict": True, "schema": {
    "type": "object", "properties": {"answers": {"type": "array", "items": {"type": "string"}},
                                     "sources": {"type": "array", "items": {"type": "string"}}},
    "required": ["answers", "sources"], "additionalProperties": False}}}
_VERDICT = {"type": "json_schema", "json_schema": {"name": "verdict", "strict": True, "schema": {
    "type": "object", "properties": {"fits": {"type": "boolean"}, "reason": {"type": "string"},
                                     "common": {"type": "integer"},
                                     "parts": {"type": "array", "items": {"type": "string"}}},
    "required": ["fits", "reason", "common", "parts"], "additionalProperties": False}}}
JUDGE_SYSTEM = (
    "You check answers for a word puzzle game. An answer passes when it clearly belongs to its category and reads as "
    "natural English a typical adult would understand at once: a well-known saying, name, or title, or a natural "
    "description whose words go together. Puzzle answers are often long, vivid descriptions, and that is fine. Reject "
    "an answer that is made up or oddly combined, has a missing or wrong word, is misspelled, or doesn't fit its "
    "category. A song, quotation, title, headline, or character must be real: reject it unless you are confident the "
    "exact words exist and come from the named source. Reply with JSON only."
)
_JUDGE_EXAMPLES = "\n".join(
    ["Examples of verdicts:"]
    + [f"{json.dumps({k: e[k] for k in ('category', 'answer', 'source') if k in e})} -> {json.dumps(e['verdict'])}"
       for e in puzzle_examples.JUDGE])
_RATING = ("Rate how natural and familiar it is, 1 to 5: 5 means a well-known expression, name, or thing; 4 means "
           "natural wording people would say or write; 3 means understandable but forced or unusual; 2 means awkward; "
           "1 means made up or broken.")
_RATING_SOURCED = ("Rate how sure you are, 1 to 5, that these exact words are real and come from the source: 5 means "
                   "certain, 4 fairly sure, 3 unsure, 1 likely invented. Name the real source in your reason.")
_PARTS = {
    "Before & After": ("Also give the two phrases it joins in parts, like [\"PIECE OF CAKE\", \"CAKE WALK\"] for "
                       "PIECE OF CAKE WALK. Each must be a real, common phrase. JACK THE LADDER UP fails: its halves "
                       "aren't phrases."),
    "Same Name": ("Also give the two phrases it names in parts, like [\"BIRTHDAY CAKE\", \"WEDDING CAKE\"] for "
                  "BIRTHDAY & WEDDING CAKE. Each must be a real, common phrase. MELANIE & SULLIVAN fails: nothing is shared."),
}


def example_answers() -> list[str]:
    """Every few-shot example, so the generator can't hand one back as its own."""
    return [normalize(a) for table in (puzzle_examples.MAIN, puzzle_examples.BONUS) for xs in table.values() for a in xs]


def examples_for(category: str, bonus: bool, rng: random.Random, n: int = 3) -> list[str]:
    """A seeded handful of the category's examples, or none when it has none."""
    pool = (puzzle_examples.BONUS if bonus else puzzle_examples.MAIN).get(category, [])
    return rng.sample(pool, min(n, len(pool)))


def _ask_generator(client: OpenRouter, s: Settings, category: str, bonus: bool, ideas: list[str], n: int,
                   examples: Sequence[str] = ()):
    size = (f"two to four everyday words, at least {s.bonus_min_letters} letters in all, and short enough to fit "
            f"{len(s.bonus_rows)} lines of {max(s.bonus_rows)} squares" if bonus
            else f"three to six words, at least {s.main_min_letters} letters in all, and short enough to fit "
                 f"{len(s.rows)} lines of {min(s.rows)} to {max(s.rows)} squares without splitting a word")
    sourced = ([f"These must be real. In sources, at the same position as each answer, name where it comes from: "
                f"the song and artist, the film, the book and author, the speaker, or the event and year."]
               if category in SOURCED else ["Leave sources empty."])
    request = "\n".join([
        f"Category: {category}",
        f"What fits: {DESCRIPTIONS.get(category, 'something that clearly belongs to this category')}.",
        *([f"Examples of the style, to show length and wording; write new ones, never these: {'; '.join(examples)}."]
          if examples else []),
        f"Write {n} different answers. Each is {size}.",
        *sourced,
        f"For variety, these words may suggest topics, but never force them in: {', '.join(ideas)}.",
        'Reply as JSON: {"answers": ["...", "..."], "sources": ["...", "..."]}',
    ])
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": request}]
    return client.chat(model=s.generator, messages=messages, tools=None, response_format=_ANSWERS,
                       provider=s.providers.get(s.generator))


def _ask_judge(client: OpenRouter, s: Settings, category: str, answer: str, source: str | None = None):
    item = {"category": category, "means": DESCRIPTIONS.get(category, category), "answer": answer}
    if category in SOURCED:
        item["source"] = source or "not given: identify it yourself"
    request = "\n".join([
        _JUDGE_EXAMPLES,
        "",
        "Does this answer read as natural English and clearly belong to its category?",
        _RATING_SOURCED if category in SOURCED else _RATING,
        _PARTS.get(category, "Leave parts empty."),
        'Reply as JSON: {"fits": true or false, "reason": "a few words", "common": 1 to 5, "parts": [...]}',
        json.dumps(item),
    ])
    messages = [{"role": "system", "content": JUDGE_SYSTEM}, {"role": "user", "content": request}]
    return client.chat(model=s.judge, messages=messages, tools=None, response_format=_VERDICT,
                       provider=s.providers.get(s.judge))


def _ideas(rng: random.Random, pool: list[str], n: int = 6) -> list[str]:
    return [w.upper() for w in rng.sample(pool, min(n, len(pool)))]


# Everyday topics that nudge each request somewhere different. A fixed list, so no odd or crude word
# ever lands in a prompt the way a random dictionary word can.
TOPICS = """weather seasons holidays birthdays weddings school office travel airports trains road trips camping
beach mountains gardening cooking baking breakfast desserts coffee tea picnics restaurants grocery shopping
fashion shoes jewelry sports baseball basketball soccer tennis golf swimming running cycling fishing hiking
music concerts movies television theater books libraries art museums photography science space astronomy
oceans rivers forests deserts islands cities small towns farms animals pets birds insects flowers trees
weather forecasts history inventions machines cars boats tools hardware kitchen bathroom bedroom laundry
cleaning furniture toys games puzzles cards board games video games hobbies crafts knitting painting
dancing parties friendship family childhood manners money banking jobs careers medicine health exercise
sleep dreams morning night time clocks calendars mail telephones computers internet news newspapers
radio maps geography languages food trucks fairs circuses zoos parks playgrounds winter summer spring
autumn rain snow sunshine storms""".split()


def _idea_pool() -> list[str]:
    return sorted(set(TOPICS))


# Generation


def generate(
    client: OpenRouter,
    s: Settings,
    main: Sequence[tuple[str, int]],
    bonus: Sequence[tuple[str, int]],
    seed: int,
    known: Sequence[Puzzle],
    seen_path: Path | None = None,
    rhymes: dict[str, set[str]] | None = None,
    ideas: list[str] | None = None,
    dictionary: frozenset[str] | None = None,
    say=lambda line: None,
    heartbeat: float = 120.0,
    clock=time.monotonic,
    on_accept=lambda puzzles, sources: None,
) -> Result:
    """Puzzles for each (category, count), checked and judged. Accepted answers join the seen registry.
    Every `heartbeat` seconds, `say` gets a status line, and `on_accept` hears every accepted puzzle at once,
    with the sources named so far.
    A failed request is skipped; after MAX_FAILURES in a row, the run stops and returns what it has."""
    rng = random.Random(f"puzzlegen:{seed}")
    seen_path = SEEN if seen_path is None else seen_path
    rhymes = load_rhymes(data_dir() / "cmudict.dict") if rhymes is None else rhymes
    dictionary = load_dictionary() if dictionary is None else dictionary  # still None without the word data: no spelling check
    pool = ideas if ideas is not None else _idea_pool()
    seen_path.parent.mkdir(parents=True, exist_ok=True)
    seen = seen_path.read_text().splitlines() if seen_path.exists() else []
    prior = NearIndex([*seen, *(p.answer for p in known), *example_answers()])  # anything used before this run
    this_run = NearIndex()  # this run's accepted answers
    result = Result()
    wanted_total = sum(n for _, n in main) + sum(n for _, n in bonus)
    last = [clock()]
    began = last[0]

    def status(category: str, is_bonus: bool, got: int, count: int) -> None:
        if clock() - last[0] >= heartbeat:
            last[0] = clock()
            say(f"  {category}{' (bonus)' if is_bonus else ''}: {got} of {count} · {result.requests} requests · "
                f"${result.usage.cost:.4f} · {len(result.puzzles)} of {wanted_total} overall · "
                f"{duration(last[0] - began)} elapsed")

    failures = [0]

    def record(kind: str, outcome):
        """Count a reply or a failure. Returns the reply, or None if the request failed."""
        if isinstance(outcome, BaseException):
            if not isinstance(outcome, (openai.APIError, EmptyResponse)):
                raise outcome
            failures[0] += 1
            result.rejected[f"{kind} request failed"] += 1
            if failures[0] >= MAX_FAILURES:
                result.stopped = True
                say(f"Stopping: {MAX_FAILURES} requests in a row failed, the last with {outcome}. "
                    "Rerun the same command to top up.")
            return None
        failures[0] = 0
        result.usage += outcome.usage
        return outcome

    def attempt(call):
        try:
            return call()
        except Exception as err:  # handed to record on the main thread
            return err

    with ThreadPoolExecutor(max_workers=max(1, s.judges)) as judges:
        for is_bonus, wanted in ((False, main), (True, bonus)):
            rows = s.bonus_rows if is_bonus else s.rows
            for category, count in wanted:
                got = 0
                pending = NearIndex()  # this category's answers queued or sent to the judge, so overlapping replies can't repeat one
                queue: list[tuple[str, str]] = []  # (answer, source) checked and waiting for a judge
                flight: deque = deque()  # (answer, source, future) with the judge, handled in the order sent
                while got < count and not result.stopped:
                    # Keep the judges busy across replies, with no more in flight than the answers still needed could use
                    while len(flight) < max(1, min(s.judges, 2 * (count - got))) and not result.stopped:
                        if queue:
                            answer, source = queue.pop(0)
                            flight.append((answer, source, judges.submit(
                                attempt, lambda a=answer, src=source: _ask_judge(client, s, category, a, src))))
                            continue
                        if result.requests >= s.max_requests or len(flight) >= count - got:
                            break  # out of requests, or what's with the judge could fill the quota on its own
                        result.requests += 1
                        ideas = _ideas(rng, pool)
                        shown = examples_for(category, is_bonus, rng)
                        reply = record("generator", attempt(lambda: _ask_generator(client, s, category, is_bonus, ideas,
                                                                                   s.batch, shown)))
                        if reply is None:
                            continue
                        answers = list(zip(*parse_reply(reply.message.content)))
                        rng.shuffle(answers)  # the first answer is the most typical; a shuffle keeps the pick varied
                        status(category, is_bonus, got, count)
                        if not answers:
                            result.rejected["reply didn't parse"] += 1
                        for raw, source in answers:
                            verdict = _check(raw, category, rows, rhymes, prior, this_run, pending, result,
                                             0 if is_bonus else s.main_min_letters, s if is_bonus else None, dictionary)
                            if verdict is not None:
                                pending.add(verdict)
                                queue.append((verdict, source))
                    if not flight:
                        break
                    answer, source, future = flight.popleft()
                    judged = record("judge", future.result())
                    if judged is None or result.stopped:
                        continue
                    fits, reason, common, parts = _verdict(judged.message.content)
                    if fits and common < FAMILIAR_FOR.get(category, FAMILIAR):
                        fits, reason = False, f"familiarity {common} of 5: {reason}"
                    if fits and not parts_ok(category, answer, parts):
                        fits, reason = False, f"its parts {parts} don't rebuild the answer"
                    if not fits:
                        result.rejected["judge: doesn't fit the category"] += 1
                        result.judged_out.append((category, answer, reason))
                        continue
                    this_run.add(answer)
                    if category in SOURCED and source:
                        result.sources[answer] = source
                    with open(seen_path, "a") as f:
                        f.write(answer + "\n")
                    result.puzzles.append(Puzzle(category, answer, bonus=is_bonus))
                    on_accept(result.puzzles, result.sources)
                    got += 1
                    status(category, is_bonus, got, count)
                for _, _, future in flight:  # verdicts no longer needed still cost money
                    outcome = future.result()
                    if not isinstance(outcome, BaseException):
                        result.usage += outcome.usage
                say(f"  {category}{' (bonus)' if is_bonus else ''}: {got} of {count}")
    return result


def _check(raw: str, category: str, rows, rhymes, prior: NearIndex, this_run: NearIndex, pending: NearIndex,
           result: Result, min_letters: int = 0, bonus: Settings | None = None,
           dictionary: frozenset[str] | None = None) -> str | None:
    """The answer if it passes every check in code, else None with the reason counted.
    With `bonus`, the answer is also held to the bonus round's length and difficulty."""
    try:
        answer = normalize(raw)
    except ValueError:
        result.rejected["not board text"] += 1
        return None
    if sum(c in LETTERS for c in answer) < 2:
        result.rejected["not board text"] += 1
        return None
    if prior.has_near(answer):
        result.rejected["already used"] += 1
        return None
    if this_run.has_near(answer) or pending.has_near(answer):
        result.rejected["duplicate in this batch"] += 1
        return None
    if missing_apostrophe(answer):
        result.rejected["contraction without its apostrophe"] += 1
        return None
    if dictionary is not None and unknown_words(answer, dictionary):
        result.rejected["a word no dictionary or name list holds"] += 1
        return None
    if not fits_rows(answer, rows):
        result.rejected["doesn't fit the board"] += 1
        return None
    if sum(c in LETTERS for c in answer) < min_letters:
        result.rejected["too short for a main puzzle"] += 1
        return None
    if bonus and sum(c in LETTERS for c in answer) < bonus.bonus_min_letters:
        result.rejected["too short for a bonus puzzle"] += 1
        return None
    if bonus and hidden_after_picks(answer, bonus) < bonus.bonus_min_hidden:
        result.rejected["too easy for a bonus puzzle"] += 1
        return None
    if not structure_ok(category, answer, rhymes):
        result.rejected[f"breaks the {category} rule"] += 1
        return None
    return answer


def _verdict(text: str | None) -> tuple[bool, str, int, list[str]]:
    data: dict = {}
    for candidate in (text or "", *re.findall(r"\{.*\}", text or "", re.S)):
        try:
            data = json.loads(candidate)
            break
        except json.JSONDecodeError:
            continue
    parts = data.get("parts") if isinstance(data.get("parts"), list) else []
    common = data.get("common") if isinstance(data.get("common"), int) else 0
    return data.get("fits") is True, str(data.get("reason", "")), common, [p for p in parts if isinstance(p, str)]


# Pool files


def save_pool(path: Path, puzzles: Sequence[Puzzle], s: Settings, seed: int, rejected: dict, cost: float,
              judged_out: Sequence[tuple[str, str, str]] = (), final: bool = True,
              sources: dict[str, str] | None = None) -> None:
    """Write the batch file. Its history stays: every recheck, and one entry per finished run.
    `final=False` saves puzzles mid-run without logging a run. Sources the generator named stay with their puzzles."""
    old = json.loads(path.read_text()) if path.exists() else {}
    sources = {**_sources(old), **(sources or {})}
    runs = list(old.get("runs", []))
    if final:
        runs.append({"created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "prompt_version": PROMPT_VERSION,
                     "rejected": dict(rejected), "cost": cost,
                     "judged_out": [{"category": c, "answer": a, "reason": r} for c, a, r in judged_out]})
    path.write_text(json.dumps({
        "generator": s.generator, "judge": s.judge, "prompt_version": PROMPT_VERSION, "seed": seed,
        "cost": sum(run["cost"] for run in runs), "runs": runs, "rechecked": old.get("rechecked", []),
        "puzzles": [_row(p, sources) for p in puzzles],
    }, indent=2) + "\n")


def _sources(data: dict) -> dict[str, str]:
    return {p["answer"]: p["source"] for p in data.get("puzzles", []) if p.get("source")}


def _row(p: Puzzle, sources: dict[str, str]) -> dict:
    return {"category": p.category, "answer": p.answer, "bonus": p.bonus,
            **({"source": sources[p.answer]} if p.answer in sources else {})}


def load_pool(path: Path) -> list[Puzzle]:
    data = json.loads(Path(path).read_text())
    rows = data["puzzles"] if isinstance(data, dict) else data
    return [Puzzle.from_dict(p) for p in rows]


def recheck(client: OpenRouter, s: Settings, path: Path, against: Sequence[Path], known: Sequence[Puzzle],
            say=lambda line: None, dictionary: frozenset[str] | None = None, rejudge: bool = False) -> list[str]:
    """Hold a batch file to the current checks: drop near repeats of `known` puzzles, of the `against` files,
    and of earlier puzzles in the file; contractions without apostrophes; misspellings; bonus puzzles too short
    or too easy; and categories whose familiarity bar has risen, which get judged again. With `rejudge`,
    every puzzle goes back to the current judge. Rewrites the file, and returns what it dropped."""
    data = json.loads(path.read_text())
    dictionary = load_dictionary() if dictionary is None else dictionary
    prior = NearIndex([p.answer for p in known] + [p.answer for f in against for p in load_pool(f)])
    kept_index, kept, dropped = NearIndex(), [], []
    pool = load_pool(path)
    sources = _sources(data)
    to_judge = [p for p in pool if rejudge or p.category in FAMILIAR_FOR]

    def judge(p: Puzzle):
        try:
            return _verdict(_ask_judge(client, s, p.category, p.answer, sources.get(p.answer)).message.content)
        except (openai.APIError, EmptyResponse):
            return None  # no answer from the judge: the puzzle stays

    with ThreadPoolExecutor(max_workers=max(1, s.judges)) as judges:
        verdicts = dict(zip((p.answer for p in to_judge), judges.map(judge, to_judge)))
    for p in pool:
        reason = None
        if prior.has_near(p.answer):
            reason = "near an earlier batch or a hand-written puzzle"
        elif kept_index.has_near(p.answer):
            reason = "near an earlier puzzle in this file"
        elif missing_apostrophe(p.answer):
            reason = "contraction without its apostrophe"
        elif dictionary is not None and unknown_words(p.answer, dictionary):
            reason = f"a word no dictionary or name list holds: {', '.join(unknown_words(p.answer, dictionary))}"
        elif p.bonus and sum(c in LETTERS for c in p.answer) < s.bonus_min_letters:
            reason = "too short for a bonus puzzle"
        elif p.bonus and hidden_after_picks(p.answer, s) < s.bonus_min_hidden:
            reason = f"too easy for a bonus puzzle: {hidden_after_picks(p.answer, s):.0%} hidden after the usual picks"
        elif verdicts.get(p.answer) is not None:
            fits, why, common, parts = verdicts[p.answer]
            if not fits or common < FAMILIAR_FOR.get(p.category, FAMILIAR) or not parts_ok(p.category, p.answer, parts):
                reason = f"judged again{' by ' + s.judge if rejudge else ''}: familiarity {common} of 5, {why}"
        if reason:
            dropped.append(p.answer)
            say(f"  dropped {p.category}: {p.answer} ({reason})")
            continue
        kept_index.add(p.answer)
        kept.append(p)
    data["puzzles"] = [_row(p, sources) for p in kept]
    if rejudge:
        data["judge"] = s.judge  # every puzzle left has passed it, so reports name it; the history keeps the first
    data.setdefault("rechecked", []).append({"prompt_version": PROMPT_VERSION, "dropped": dropped,
                                             "against": [str(f) for f in against],
                                             **({"rejudged_by": s.judge} if rejudge else {})})
    path.write_text(json.dumps(data, indent=2) + "\n")
    return dropped


def known_puzzles() -> list[Puzzle]:
    """Every puzzle written by hand, which generated ones must never repeat."""
    out = []
    for name in ("dev.json", "private.json"):
        path = project.ROOT / "puzzles" / name
        if path.exists():
            out += project.load_puzzles(path)
    return out


def mix(config: dict) -> tuple[dict[str, float], dict[str, float]]:
    c = config["puzzlegen"]
    return dict(c["main_mix"]), dict(c["bonus_mix"])


def _client() -> OpenRouter:
    from rstlne.cli import clients

    client, _ = clients({"llm"}, None, None)
    client.deadline = DEADLINE
    return client


def main(argv: Sequence[str] | None = None) -> None:
    line_output()
    parser = argparse.ArgumentParser(prog="python -m rstlne.puzzlegen", description="Generate fresh, checked puzzles.")
    parser.add_argument("--recheck", help="hold an existing batch file to the current checks, then exit")
    parser.add_argument("--against", nargs="*", default=[], help="with --recheck: batch files it must not repeat")
    parser.add_argument("--rejudge", action="store_true", help="with --recheck: send every puzzle back to the current judge")
    parser.add_argument("--main", type=int, default=40, help="main round puzzles")
    parser.add_argument("--bonus", type=int, default=10, help="bonus round puzzles")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--out", help="the pool file to write")
    args = parser.parse_args(argv)
    config = project.load_config()
    s = Settings.from_config(config)
    if args.recheck:
        path = Path(args.recheck)
        print(f"Rechecking {path} against {', '.join(args.against) or 'the hand-written puzzles'}", flush=True)
        dropped = recheck(_client(), s, path, [Path(f) for f in args.against], known_puzzles(),
                          say=lambda line: print(line, flush=True), rejudge=args.rejudge)
        held = load_pool(path)
        print(f"Dropped {len(dropped)}; {path} now holds {sum(not p.bonus for p in held)} main and "
              f"{sum(p.bonus for p in held)} bonus. Rerun its generate command to top it up.")
        return
    if args.seed is None or args.out is None:
        parser.error("--seed and --out are needed to generate")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    have = load_pool(out) if out.exists() else []  # a rerun tops the file up
    short_main = max(0, args.main - sum(not p.bonus for p in have))
    short_bonus = max(0, args.bonus - sum(p.bonus for p in have))
    if not short_main and not short_bonus:
        print(f"{out} already holds {args.main} main and {args.bonus} bonus puzzles")
        return
    rng = random.Random(f"mix:{args.seed}:{len(have)}")
    main_mix, bonus_mix = mix(config)
    client = _client()
    print(f"Generating {short_main} main and {short_bonus} bonus puzzles with {s.generator}, judged by {s.judge}; "
          f"a status line every 2 minutes{f', topping up {out}' if have else ''}", flush=True)
    began = time.monotonic()
    result = generate(
        client, s, split(short_main, main_mix, rng) if short_main else [],
        split(short_bonus, bonus_mix, rng) if short_bonus else [], args.seed * 1000 + len(have),
        known_puzzles() + have, say=lambda line: print(line, flush=True),
        on_accept=lambda puzzles, sources: save_pool(out, have + puzzles, s, args.seed, {}, 0.0, final=False,
                                                     sources=sources),
    )
    save_pool(out, have + result.puzzles, s, args.seed, result.rejected, result.usage.cost, result.judged_out,
              sources=result.sources)
    total_main = sum(not p.bonus for p in have + result.puzzles)
    total_bonus = sum(p.bonus for p in have + result.puzzles)
    print(f"{len(result.puzzles)} new puzzles in {result.requests} generator requests and "
          f"{duration(time.monotonic() - began)}, ${result.usage.cost:.4f}; "
          f"{out} holds {total_main} of {args.main} main and {total_bonus} of {args.bonus} bonus")
    for reason, n in result.rejected.most_common():
        print(f"  rejected {n}: {reason}")
    for category, answer, reason in result.judged_out:
        print(f"  judged out: {category}: {answer} ({reason})")
    if total_main < args.main or total_bonus < args.bonus:
        sys.exit(f"Short of the {args.main} main and {args.bonus} bonus asked for: rerun the same command to top up.")


if __name__ == "__main__":
    main()
