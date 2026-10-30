"""Bot version 3: what a stealer banks before solving, flat choices played for dollars, and fitting the gain."""

import json
from dataclasses import replace

import pytest
from bot_fixtures import belief, view_at
from helpers import spin_to

from rstlne import selfplay
from rstlne.engine.rules import public_view
from rstlne.engine.state import CallConsonant
from rstlne.players.bot import versions
from rstlne.players.bot.objective import Objective, Value
from rstlne.players.bot.player import BotPlayer

V1 = versions.knobs(1)
STEPS = tuple(float(g) for g in range(0, 5000, 500))  # 0, 500, ... 4500: ten equally likely gains
GAIN = ((1, ((0, STEPS),)),)
V3 = replace(V1, stealer_gain=GAIN, flat_dollars=True)


def goal(rules, wheel_spec, knobs, round_number=4, totals=(4000, 0, 2000), banks=(0, 0, 0)):
    view, _ = view_at(rules, wheel_spec, round_number, totals=totals)
    view = replace(view, banks=tuple(banks))
    return Objective(view, rules, wheel_spec, knobs)


# The stealer's gain


def test_version_1_gives_a_stealer_only_the_bank_it_holds(rules, wheel_spec):
    g = goal(rules, wheel_spec, V1)
    assert g.lose_round(False, {2: 1.0}).main == 1.0  # $4,000 against $2,000 + the $1,000 minimum looks certain


def test_version_3_averages_the_win_chance_over_the_stealers_gain(rules, wheel_spec):
    g = goal(rules, wheel_spec, V3)
    # The stealer banks max(g, $1,000) on top of $2,000: ahead for g below $2,000, tied at $2,000, behind above
    assert g.lose_round(False, {2: 1.0}).main == pytest.approx((4 * 1.0 + 0.5) / 10)


def test_a_negative_gain_still_banks_the_minimum(rules, wheel_spec):
    knobs = replace(V3, stealer_gain=((1, ((0, (-3000.0,) * 10),)),))
    g = goal(rules, wheel_spec, knobs, totals=(2500, 0, 2000), banks=(0, 0, 3000))
    assert g.lose_round(False, {2: 1.0}).main == 0.0  # $2,000 + max(3,000 - 3,000, $1,000) passes $2,500


@pytest.mark.parametrize("round_number, hidden, expected", [(3, 2, "A"), (3, 7, "B"), (4, 7, "C")])
def test_the_gain_follows_the_round_and_the_hidden_squares(rules, wheel_spec, round_number, hidden, expected):
    a, b, c = ((1.0,) * 10, (2.0,) * 10, (3.0,) * 10)
    knobs = replace(V3, stealer_gain=((1, ((0, a), (5, b))), (4, ((0, c),))))
    g = goal(rules, wheel_spec, knobs, round_number=round_number)
    assert g.gains_for(hidden) == {"A": a, "B": b, "C": c}[expected]


def test_hidden_squares_count_the_letters_still_hidden(rules, wheel_spec):
    view, _ = view_at(rules, wheel_spec, 4)
    assert Objective(view, rules, wheel_spec, V3).hidden == view.board.count("_") > 0


def test_money_rounds_ignore_the_gain(rules, wheel_spec):
    for knobs in (V1, V3):
        g = goal(rules, wheel_spec, knobs, round_number=2)
        assert g.lose_round(False, {2: 1.0}) == Value(0.0)


def test_values_carry_dollars_in_both_modes(rules, wheel_spec):
    for round_number in (2, 4):
        g = goal(rules, wheel_spec, V3, round_number=round_number)
        assert g.win_round(2500, False, False).dollars == 2500
        assert g.win_round(300, False, False).dollars == 1000  # the solve minimum


# Flat choices


def test_flat_choices_go_to_dollars(rules, wheel_spec):
    g = goal(rules, wheel_spec, V3)
    options = {"spin": Value(1.0, 0.0, 500.0), "solve": Value(1.0, 0.0, 2000.0)}
    assert g.choose(options) == "solve" and g.last_flat
    g = goal(rules, wheel_spec, V1)
    assert g.choose(options) == "spin" and not g.last_flat  # version 1 takes the first of the tied


def test_a_choice_that_moves_the_win_chance_ignores_dollars(rules, wheel_spec):
    g = goal(rules, wheel_spec, V3)
    assert g.choose({"spin": Value(0.9, 0.0, 9000.0), "solve": Value(1.0, 0.0, 1000.0)}) == "solve"
    assert not g.last_flat


def test_money_rounds_choose_by_dollars_as_always(rules, wheel_spec):
    g = goal(rules, wheel_spec, V3, round_number=2)
    assert g.choose({"spin": Value(500.0, 0.0, 500.0), "solve": Value(2000.0, 0.0, 2000.0)}) == "solve"
    assert not g.last_flat


class Fixed:
    name = "fixed"

    def __init__(self, b):
        self.b = b

    def read(self, view, refuted=frozenset(), suggested=None):
        return self.b


