import json
from pathlib import Path

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
    out = numbers.build("x", toml, pairs=pairs, bonus=None, letters=[tmp_path / "none.json"], gap=tmp_path / "none.json")
    assert out["meta"]["phase"] == "x" and out["meta"]["lineups"] == ["L"]
    assert out["lineups"]["L"]["label"] == "one · two · decision"
    assert out["pairs"][0]["label"] == "L one minus two" and out["pairs"][0]["sets"] == 2
    assert out["letters"] is None and out["reading_gap"] is None and out["bonus"] is None
    assert all("play" in e for e in out["lineups"]["L"]["entrants"].values())
    assert set(out["comebacks"]) == {"3", "4", "round_4_by_kind"} and "pairs" in out["noise"]
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


def test_letter_files_merge_by_lineup_id_and_keep_only_the_phase(tmp_path):
    def rows(lineup, n):
        return [{"lineup": lineup, "player": "bot", "kind": "consonant", "letter": "T", "count": 1,
                 "board": ["SPARE TIRE", "Thing", ["R"], []], "judge": {"T": [0.9, 1.0]}}] * n
    old = tmp_path / "a.json"
    old.write_text(json.dumps({"judge_version": 6, "rows": rows("lineup 2", 2) + rows("lineup 1", 1) + rows("lineup 6a", 1)}))
    new = tmp_path / "b.json"
    new.write_text(json.dumps({"judge_version": 6, "rows": rows("lineup 6a", 3)}))
    merged = numbers.merge_letters([old, new], ["2", "6a", "6d1"])
    assert [r["lineup"] for r in merged["rows"]] == ["2", "2", "6a", "6a", "6a"]  # 6a from the later file, 1 dropped
    other = tmp_path / "c.json"
    other.write_text(json.dumps({"judge_version": 5, "rows": rows("lineup 2", 1)}))
    with pytest.raises(ValueError):
        numbers.merge_letters([old, other], ["2"])
    assert numbers.lineup_id("lineup 3b") == "3b" and numbers.lineup_id("seed707-abc") == "seed707-abc"


def test_rstlne_share_counts_letters_only():
    assert numbers.rstlne_share("RIVER STONE") == pytest.approx(7 / 10)  # R, E, R, S, T, N, E of the 10 letters
    assert numbers.rstlne_share("QUICK JAB") == 0


def test_bonus_shares_compare_the_deck_with_aired_bonus_puzzles_once_per_airing(tmp_path):
    deck = tmp_path / "deck.json"
    deck.write_text(json.dumps({"puzzles": [
        {"category": "Thing", "answer": "TEN", "bonus": True},          # 3 of 3
        {"category": "Thing", "answer": "BUCK", "bonus": True},         # 0 of 4
        {"category": "Thing", "answer": "MAIN ROUND", "bonus": False},  # not a bonus puzzle
    ]}))
    archive = tmp_path / "aired.csv"
    archive.write_text("Puzzle,Category,Date,Episode_Number,Round\n"
                       "TEA,Thing,9/1/20,#7000,BR\n"     # 2 of 3
                       "TEA,Thing,9/1/20,#7000,BR\n"     # listed twice: counted once
                       "MOCK,Thing,9/2/20,#7001,BR\n"    # 0 of 4
                       "STAR,Thing,9/2/20,#7001,R1\n")   # a main round: left out
    out = numbers.bonus_shares(deck, archive)
    assert out["deck"] == {"puzzles": 2, "mean": pytest.approx(0.5)}
    assert out["aired"]["puzzles"] == 2 and out["aired"]["mean"] == pytest.approx(1 / 3, abs=1e-4)  # rounded to 4 places
    assert out["aired"]["bands"] == [pytest.approx(0.5), 0, pytest.approx(0.5)]  # under 30%, 30 to 40%, 40% or more
    assert numbers.bonus_shares(deck, tmp_path / "missing.csv")["aired"] is None


