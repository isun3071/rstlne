import io

import pytest
from fakes import FakeDecisions, board_reader, completion, decide_by, router
from helpers import set_seat, spin_to, start
from rich.console import Console

from rstlne import cli
from rstlne.engine.rules import apply
from rstlne.engine.state import CallConsonant
from rstlne.live import LiveShow
from rstlne.players.decision import DecisionPlayer
from rstlne.players.llm import LLMPlayer
from rstlne.runner import play_game


def console():
    return Console(file=io.StringIO(), width=120, force_terminal=True, color_system=None, record=True)


def text(live, state):
    out = console()
    out.print(live.render(state))
    return out.export_text()


@pytest.fixture
def players(rules, wheel_spec):
    client = router([])
    return [LLMPlayer(i, f"test/model-{i + 1}", client, rules, wheel_spec) for i in range(3)]


def test_board_shows_revealed_letters_but_never_the_answer(rules, wheel_spec, players):
    state = apply(spin_to(start(rules, wheel_spec), 3), CallConsonant("F"))  # WHEEL OF FORTUNE
    screen = text(LiveShow(players, pause=0, console=console()), state)
    assert "Round 1 of 4" in screen and "Phrase" in screen
    assert screen.count(" F ") >= 2
    assert "WHEEL" not in screen and "FORTUNE" not in screen


def test_seats_show_models_banks_totals_cards_and_whose_turn(rules, wheel_spec, players):
    state = set_seat(set_seat(start(rules, wheel_spec), 0, bank=1200, wild=True), 2, total=3000)
    screen = text(LiveShow(players, pause=0, console=console()), state)
    for expected in ("test/model-1", "test/model-2", "test/model-3", "$1,200", "$3,000", "Wild Card"):
        assert expected in screen
    seat_one = next(line for line in screen.splitlines() if "test/model-1" in line)
    assert "▶" in seat_one


def test_moves_list_keeps_the_latest_moves(rules, wheel_spec, players):
    live = LiveShow(players, pause=0, console=console(), moves_shown=2)
    state = start(rules, wheel_spec)
    live.start(state)
    state = spin_to(state, 3)
    live.result(state)
    state = apply(state, CallConsonant("F"))
    live.result(state)
    state = apply(spin_to(state, 3), CallConsonant("Z"))
    live.result(state)
    live.stop()
    screen = text(live, state)
    assert "Seat 1 called F: 2 Fs, +$1,200." in screen
    assert "Seat 1 called Z: none. Turn passes." in screen
    assert "Seat 1 spun $600." not in screen.split("Moves")[1]


def test_thinking_shows_the_decision_seat_probabilities(rules, wheel_spec):
    solver = LLMPlayer(0, "openai/gpt-6-luna", router([]), rules, wheel_spec)
    decision = DecisionPlayer(0, "typesafe/jev-1.14", FakeDecisions(decide_by(0.12)), solver, rules, wheel_spec, 0.8)
    others = [LLMPlayer(i, f"test/model-{i + 1}", router([completion(("spin", {}))]), rules, wheel_spec) for i in (1, 2)]
    players = [decision, *others]
    state = start(rules, wheel_spec)
    live = LiveShow(players, pause=0, console=console())
    live.start(state)
    live.result(apply(state, decision.decide(cli_view(state))))
    live.stop()
    screen = text(live, state)
    assert "typesafe/jev-1.14 + openai/gpt-6-luna" in screen
    assert "P(solvable) 0.12" in screen


def cli_view(state):
    from rstlne.engine.rules import public_view

    return public_view(state, state.seat)


def test_a_whole_game_plays_on_the_live_screen(rules, wheel_spec):
    client = router(board_reader)
    players = [LLMPlayer(i, f"test/model-{i + 1}", client, rules, wheel_spec) for i in range(3)]
    out = console()
    live = LiveShow(players, pause=0, console=out)
    state = start(rules, wheel_spec)
    live.start(state)
    final = play_game(state, players, on_result=live.result)
    live.finish(final, "logs/test.jsonl")
    assert "Final totals" in out.export_text()


def test_live_is_for_model_only_games(tmp_path):
    with pytest.raises(SystemExit, match="model-only"):
        cli.main(["--seats", "human,llm:a/one,llm:b/two", "--live", "--log-dir", str(tmp_path)], client=router([]))


def test_live_without_a_terminal_falls_back_to_plain_lines(tmp_path, capsys):
    argv = ["--seats", "llm:a/one,llm:b/two,llm:c/three", "--seed", "3", "--pause", "0", "--live", "--log-dir", str(tmp_path)]
    final = cli.main(argv, client=router(board_reader))
    assert final.phase.value == "game_over"
    out = capsys.readouterr().out
    assert "--live needs a terminal" in out
    assert "Final totals" in out
