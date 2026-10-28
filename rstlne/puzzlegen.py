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
from collections import Counter
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import openai

from rstlne import settings as project
from rstlne.engine.puzzle import LETTERS, Puzzle, normalize
from rstlne.llm.openrouter import EmptyResponse, OpenRouter, Usage
from rstlne.narrate import duration, line_output
from rstlne.players.bot.lexicon import data_dir, rhyme_key

PROMPT_VERSION = 3
DEADLINE = 60  # seconds for one request: a batch of answers takes a few
MAX_FAILURES = 5  # requests failing in a row before a run stops and keeps what it has
FAMILIAR = 4  # the judge rates how familiar an answer is, 1 to 5; below this it's out
FAMILIAR_FOR = {"Rhyme Time": 5}  # categories where made-up answers come easily need the top rating
SEEN = project.ROOT / "puzzles" / "generated" / "seen.txt"
_ARTICLES = {"A", "AN", "THE"}
_AND = {"&", "AND"}

SYSTEM = (
    "You write answers for a word puzzle game. An answer is a common English phrase, name, or thing that a "
    "typical adult would recognize, and it must clearly belong to its category. Write each answer in plain "
    "capital letters, with spaces between words. Use only letters, spaces, hyphens, apostrophes, and the "
    "ampersand (&). No numbers. Reply with JSON only."
)

# What each category asks for, in plain terms. Structural categories spell out their rule.
DESCRIPTIONS = {
    "Phrase": "a common saying, idiom, or everyday expression",
    "Thing": "an everyday object or thing, often with a describing word",
    "Things": "a group of everyday things, in the plural",
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
    "Event": "an occasion, celebration, or happening",
    "Fun & Games": "a game, sport, toy, or pastime",
    "Show Biz": "something from film, television, music, or theater",
    "Title": "the title of a well-known film, book, song, or show",
    "Occupation": "a job or profession",
    "What Are You Wearing?": "an item of clothing or an accessory, often with a describing word",
    "What Are You Doing?": "an activity, starting with a verb that ends in ING, like WALKING THE DOG",
    "Before & After": ("two common phrases joined into one, where the last word of the first phrase is the first "
                       "word of the second and is written only once, like PIECE OF CAKE WALK"),
    "Same Name": "two things that end with the same word, written as FIRST & SECOND SHARED, like BIRTHDAY & WEDDING CAKE",
    "Rhyme Time": "a phrase whose two main words rhyme, like WEAR AND TEAR",
    "Same Letter": "a phrase in which every word starts with the same letter, like BIG BLUE BUBBLES",
}


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

    @classmethod
    def from_config(cls, config: dict) -> Settings:
        c = config["puzzlegen"]
        pins = config.get("providers", {})
        return cls(c["generator"], c["judge"], c.get("batch", 10), tuple(c["rows"]), tuple(c["bonus_rows"]),
                   c.get("max_requests", 200), c.get("main_min_letters", 8), c.get("judges", 4),
                   {m: pins[m] for m in (c["generator"], c["judge"]) if m in pins})


@dataclass
class Result:
    puzzles: list[Puzzle] = field(default_factory=list)
    rejected: Counter = field(default_factory=Counter)  # reason -> count
    judged_out: list[tuple[str, str, str]] = field(default_factory=list)  # (category, answer, the judge's reason)
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
        first, second = (normalize(p).split(" ") for p in parts)
    except ValueError:
        return False
    words = answer.split(" ")
    if category == "Before & After":  # PIECE OF CAKE + CAKE WALK, the shared word written once
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


def parse_answers(text: str | None) -> list[str]:
    """The answers from a reply, through code fences and stray words around the JSON."""
    if not text:
        return []
    for candidate in (text, *re.findall(r"\{.*\}", text, re.S)):
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        answers = data.get("answers") if isinstance(data, dict) else None
        if isinstance(answers, list):
            return [a for a in answers if isinstance(a, str)]
    return []


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
    "type": "object", "properties": {"answers": {"type": "array", "items": {"type": "string"}}},
    "required": ["answers"], "additionalProperties": False}}}
_VERDICT = {"type": "json_schema", "json_schema": {"name": "verdict", "strict": True, "schema": {
    "type": "object", "properties": {"fits": {"type": "boolean"}, "reason": {"type": "string"},
                                     "common": {"type": "integer"},
                                     "parts": {"type": "array", "items": {"type": "string"}}},
    "required": ["fits", "reason", "common", "parts"], "additionalProperties": False}}}
