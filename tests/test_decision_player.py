from dataclasses import replace

import pytest
from fakes import FakeDecisions, board_reader, completion, decide_by, router, solvable_when_full
from helpers import set_seat, solve, spin_to, start, to_round

from wof.engine.puzzle import CONSONANTS, LETTERS, VOWELS
from wof.engine.rules import apply, public_view
from wof.engine.state import (
    BonusPicks,
    BonusSolve,
    BuyVowel,
    CallConsonant,
    CallLetter,
    Choose,
    Phase,
    Solve,
    Spin,
    UseWild,
)
from wof.players.base import InvalidResponse
from wof.players.decision import SOLVABLE, DecisionPlayer
from wof.players.llm import LLMPlayer
from wof.runner import play_game


@pytest.fixture
def game(rules, wheel_spec):
    return start(rules, wheel_spec)  # round 1: WHEEL OF FORTUNE, seat 0 up


def seat(rules, wheel_spec, answer, solver_replies=(), seat=0, threshold=0.8):
    decisions = FakeDecisions(answer)
    solver_client = router(list(solver_replies))
    solver = LLMPlayer(seat, "openai/gpt-6-luna", solver_client, rules, wheel_spec)
    player = DecisionPlayer(seat, "typesafe/jev-1.14", decisions, solver, rules, wheel_spec, threshold, session_id="g-seat1")
    return player, decisions, solver_client.client.calls


def options(call, name):
    return list(call["questions"][name]["criteria"])


# Normal turns


def test_turn_asks_whether_to_solve_and_skips_a_one_option_action_question(rules, wheel_spec, game):
    player, decisions, _ = seat(rules, wheel_spec, decide_by(0.1))
    assert player.decide(public_view(game, 0)) == Spin()  # $0 bank: spinning is the only other move
    (call,) = decisions.calls
    assert set(call["questions"]) == {"solvable"}
    assert call["questions"]["solvable"]["type"] == "noul"
    assert call["questions"]["solvable"]["instructions"] == SOLVABLE
    assert call["model"] == "typesafe/jev-1.14" and call["session_id"] == "g-seat1"


def test_turn_with_money_asks_action_and_vowel_in_one_call(rules, wheel_spec, game):
    state = set_seat(game, 0, bank=1000)
    state = replace(state, round=replace(state.round, used=frozenset("ET")))
    player, decisions, _ = seat(rules, wheel_spec, decide_by(0.1, {"action": "buy_vowel", "vowel": "O"}))
    assert player.decide(public_view(state, 0)) == BuyVowel("O")
    (call,) = decisions.calls
    assert set(call["questions"]) == {"solvable", "action", "vowel"}
    assert options(call, "action") == ["spin", "buy_vowel"]
    assert options(call, "vowel") == ["A", "I", "O", "U"]


@pytest.mark.parametrize("p_yes, solves", [(0.8, True), (0.95, True), (0.79, False)])
def test_solve_check_hands_off_to_the_solver_at_the_threshold(rules, wheel_spec, game, p_yes, solves):
    replies = [completion(("solve", {"answer": "WHEEL OF FORTUNE"}))]
    player, _, solver_calls = seat(rules, wheel_spec, decide_by(p_yes), replies)
    action = player.decide(public_view(game, 0))
    if solves:
        assert action == Solve("WHEEL OF FORTUNE")
        assert [t["function"]["name"] for t in solver_calls[0]["tools"]] == ["solve"]
        assert player.last_call.raw["solve_check"] == p_yes
    else:
        assert action == Spin() and solver_calls == []
        assert player.last_call.raw["solve_check"] is None
    assert player.last_call.raw["threshold"] == 0.8


