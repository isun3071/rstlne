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


# A human seat on the live screen


def human_table(rules, wheel_spec, typed=(), timed=None):
    """A human in seat 1 and two models, on a live screen that answers prompts from `typed`."""
    from rstlne.players.human_cli import HumanPlayer
    answers, prompts = iter(typed), []
    out = console()
    others = [LLMPlayer(i, f"test/model-{i + 1}", router([]), rules, wheel_spec) for i in (1, 2)]
    human = HumanPlayer(0)
    players = [human, *others]
    live = LiveShow(players, pause=0, console=out, read=lambda p: prompts.append(p) or next(answers),
                    read_timed=lambda seconds: timed)
    human.use_screen(live)
    return live, human, out, prompts


def test_a_human_takes_turns_on_the_live_screen(rules, wheel_spec):
    from rstlne.engine.state import Spin
    live, human, out, prompts = human_table(rules, wheel_spec, typed=["x", "s"])
    state = start(rules, wheel_spec)
    live.start(state)
    assert human.decide(cli_view(state)) == Spin()
    screen = out.export_text()
    assert "Round 1 of 4" in screen and "Moves" in screen  # the board, not a table of text lines
    assert "Round banks:" not in screen
    assert "Try: s to spin" in screen  # the typo's hint, shown on the screen before asking again
    assert prompts == ["s to spin, solve <answer>: "] * 2


def test_the_bonus_clock_runs_on_the_live_screen(rules, wheel_spec):
    from rstlne.engine.rules import public_view
    from rstlne.engine.state import BonusPicks, BonusSolve
    from helpers import solve
    live, human, out, _ = human_table(rules, wheel_spec, timed="big city")
    state = apply(solve(start(rules, wheel_spec, main_rounds=1)), BonusPicks(("C", "D", "M"), "A"))
    live.start(state)
    assert human.decide(public_view(state, 0)) == BonusSolve("big city")
    assert "You have 10 seconds" in out.export_text()


def test_thinking_stays_hidden_while_a_human_plays(rules, wheel_spec):
    live, *_ = human_table(rules, wheel_spec)
    live.thoughts[1] = "confidence 0.95 in WHEEL OF FORTUNE"
    screen = text(live, start(rules, wheel_spec))
    assert "Thinking" not in screen and "WHEEL OF FORTUNE" not in screen


def test_live_takes_a_human_seat(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(cli, "LiveShow", lambda players, *a, **k: seen.append(players) or (_ for _ in ()).throw(SystemExit("built")))
    monkeypatch.setattr(cli.sys.stdout, "isatty", lambda: True)
    with pytest.raises(SystemExit, match="built"):
        cli.main(["--seats", "human,llm:a/one,llm:b/two", "--live", "--log-dir", str(tmp_path)], client=router([]))
    assert seen and seen[0][0].describe() == {"kind": "human"}


def test_live_without_a_terminal_falls_back_to_plain_lines(tmp_path, capsys):
    argv = ["--seats", "llm:a/one,llm:b/two,llm:c/three", "--seed", "3", "--pause", "0", "--live", "--log-dir", str(tmp_path)]
    final = cli.main(argv, client=router(board_reader))
    assert final.phase.value == "game_over"
    out = capsys.readouterr().out
    assert "--live needs a terminal" in out
    assert "Final totals" in out


def test_board_rows_wrap_at_word_breaks_within_the_row_width():
    from rstlne.engine.puzzle import board
    from rstlne.live import TILES_PER_ROW, board_rows

    rows = board_rows(board("DON'T COUNT YOUR CHICKENS BEFORE THEY HATCH", frozenset()))
    assert all(len(row) <= TILES_PER_ROW for row in rows)
    assert ["".join(row).replace("_", "x") for row in rows][0] == "xxx'x xxxxx"
    assert len(rows) == 4


def test_board_rows_have_space_between_them(rules, wheel_spec, players):
    from dataclasses import replace

    from rstlne.engine.puzzle import Puzzle

    state = start(rules, wheel_spec)
    puzzle = Puzzle("Phrase", "DON'T COUNT YOUR CHICKENS BEFORE THEY HATCH")
    state = replace(state, round=replace(state.round, puzzle=puzzle, used=frozenset("TC")))
    screen = text(LiveShow(players, pause=0, console=console()), state)
    inside = screen.split("Phrase ─")[1].split("Wedge:")[0].splitlines()[1:]
    tiles = [i for i, line in enumerate(inside) if "T" in line or "C" in line or "'" in line]
    assert len(tiles) >= 3
    assert all(inside[i + 1].strip("│ ") == "" for i in tiles[:-1])


def test_thinking_drops_labels_and_markdown(rules, wheel_spec, players):
    live = LiveShow(players, pause=0, console=console())
    assert live.clean("reasoning: **Solving punctuation issues**\nmore") == "Solving punctuation issues"
    assert live.clean("content: I'll spin.") == "I'll spin."
    assert live.clean("P(solvable) 0.12, action spin (0.90)") == "P(solvable) 0.12, action spin (0.90)"


def solved_round_one(rules, wheel_spec):
    """Seat 1 calls F, then solves WHEEL OF FORTUNE."""
    from helpers import solve

    state = apply(spin_to(start(rules, wheel_spec), 3), CallConsonant("F"))
    return state, solve(state)


def test_live_holds_the_solved_board_before_the_next_round(rules, wheel_spec, players):
    before, after = solved_round_one(rules, wheel_spec)
    sleeps, frames = [], []
    live = LiveShow(players, pause=1.5, console=console(), sleep=sleeps.append, solve_pause=10)
    live.start(before)
    live._show = frames.append
    live.result(after)
    live.stop()
    solved, next_round = (text_of(frame) for frame in frames)
    assert "W   H   E   E   L" in solved and "Solved" in solved
    assert "Round 1 of 4" in solved
    assert "Round 2 of 4" in next_round and "W   H   E" not in next_round
    assert sleeps == [10, 1.5]


def test_no_hold_when_pauses_are_off(rules, wheel_spec, players):
    before, after = solved_round_one(rules, wheel_spec)
    sleeps = []
    live = LiveShow(players, pause=0, console=console(), sleep=sleeps.append, solve_pause=10)
    live.start(before)
    live.result(after)
    live.stop()
    assert 10 not in sleeps


def test_plain_show_puzzle_prints_the_solved_board_and_holds_it(rules, wheel_spec, players):
    from rstlne.show import Show

    before, after = solved_round_one(rules, wheel_spec)
    lines, sleeps = [], []
    show = Show(players, 1.5, False, show_puzzle=True, solve_pause=10, write=lines.append, sleep=sleeps.append)
    show.start(before)
    show.result(after)
    printed = "\n".join(lines)
    assert "Board: W H E E L   O F   F O R T U N E" in printed
    assert printed.index("Board: W H E E L") < printed.index("=== Round 2 ===")
    assert sleeps == [10, 1.5]


def text_of(renderable):
    out = console()
    out.print(renderable)
    return out.export_text()
