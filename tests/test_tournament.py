import json
from collections import Counter
from itertools import permutations

import pytest
from fakes import FakeDecisions, board_reader, decide_by, router, solvable_when_full
from helpers import start
from test_runner import Scripted, solves

from rstlne import settings
from rstlne.engine.puzzle import Puzzle
from rstlne.runner import GameLog, play_game
from rstlne.tournament import (
    bootstrap,
    deal,
    folder_name,
    parse_entrants,
    report,
    run_tournament,
    schedule,
    split_wins,
    table,
)

ENTRANTS = ["llm:a/one", "llm:b/two", "decision"]
DEV = settings.ROOT / "puzzles" / "dev.json"


def run(tmp_path, sets=1, parallel=3, max_cost=None, client=None, mode="all", write=None, heartbeat=120):
    client = client or router(board_reader)
    decisions = FakeDecisions(decide_by(solvable_when_full))
    result = run_tournament(
        ENTRANTS, sets=sets, seed=42, puzzles_path=DEV, out_dir=tmp_path, parallel=parallel,
        max_cost=max_cost, client=client, decisions=decisions, mode=mode,
        write=write or (lambda line: None), heartbeat=heartbeat,
    )
    return result, client


def finished(path):
    lines = path.read_text().splitlines()
    return bool(lines) and json.loads(lines[-1])["type"] == "summary"


def headers(path):
    return [json.loads(p.read_text().splitlines()[0]) for p in sorted(path.glob("set*.jsonl"))]


# Set structure


def test_a_set_has_exactly_six_games_one_per_ordering():
    games = schedule(sets=2, seed=42)
    assert len(games) == 12
    first = [g for g in games if g.set == 0]
    assert len(first) == 6
    assert sorted(g.order for g in first) == sorted(permutations(range(3)))
    assert [g.permutation for g in first] == list(range(6))


def test_each_player_sits_in_each_seat_exactly_twice_per_set():
    seats = Counter((entrant, seat) for g in schedule(sets=1, seed=42) for seat, entrant in enumerate(g.order))
    assert seats == {(entrant, seat): 2 for entrant in range(3) for seat in range(3)}


def test_each_player_directly_follows_each_other_exactly_three_times_per_set():
    """Turns pass Seat 1, 2, 3, and back to Seat 1, so the follower of the last seat is the first seat."""
    follows = Counter(
        (g.order[seat], g.order[(seat + 1) % 3]) for g in schedule(sets=1, seed=42) for seat in range(3)
    )
    assert follows == {(a, b): 3 for a in range(3) for b in range(3) if a != b}


def test_all_games_in_a_set_share_a_seed_and_sets_differ():
    games = schedule(sets=2, seed=42)
    assert len({g.seed for g in games if g.set == 0}) == 1
    assert len({g.seed for g in games if g.set == 1}) == 1
    assert games[0].seed != games[6].seed
    assert schedule(sets=2, seed=42) == games


def test_cyclic_sets_keep_the_three_rotations():
    games = schedule(sets=1, seed=42, mode="cyclic")
    assert [g.order for g in games] == [(0, 1, 2), (2, 0, 1), (1, 2, 0)]
    seats = Counter((entrant, seat) for g in games for seat, entrant in enumerate(g.order))
    assert set(seats.values()) == {1}


# Puzzles


def puzzles(n):
    return [Puzzle("Thing", f"PUZZLE {chr(65 + i)}") for i in range(n)]


def test_puzzles_are_dealt_without_replacement_until_the_pool_runs_out():
    pool = puzzles(10)
    hands = deal(pool, per_set=4, sets=5, seed=1, label="main")
    assert all(len(hand) == 4 and len(set(hand)) == 4 for hand in hands)  # no set repeats a puzzle
    first_pass = [p for hand in hands for p in hand][:10]
    assert sorted(p.answer for p in first_pass) == sorted(p.answer for p in pool)  # all 10 before any repeat
    assert deal(pool, per_set=4, sets=3, seed=1, label="main") == hands[:3]  # set N never depends on later sets
    assert deal(pool, per_set=4, sets=5, seed=2, label="main") != hands


def test_a_set_that_straddles_a_reshuffle_skips_puzzles_it_holds():
    pool = puzzles(5)
    hands = deal(pool, per_set=4, sets=6, seed=3, label="main")
    assert all(len(set(hand)) == 4 for hand in hands)
    counts = Counter(p for hand in hands for p in hand)
    assert max(counts.values()) - min(counts.values()) <= 1  # used evenly, give or take one


def test_all_games_in_a_set_use_the_same_puzzles(tmp_path):
    run(tmp_path)
    found = {(json.dumps(h["puzzles"]), json.dumps(h["bonus_puzzle"]), h["seed"]) for h in headers(tmp_path)}
    assert len(found) == 1


