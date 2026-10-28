"""How revealing letters moves the chance that the reader's best guess is right.

Answers outside the Belief's list, the out of vocabulary share among them, are never guessed,
so they add nothing to these chances.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from rstlne.players.bot.belief import Belief


@dataclass(frozen=True)
class Reveal:
    hit: float  # chance the best guess is right once the letter shows, given that it's there
    miss: float  # the same, given that it isn't


def _cells(belief: Belief, letters: str) -> dict[tuple, list[float]]:
    cells: dict[tuple, list[float]] = {}
    for answer, p in belief.answers:
        key = tuple((i, c) for i, c in enumerate(answer) if c in letters)
        cells.setdefault(key, []).append(p)
    return cells


def solve_chance(belief: Belief, letters: Iterable[str]) -> float:
    """The chance of guessing right after `letters` show: the best answer in each reveal pattern."""
    return sum(max(ps) for ps in _cells(belief, "".join(letters)).values())


def after(belief: Belief, letter: str) -> Reveal:
    p_hit = belief.stats(letter).p_hit
    hit = miss = 0.0
    for key, ps in _cells(belief, letter).items():
        if key:
            hit += max(ps)
        else:
            miss = max(ps)
    return Reveal(
        hit=min(1.0, hit / p_hit) if p_hit > 0 else 0.0,
        miss=min(1.0, miss / (1 - p_hit)) if p_hit < 1 else 0.0,
    )


def after_wrong_solve(belief: Belief) -> float:
    """Confidence in the next answer once the best one turns out wrong."""
    if len(belief.answers) < 2:
        return 0.0
    return belief.answers[1][1] / (1 - belief.answers[0][1])
