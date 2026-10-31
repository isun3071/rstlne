"""What the bot plays for: dollars in rounds 1 and 2, the chance of finishing first from round 3 on.
From version 3, an opponent who takes the round banks what it holds plus a spread of what it adds before
solving, and a choice where every option wins equally goes to dollars."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np

from rstlne.engine.state import PublicView, Rules
from rstlne.engine.wheel import WheelSpec
from rstlne.players.bot.versions import Knobs

MONEY_ROUNDS = 2  # rounds 1 and 2 always play for money


@dataclass(frozen=True)
class Value:
    """A move's worth: dollars, or win chance, plus bonus value that only breaks ties in win mode.
    `dollars` is the move's worth in dollars in either mode, for choices where every option wins equally."""

    main: float
    bonus: float = 0.0
    dollars: float = 0.0

    def __add__(self, other: Value) -> Value:
        return Value(self.main + other.main, self.bonus + other.bonus, self.dollars + other.dollars)

    def __mul__(self, weight: float) -> Value:
        return Value(self.main * weight, self.bonus * weight, self.dollars * weight)

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


def win_chance(table, rounds_left: int, lead: float) -> float | None:
    """The table's chance of finishing first with this lead and this many rounds left, or None without a row."""
    for left, points in table:
        if left == rounds_left and points:
            return float(np.interp(lead, [x for x, _ in points], [p for _, p in points]))
    return None


class Objective:
    def __init__(self, view: PublicView, rules: Rules, spec: WheelSpec, knobs: Knobs,
                 llm_share: Mapping[int, float] | None = None):
        self.seat = view.seat
        self.totals = view.totals
        self.banks = view.banks
        self.knobs = knobs
        self.minimum = rules.solve_minimum
        self.win_mode = view.round_number is not None and view.round_number > MONEY_ROUNDS
        self.round_number = view.round_number
        self.hidden = view.board.count("_")  # letter squares still hidden
        self.gains = self.gains_for(self.hidden) if self.win_mode else None
        # From version 4: each opponent's gain mixes the LLM and bot tables by how LLM-like that seat plays
        mixing = bool(knobs.stealer_gain_llm and knobs.stealer_gain_bot and llm_share is not None)
        self.llm_share = llm_share if mixing else None
        self.gains_llm = self.gains_for(self.hidden, knobs.stealer_gain_llm) if mixing and self.win_mode else None
        self.gains_bot = self.gains_for(self.hidden, knobs.stealer_gain_bot) if mixing and self.win_mode else None
        self.last_flat = False  # whether the latest choice went to dollars
        self._lost: dict = {}  # lose_round answers: one decision asks the same few questions many times
        self.rounds_left = rules.main_rounds - (view.round_number or rules.main_rounds)  # after this round
        self.reach_bonus = self.first(self.totals, self.rounds_left + 1) if rules.bonus_round else 0.0
        envelopes = spec.envelopes
        replaced, million = spec.million_swap
        self.wild_value = knobs.wild_bonus_lift * sum(envelopes) / len(envelopes) * self.reach_bonus
        self.million_value = knobs.bonus_solve * (million - replaced) / len(envelopes) * self.reach_bonus

    def gains_for(self, hidden: int, table=None) -> tuple[float, ...] | None:
        """What a stealer adds before solving, at this round and this many hidden squares; None without a table."""
        table = self.knobs.stealer_gain if table is None else table
        rows = [bands for start, bands in table if start <= (self.round_number or 0)]
        if not rows:
            return None
        return [gains for start, gains in rows[-1] if start <= hidden][-1]

    def first(self, totals: Sequence[float], rounds_left: int) -> float:
        """The chance of finishing first: the self-play table where it has a row, else the formula.
        With no rounds left, the lead decides."""
        if rounds_left > 0 and self.knobs.win_table:
            lead = totals[self.seat] - max(t for i, t in enumerate(totals) if i != self.seat)
            chance = win_chance(self.knobs.win_table, rounds_left, lead)
            if chance is not None:
                return chance
        return p_first(totals, self.seat, rounds_left, self.knobs.win_sigma)

    def _cards(self, wild: bool, million: bool) -> float:
        return self.wild_value * wild + self.million_value * million

    def _value(self, dollars: float, totals: Sequence[float], cards: float) -> Value:
        if self.win_mode:
            return Value(self.first(totals, self.rounds_left), cards, dollars + cards)
        return Value(dollars + cards, 0.0, dollars + cards)

    def win_round(self, bank: float, wild: bool, million: bool) -> Value:
        banked = max(bank, self.minimum)
        totals = list(self.totals)
        totals[self.seat] += banked
        return self._value(banked, totals, self._cards(wild, million))

    def lose_round(self, wild: bool, stealers: Mapping[int, float] | None = None) -> Value:
        """Another seat solves. `stealers` weights who; the Million card is lost, the Wild Card kept."""
        if not self.win_mode or not stealers:
            return self._value(0, self.totals, self._cards(wild, False))
        key = (wild, tuple(stealers.items()))
        if key not in self._lost:
            self._lost[key] = self._stolen(wild, stealers)
        return self._lost[key]

    def _stolen(self, wild: bool, stealers: Mapping[int, float]) -> Value:
        total = sum(stealers.values())
        value = ZERO
        for seat, weight in stealers.items():
            if self.llm_share is not None and self.gains_llm and self.gains_bot:
                w = self.llm_share.get(seat, 0.5)
                taken = self._taken(seat, wild, self.gains_llm) * w + self._taken(seat, wild, self.gains_bot) * (1 - w)
                value += taken * (weight / total)
                continue
            gains = self.gains or (0.0,)  # versions 1 to 3, summed in their original order so they play exactly as frozen
            taken = ZERO
            for gain in gains:
                totals = list(self.totals)
                totals[seat] += max(self.banks[seat] + gain, self.minimum)
                taken += self._value(0, totals, self._cards(wild, False))
            value += taken * (weight / total / len(gains))
        return value

    def _taken(self, seat: int, wild: bool, gains: Sequence[float]) -> Value:
        """The bot's worth if `seat` takes the round, averaged over what it might add before solving."""
        taken = ZERO
        for gain in gains:
            totals = list(self.totals)
            totals[seat] += max(self.banks[seat] + gain, self.minimum)
            taken += self._value(0, totals, self._cards(wild, False))
        return taken * (1 / len(gains))

    def choose(self, options: Mapping[str, Value]) -> str:
        """The best move. From round 3, moves within the tie margin of the best go to bonus value, or from
        version 3, when every option is that close, to dollars."""
        self.last_flat = False
        best = max(options, key=lambda k: options[k].main)
        if not self.win_mode:
            return best
        floor = options[best].main - self.knobs.tie_margin
        tied = [k for k in options if options[k].main >= floor]
        if self.knobs.flat_dollars and len(options) > 1 and len(tied) == len(options):
            self.last_flat = True
            return max(options, key=lambda k: options[k].dollars)
        return max(tied, key=lambda k: (options[k].bonus, options[k].main))

    def choose_value(self, options: Mapping[str, Value]) -> Value:
        return options[self.choose(options)]
