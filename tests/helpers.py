"""Shared test setup. Tests drive specific wedges by choosing the spin index
for a fixed seed, so every landing still comes from the real seeded wheel."""

from dataclasses import replace

import pytest

from wof.engine import wheel
from wof.engine.puzzle import Puzzle
from wof.engine.rules import apply, new_game
from wof.engine.state import IllegalAction, Solve, Spin

PUZZLES = (
    Puzzle("Phrase", "WHEEL OF FORTUNE"),
    Puzzle("Food & Drink", "BANANA SPLIT"),
    Puzzle("Landmark", "GOLDEN GATE BRIDGE"),
    Puzzle("Phrase", "WELL-KNOWN FACT"),
)
BONUS = Puzzle("Place", "BIG CITY", bonus=True)


def start(rules, spec, seed=7, **rule_changes):
    return new_game(seed, replace(rules, **rule_changes), spec, PUZZLES, BONUS)


def force(state, number, third=None):
    """Move the round's spin index forward to the next spin that lands on `number`."""
    r = state.round
    for i in range(r.spin_index, r.spin_index + 10_000):
        slot = wheel.spin(state.seed, r.number, i)
        if slot // 3 + 1 == number and (third is None or slot % 3 == third):
            return replace(state, round=replace(r, spin_index=i))
    pytest.fail(f"no spin in 10,000 lands on wedge {number}; the seeded wheel looks broken")


def spin_to(state, number, third=None):
    return apply(force(state, number, third), Spin())


def solve(state):
    """The seat whose turn it is solves correctly."""
    return apply(state, Solve(state.round.puzzle.answer))


def to_round(state, number):
    while state.round.number < number:
        state = solve(state)
    return state


def set_seat(state, seat, **changes):
    return state.with_seat(seat, **changes)


def illegal(state, action, code):
    with pytest.raises(IllegalAction) as err:
        apply(state, action)
    assert err.value.code == code
