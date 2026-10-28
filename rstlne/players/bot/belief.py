"""What the reader concludes from a board: per letter odds, the likeliest answers, and how much it doesn't know."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from rstlne.engine.puzzle import LETTERS

_TOLERANCE = 1e-9


@dataclass(frozen=True)
class LetterStats:
    p_hit: float  # chance the letter is in the answer
    count: float  # E[count | hit]: copies expected when it is
    entropy: float  # bits of uncertainty in where it would show


NEVER = LetterStats(p_hit=0.0, count=0.0, entropy=0.0)


@dataclass(frozen=True)
class Belief:
    letters: Mapping[str, LetterStats]  # letters left out never hit, like used ones
    answers: tuple[tuple[str, float], ...]  # top whole answers, most likely first, with raw probabilities
    oov: float  # chance the answer holds a word or name outside the vocabulary

    def __post_init__(self) -> None:
        for letter, s in self.letters.items():
            if letter not in LETTERS:
                raise ValueError(f"{letter!r} is not an uppercase letter")
            if not 0 <= s.p_hit <= 1:
                raise ValueError(f"{letter}: p_hit {s.p_hit} is outside 0 to 1")
            if s.p_hit > 0 and s.count < 1 - _TOLERANCE or s.p_hit == 0 and s.count != 0:
                raise ValueError(f"{letter}: count {s.count} must be at least 1 when the letter can hit, else 0")
            if s.entropy < 0:
                raise ValueError(f"{letter}: entropy {s.entropy} is negative")
        probabilities = [p for _, p in self.answers]
        if probabilities != sorted(probabilities, reverse=True):
            raise ValueError("answers must come most likely first")
        if not 0 <= self.oov <= 1:
            raise ValueError(f"oov {self.oov} is outside 0 to 1")
        if sum(probabilities) + self.oov > 1 + _TOLERANCE:
            raise ValueError("answer probabilities and the oov share sum past 1")

    @property
    def best(self) -> str | None:
        return self.answers[0][0] if self.answers else None

    @property
    def confidence(self) -> float:
        """The raw probability of the best answer. Calibration happens outside the reader."""
        return self.answers[0][1] if self.answers else 0.0

    def stats(self, letter: str) -> LetterStats:
        return self.letters.get(letter, NEVER)
