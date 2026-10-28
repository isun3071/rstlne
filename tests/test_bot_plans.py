import pytest
from bot_fixtures import SURE, belief, view_at
from helpers import set_seat, solve, start
from test_bot_value import BANKRUPT, CALM, KNOBS, RISKY, only, situation

from rstlne.engine.rules import public_view
from rstlne.engine.wheel import Kind, Wedge
from rstlne.players.bot import bonus, planner

RICH = Wedge(1, Kind.CASH, 5000)


def test_a_hit_raises_confidence_in_the_known_answer():
    assert planner.next_confidence(0.95, 0.95) == pytest.approx(1.0)  # only the known answer has this letter
    assert planner.next_confidence(0.95, 1.0) == pytest.approx(0.95)  # every answer has it: nothing learned
    assert 0.95 < planner.next_confidence(0.95, 0.97) < 1.0


def test_with_a_kind_wheel_the_planner_milks_the_board(rules, wheel_spec):
    s = situation(rules, wheel_spec, SURE, wheel=only(RICH))
    assert planner.decide(s, ("spin", "buy_vowel", "solve")) == "spin"


def test_with_a_cruel_wheel_the_planner_solves(rules, wheel_spec):
    s = situation(rules, wheel_spec, SURE, odds=RISKY, wheel=only(BANKRUPT, Wedge(3, Kind.CASH, 500)), bank=4000)
    assert planner.decide(s, ("spin", "buy_vowel", "solve")) == "solve"


def test_the_planner_solves_once_no_consonant_is_left(rules, wheel_spec):
    done = belief([("WHEEL OF FORTUNE", 1.0)], E=(1.0, 3.0))
    assert planner.decide(situation(rules, wheel_spec, done, wheel=only(RICH)), ("buy_vowel", "solve")) == "solve"


def test_bigger_counts_get_called_first(rules, wheel_spec):
    s = situation(rules, wheel_spec, SURE, wheel=only(RICH))
    assert planner.order(s) == ["F", "H", "L", "N", "R", "T", "W"]  # every consonant shows once
    banana = belief([("BANANA", 1.0)], B=(1.0, 1.0), N=(1.0, 2.0))
    assert planner.order(situation(rules, wheel_spec, banana))[0] == "N"


# Bonus round


def bonus_view(rules, wheel_spec, wild=False):
    state = solve(set_seat(start(rules, wheel_spec, main_rounds=1), 0, wild=wild))
    return public_view(state, 0)


def test_bonus_picks_split_the_likely_answers(rules, wheel_spec):
    view = bonus_view(rules, wheel_spec)  # BIG CITY, with R S T L N E shown
    b = belief([("BIG CITY", 0.4), ("BOG CITY", 0.4)], I=(1.0, 1.5), O=(0.4, 1.0))  # only a vowel tells them apart
    picks = bonus.picks(b, view, rules)
    assert len(picks.consonants) == 3 and picks.vowel in ("I", "O")
    assert not set(picks.consonants) & set(rules.bonus_letters)


def test_bonus_picks_fall_back_to_letter_frequency_and_use_the_wild_card(rules, wheel_spec):
    view = bonus_view(rules, wheel_spec, wild=True)
    picks = bonus.picks(belief([], oov=1.0), view, rules)
    assert picks.consonants == ("C", "D", "H", "M") and picks.vowel == "A"


def test_bonus_solve_gives_the_best_guess_or_a_filled_board(rules, wheel_spec):
    view = bonus_view(rules, wheel_spec)
    assert bonus.answer(belief([("BIG CITY", 0.9)]), view) == "BIG CITY"
    assert bonus.answer(belief([], oov=1.0), view) == view.board.replace("   ", "\0").replace(" ", "").replace("\0", " ").replace("_", "E")
