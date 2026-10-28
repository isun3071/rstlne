import json
from dataclasses import replace

import pytest

from rstlne import selfplay
from rstlne.engine.puzzle import Puzzle
from rstlne.players.bot import versions
from rstlne.players.bot.reader import WordListReader

KNOBS = replace(versions.knobs(1), samples=200)
PUZZLES = [Puzzle("Thing", "BACK PORCH"), Puzzle("Place", "BIG CITY"), Puzzle("Thing", "HOT COCOA", bonus=True)]
WORDS = {"back": 50, "porch": 20, "perch": 10, "big": 60, "city": 40, "hot": 30, "cocoa": 10, "coca": 5}


def reader(knobs):
    return WordListReader(WORDS, knobs)


# Boards


def test_a_board_fills_in_letter_frequency_order_misses_included():
    stops = selfplay.stops(Puzzle("Thing", "BACK PORCH"))
    assert stops[0] == (0.0, frozenset())
    shares = [s for s, _ in stops]
    assert shares == sorted(shares) and all(s < 1 for s in shares)
    _, used = stops[-1]
    assert "E" in used and "T" in used  # called and missed, the way a real board fills
    assert len({round(s, 1) for s in shares}) == len(shares)  # one stop per tenth of the board at most


def test_a_bonus_board_shows_rstlne_and_the_bot_s_own_picks(rules, wheel_spec):
    board = selfplay.bonus_board(Puzzle("Thing", "HOT COCOA", bonus=True), reader(KNOBS), rules, wheel_spec)
    assert set(rules.bonus_letters) <= board.used and len(board.used) == len(rules.bonus_letters) + 4


# Reading


def test_each_board_records_the_reader_s_answer_and_how_it_did(rules, wheel_spec):
    rows = selfplay.read_puzzle(Puzzle("Thing", "BACK PORCH"), reader(KNOBS), rules, wheel_spec)
    assert rows and {"answer", "category", "bonus", "shown", "used", "best", "confidence", "correct", "oov",
                     "p_true", "seconds"} <= set(rows[0])
    full = rows[-1]
    assert full["best"] == "BACK PORCH" and full["correct"] and full["p_true"] == full["confidence"]
    assert all(0 <= r["p_true"] <= 1 for r in rows)


def test_shards_split_puzzles_without_overlap():
    many = [Puzzle("Thing", f"THING {i}") for i in range(10)]
    parts = [selfplay.shard_of(many, i, 3) for i in (1, 2, 3)]
    assert sorted(p.answer for part in parts for p in part) == sorted(p.answer for p in many)
    assert not set(parts[0]) & set(parts[1])


def test_reads_write_one_file_per_shard_and_resume(tmp_path, rules, wheel_spec):
    lines = []
    selfplay.read_all(PUZZLES, tmp_path, rules, wheel_spec, KNOBS, reader, shard=(1, 1), say=lines.append)
    path = tmp_path / "reads-shard1of1.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert {r["answer"] for r in rows} == {p.answer for p in PUZZLES}
    assert any(line.startswith("Read 3 puzzles") for line in lines)
    selfplay.read_all(PUZZLES, tmp_path, rules, wheel_spec, KNOBS, reader, shard=(1, 1), say=lines.append)
    assert len(path.read_text().splitlines()) == len(rows)  # nothing read twice
    assert any("already read" in line for line in lines)


def test_reads_report_accuracy_by_confidence(tmp_path, rules, wheel_spec):
    selfplay.read_all(PUZZLES, tmp_path, rules, wheel_spec, KNOBS, reader, shard=(1, 1))
    summary = selfplay.summarize_reads(tmp_path)
    assert summary["boards"] > 0 and 0 <= summary["accuracy"] <= 1
    assert sum(b["boards"] for b in summary["by_confidence"]) == summary["boards"]


def test_knob_overrides_parse_to_their_types():
    knobs = selfplay.override(versions.knobs(1), ["phrase_odds=0.5", "samples=100", "steal_prior=-3,3,2"])
    assert knobs.phrase_odds == 0.5 and knobs.samples == 100 and knobs.steal_prior == (-3.0, 3.0, 2.0)
    with pytest.raises(ValueError, match="no knob"):
        selfplay.override(versions.knobs(1), ["nonsense=1"])


