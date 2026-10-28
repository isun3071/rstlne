"""What the bot plays for: dollars in rounds 1 and 2, the chance of finishing first from round 3 on."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from rstlne.engine.state import PublicView, Rules
from rstlne.engine.wheel import WheelSpec
from rstlne.players.bot.versions import Knobs

MONEY_ROUNDS = 2  # rounds 1 and 2 always play for money


@dataclass(frozen=True)
class Value:
    """A move's worth: dollars, or win chance, plus bonus value that only breaks ties in win mode."""

    main: float
    bonus: float = 0.0

    def __add__(self, other: Value) -> Value:
        return Value(self.main + other.main, self.bonus + other.bonus)

    def __mul__(self, weight: float) -> Value:
        return Value(self.main * weight, self.bonus * weight)

    __rmul__ = __mul__


ZERO = Value(0.0)


def p_first(totals: Sequence[float], seat: int, rounds_left: int, sigma: float) -> float:
    """The heuristic chance `seat` finishes first. A tie for first is a shared win."""
    best_other = max(t for i, t in enumerate(totals) if i != seat)
    lead = totals[seat] - best_other
    if rounds_left <= 0:
        if lead != 0:
            return float(lead > 0)
        return 1 / (1 + sum(1 for i, t in enumerate(totals) if i != seat and t == best_other))
    return 0.5 * (1 + math.erf(lead / (sigma * math.sqrt(rounds_left) * math.sqrt(2))))


class Objective:
    def __init__(self, view: PublicView, rules: Rules, spec: WheelSpec, knobs: Knobs):
        self.seat = view.seat
        self.totals = view.totals
        self.banks = view.banks
        self.knobs = knobs
        self.minimum = rules.solve_minimum
        self.win_mode = view.round_number is not None and view.round_number > MONEY_ROUNDS
        self.rounds_left = rules.main_rounds - (view.round_number or rules.main_rounds)  # after this round
        self.reach_bonus = p_first(self.totals, self.seat, self.rounds_left + 1, knobs.win_sigma) if rules.bonus_round else 0.0
        envelopes = spec.envelopes
        replaced, million = spec.million_swap
        self.wild_value = knobs.wild_bonus_lift * sum(envelopes) / len(envelopes) * self.reach_bonus
        self.million_value = knobs.bonus_solve * (million - replaced) / len(envelopes) * self.reach_bonus

    def _cards(self, wild: bool, million: bool) -> float:
        return self.wild_value * wild + self.million_value * million

    def _value(self, dollars: float, totals: Sequence[float], cards: float) -> Value:
        if self.win_mode:
            return Value(p_first(totals, self.seat, self.rounds_left, self.knobs.win_sigma), cards)
        return Value(dollars + cards)

    def win_round(self, bank: float, wild: bool, million: bool) -> Value:
        banked = max(bank, self.minimum)
        totals = list(self.totals)
        totals[self.seat] += banked
        return self._value(banked, totals, self._cards(wild, million))

    def lose_round(self, wild: bool, stealers: Mapping[int, float] | None = None) -> Value:
        """Another seat solves. `stealers` weights who; the Million card is lost, the Wild Card kept."""
        if not self.win_mode or not stealers:
            return self._value(0, self.totals, self._cards(wild, False))
        total = sum(stealers.values())
        value = ZERO
        for seat, weight in stealers.items():
            totals = list(self.totals)
            totals[seat] += max(self.banks[seat], self.minimum)
            value += self._value(0, totals, self._cards(wild, False)) * (weight / total)
        return value

    def choose(self, options: Mapping[str, Value]) -> str:
        """The best move. From round 3, moves within the tie margin of the best go to bonus value."""
        best = max(options, key=lambda k: options[k].main)
        if not self.win_mode:
            return best
        floor = options[best].main - self.knobs.tie_margin
        tied = [k for k in options if options[k].main >= floor]
        return max(tied, key=lambda k: (options[k].bonus, options[k].main))

    def choose_value(self, options: Mapping[str, Value]) -> Value:
        return options[self.choose(options)]