def test_bonus_solves_split_by_how_much_rstlne_shows(tmp_path):
    def puzzle(player, i, answer, solved):
        folder = tmp_path / player
        folder.mkdir(exist_ok=True)
        rows = [{"type": "game", "bonus_test": {"entrant": player, "puzzle": i}},
                {"type": "summary", "bonus": {"puzzle": {"answer": answer}, "solved": solved}}]
        (folder / f"puzzle{i:03d}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    puzzle("bot", 0, "BUCK", True)    # 0%: under 30%
    puzzle("bot", 1, "TENT", False)   # 100%: 40% or more
    puzzle("bot", 2, "TEN", True)
    puzzle("bot", 3, "TUCK", False)   # 25%: under 30%, unfinished below
    (tmp_path / "bot" / "puzzle003.jsonl").write_text(json.dumps({"type": "game", "bonus_test": {"entrant": "bot", "puzzle": 3}}) + "\n")
    out = numbers.bonus_by_share(tmp_path)
    assert out["bands"] == ["under 30%", "30 to 40%", "40% or more"]
    assert out["entrants"]["bot"] == [[1, 1], [0, 0], [1, 2]]


def _jsonl(path, rows):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return path


def test_probe_rows_name_each_player_and_a_later_row_replaces_an_earlier_ask(tmp_path):
    def ask(right, puzzle=0, **who):
        return {**who, "deck": "aired", "board": "blank", "puzzle": puzzle, "right": right}
    first = _jsonl(tmp_path / "a.jsonl", [ask(False, model="openai/x"), ask(True, 1, model="openai/x")])
    rerun = _jsonl(tmp_path / "b.jsonl", [ask(True, model="openai/x"), ask(True, version=6), ask(False, 1, seat="bot")])
    tally = numbers.probe_tally([first, rerun])
    assert tally["llm:openai/x"]["aired"]["blank"] == [2, 2]  # puzzle 0 asked twice: the rerun's answer counts
    assert tally["bot"]["aired"]["blank"] == [1, 2]  # a bot row names a version or a seat


def test_memory_gives_each_player_aired_minus_control_with_an_interval_and_pools_the_models(tmp_path):
    rows = []
    for deck, rights in (("aired", [1, 1, 0, 0]), ("generated", [1, 0, 0, 0])):
        for i, r in enumerate(rights):
            rows += [{"model": m, "deck": deck, "board": "RSTLNE", "puzzle": i, "right": bool(r)} for m in ("a/x", "b/y")]
            rows.append({"version": 6, "deck": deck, "board": "RSTLNE", "puzzle": i, "right": bool(r)})
    out = numbers.memory([_jsonl(tmp_path / "m.jsonl", rows)])
    x = out["players"]["llm:a/x"]["RSTLNE"]
    assert x["aired"] == [2, 4] and x["generated"] == [1, 4] and x["gap"] == pytest.approx(0.25)
    assert x["ci95"][0] <= 0.25 <= x["ci95"][1]
    assert numbers.memory([_jsonl(tmp_path / "m.jsonl", rows)]) == out  # fixed seed
    pooled = out["models_pooled"]["RSTLNE"]  # LLMs only: the bot is its own row
    assert pooled["aired"] == [4, 8] and pooled["generated"] == [2, 8] and pooled["gap"] == pytest.approx(0.25)
    assert "bot" in out["players"]
    assert numbers.memory([tmp_path / "missing.jsonl"]) is None


def test_shown_share_counts_the_letters_a_set_of_calls_fills():
    assert numbers.shown_share("TOUGH WORKOUT", set("RSTLNE")) == pytest.approx(3 / 12)
    assert numbers.shown_share("TOUGH WORKOUT", set("RSTLNEMPGA")) == pytest.approx(4 / 12)


def test_blatt_counts_each_board_per_player_and_the_contestants_boards(tmp_path):
    deck = tmp_path / "blatt.json"
    deck.write_text(json.dumps({"source": "s", "puzzles": [
        {"category": "Thing", "answer": "TOUGH WORKOUT", "bonus": True, "contestant_picks": "MPGA"},
        {"category": "Place", "answer": "GULF", "bonus": True, "contestant_picks": "GHWO"}]}))
    blank = _jsonl(tmp_path / "blank.jsonl", [{"seat": "bot", "puzzle": i, "right": False} for i in range(2)])
    picks = _jsonl(tmp_path / "picks.jsonl", [{"seat": "bot", "puzzle": 0, "right": True},
                                              {"seat": "llm:a/x", "puzzle": 0, "right": True}])
    own = tmp_path / "report.json"
    own.write_text(json.dumps({"entrants": [{"entrant": "bot", "solved": 2, "puzzles": 2, "shown_after_picks": 0.4,
                                             "cost": 0.0}]}))
    out = numbers.blatt(deck, {"blank": blank, "contestant": picks, "own": own, "RSTLNE": tmp_path / "missing.jsonl"})
    assert out["puzzles"] == 2
    assert out["boards"]["blank"]["bot"] == [0, 2]
    assert out["boards"]["contestant"] == {"bot": [1, 1], "llm:a/x": [1, 1]}
    assert out["boards"]["own"]["bot"] == [2, 2] and out["own_shown"]["bot"] == 0.4
    assert out["boards"]["RSTLNE"] is None
    assert out["shown"]["RSTLNE"] == pytest.approx((3 / 12 + 1 / 4) / 2, abs=1e-4)
    assert out["shown"]["contestant"] == pytest.approx((4 / 12 + 2 / 4) / 2, abs=1e-4)


def test_variants_summarize_each_self_play_folder_that_exists(tmp_path, monkeypatch):
    from rstlne import selfplay
    (tmp_path / "milk").mkdir()
    monkeypatch.setattr(selfplay, "games_summary", lambda folder: {"games": 3, "folder": Path(folder).name})
    out = numbers.variants({"milk_all": tmp_path / "milk", "vowel_first": tmp_path / "none"})
    assert out == {"milk_all": {"games": 3, "folder": "milk"}}


def test_pooled_seats_merge_every_game_round_and_solve_of_the_named_seats():
    raw = {"bot #1": {"rounds_won": [1, 2], "tries": [1, 3], "shown_right": [0.6, 0.7, 0.8], "round_money": [1000, 3000, 5000]},
           "bot #2": {"rounds_won": [0, 1], "tries": [0, 1], "shown_right": [0.5], "round_money": [2000]},
           "llm:x": {"rounds_won": [9], "tries": [9], "shown_right": [0.1], "round_money": [1]}}
    out = numbers.pool_seats(raw, ["bot #1", "bot #2"])
    assert out["seats"] == 2 and out["seat_games"] == 4
    assert out["rounds_won_per_game"] == pytest.approx(1.0)  # 4 rounds over 4 seat-games
    assert out["solve_accuracy"] == pytest.approx(4 / 5)
    assert out["shown_at_correct_solve"]["median"] == pytest.approx(0.65)  # of 0.5, 0.6, 0.7, 0.8
    assert out["money_per_round_won"]["median"] == pytest.approx(2500)  # of 1000, 2000, 3000, 5000
    assert numbers.pool_seats(raw, []) is None