# Running and reporting


def test_a_trial_set_plays_six_tagged_games_and_reports(tmp_path):
    result, _ = run(tmp_path)
    logs = sorted(tmp_path.glob("set*.jsonl"))
    assert [p.name for p in logs] == [f"set000-perm{k}.jsonl" for k in range(6)]
    assert all(finished(p) for p in logs)
    tags = [h["tournament"] for h in headers(tmp_path)]
    assert [(t["set"], t["permutation"]) for t in tags] == [(0, k) for k in range(6)]
    assert sorted(tuple(t["entrants"]) for t in tags) == sorted(permutations(range(3)))
    assert result["games"] == 6 and result["sets"] == 1 and result["dev_run"] is True
    entrants = {e["entrant"]: e for e in result["entrants"]}
    assert all(e["games"] == 6 for e in entrants.values())
    assert sum(e["wins"] for e in entrants.values()) == pytest.approx(6)
    (only_set,) = result["per_set"]
    assert only_set["set"] == 0 and sum(e["wins"] for e in only_set["entrants"]) == pytest.approx(6)
    assert sorted(result["puzzle_usage"].values()) == [1] * 5  # 4 main and 1 bonus, used by one set
    assert set(entrants["llm:a/one"]["ci95"]) == {"win_rate", "avg_total", "avg_main_winnings", "solve_accuracy"}
    assert len(result["pairwise"]) == 3
    assert json.loads((tmp_path / "report.json").read_text()) == result


def test_rerunning_skips_finished_games(tmp_path):
    run(tmp_path)
    _, client = run(tmp_path, client=router(board_reader))
    assert client.client.calls == []


def test_rerunning_replays_an_unfinished_game(tmp_path):
    run(tmp_path)
    broken = tmp_path / "set000-perm4.jsonl"
    broken.write_text("\n".join(broken.read_text().splitlines()[:5]) + "\n")
    untouched = (tmp_path / "set000-perm0.jsonl").read_text()
    _, client = run(tmp_path, client=router(board_reader))
    assert client.client.calls and finished(broken)
    assert (tmp_path / "set000-perm0.jsonl").read_text() == untouched


def test_budget_cap_stops_new_games(tmp_path):
    result, _ = run(tmp_path, sets=2, parallel=1, max_cost=0.0001)
    assert len(list(tmp_path.glob("set*.jsonl"))) == 1
    assert result["games"] == 1 and result["stopped_by_budget"] is True


def test_cyclic_mode_runs_three_games_a_set(tmp_path):
    result, _ = run(tmp_path, mode="cyclic")
    assert result["games"] == 3 and len(list(tmp_path.glob("set*.jsonl"))) == 3


@pytest.mark.parametrize(
    "totals, wins",
    [([5000, 2000, 1000], [1, 0, 0]), ([5000, 5000, 1000], [0.5, 0.5, 0]), ([0, 0, 0], [1 / 3] * 3)],
)
def test_split_wins(totals, wins):
    assert split_wins(totals) == pytest.approx(wins)


def test_bootstrap_resamples_sets_reproducibly():
    rows = [{"wins": w, "games": 6} for w in (6, 0, 3, 3, 4, 2)]
    ci = bootstrap(rows, lambda rs: sum(r["wins"] for r in rs) / sum(r["games"] for r in rs))
    assert ci == bootstrap(rows, lambda rs: sum(r["wins"] for r in rs) / sum(r["games"] for r in rs))
    assert ci[0] < 0.5 < ci[1] and 0 <= ci[0] and ci[1] <= 1
    same = [{"wins": 3, "games": 6}] * 6
    assert bootstrap(same, lambda rs: sum(r["wins"] for r in rs) / sum(r["games"] for r in rs)) == (0.5, 0.5)


def test_parse_entrants():
    assert parse_entrants(seats="llm:a/one,decision,decision:typesafe/jev-1.13", models=None) == [
        "llm:a/one", "decision", "decision:typesafe/jev-1.13",
    ]
    assert parse_entrants(seats=None, models="a/one,b/two,c/three") == ["llm:a/one", "llm:b/two", "llm:c/three"]
    with pytest.raises(ValueError, match="human"):
        parse_entrants(seats="human,llm:a/one,llm:b/two", models=None)
    with pytest.raises(ValueError):
        parse_entrants(seats=None, models=None)


