"""Steal odds: the chance an opponent solves before the wheel comes back, learned from what each seat does."""

from __future__ import annotations

import math
from dataclasses import dataclass

from rstlne.players.bot.versions import Knobs

SEATS = 3


@dataclass(frozen=True)
class Odds:
    seats: tuple[int, int]  # the next seat, then the one after
    next: float
    after: float

    @property
    def total(self) -> float:
        return self.next + (1 - self.next) * self.after


class Steal:
    """A shared logistic prior on (share revealed, the bot's confidence), scaled per seat by what it does.

    Each seat's odds multiply by (solves + k) / (expected solves + k), where expected solves
    sum the prior over the turns that seat could have solved, and k is the pseudo-count.
    """

    def __init__(self, me: int, knobs: Knobs):
        self.me = me
        self.knobs = knobs
        self.solves = [0.0] * SEATS
        self.expected = [0.0] * SEATS

    def prior(self, share: float, confidence: float) -> float:
        w0, w1, w2 = self.knobs.steal_prior
        return 1 / (1 + math.exp(-(w0 + w1 * share + w2 * confidence)))

    def q(self, seat: int, share: float, confidence: float) -> float:
        p = self.prior(share, confidence)
        k = self.knobs.steal_pseudo
        scale = (self.solves[seat] + k) / (self.expected[seat] + k)
        odds = p / (1 - p) * scale
        return odds / (1 + odds)

    def note(self, seat: int, share: float, confidence: float, solved: bool) -> None:
        """A turn where `seat` could have solved: it either solved correctly or didn't."""
        self.expected[seat] += self.prior(share, confidence)
        self.solves[seat] += solved

    def odds(self, share: float, confidence: float, share_after: float, confidence_after: float) -> Odds:
        nxt, after = (self.me + 1) % SEATS, (self.me + 2) % SEATS
        return Odds((nxt, after), self.q(nxt, share, confidence), self.q(after, share_after, confidence_after))
