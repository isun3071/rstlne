import math

import pytest
from bot_fixtures import LOST, SURE, belief, view_at

from rstlne.engine.wheel import Kind, Wedge
from rstlne.players.bot import info, versions
from rstlne.players.bot.objective import Objective, Value, p_first
from rstlne.players.bot.steal import Steal

KNOBS = versions.knobs(1)


# info: how a reveal moves the chance the best guess is right


CAT = belief([("CAT", 0.5), ("BAT", 0.3)], C=(0.5, 1.0), B=(0.3, 1.0), A=(0.8, 1.0), T=(0.8, 1.0))


def test_solve_chance_adds_the_best_guess_in_each_reveal_pattern():
    assert info.solve_chance(CAT, "") == pytest.approx(0.5)
    assert info.solve_chance(CAT, "C") == pytest.approx(0.8)  # C or no C tells CAT from BAT
    assert info.solve_chance(CAT, "A") == pytest.approx(0.5)  # both have A in the same square


def test_bonus_patterns_keep_track_of_which_letter_is_where():
    two = belief([("COT", 0.4), ("CAT", 0.4)], A=(0.4, 1.0), O=(0.4, 1.0))
    assert info.solve_chance(two, "AO") == pytest.approx(0.8)


def test_a_reveal_splits_into_the_confidence_after_a_hit_and_after_a_miss():
    after = info.after(CAT, "C")
    assert after.hit == pytest.approx(1.0) and after.miss == pytest.approx(0.6)
    assert info.after(CAT, "Z") == info.Reveal(hit=0.0, miss=0.5)


def test_a_wrong_solve_leaves_the_next_answer():
    assert info.after_wrong_solve(CAT) == pytest.approx(0.6)
    assert info.after_wrong_solve(belief([], oov=1.0)) == 0.0


# objective


def test_win_chance_heuristic_and_shared_ties():
    assert p_first((10, 0, 0), 0, 0, 6000) == 1 and p_first((0, 10, 0), 0, 0, 6000) == 0
    assert p_first((5, 5, 0), 0, 0, 6000) == 0.5 and p_first((5, 5, 5), 1, 0, 6000) == pytest.approx(1 / 3)
    assert p_first((3000, 0, 0), 0, 1, 3000) == pytest.approx(0.5 * (1 + math.erf(1 / math.sqrt(2))))


def test_rounds_1_and_2_pay_dollars_with_the_1000_minimum(rules, wheel_spec):
    view, _ = view_at(rules, wheel_spec, round_number=2)
    goal = Objective(view, rules, wheel_spec, KNOBS)
    assert not goal.win_mode
    assert goal.win_round(1500, wild=False, million=False).main == 1500
    assert goal.win_round(200, wild=False, million=False).main == 1000
    assert goal.lose_round(wild=False).main == 0


def test_from_round_3_payoffs_are_win_chances(rules, wheel_spec):
    view, _ = view_at(rules, wheel_spec, round_number=4, totals=(10000, 12000, 0))
    goal = Objective(view, rules, wheel_spec, KNOBS)
    assert goal.win_mode
    assert goal.win_round(1500, wild=False, million=False).main == 0  # 11,500 still trails 12,000
    assert goal.win_round(2500, wild=False, million=False).main == 1


def test_win_chance_counts_rounds_3_and_later_whatever_the_round_count(rules, wheel_spec):
    from dataclasses import replace
    long = replace(rules, main_rounds=6)
    view, _ = view_at(rules, wheel_spec, round_number=3)
    assert Objective(view, long, wheel_spec, KNOBS).win_mode
    view, _ = view_at(rules, wheel_spec, round_number=2)
    assert not Objective(view, replace(rules, main_rounds=2), wheel_spec, KNOBS).win_mode


def test_held_cards_count_in_dollars_early_and_as_bonus_value_later(rules, wheel_spec):
    early, _ = view_at(rules, wheel_spec, round_number=1)
    goal = Objective(early, rules, wheel_spec, KNOBS)
    lift = KNOBS.wild_bonus_lift * sum(wheel_spec.envelopes) / len(wheel_spec.envelopes)
    assert goal.wild_value == pytest.approx(lift * goal.reach_bonus)
    assert goal.win_round(0, wild=True, million=False).main == pytest.approx(1000 + goal.wild_value)
    late, _ = view_at(rules, wheel_spec, round_number=3)
    goal = Objective(late, rules, wheel_spec, KNOBS)
    assert goal.win_round(0, wild=True, million=False).bonus == pytest.approx(goal.wild_value)


def test_near_ties_in_win_chance_go_to_the_move_with_more_bonus_value(rules, wheel_spec):
    view, _ = view_at(rules, wheel_spec, round_number=3)
    goal = Objective(view, rules, wheel_spec, KNOBS)
    margin = KNOBS.tie_margin
    assert goal.choose({"spend": Value(0.50), "keep": Value(0.50 - margin / 2, 3000)}) == "keep"
    assert goal.choose({"spend": Value(0.50), "keep": Value(0.50 - margin * 2, 3000)}) == "spend"
    early, _ = view_at(rules, wheel_spec, round_number=1)
    assert Objective(early, rules, wheel_spec, KNOBS).choose({"a": Value(500), "b": Value(499, 9999)}) == "a"


# steal odds


def test_steal_odds_start_at_the_prior_and_follow_what_each_seat_does():
    steal = Steal(me=0, knobs=KNOBS)
    prior = steal.q(1, share=0.5, confidence=0.5)
    assert prior == steal.q(2, share=0.5, confidence=0.5)
    for _ in range(6):
        steal.note(1, share=0.3, confidence=0.4, solved=True)
        steal.note(2, share=0.3, confidence=0.4, solved=False)
    assert steal.q(1, 0.5, 0.5) > prior > steal.q(2, 0.5, 0.5)


def test_opponents_steal_in_sequence_around_the_table():
    steal = Steal(me=1, knobs=KNOBS)
    q_next, q_after = steal.q(2, 0.4, 0.5), steal.q(0, 0.6, 0.7)
    odds = steal.odds(share=0.4, confidence=0.5, share_after=0.6, confidence_after=0.7)
    assert odds.next == pytest.approx(q_next) and odds.after == pytest.approx(q_after)
    assert odds.total == pytest.approx(q_next + (1 - q_next) * q_after)
    assert odds.seats == (2, 0)
