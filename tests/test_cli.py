import json

import pytest
from fakes import FakeDecisions, board_reader, decide_by, router, solvable_when_full

from rstlne import cli, settings


def test_parse_seats():
    assert cli.parse_seats("human,llm:openai/gpt-x,llm:anthropic/claude-y") == [
        ("human", None),
        ("llm", "openai/gpt-x"),
        ("llm", "anthropic/claude-y"),
    ]
    assert cli.parse_seats("decision,decision:typesafe/jev-1.13,human") == [
        ("decision", None),
        ("decision", "typesafe/jev-1.13"),
        ("human", None),
    ]


@pytest.mark.parametrize("seats, message", [
    ("human,human", "three seats"),
    ("bot,human,human", "bot"),
    ("human,llm:,human", "slug"),
    ("human,robot,human", "robot"),
])
def test_bad_seats_are_explained(seats, message):
    with pytest.raises(ValueError, match=message):
        cli.parse_seats(seats)


def test_puzzle_picks_are_seeded_and_never_repeat():
    puzzles = settings.load_puzzles(settings.ROOT / "puzzles" / "dev.json")
    first = cli.pick_puzzles(puzzles, 4, seed=11)
    assert first == cli.pick_puzzles(puzzles, 4, seed=11)
    main, bonus = first
    assert len(set(main)) == 4 and not any(p.bonus for p in main)
    assert bonus.bonus
    assert {cli.pick_puzzles(puzzles, 4, seed=s)[1] for s in range(30)} != {bonus}


def test_dev_puzzles_are_valid():
    raw = json.loads((settings.ROOT / "puzzles" / "dev.json").read_text())
    puzzles = settings.load_puzzles(settings.ROOT / "puzzles" / "dev.json")
    assert len(puzzles) == len(raw)
    assert sum(not p.bonus for p in puzzles) >= 20
    assert sum(p.bonus for p in puzzles) >= 8
    assert len({p.answer for p in puzzles}) == len(puzzles)


def test_a_model_only_game_runs_from_the_command_line(tmp_path, capsys):
    argv = ["--seats", "llm:a/one,llm:b/two,llm:c/three", "--seed", "3", "--pause", "0", "--log-dir", str(tmp_path)]
    client = router(board_reader)
    final = cli.main(argv, client=client)
    assert final.phase.value == "game_over"
    out = capsys.readouterr().out
    assert "Final totals" in out
    logs = list(tmp_path.glob("*.jsonl"))
    assert len(logs) == 1
    records = [json.loads(line) for line in logs[0].read_text().splitlines()]
    assert records[0]["seats"][0] == {"kind": "llm", "model": "a/one", "temperature": None}
    assert records[-1]["type"] == "summary" and records[-1]["usage"]["calls"] > 0
    assert "cached_tokens" in records[-1]["usage"]
    sessions = {call["extra_body"]["session_id"] for call in client.client.calls}
    assert sessions == {f"{logs[0].stem}-seat{n}" for n in (1, 2, 3)}


def test_a_decision_model_game_runs_from_the_command_line(tmp_path):
    argv = ["--seats", "decision,decision,llm:c/three", "--seed", "4", "--pause", "0", "--log-dir", str(tmp_path)]
    decisions = FakeDecisions(decide_by(solvable_when_full))
    final = cli.main(argv, client=router(board_reader), decisions=decisions)
    assert final.phase.value == "game_over"
    header = json.loads(next(tmp_path.glob("*.jsonl")).read_text().splitlines()[0])
    assert header["seats"][0] == {"kind": "decision", "model": "typesafe/jev-1.14", "solver": "openai/gpt-6-luna", "threshold": 0.8}
    assert {c["session_id"] for c in decisions.calls} >= {f"{next(tmp_path.glob('*.jsonl')).stem}-seat1"}


def test_show_puzzle_prints_the_table_after_every_move(tmp_path, capsys):
    argv = ["--seats", "llm:a/one,llm:b/two,llm:c/three", "--seed", "3", "--pause", "0",
            "--log-dir", str(tmp_path), "--show-puzzle"]
    cli.main(argv, client=router(board_reader))
    lines = capsys.readouterr().out.splitlines()
    first_move = next(i for i, line in enumerate(lines) if line.startswith("Seat 1 spun"))
    assert lines[first_move + 1].strip().startswith("Round 1. Category:")
    assert lines[first_move + 2].strip().startswith("Board:")
    moves = [line for line in lines if line.startswith("Seat ") and not line.startswith(("Seat 1 (", "Seat 2 (", "Seat 3 ("))]
    boards = [line for line in lines if line.strip().startswith("Board:")]
    assert len(boards) == len(moves) - 1  # the move that ends the game is followed by the final totals instead


def test_without_show_puzzle_model_games_print_no_table(tmp_path, capsys):
    argv = ["--seats", "llm:a/one,llm:b/two,llm:c/three", "--seed", "3", "--pause", "0", "--log-dir", str(tmp_path)]
    cli.main(argv, client=router(board_reader))
    assert not any(line.strip().startswith("Board:") for line in capsys.readouterr().out.splitlines())