def test_a_bot_with_the_game_won_calls_a_letter_it_expects_not_the_first_in_the_alphabet(rules, wheel_spec):
    _, state = view_at(rules, wheel_spec, 4, totals=(100_000, 0, 0))
    state = spin_to(state, 3)  # a cash wedge, waiting on a consonant
    knows = belief([("WHEEL OF FORTUNE", 0.5)], T=(0.95, 1.0), N=(0.9, 1.0))
    v1 = BotPlayer(0, rules, wheel_spec, Fixed(knows), knobs=V1)
    assert v1.decide(public_view(state, 0)) == CallConsonant("B")  # every letter wins, so v1 takes the first
    v3 = BotPlayer(0, rules, wheel_spec, Fixed(knows), knobs=V3)
    assert v3.decide(public_view(state, 0)) == CallConsonant("T")
    assert v3.last_call.raw["flat"] is True and "flat" not in v1.last_call.raw


# Versions


def test_versions_1_and_2_leave_the_new_knobs_off():
    for v in (1, 2):
        assert versions.knobs(v).stealer_gain == () and versions.knobs(v).flat_dollars is False


def test_the_new_knobs_parse_from_the_command_line(tmp_path):
    path = tmp_path / "gain.json"
    path.write_text(json.dumps({"knob": [[1, [[0, list(STEPS)]]]]}))
    knobs = selfplay.override(V1, [f"stealer_gain=@{path}", "flat_dollars=true"])
    assert knobs.stealer_gain == GAIN and knobs.flat_dollars is True
    assert selfplay.override(V1, ["flat_dollars=false"]).flat_dollars is False


# Fitting the gain


def step(round_number, phase, seat, banks, hidden, kind="spin", outcome="landed"):
    return selfplay.Step(round_number, phase, seat, tuple(banks), hidden, kind, outcome)


def test_every_decision_of_a_seat_that_didnt_solve_is_a_point_on_the_solvers_gain():
    steps = [
        step(1, "turn", 0, (0, 0, 0), 10),
        step(1, "call_consonant", 0, (0, 0, 0), 10, "call_consonant", "correct"),  # not a turn
        step(1, "turn", 1, (0, 0, 500), 8),
        step(1, "turn", 2, (0, 0, 500), 8),  # the solver's own turn
        step(1, "turn", 2, (0, 0, 3000), 4, "solve", "solved"),
        step(2, "turn", 0, (0, 0, 0), 12),  # a round with no correct solve
    ]
    assert selfplay.gain_points(steps) == [(1, 10, 3000.0), (1, 8, 2500.0)]


def test_tournament_logs_turn_into_the_same_steps(tmp_path):
    rows = [{"type": "game"}]
    for seat, phase, kind, outcome, banks, used in [
        (0, "turn", "spin", "landed", (0, 0, 0), ""),
        (1, "turn", "spin", "landed", (0, 700, 0), "K"),
        (1, "turn", "solve", "solved", (0, 1400, 0), "KC"),
    ]:
        rows.append({"type": "action", "seat": seat, "action": {"kind": kind}, "result": {"outcome": outcome},
                     "state": {"phase": phase, "seats": [{"bank": b} for b in banks],
                               "round": {"number": 1, "used": list(used), "puzzle": {"answer": "BACK PORCH"}}}})
    steps = selfplay.log_steps(rows)
    assert steps[0].hidden == 9 and steps[1].hidden == 8 and steps[2].banks == (0, 1400, 0)
    assert selfplay.gain_points(steps) == [(1, 9, 1400.0)]


def test_the_fit_weights_bot_and_llm_opponents_half_and_half():
    llm = [(1, 4, 0.0)] * 900
    bot = [(1, 4, 1000.0)] * 300
    table, report = selfplay.fit_stealer_gain(llm, bot)
    assert table == ((1, ((0, (0.0,) * 10 + (1000.0,) * 10),)),)  # three times as many LLM points count no more
    assert report[0]["llm"]["points"] == 900 and report[0]["bot"]["points"] == 300


def test_sparse_bands_merge_into_the_one_with_fewer_hidden_squares():
    points = [(1, 1, 0.0)] * 300 + [(1, 7, 100.0)] * 50 + [(1, 12, 900.0)] * 300 + [(4, 12, 5000.0)] * 250
    table, _ = selfplay.fit_stealer_gain(points, [])
    early, late = table
    assert [band for band, _ in early[1]] == [0, 10]  # 6-9 had only 50, so it joined 0-2 (3-5 was empty)
    assert late == (4, ((0, (5000.0,) * 20),))  # round 4's only band covers every hidden count


def test_a_band_with_one_source_uses_it_alone():
    table, _ = selfplay.fit_stealer_gain([], [(1, 4, 700.0)] * 250)
    assert table == ((1, ((0, (700.0,) * 20),)),)


@pytest.mark.parametrize("name, ok", [("tuning-101.json", True), ("grading-303.json", False), ("dev.json", False),
                                      ("private.json", False)])
def test_the_gain_is_never_fit_on_grading_or_dev_puzzles(name, ok):
    if ok:
        selfplay.check_fit_puzzles(name)
    else:
        with pytest.raises(ValueError, match="grading|dev|private"):
            selfplay.check_fit_puzzles(name)


def test_a_tournament_folder_must_say_which_puzzles_it_played(tmp_path):
    with pytest.raises(ValueError, match="report.json"):
        selfplay.tournament_gain_points([tmp_path])
    (tmp_path / "report.json").write_text(json.dumps({"puzzles": "puzzles/generated/grading-303.json"}))
    with pytest.raises(ValueError, match="grading"):
        selfplay.tournament_gain_points([tmp_path])