# The steal curve


import math  # noqa: E402
import random  # noqa: E402

import numpy as np  # noqa: E402


def game_log(path, turns, set_index=0, models=("a/one", "b/two", "c/three"), finished=True):
    """A tournament log with main round turns: (seat, phase, kind, outcome, used letters, answer)."""
    rows = [{"type": "game", "seats": [{"kind": "llm", "model": m} for m in models],
             "tournament": {"set": set_index}}]
    for seat, phase, kind, outcome, used, answer in turns:
        rows.append({"type": "action", "seat": seat, "action": {"kind": kind},
                     "result": {"outcome": outcome},
                     "state": {"phase": phase, "round": {"number": 1, "used": sorted(used),
                                                        "puzzle": {"category": "Thing", "answer": answer}}}})
    if finished:
        rows.append({"type": "summary"})
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")


def test_every_turn_a_player_could_solve_becomes_a_data_point(tmp_path, rules, wheel_spec):
    game_log(tmp_path / "set000-perm0.jsonl", [
        (0, "turn", "spin", "landed", "", "BACK PORCH"),
        (0, "call_consonant", "call_consonant", "correct", "", "BACK PORCH"),  # not a turn: no solve on offer
        (1, "turn", "buy_vowel", "correct", "C", "BACK PORCH"),
        (2, "turn", "solve", "wrong_solve", "CA", "BACK PORCH"),
        (0, "turn", "solve", "solved", "CAK", "BACK PORCH"),
    ])
    game_log(tmp_path / "set000-perm1.jsonl", [(0, "turn", "spin", "landed", "", "BACK PORCH")], finished=False)
    points = selfplay.steal_points([tmp_path], reader(KNOBS), rules, wheel_spec)
    assert [p["solved"] for p in points] == [0, 0, 0, 1]  # the unfinished game is left out
    assert [p["model"] for p in points] == ["a/one", "b/two", "c/three", "a/one"]
    assert points[0]["shown"] == 0 and points[3]["shown"] == pytest.approx(4 / 9)  # C shows twice
    assert all(0 <= p["confidence"] <= 1 for p in points) and points[3]["set"].endswith(":0")  # sets are per tournament


def test_the_fit_recovers_a_known_curve():
    rng = random.Random(4)
    a, b, c = -4.0, 3.0, 5.0
    points = []
    for i in range(6000):
        shown, confidence = rng.random(), rng.random() ** 2
        q = 1 / (1 + math.exp(-(a + b * shown + c * confidence)))
        points.append({"shown": shown, "confidence": confidence, "solved": int(rng.random() < q), "set": i % 60})
    fit = selfplay.fit_steal(points, resamples=200)
    assert fit["a"] == pytest.approx(a, abs=0.35) and fit["b"] == pytest.approx(b, abs=0.35)
    assert fit["c"] == pytest.approx(c, abs=0.4)
    for name, truth in (("a", a), ("b", b), ("c", c)):
        lo, hi = fit["ci95"][name]
        assert lo < truth < hi


def test_the_report_checks_the_curve_against_what_happened(tmp_path, rules, wheel_spec):
    turns = []
    for k in range(12):
        turns += [(0, "turn", "spin", "landed", "", "BACK PORCH"), (1, "turn", "solve", "solved", "CAK", "BACK PORCH")]
    for s in range(3):
        game_log(tmp_path / f"set00{s}-perm0.jsonl", turns, set_index=s)
    lines = []
    fit = selfplay.steal(tmp_path, tmp_path / "out", rules, wheel_spec, KNOBS, reader, resamples=50, say=lines.append)
    saved = json.loads((tmp_path / "out" / "steal-fit.json").read_text())
    assert saved["a"] == fit["a"] and set(saved["by_model"]) == {"a/one", "b/two"}
    assert saved["points"] == 72 and saved["solves"] == 36
    assert saved["solve_attempts"]["shown"]["median"] == pytest.approx(4 / 9)
    assert saved["by_model"]["a/one"]["a"] is None  # never solved, so no curve of its own
    assert any(line.startswith("a ") or "steal_prior" in line for line in lines)
    assert (tmp_path / "out" / "steal-points.jsonl").exists()
