"""Bot versions. A version fixes the bot's code, data files, and knobs; tournaments never mix them."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Knobs:
    samples: int = 400  # whole answers the reader samples per board
    top_answers: int = 50  # answers a Belief keeps
    unknown_word: float = 0.02  # prior share of words outside the vocabulary
    known_answer: float = 0.95  # confidence at which the planner takes over
    safe_hit: float = 0.99  # p_hit at which a consonant is safe to call
    tie_margin: float = 0.005  # from round 3, win chances this close to the best count as tied
    win_sigma: float = 6000.0  # spread of one round's winnings, for the win chance heuristic
    wild_bonus_lift: float = 0.10  # rise in bonus solve chance from the Wild Card's extra consonant
    bonus_solve: float = 0.5  # chance of solving the bonus puzzle, for card values
    # Steal curve, logistic on (share revealed, raw confidence): fit on 4,303 turns of three LLMs on fresh puzzles
    steal_prior: tuple[float, float, float] = (-3.27, 2.61, 1.92)
    steal_pseudo: float = 2.0  # pseudo-count that shrinks each seat's estimate toward the prior
    # The full reader
    vocabulary: int = 100_000  # most common wordfreq words a free slot can hold
    slot_candidates: int = 400  # free words kept per slot, the likeliest first
    pair_weight: float = 0.95  # how far word pair counts (Witten-Bell) pull a word's odds from its own frequency
    phrase_odds: float = 1.0  # odds a run of slots is a known phrase or name that fits the category, against free words
    phrase_odds_other: float = 0.1  # the same for one whose kind doesn't fit the category
    name_odds: float = 0.05  # the same for a one-word name that fits the category
    name_odds_other: float = 0.005  # and a one-word name that doesn't
    fit_weight: float = 4.0  # how strongly word vectors' category fit scales a word's odds
    ing_boost: float = 20.0  # What Are You Doing?: words ending in ING
    same_letter_boost: float = 20.0  # Same Letter: neighbors sharing a first letter
    rhyme_boost: float = 20.0  # Rhyme Time: words that rhyme
    same_name_boost: float = 50.0  # Same Name: both halves name a known phrase with the shared ending
    # Confidence correction: (raw confidence, how often it was right) points; none means no change
    calibration: tuple[tuple[float, float], ...] = ()
    # Chance of finishing first by (rounds left, ((lead, chance), ...)), from self-play; none uses win_sigma's formula
    win_table: tuple[tuple[int, tuple[tuple[float, float], ...]], ...] = ()
    # Self-play only: solve as soon as calibrated confidence reaches this, like an LLM. None plays normally.
    eager_solve: float | None = None
    # From version 3. What an opponent adds to its bank before it solves, as 10 equally likely gains, by
    # (from round, ((from hidden letter squares, gains), ...)). None counts only the bank it holds now.
    stealer_gain: tuple[tuple[int, tuple[tuple[int, tuple[float, ...]], ...]], ...] = ()
    # From version 3. When every option scores within the tie margin, choose by dollars, as in rounds 1 and 2.
    flat_dollars: bool = False


def _tuples(value):
    return tuple(_tuples(v) for v in value) if isinstance(value, list) else value


def _win_table(name: str) -> tuple:
    return _tuples(json.loads((Path(__file__).parent / name).read_text())["knob"])


# Frozen 2026-10-29. In bot games on grading puzzles they tied, 37% each (gap +0%, 95% interval -2% to +3%),
# so both are kept. v1 reads win chances from the formula; v2 from the win table built in self-play.
# A change to either is a new version, never an edit here.
VERSIONS = {
    1: Knobs(),
    2: Knobs(win_table=_win_table("win-table-v2.json")),
}
DATA = {1: "0640bcd6a420", 2: "0640bcd6a420"}  # the word data each version was frozen with, by fingerprint


def current(config: dict) -> int:
    """The version `[bot] version` in config.toml picks."""
    version = config.get("bot", {}).get("version")
    if version is None:
        raise ValueError("config.toml needs [bot] version")
    if version not in VERSIONS:
        raise ValueError(f"bot version {version} doesn't exist. Known versions: {', '.join(map(str, VERSIONS))}")
    return version


def knobs(version: int) -> Knobs:
    return VERSIONS[version]