JUDGE_SYSTEM = (
    "You check answers for a word puzzle game. Be strict: reject an answer unless it is a real, common phrase, name, "
    "or thing that people actually say or write, and it clearly belongs to its category. Made-up combinations fail, "
    "like BOUND CAULIFLOWER for Food & Drink. Reply with JSON only."
)
_PARTS = {
    "Before & After": ("Also give the two phrases it joins in parts, like [\"PIECE OF CAKE\", \"CAKE WALK\"] for "
                       "PIECE OF CAKE WALK. Each must be a real, common phrase. JACK THE LADDER UP fails: its halves "
                       "aren't phrases."),
    "Same Name": ("Also give the two phrases it names in parts, like [\"BIRTHDAY CAKE\", \"WEDDING CAKE\"] for "
                  "BIRTHDAY & WEDDING CAKE. Each must be a real, common phrase. MELANIE & SULLIVAN fails: nothing is shared."),
}


def _ask_generator(client: OpenRouter, s: Settings, category: str, bonus: bool, ideas: list[str], n: int):
    size = ("short: two or three words, at most 14 letters in all" if bonus
            else "one to six words, no word longer than 12 letters")
    request = "\n".join([
        f"Category: {category}",
        f"What fits: {DESCRIPTIONS.get(category, 'something that clearly belongs to this category')}.",
        f"Write {n} different answers. Each is {size}.",
        f"For variety, these words may suggest topics, but never force them in: {', '.join(ideas)}.",
        'Reply as JSON: {"answers": ["...", "..."]}',
    ])
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": request}]
    return client.chat(model=s.generator, messages=messages, tools=None, response_format=_ANSWERS,
                       provider=s.providers.get(s.generator))


def _ask_judge(client: OpenRouter, s: Settings, category: str, answer: str):
    request = "\n".join([
        "Is this answer a real, common phrase, name, or thing, and does it clearly belong to its category?",
        "Rate how familiar it is as common: 5 means nearly everyone says or knows it, 3 means some people would, "
        "1 means nobody says it.",
        _PARTS.get(category, "Leave parts empty."),
        'Reply as JSON: {"fits": true or false, "reason": "a few words", "common": 1 to 5, "parts": [...]}',
        json.dumps({"category": category, "means": DESCRIPTIONS.get(category, category), "answer": answer}),
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
    say=lambda line: None,
    heartbeat: float = 120.0,
    clock=time.monotonic,
    on_accept=lambda puzzles: None,
) -> Result:
    """Puzzles for each (category, count), checked and judged. Accepted answers join the seen registry.
    Every `heartbeat` seconds, `say` gets a status line, and `on_accept` hears every accepted puzzle at once.
    A failed request is skipped; after MAX_FAILURES in a row, the run stops and returns what it has."""
    rng = random.Random(f"puzzlegen:{seed}")
    seen_path = SEEN if seen_path is None else seen_path
    rhymes = load_rhymes(data_dir() / "cmudict.dict") if rhymes is None else rhymes
    pool = ideas if ideas is not None else _idea_pool()
    seen_path.parent.mkdir(parents=True, exist_ok=True)
    seen = seen_path.read_text().splitlines() if seen_path.exists() else []
    prior = NearIndex([*seen, *(p.answer for p in known)])  # anything used before this run
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
                while got < count and result.requests < s.max_requests and not result.stopped:
                    result.requests += 1
                    ideas = _ideas(rng, pool)
                    reply = record("generator", attempt(lambda: _ask_generator(client, s, category, is_bonus, ideas, s.batch)))
                    if reply is None:
                        continue
                    answers = parse_answers(reply.message.content)
                    rng.shuffle(answers)  # the first answer is the most typical; a shuffle keeps the pick varied
                    status(category, is_bonus, got, count)
                    if not answers:
                        result.rejected["reply didn't parse"] += 1
                    pending = NearIndex()  # this reply's answers so far
                    candidates = []
                    for raw in answers:
                        verdict = _check(raw, category, rows, rhymes, prior, this_run, pending, result,
                                         0 if is_bonus else s.main_min_letters)
                        if verdict is not None:
                            pending.add(verdict)
                            candidates.append(verdict)
                    while candidates and got < count and not result.stopped:
                        chunk, candidates = candidates[:max(1, s.judges)], candidates[max(1, s.judges):]
                        futures = [judges.submit(attempt, lambda a=a: _ask_judge(client, s, category, a)) for a in chunk]
                        for answer, future in zip(chunk, futures):
                            judged = record("judge", future.result())
                            if judged is None or got == count or result.stopped:
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
                            with open(seen_path, "a") as f:
                                f.write(answer + "\n")
                            result.puzzles.append(Puzzle(category, answer, bonus=is_bonus))
                            on_accept(result.puzzles)
                            got += 1
                            status(category, is_bonus, got, count)
                say(f"  {category}{' (bonus)' if is_bonus else ''}: {got} of {count}")
    return result


def _check(raw: str, category: str, rows, rhymes, prior: NearIndex, this_run: NearIndex, pending: NearIndex,
           result: Result, min_letters: int = 0) -> str | None:
    """The answer if it passes every check in code, else None with the reason counted."""
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
    if not fits_rows(answer, rows):
        result.rejected["doesn't fit the board"] += 1
        return None
    if sum(c in LETTERS for c in answer) < min_letters:
        result.rejected["too short for a main puzzle"] += 1
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
              judged_out: Sequence[tuple[str, str, str]] = (), final: bool = True) -> None:
    """Write the batch file. Its history stays: every recheck, and one entry per finished run.
    `final=False` saves puzzles mid-run without logging a run."""
    old = json.loads(path.read_text()) if path.exists() else {}
    runs = list(old.get("runs", []))
    if final:
        runs.append({"created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "prompt_version": PROMPT_VERSION,
                     "rejected": dict(rejected), "cost": cost,
                     "judged_out": [{"category": c, "answer": a, "reason": r} for c, a, r in judged_out]})
    path.write_text(json.dumps({
        "generator": s.generator, "judge": s.judge, "prompt_version": PROMPT_VERSION, "seed": seed,
        "cost": sum(run["cost"] for run in runs), "runs": runs, "rechecked": old.get("rechecked", []),
        "puzzles": [{"category": p.category, "answer": p.answer, "bonus": p.bonus} for p in puzzles],
    }, indent=2) + "\n")


