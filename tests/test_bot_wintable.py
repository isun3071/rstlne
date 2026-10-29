import json
import random
from dataclasses import replace

import pytest
from bot_fixtures import view_at

from rstlne import selfplay
from rstlne.players.bot import versions
from rstlne.players.bot.objective import Objective, p_first, win_chance

KNOBS = versions.knobs(1)


def games(n, rng, leader_wins=0.9):
    """Games where the leader after round 3 goes on to finish first `leader_wins` of the time."""
    out = []
    for k in range(n):
        lead_seat = rng.randrange(3)
        after3 = [rng.randrange(0, 8000) for _ in range(3)]
        after3[lead_seat] += rng.randrange(1000, 12000)
        winner = lead_seat if rng.random() < leader_wins else rng.choice([s for s in range(3) if s != lead_seat])
        final = list(after3)
        final[winner] += 20_000
        out.append({"set": k // 6, "seats": ["a", "b", "c"], "totals": final,
                    "round_totals": [[0, 0, 0], [0, 0, 0], after3, final]})
    return out


def test_the_table_learns_how_often_a_lead_holds():
    table = selfplay.build_win_table(games(3000, random.Random(2)), main_rounds=4)
    one_left = dict(table)[1]
    leads = [x for x, _ in one_left]
    chances = [p for _, p in one_left]
    assert chances == sorted(chances)  # a bigger lead never lowers the chance
    assert win_chance(table, 1, 8000) == pytest.approx(0.9, abs=0.08)
    assert win_chance(table, 1, -8000) < 0.15
    assert min(leads) < 0 < max(leads)


def test_the_bot_reads_its_win_chance_from_the_table_where_it_has_one(rules, wheel_spec):
    table = ((1, ((-10000.0, 0.02), (0.0, 0.4), (10000.0, 0.97))),)
    view, _ = view_at(rules, wheel_spec, round_number=3, totals=(5000, 0, 0))
    goal = Objective(view, rules, wheel_spec, replace(KNOBS, win_table=table))
    plain = Objective(view, rules, wheel_spec, KNOBS)
    banked = goal.win_round(1000, wild=False, million=False).main  # lead 6,000 with one round left
    assert banked == pytest.approx(0.4 + 0.57 * 0.6)
    assert plain.win_round(1000, wild=False, million=False).main == pytest.approx(p_first((6000, 0, 0), 0, 1, KNOBS.win_sigma))


def test_with_no_rounds_left_the_lead_decides_whatever_the_table_says(rules, wheel_spec):
    table = ((1, ((0.0, 0.5),)),)
    view, _ = view_at(rules, wheel_spec, round_number=4, totals=(5000, 6000, 0))
    goal = Objective(view, rules, wheel_spec, replace(KNOBS, win_table=table))
    assert goal.win_round(500, wild=False, million=False).main == 0.5  # 6,000 against 6,000: a shared win
    assert goal.win_round(2000, wild=False, million=False).main == 1


def test_big_knobs_load_from_a_file(tmp_path):
    path = tmp_path / "table.json"
    path.write_text(json.dumps({"knob": [[1, [[-1000, 0.1], [1000, 0.8]]]]}))
    knobs = selfplay.override(KNOBS, [f"win_table=@{path}"])
    assert knobs.win_table == ((1, ((-1000.0, 0.1), (1000.0, 0.8))),)


def test_the_win_table_job_reads_game_folders_and_writes_the_knob(tmp_path):
    folder = tmp_path / "games"
    folder.mkdir()
    with open(folder / "games-shard1of1.jsonl", "w") as f:
        for g in games(600, random.Random(3)):
            f.write(json.dumps(g) + "\n")
    lines = []
    table = selfplay.win_table([folder], tmp_path / "out", main_rounds=4, say=lines.append)
    saved = json.loads((tmp_path / "out" / "win-table.json").read_text())
    assert saved["games"] == 600 and saved["knob"] == [[r, [list(p) for p in pts]] for r, pts in table]
    assert any("1 round left" in line for line in lines)
