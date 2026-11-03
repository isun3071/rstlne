"""Steal odds: the chance an opponent solves before the wheel comes back, learned from what each seat does."""

from __future__ import annotations

import math
from dataclasses import dataclass

from rstlne.players.bot.versions import Knobs

SEATS = 3
LLM_LOG_LIMIT = 30.0  # how far the log odds that a seat plays like an LLM may run, so they never overflow


def logistic(coefficients, share: float, confidence: float) -> float:
    w0, w1, w2 = coefficients
    return 1 / (1 + math.exp(-(w0 + w1 * share + w2 * confidence)))


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
        self.llm_log = [0.0] * SEATS  # from version 4: log odds that each seat plays like an LLM rather than a bot
        self._turn: list | None = None  # from version 6: the opponent turn under way: seat, first board, solved

    def prior(self, share: float, confidence: float) -> float:
        w0, w1, w2 = self.knobs.steal_prior
        return 1 / (1 + math.exp(-(w0 + w1 * share + w2 * confidence)))

    def turn_prior(self, seat: int, share: float, confidence: float) -> float:
        """From version 6: the chance `seat` solves correctly during its whole turn at this board, before what it has
        done this game: the LLM curve and the bot curve per turn, mixed by how LLM-like the seat plays."""
        q_llm = logistic(self.knobs.steal_turn, share, confidence)
        w = self.llm_share(seat)
        if not self.knobs.steal_turn_bot or w is None:
            return q_llm
        return w * q_llm + (1 - w) * logistic(self.knobs.steal_turn_bot, share, confidence)

    def own_turn(self, share: float, confidence: float) -> float:
        """The bot's own chance to solve during a turn at this board while its confidence is low: from version 6 the
        bot curve per turn, before that the shared prior."""
        if self.knobs.steal_turn_bot:
            return logistic(self.knobs.steal_turn_bot, share, confidence)
        return self.prior(share, confidence)

    def q(self, seat: int, share: float, confidence: float) -> float:
        p = self.turn_prior(seat, share, confidence) if self.knobs.steal_turn else self.prior(share, confidence)
        k = self.knobs.steal_pseudo
        scale = (self.solves[seat] + k) / (self.expected[seat] + k)
        odds = p / (1 - p) * scale
        return odds / (1 + odds)

    def note(self, seat: int, share: float, confidence: float, solved: bool) -> None:
        """A decision where `seat` could have solved: it either solved correctly or didn't. From version 6, decisions
        gather into the seat's turn, counted once it ends (`turn_over`), at its first board."""
        if self.knobs.steal_turn:
            if self._turn is None or self._turn[0] != seat:
                self.turn_over()
                self._turn = [seat, share, confidence, False]
            self._turn[3] = self._turn[3] or solved
        else:
            self.expected[seat] += self.prior(share, confidence)
            self.solves[seat] += solved
        if self.knobs.steal_bot:
            # how likely this choice is from an LLM (the shared prior) against from a bot (version 4's bot curve)
            q_llm, q_bot = logistic(self.knobs.steal_prior, share, confidence), logistic(self.knobs.steal_bot, share, confidence)
            ratio = q_llm / q_bot if solved else (1 - q_llm) / (1 - q_bot)
            self.llm_log[seat] = max(-LLM_LOG_LIMIT, min(LLM_LOG_LIMIT, self.llm_log[seat] + math.log(ratio)))

    def turn_over(self) -> None:
        """From version 6: the opponent turn under way ended. It counts once: the chance it began with, and its solve."""
        if self._turn is None:
            return
        seat, share, confidence, solved = self._turn
        self.expected[seat] += self.turn_prior(seat, share, confidence)
        self.solves[seat] += solved
        self._turn = None

    def llm_share(self, seat: int) -> float | None:
        """From version 4: the chance `seat` plays like an LLM rather than a bot, from 1/2 at the start of the game."""
        return 1 / (1 + math.exp(-self.llm_log[seat])) if self.knobs.steal_bot else None

    def llm_shares(self) -> dict[int, float] | None:
        if not self.knobs.steal_bot:
            return None
        return {seat: self.llm_share(seat) for seat in range(SEATS) if seat != self.me}

    def odds(self, share: float, confidence: float, share_after: float, confidence_after: float) -> Odds:
        nxt, after = (self.me + 1) % SEATS, (self.me + 2) % SEATS
        return Odds((nxt, after), self.q(nxt, share, confidence), self.q(after, share_after, confidence_after))