def test_when_solving_is_the_only_move_the_solver_answers_without_asking(rules, wheel_spec, game):
    state = replace(game, round=replace(game.round, used=frozenset("WHLFRTN")))  # no consonants, $0 bank
    player, decisions, _ = seat(rules, wheel_spec, decide_by(0.0), [completion(("solve", {"answer": "WHEEL OF FORTUNE"}))])
    assert player.decide(public_view(state, 0)) == Solve("WHEEL OF FORTUNE")
    assert decisions.calls == []


def test_solver_retries_skip_the_decision_model(rules, wheel_spec, game):
    replies = [completion(content="hmm"), completion(("solve", {"answer": "WHEEL OF FORTUNE"}))]
    player, decisions, _ = seat(rules, wheel_spec, decide_by(0.9), replies)
    view = public_view(game, 0)
    with pytest.raises(InvalidResponse):
        player.decide(view)
    assert player.decide(view, error="No tool call.") == Solve("WHEEL OF FORTUNE")
    assert len(decisions.calls) == 1


# Letter and special wedge choices


def test_consonant_question_lists_only_unused_consonants(rules, wheel_spec, game):
    state = spin_to(apply(spin_to(game, 3), CallConsonant("F")), 3)
    player, decisions, _ = seat(rules, wheel_spec, decide_by(picks={"consonant": "T"}))
    assert player.decide(public_view(state, 0)) == CallConsonant("T")
    assert options(decisions.calls[0], "consonant") == sorted(CONSONANTS - {"F"})


def test_free_play_offers_every_unused_letter(rules, wheel_spec, game):
    player, decisions, _ = seat(rules, wheel_spec, decide_by(picks={"letter": "E"}))
    assert player.decide(public_view(spin_to(game, 16), 0)) == CallLetter("E")
    assert options(decisions.calls[0], "letter") == sorted(LETTERS)


def test_mystery_keep_or_flip(rules, wheel_spec, game):
    state = apply(spin_to(to_round(game, 2), 5), CallConsonant("N"))
    player, decisions, _ = seat(rules, wheel_spec, decide_by(picks={"mystery": "flip"}), seat=1)
    assert player.decide(public_view(state, 1)) == Choose("flip")
    assert options(decisions.calls[0], "mystery") == ["keep", "flip"]


def test_express_pass_or_play(rules, wheel_spec, game):
    state = apply(spin_to(to_round(game, 3), 12), CallConsonant("G"))
    player, decisions, _ = seat(rules, wheel_spec, decide_by(picks={"express": "play"}), seat=2)
    assert player.decide(public_view(state, 2)) == Choose("play")
    assert options(decisions.calls[0], "express") == ["pass", "play"]


def test_wild_card_spend_or_keep(rules, wheel_spec, game):
    state = apply(spin_to(game, 2), CallConsonant("F"))
    player, decisions, _ = seat(rules, wheel_spec, decide_by(picks={"wild_card": "spend"}))
    assert player.decide(public_view(state, 0)) == UseWild(True)
    assert options(decisions.calls[0], "wild_card") == ["spend", "keep"]


def test_express_ride_asks_consonant_and_vowel_with_the_action(rules, wheel_spec, game):
    state = apply(apply(spin_to(to_round(game, 3), 12), CallConsonant("G")), Choose("play"))
    player, decisions, _ = seat(rules, wheel_spec, decide_by(0.1, {"action": "call_consonant", "consonant": "D"}), seat=2)
    assert player.decide(public_view(state, 2)) == CallConsonant("D")
    (call,) = decisions.calls
    assert set(call["questions"]) == {"solvable", "action", "vowel", "consonant"}
    assert options(call, "action") == ["call_consonant", "buy_vowel"]
    assert "G" not in options(call, "consonant")


def test_choice_outside_the_options_is_invalid(rules, wheel_spec, game):
    state = spin_to(game, 3)
    player, _, _ = seat(rules, wheel_spec, lambda q, s: {"consonant": {"type": "choice", "choice": "E", "probabilities": {}}})
    with pytest.raises(InvalidResponse) as err:
        player.decide(public_view(state, 0))
    assert err.value.code == "bad_decision"


