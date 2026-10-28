from dataclasses import replace

import pytest
from helpers import set_seat, solve, start, to_round

from rstlne.engine.rules import current_wheel, public_view
from rstlne.engine.wheel import Kind
from rstlne.narrate import table, wheel_text


@pytest.fixture
def game(rules, wheel_spec):
    return start(rules, wheel_spec)


def kinds(view):
    return {w.kind for w in view.wheel}


def test_every_seat_sees_the_wheel_as_it_stands(game):
    for seat in range(3):
        view = public_view(game, seat)
        assert view.wheel == current_wheel(game) and len(view.wheel) == 72
        assert view.mystery_flipped is None


def test_a_card_that_left_the_wheel_stays_off_even_when_nobody_holds_it(game):
    """Claimed, then lost to Bankrupt: no seat holds the Million card, yet the wedge is gone for the round."""
    state = replace(game, round=replace(game.round, million_on_wheel=False, wild_on_wheel=False))
    view = public_view(state, 1)
    assert not any(view.million_cards) and Kind.MILLION not in kinds(view)
    assert not any(w.wild for w in view.wheel)


def test_the_view_says_which_mystery_wedge_was_flipped(game):
    state = to_round(game, 2)
    state = replace(state, round=replace(state.round, mystery_flipped=5))
    view = public_view(state, 0)
    assert view.mystery_flipped == 5 and Kind.MYSTERY not in kinds(view)


def test_the_wheel_never_shows_which_mystery_wedge_hides_the_prize(game):
    state = to_round(game, 2)
    views = {
        repr(public_view(replace(state, round=replace(state.round, mystery_prize=n)), 0))
        for n in (5, 17)
    }
    assert len(views) == 1


def test_the_bonus_round_has_no_wheel(rules, wheel_spec):
    state = solve(set_seat(start(rules, wheel_spec, main_rounds=1), 0, wild=True))
    view = public_view(state, 0)
    assert view.wheel == () and view.mystery_flipped is None
    assert wheel_text(view) is None
    assert not any(line.startswith("Wheel:") for line in table(view, 0))


@pytest.mark.parametrize("round_number, changes, text", [
    (1, {}, "Wheel: the Wild Card on wedge 2; the Million wedge on wedge 9."),
    (1, {"million_on_wheel": False}, "Wheel: the Wild Card on wedge 2."),
    (2, {}, "Wheel: the Wild Card on wedge 2; the Million wedge on wedge 9; Mystery wedges 5 and 17."),
    (2, {"mystery_flipped": 5, "wild_on_wheel": False},
     "Wheel: the Million wedge on wedge 9; Mystery wedge 5 already flipped, so the other plays as plain cash."),
    (3, {}, "Wheel: the Wild Card on wedge 2; the Million wedge on wedge 9; the Express on wedge 12."),
    (4, {}, "Wheel: no special wedges."),
])
def test_the_table_names_the_special_wedges_still_on_the_wheel(game, round_number, changes, text):
    state = to_round(game, round_number)
    state = replace(state, round=replace(state.round, **changes))
    view = public_view(state, 0)
    assert wheel_text(view) == text
    assert text in table(view, 0)
