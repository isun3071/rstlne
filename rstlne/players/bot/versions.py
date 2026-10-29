"""Bot versions. A version fixes the bot's code, data files, and knobs; tournaments never mix them."""

from __future__ import annotations

from dataclasses import dataclass


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
    steal_prior: tuple[float, float, float] = (-4.0, 4.0, 3.0)  # logistic: intercept, share revealed, confidence
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
    # Self-play only: solve as soon as calibrated confidence reaches this, like an LLM. None plays normally.
    eager_solve: float | None = None


VERSIONS = {1: Knobs()}  # v1 is in development until self-play freezes it


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
