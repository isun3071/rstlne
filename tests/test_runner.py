import json

import pytest
from helpers import BONUS, PUZZLES, spin_to, start

from rstlne.engine.rules import apply
from rstlne.engine.state import BonusPicks, BonusSolve, BuyVowel, CallConsonant, Phase, Solve, Spin
from rstlne.players.base import Player
from rstlne.runner import GameLog, play_game, play_turn


class Scripted(Player):
    def __init__(self, choose, max_attempts=3):
        self.choose = choose
        self.max_attempts = max_attempts
        self.errors = []
        self.seen = []

    def decide(self, view, error=None):
        self.errors.append(error)
        return self.choose(view)

    def observe(self, view, result):
        self.seen.append(result)


def solves(view):
    if view.phase is Phase.BONUS_PICKS:
        return BonusPicks(("B", "G", "C"), "I")
    if view.phase is Phase.BONUS_SOLVE:
        return BonusSolve(BONUS.answer)
    return Solve(PUZZLES[view.round_number - 1].answer)


def lines(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


@pytest.fixture
def game(rules, wheel_spec):
    return start(rules, wheel_spec)


def test_three_invalid_responses_forfeit_the_turn(game, tmp_path):
    bad = Scripted(lambda view: BuyVowel("E"))  # the round bank is $0
    players = [bad, Scripted(solves), Scripted(solves)]
    with GameLog(tmp_path / "game.jsonl", game, players) as log:
        state = play_turn(game, players, log)
    assert state.seat == 1 and state.last.outcome == "forfeit"
    assert bad.errors[0] is None
    assert all("costs" in error for error in bad.errors[1:]) and len(bad.errors) == 3
    records = lines(tmp_path / "game.jsonl")
    invalid = [r for r in records if r["type"] == "invalid"]
    assert [r["category"] for r in invalid] == ["insufficient funds"] * 3
    assert records[-1]["type"] == "action" and records[-1]["action"]["kind"] == "forfeit"


def test_a_valid_retry_plays_on(game):
    replies = iter([BuyVowel("E"), Spin()])
    player = Scripted(lambda view: next(replies))
    state = play_turn(game, [player, Scripted(solves), Scripted(solves)])
    assert state.last.outcome == "landed"
    assert len(player.errors) == 2 and player.errors[1] is not None


def test_humans_retry_without_limit(game):
    replies = iter([BuyVowel("E")] * 5 + [Spin()])
    human = Scripted(lambda view: next(replies), max_attempts=None)
    state = play_turn(game, [human, Scripted(solves), Scripted(solves)])
    assert state.last.outcome == "landed"
    assert len(human.errors) == 6


def test_repeated_letter_is_logged_but_not_reprompted(game, tmp_path):
    state = apply(spin_to(game, 3), CallConsonant("F"))
    state = spin_to(state, 3)
    caller = Scripted(lambda view: CallConsonant("F"))
    players = [caller, Scripted(solves), Scripted(solves)]
    with GameLog(tmp_path / "game.jsonl", state, players) as log:
        state = play_turn(state, players, log)
        log.summary(state)
    assert state.last.outcome == "repeated"
    assert caller.errors == [None]
    summary = lines(tmp_path / "game.jsonl")[-1]
    assert summary["invalid"][0] == {"repeated letter": 1}


def test_log_records_what_the_spec_asks_for(game, tmp_path):
    players = [Scripted(solves) for _ in range(3)]
    with GameLog(tmp_path / "game.jsonl", game, players) as log:
        final = play_game(game, players, log)
    records = lines(tmp_path / "game.jsonl")
    header, *actions, summary = records
    assert header["type"] == "game" and header["seed"] == game.seed
    assert len(header["seats"]) == 3
    assert {"state", "seat", "raw", "action", "result", "wedge", "usage"} <= set(actions[0])
    assert "rules" not in actions[0]["state"] and "wheel" not in actions[0]["state"]
    assert summary["type"] == "summary"
    assert summary["totals"] == [s.total for s in final.seats]
    assert summary["usage"]["calls"] == 0


def test_every_player_observes_every_result(game):
    players = [Scripted(solves) for _ in range(3)]
    play_game(game, players)
    assert {len(p.seen) for p in players} == {6}  # four solves, the bonus picks, and the bonus solve


@pytest.mark.parametrize("attempt, fits", [("SPILL", False), ("WHEEL OF FORTUNA", True)])
def test_wrong_solves_record_whether_they_fit_the_board(game, tmp_path, attempt, fits):
    players = [Scripted(lambda view: Solve(attempt)), Scripted(solves), Scripted(solves)]
    with GameLog(tmp_path / "game.jsonl", game, players) as log:
        state = play_turn(game, players, log)
        log.summary(state)
    records = lines(tmp_path / "game.jsonl")
    (action,) = [r for r in records if r["type"] == "action"]
    assert action["result"]["outcome"] == "wrong_solve" and action["fits_board"] is fits
    assert records[-1]["invalid"][0] == ({} if fits else {"solve doesn't fit the board": 1})


def test_correct_solves_are_marked_as_fitting(game, tmp_path):
    players = [Scripted(solves) for _ in range(3)]
    with GameLog(tmp_path / "game.jsonl", game, players) as log:
        play_turn(game, players, log)
    (action,) = [r for r in lines(tmp_path / "game.jsonl") if r["type"] == "action"]
    assert action["fits_board"] is True


def test_solves_record_their_timing_and_the_money_left_on_the_table(game, wheel_spec, tmp_path):
    from statistics import mean

    from rstlne.engine.wheel import layout

    players = [Scripted(solves) for _ in range(3)]
    with GameLog(tmp_path / "game.jsonl", game, players) as log:
        state = play_turn(game, players, log)  # seat 1 solves WHEEL OF FORTUNE with nothing called
        log.summary(state)
    records = lines(tmp_path / "game.jsonl")
    (action,) = [r for r in records if r["type"] == "action"]
    average_spin = mean(w.value for w in layout(wheel_spec, 1))  # Bankrupt and Lose a Turn count as $0
    assert action["solve_timing"] == {
        "board_shown": 0.0,
        "hidden_consonants": 7,  # W H L F R T N
        "hidden_copies": 8,  # two Fs
        "money_left": round(8 * average_spin),
    }
    assert records[-1]["solve_timing"][0] == {
        "correct_solves": 1,
        "avg_board_shown": 0.0,
        "money_left": round(8 * average_spin),
    }
    assert records[-1]["solve_timing"][1] == {"correct_solves": 0, "avg_board_shown": None, "money_left": 0}


def test_solve_timing_counts_what_is_already_showing(game, tmp_path):
    state = apply(spin_to(game, 3), CallConsonant("F"))  # 2 of 14 letters showing
    players = [Scripted(solves) for _ in range(3)]
    with GameLog(tmp_path / "game.jsonl", state, players) as log:
        play_turn(state, players, log)
    (action,) = [r for r in lines(tmp_path / "game.jsonl") if r["type"] == "action"]
    assert action["solve_timing"]["board_shown"] == round(2 / 14, 3)
    assert action["solve_timing"]["hidden_consonants"] == 6 and action["solve_timing"]["hidden_copies"] == 6


def test_other_moves_have_no_solve_timing(game, tmp_path):
    players = [Scripted(lambda view: Spin()), Scripted(solves), Scripted(solves)]
    with GameLog(tmp_path / "game.jsonl", game, players) as log:
        play_turn(game, players, log)
    (action,) = [r for r in lines(tmp_path / "game.jsonl") if r["type"] == "action"]
    assert "solve_timing" not in action


def test_log_lines_reach_disk_as_they_are_written(game, tmp_path):
    players = [Scripted(solves) for _ in range(3)]
    path = tmp_path / "game.jsonl"
    with GameLog(path, game, players) as log:
        assert lines(path)[0]["type"] == "game"  # readable mid-game, before the log closes
        play_turn(game, players, log)
        assert lines(path)[-1]["type"] == "action"