# Bonus round


def test_bonus_picks_come_one_letter_at_a_time(rules, wheel_spec):
    state = solve(set_seat(start(rules, wheel_spec, main_rounds=1), 0, wild=True))
    assert state.phase is Phase.BONUS_PICKS
    player, decisions, solver_calls = seat(rules, wheel_spec, decide_by(), [completion(("bonus_solve", {"answer": "BIG CITY"}))])
    picks = player.decide(public_view(state, 0))
    assert picks == BonusPicks(("B", "C", "D", "F"), "A")
    asked = [(list(c["questions"])[0], options(c, list(c["questions"])[0])) for c in decisions.calls]
    given = set(rules.bonus_letters)
    assert asked == [
        ("consonant", sorted(CONSONANTS - given)),
        ("consonant", sorted(CONSONANTS - given - {"B"})),
        ("consonant", sorted(CONSONANTS - given - {"B", "C"})),
        ("vowel", sorted(VOWELS - given)),
        ("consonant", sorted(CONSONANTS - given - {"B", "C", "D"})),
    ]
    state = apply(state, picks)
    assert player.decide(public_view(state, 0)) == BonusSolve("BIG CITY")
    assert [t["function"]["name"] for t in solver_calls[0]["tools"]] == ["bonus_solve"]


# State and logging


def test_state_carries_the_public_view_and_rules(rules, wheel_spec, game):
    player, decisions, _ = seat(rules, wheel_spec, decide_by())
    player.decide(public_view(set_seat(game, 0, wild=True), 0))
    state = decisions.calls[0]["state"]
    assert "You are Seat 1" in state
    for text in ("Round 1. Category: Phrase", "Board: _ _ _ _ _", "Used letters:", "Round banks:", "Game totals:",
                 "Cards: You hold the Wild Card.", "Mystery wedges", "Bankrupt"):
        assert text in state
    assert "WHEEL OF FORTUNE" not in state


def test_log_records_distributions_choices_threshold_and_usage(rules, wheel_spec, game):
    player, _, _ = seat(rules, wheel_spec, decide_by(0.9), [completion(("solve", {"answer": "WHEEL OF FORTUNE"}))])
    player.decide(public_view(set_seat(game, 0, bank=1000), 0))
    raw = player.last_call.raw
    (decision,) = raw["decisions"]
    assert decision["answers"]["solvable"] == {"type": "noul", "noul": 0.9}
    assert set(decision["answers"]["action"]["probabilities"]) == {"spin", "buy_vowel"}
    assert decision["chosen"] == {"solvable": 0.9, "action": "spin", "vowel": "A"}
    assert decision["questions"]["action"] == {"type": "choice", "options": ["spin", "buy_vowel"]}
    assert raw["threshold"] == 0.8 and raw["solve_check"] == 0.9
    assert raw["solver"]["tool_calls"][0]["name"] == "solve"
    assert player.last_call.usage.calls == 2  # one decision call and one solver call


def test_describe_names_both_models_and_the_threshold(rules, wheel_spec):
    player, _, _ = seat(rules, wheel_spec, decide_by())
    assert player.describe() == {"kind": "decision", "model": "typesafe/jev-1.14", "solver": "openai/gpt-6-luna", "threshold": 0.8}


def test_three_decision_seats_finish_a_game(rules, wheel_spec, game):
    decisions = FakeDecisions(decide_by(solvable_when_full))
    solver_client = router(board_reader)
    players = [
        DecisionPlayer(i, "typesafe/jev-1.14", decisions, LLMPlayer(i, "openai/gpt-6-luna", solver_client, rules, wheel_spec),
                       rules, wheel_spec, 0.8)
        for i in range(3)
    ]
    final = play_game(game, players)
    assert final.phase is Phase.GAME_OVER
    assert decisions.calls and solver_client.client.calls
