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
