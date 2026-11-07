import json

import pytest

from rstlne import tournament
from rstlne.analysis import numbers

from test_analysis import write_game
from test_tournament import run


@pytest.fixture(scope="module")
def played(tmp_path_factory):
    folder = tmp_path_factory.mktemp("lineup")
    run(folder, sets=2)
    return folder


def test_each_entrant_gets_wins_places_solving_money_letters_and_cost(played):
    out = numbers.lineup(played)
    assert out["games"] == 12 and out["sets"] == 2
    ents = out["entrants"]
    assert set(ents) == {"llm:a/one", "llm:b/two", "decision"}
    assert sum(e["win_rate"] for e in ents.values()) == pytest.approx(1, abs=1e-3)  # rates are rounded to 4 places
    for e in ents.values():
        assert e["games"] == 12
        assert sum(e["places"]) == pytest.approx(1)
        assert 1 <= e["place"]["mean"] <= 3
        assert e["rounds_won_per_game"] * e["games"] <= e["solve_tries_per_game"] * e["games"] + 1e-9
        assert e["win_ci95"] is not None and e["win_ci95"][0] <= e["win_rate"] <= e["win_ci95"][1]
        assert set(e["consonants"]) >= {"per_game", "hit_rate", "copies", "copies_when_hit"}
        assert e["cost"]["mean"] >= 0


def test_entrant_win_rates_and_intervals_match_the_tournament_report(played):
    report = {e["entrant"]: e for e in tournament.report(played)["entrants"]}
    for name, e in numbers.lineup(played)["entrants"].items():
        assert e["win_rate"] == report[name]["win_rate"]
        assert e["win_ci95"] == report[name]["ci95"]["win_rate"]


def test_a_pair_is_the_mean_set_by_set_difference_with_the_shared_bootstrap():
    a = {0: 0.5, 1: 1 / 3, 2: 0.0, 3: 2 / 3}
    b = {0: 1 / 6, 1: 1 / 3, 2: 1 / 6, 4: 1.0}  # set 4 has no partner: left out
    p = numbers.pair_of(a, b)
    diffs = [a[k] - b[k] for k in (0, 1, 2, 3) if k in b]
    assert p["sets"] == 3
    assert p["diff"] == pytest.approx(sum(diffs) / 3, abs=1e-4)
    assert p["ci95"] == list(tournament.bootstrap(diffs, lambda r: sum(r) / len(r)))
    assert numbers.pair_of(a, b) == p  # same seed, same interval every run


def test_per_set_win_shares_split_ties_and_average_the_six_games(tmp_path):
    write_game(tmp_path, "set000-perm0", totals=(1000, 1000, 0))
    write_game(tmp_path, "set000-perm1", totals=(0, 2000, 0))
    write_game(tmp_path, "set001-perm0", set_index=1, totals=(3000, 0, 0))
    shares = numbers.set_shares(tmp_path)
    assert shares["llm:openai/gpt-6.1-sol"] == {0: pytest.approx(0.25), 1: pytest.approx(1.0)}
    assert shares["bot #1"] == {0: pytest.approx(0.75), 1: 0.0}


def test_letter_judgments_summarize_per_lineup_and_player_with_copies_folded():
    def row(player, letter, count, judge, lineup="6a"):
        return {"lineup": lineup, "player": player, "kind": "consonant", "letter": letter, "count": count,
                "board": ["SPARE TIRE", "Thing", ["R"], []], "judge": judge}
    judge = {"T": [0.9, 1.0], "S": [0.8, 1.0], "N": [0.1, 0.0]}
    rows = [row("bot", "T", 1, judge), row("llm:x #1", "S", 1, judge), row("llm:x #2", "N", 0, judge)]
    out = numbers.letters_summary({"judge_version": 6, "rows": rows})
    assert out["judge_version"] == 6
    x = out["rows"]["6a"]["llm:x"]["consonant"]
    assert x["n"] == 2 and x["hit"] == pytest.approx(0.5) and x["judge"] == pytest.approx(0.45)
    assert x["top"] == pytest.approx(0.0) and x["rule_hit"] == pytest.approx(1.0)
    assert out["rows"]["6a"]["bot"]["consonant"]["top"] == pytest.approx(1.0)


def test_build_reads_the_phase_and_skips_analyses_not_yet_run(played, tmp_path):
    toml = tmp_path / "lineups.toml"
    toml.write_text(f'default = "x"\n[x.L]\nfolder = "{played}"\nlabel = "one · two · decision"\n')
    pairs = [("L one minus two", ("L", "llm:a/one"), ("L", "llm:b/two"))]
    out = numbers.build("x", toml, pairs=pairs, bonus=None, letters=tmp_path / "none.json", gap=tmp_path / "none.json")
    assert out["meta"]["phase"] == "x" and out["meta"]["lineups"] == ["L"]
    assert out["lineups"]["L"]["label"] == "one · two · decision"
    assert out["pairs"][0]["label"] == "L one minus two" and out["pairs"][0]["sets"] == 2
    assert out["letters"] is None and out["reading_gap"] is None and out["bonus"] is None
    json.dumps(out)  # writable as is


def test_the_reading_gap_summary_gives_each_category_its_share_and_board():
    from rstlne.analysis import reading_gap as rg
    found = [{"name": "sol", "category": rg.WRONG, "shown": 0.3}, {"name": "sol", "category": rg.WRONG, "shown": 0.5},
             {"name": "sol", "category": rg.UNSURE, "shown": 0.6, "calibrated": 0.7},
             {"name": "sol", "category": rg.KNEW, "shown": 0.8, "how": "bankrupt"}]
    split = {"round": {1: [3, 5]}, "length": {"17 letters or fewer": [1, 2]}}
    out = rg.summarize(found, split)
    sol = out["players"]["sol"]
    assert sol["rounds"] == 4
    assert sol["categories"][rg.WRONG] == {"share": 0.5, "rounds": 2, "median_shown": 0.4}
    assert sol["categories"][rg.UNSURE]["median_calibrated"] == 0.7
    assert sol["categories"][rg.KNEW]["how"] == {"bankrupt": 1}
    assert out["by_round"] == {"1": [3, 5]} and out["by_length"] == {"17 letters or fewer": [1, 2]}
    json.dumps(out)
