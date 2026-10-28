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
