"""The known answer planner: once the bot is nearly sure of the answer, how long to keep spinning.

Its hits are a mixture. With chance c the answer is right and every hidden consonant hits; with 1 − c
it is wrong, and each call hits only as often as the other answers allow. Each hit raises c, and the
first miss passes the wheel with the known answer refuted.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from rstlne.engine.wheel import Kind
from rstlne.players.bot.objective import ZERO, Value
from rstlne.players.bot.value import Situation

MAX_CALLS = 8  # past this many hidden consonants, the plan stops looking further ahead


def next_confidence(c: float, p_hit: float) -> float:
    """Confidence in the known answer after one of its consonants hits."""
    wrong_hit = min(1.0, max(0.0, (p_hit - c) / (1 - c))) if c < 1 else 0.0
    hit = c + (1 - c) * wrong_hit
    return c / hit if hit > 0 else c


def order(s: Situation) -> list[str]:
    """The known answer's hidden consonants, most copies first."""
    answer = s.belief.best or ""
    hidden = [c for c in s.consonants if c in answer]
    return sorted(hidden, key=lambda c: (-answer.count(c), c))


def _landings(s: Situation) -> list[tuple[Kind, float, float]]:
    """The wheel grouped into (kind, dollars per copy, share of spins)."""
    groups: dict[tuple[Kind, float], int] = {}
    for w in s.wheel:
        value = s.spec.free_play if w.kind is Kind.FREE_PLAY else w.value
        groups[(w.kind, value)] = groups.get((w.kind, value), 0) + 1
    return [(kind, value, n / len(s.wheel)) for (kind, value), n in groups.items()]


@dataclass
class Plan:
    """What the planner weighed: each option's worth, the consonants it would call in order with their copies,
    the confidence after each hit, and how the first spin's worth splits over the wedges."""

    options: dict[str, Value]
    letters: list[tuple[str, int]] = field(default_factory=list)
    confidence: list[float] = field(default_factory=list)
    spin: list[dict] = field(default_factory=list)


def decide(s: Situation, legal: Sequence[str]) -> str:
    """Spin or solve, looking ahead through the known answer's consonants."""
    return s.goal.choose(plan(s, legal).options)


def plan(s: Situation, legal: Sequence[str]) -> Plan:
    """The look-ahead behind decide, with its numbers kept for the bot's thoughts."""
    letters = order(s)[:MAX_CALLS]
    answer = s.belief.best or ""
    counts = [answer.count(c) for c in letters]
    p_hits = [s.belief.stats(c).p_hit for c in letters]
    landings = _landings(s)
    wild, million = s.wild_held, s.million_held
    memo: dict[tuple[float, int], Value] = {}
    confidence = [s.c]
    for p in p_hits:
        confidence.append(next_confidence(confidence[-1], p))

    def solve_value(bank: float, c: float) -> Value:
        return s.goal.win_round(bank, wild, million) * c + s.lose_wheel(bank, 0.0, wild, million) * (1 - c)

    def spin_value(bank: float, i: int, parts: list | None = None) -> Value:
        c = confidence[i]
        hit_chance = c / confidence[i + 1] if confidence[i + 1] > 0 else 0.0
        total = ZERO
        for kind, value, share in landings:
            detail: dict = {}
            if kind is Kind.BANKRUPT:
                outcome = s.lose_wheel(0, c, False, False)
            elif kind is Kind.LOSE_A_TURN:
                outcome = s.lose_wheel(bank, c, wild, million)
            else:
                hit = best(bank + value * counts[i], i + 1)
                miss = s.lose_wheel(bank, 0.0, wild, million)
                outcome = hit * hit_chance + miss * (1 - hit_chance)
                detail = {"hit_chance": hit_chance, "hit": hit.main, "miss": miss.main}
            if parts is not None:  # the first spin's split, for the bot's thoughts
                parts.append({"kind": kind, "money": value, "share": share, "value": outcome.main, **detail})
            total += outcome * share
        return total

    def best(bank: float, i: int) -> Value:
        key = (bank, i)
        if key not in memo:
            options = {"solve": solve_value(bank, confidence[i])}
            if i < len(letters):
                options["spin"] = spin_value(bank, i)
            memo[key] = s.goal.choose_value(options)
        return memo[key]

    options = {"solve": solve_value(s.bank, s.c)}
    first: list[dict] = []
    if letters and "spin" in legal:
        options["spin"] = spin_value(s.bank, 0, first)
    return Plan(options, list(zip(letters, counts)), confidence, first)