def test_folder_name_changes_with_anything_that_changes_play():
    config = settings.load_config()
    base = folder_name(ENTRANTS, 42, DEV, config)
    assert base == folder_name(ENTRANTS, 42, DEV, config)
    cyclic = {**config, "tournament": {"set_permutations": "cyclic"}}
    pinned = {**config, "providers": {"llm:a/one": "x"}}
    effort = {**config, "llm": {**config["llm"], "reasoning_effort": "low"}}
    assert len({base, folder_name(ENTRANTS, 43, DEV, config), folder_name(ENTRANTS, 42, DEV, cyclic),
                folder_name(ENTRANTS, 42, DEV, pinned), folder_name(ENTRANTS, 42, DEV, effort)}) == 5


def test_report_numbers_match_a_known_game(tmp_path, rules, wheel_spec):
    """Seat 1 solves rounds 1 and 4 and the bonus; seats 2 and 3 solve one round each."""
    players = [Scripted(solves) for _ in range(3)]
    state = start(rules, wheel_spec)
    header = {"tournament": {"set": 0, "permutation": 0, "entrants": [0, 1, 2], "names": ENTRANTS, "puzzles": str(DEV)}}
    with GameLog(tmp_path / "set000-perm0.jsonl", state, players, header=header) as log:
        final = play_game(state, players, log)
    envelope = final.bonus.envelope
    result = report(tmp_path)
    first, second, third = result["entrants"]
    m = rules.solve_minimum
    assert first["wins"] == 1 and second["wins"] == 0
    assert first["win_rate_by_seat"] == [1.0, None, None] and second["win_rate_by_seat"] == [None, 0.0, None]
    assert first["avg_total"] == 2 * m + envelope and first["avg_main_winnings"] == 2 * m
    assert (first["bonus_reached"], first["bonus_won"]) == (1, 1)
    assert first["solve_attempts"] == 2 and first["solve_accuracy"] == 1.0
    assert first["avg_board_shown"] == 0.0 and first["money_left_per_solve"] > 0
    assert third["solve_attempts"] == 1 and third["avg_total"] == m
    assert first["ci95"]["win_rate"] == [1.0, 1.0]  # one set: no spread to resample


def test_command_line_trial_set(tmp_path):
    from rstlne import tournament

    argv = ["--models", "a/one,b/two,c/three", "--sets", "1", "--parallel", "3", "--out", str(tmp_path / "t")]
    result = tournament.main(argv, client=router(board_reader))
    assert result["games"] == 6 and result["sets"] == 1
    assert [e["entrant"] for e in result["entrants"]] == ["llm:a/one", "llm:b/two", "llm:c/three"]
    with pytest.raises(SystemExit, match="human"):
        tournament.main(["--seats", "human,llm:a,llm:b", "--sets", "1"])


def test_games_announce_when_they_start(tmp_path):
    lines = []
    run(tmp_path, write=lines.append)
    starts = [line for line in lines if line.startswith("started ")]
    assert len(starts) == 6
    assert starts[0] == "started set000-perm0: Seat 1 llm:a/one, Seat 2 llm:b/two, Seat 3 decision"


def test_status_lines_report_games_in_progress(tmp_path):
    import time

    def slow(request):
        time.sleep(0.005)
        return board_reader(request)

    lines = []
    run(tmp_path, client=router(slow), parallel=6, write=lines.append, heartbeat=0.2)
    status = [line for line in lines if line.startswith("in progress:")]
    assert status, "expected at least one status line while the games ran"
    assert "set000-perm" in status[0] and "moves)" in status[0] and "spent" in status[0]


def test_six_games_run_at_once_by_default():
    import inspect

    assert inspect.signature(run_tournament).parameters["parallel"].default == 6


def test_table_keeps_long_names_and_three_digit_bonus_counts_apart():
    entrant = {
        "entrant": "llm:deepseek/deepseek-v4.1-flash-1017", "wins": 149.5, "win_rate": 0.5,
        "ci95": {"win_rate": [0.43, 0.57]}, "win_rate_by_seat": [0.59, 0.55, 0.37], "avg_total": 28612,
        "avg_main_winnings": 4283, "bonus_won": 137, "bonus_reached": 149, "solve_accuracy": 0.81,
        "avg_board_shown": 0.29, "money_left_per_solve": 5535, "invalid_per_game": 0.19, "cost": 1.5603,
    }
    lines = table({"games": 298, "sets": 50, "dev_run": True, "entrants": [entrant], "pairwise": []})
    header, row = lines[2], lines[3]
    assert row.startswith("llm:deepseek/deepseek-v4.1-flash-1017 ")
    assert "$4,283 " in row and " 137/149 " in row
    for column in ("main", "bonus", "solve%"):  # each value ends under its header
        assert header.index(column) + len(column) == {"main": row.index("$4,283") + 6,
                                                      "bonus": row.index("137/149") + 7,
                                                      "solve%": row.index("81%") + 3}[column]