def load_pool(path: Path) -> list[Puzzle]:
    data = json.loads(Path(path).read_text())
    rows = data["puzzles"] if isinstance(data, dict) else data
    return [Puzzle.from_dict(p) for p in rows]


def recheck(client: OpenRouter, s: Settings, path: Path, against: Sequence[Path], known: Sequence[Puzzle],
            say=lambda line: None) -> list[str]:
    """Hold a batch file to the current checks: drop near repeats of `known` puzzles, of the `against` files,
    and of earlier puzzles in the file; contractions without apostrophes; and categories whose familiarity
    bar has risen, which get judged again. Rewrites the file, and returns what it dropped."""
    data = json.loads(path.read_text())
    prior = NearIndex([p.answer for p in known] + [p.answer for f in against for p in load_pool(f)])
    kept_index, kept, dropped = NearIndex(), [], []
    for p in load_pool(path):
        reason = None
        if prior.has_near(p.answer):
            reason = "near an earlier batch or a hand-written puzzle"
        elif kept_index.has_near(p.answer):
            reason = "near an earlier puzzle in this file"
        elif missing_apostrophe(p.answer):
            reason = "contraction without its apostrophe"
        elif p.category in FAMILIAR_FOR:
            fits, why, common, parts = _verdict(_ask_judge(client, s, p.category, p.answer).message.content)
            if not fits or common < FAMILIAR_FOR[p.category] or not parts_ok(p.category, p.answer, parts):
                reason = f"judged again: familiarity {common} of 5, {why}"
        if reason:
            dropped.append(p.answer)
            say(f"  dropped {p.category}: {p.answer} ({reason})")
            continue
        kept_index.add(p.answer)
        kept.append(p)
    data["puzzles"] = [{"category": p.category, "answer": p.answer, "bonus": p.bonus} for p in kept]
    data.setdefault("rechecked", []).append({"prompt_version": PROMPT_VERSION, "dropped": dropped,
                                             "against": [str(f) for f in against]})
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
                          say=lambda line: print(line, flush=True))
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
        on_accept=lambda puzzles: save_pool(out, have + puzzles, s, args.seed, {}, 0.0, final=False),
    )
    save_pool(out, have + result.puzzles, s, args.seed, result.rejected, result.usage.cost, result.judged_out)
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
