import json

import pytest
from fakes import FakeDecisions, board_reader, decide_by, router, solvable_when_full
from helpers import start
from test_runner import Scripted, solves

from rstlne import settings
from rstlne.runner import GameLog, play_game
from rstlne.tournament import (
    parse_entrants,
    report,
    run_tournament,
    schedule,
    seating,
    split_wins,
)

ENTRANTS = ["llm:a/one", "llm:b/two", "decision"]
DEV = settings.ROOT / "puzzles" / "dev.json"


def run(tmp_path, sets=2, parallel=2, max_cost=None, client=None):
    client = client or router(board_reader)
    decisions = FakeDecisions(decide_by(solvable_when_full))
    result = run_tournament(
        ENTRANTS, sets=sets, seed=42, puzzles_path=DEV, out_dir=tmp_path, parallel=parallel,
        max_cost=max_cost, client=client, decisions=decisions, write=lambda line: None,
    )
    return result, client


def finished(path):
    lines = path.read_text().splitlines()
    return bool(lines) and json.loads(lines[-1])["type"] == "summary"


def test_rotations_put_every_entrant_in_every_seat():
    seats_held = {entrant: set() for entrant in range(3)}
    for rotation in range(3):
        for seat, entrant in enumerate(seating(rotation)):
            seats_held[entrant].add(seat)
    assert seats_held == {0: {0, 1, 2}, 1: {0, 1, 2}, 2: {0, 1, 2}}


def test_each_set_has_its_own_seed_shared_by_its_rotations():
    games = schedule(sets=2, seed=42)
    assert [(g.set, g.rotation) for g in games] == [(0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2)]
    assert len({g.seed for g in games[:3]}) == 1 and len({g.seed for g in games[3:]}) == 1
    assert games[0].seed != games[3].seed
    assert schedule(sets=2, seed=42) == games
    assert schedule(sets=2, seed=43)[0].seed != games[0].seed


@pytest.mark.parametrize(
    "totals, wins",
    [([5000, 2000, 1000], [1, 0, 0]), ([5000, 5000, 1000], [0.5, 0.5, 0]), ([0, 0, 0], [1 / 3] * 3)],
)
def test_split_wins(totals, wins):
    assert split_wins(totals) == pytest.approx(wins)


def test_parse_entrants():
    assert parse_entrants(seats="llm:a/one,decision,decision:typesafe/jev-1.13", models=None) == [
        "llm:a/one", "decision", "decision:typesafe/jev-1.13",
    ]
    assert parse_entrants(seats=None, models="a/one,b/two,c/three") == ["llm:a/one", "llm:b/two", "llm:c/three"]
    with pytest.raises(ValueError, match="human"):
        parse_entrants(seats="human,llm:a/one,llm:b/two", models=None)
    with pytest.raises(ValueError):
        parse_entrants(seats=None, models=None)


def test_a_small_tournament_plays_every_game_and_reports(tmp_path):
    result, client = run(tmp_path)
    logs = sorted(tmp_path.glob("set*.jsonl"))
    assert [p.name for p in logs] == [f"set{s:03d}-rotation{r}.jsonl" for s in range(2) for r in range(3)]
    assert all(finished(p) for p in logs)
    assert result["games"] == 6 and result["dev_run"] is True
    entrants = {e["entrant"]: e for e in result["entrants"]}
    assert set(entrants) == set(ENTRANTS)
    assert all(e["games"] == 6 for e in entrants.values())
    assert sum(e["wins"] for e in entrants.values()) == pytest.approx(6)
    assert all(len(e["win_rate_by_seat"]) == 3 for e in entrants.values())
    assert entrants["llm:a/one"]["cost"] > 0
    assert json.loads((tmp_path / "report.json").read_text()) == result


def test_rerunning_skips_finished_games(tmp_path):
    run(tmp_path)
    _, client = run(tmp_path, client=router(board_reader))
    assert client.client.calls == []


def test_rerunning_replays_an_unfinished_game(tmp_path):
    run(tmp_path)
    broken = tmp_path / "set001-rotation1.jsonl"
    broken.write_text("\n".join(broken.read_text().splitlines()[:5]) + "\n")  # a game cut off mid-round
    untouched = (tmp_path / "set000-rotation0.jsonl").read_text()
    _, client = run(tmp_path, client=router(board_reader))
    assert client.client.calls and finished(broken)
    assert (tmp_path / "set000-rotation0.jsonl").read_text() == untouched


def test_budget_cap_stops_new_games(tmp_path):
    result, _ = run(tmp_path, sets=3, parallel=1, max_cost=0.0001)  # the first game alone costs more
    assert len(list(tmp_path.glob("set*.jsonl"))) == 1
    assert result["games"] == 1 and result["stopped_by_budget"] is True


def test_report_numbers_match_a_known_game(tmp_path, rules, wheel_spec):
    """Seat 1 solves rounds 1 and 4 and the bonus; seats 2 and 3 solve one round each."""
    players = [Scripted(solves) for _ in range(3)]
    state = start(rules, wheel_spec)
    header = {"tournament": {"set": 0, "rotation": 0, "entrants": [0, 1, 2], "names": ENTRANTS, "puzzles": str(DEV)}}
    with GameLog(tmp_path / "set000-rotation0.jsonl", state, players, header=header) as log:
        final = play_game(state, players, log)
    envelope = final.bonus.envelope
    result = report(tmp_path)
    first, second, third = result["entrants"]
    m = rules.solve_minimum
    assert first["wins"] == 1 and second["wins"] == 0
    assert first["win_rate_by_seat"] == [1.0, None, None] and second["win_rate_by_seat"] == [None, 0.0, None]
    assert first["avg_total"] == 2 * m + envelope and first["avg_main_winnings"] == 2 * m
    assert (first["bonus_reached"], first["bonus_won"]) == (1, 1)
    assert (second["bonus_reached"], second["bonus_won"]) == (0, 0)
    assert first["solve_attempts"] == 2 and first["solve_accuracy"] == 1.0
    assert first["avg_board_shown"] == 0.0 and first["money_left_per_solve"] > 0
    assert third["solve_attempts"] == 1 and third["avg_total"] == m


def test_command_line_entry_point(tmp_path):
    from rstlne import tournament

    argv = ["--models", "a/one,b/two,c/three", "--sets", "1", "--parallel", "3", "--out", str(tmp_path / "t")]
    result = tournament.main(argv, client=router(board_reader))
    assert result["games"] == 3
    assert [e["entrant"] for e in result["entrants"]] == ["llm:a/one", "llm:b/two", "llm:c/three"]
    with pytest.raises(SystemExit, match="human"):
        tournament.main(["--seats", "human,llm:a,llm:b", "--sets", "1"])
