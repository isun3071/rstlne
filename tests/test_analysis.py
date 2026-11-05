import json

import pytest

from rstlne.analysis import common, detail, letters, milking, odds, progress, reading_gap

NAMES = ["llm:openai/gpt-6.1-sol", "bot #1", "bot #2"]
KINDS = ["llm", "bot", "bot"]


def act(seat, number, answer, category, used, kind, outcome, *, letter=None, guess=None, raw=None, banks=(0, 0, 0),
        phase="turn"):
    return {"type": "action", "seat": seat,
            "state": {"phase": phase, "round": {"number": number, "puzzle": {"category": category, "answer": answer},
                                                "used": sorted(used)},
                      "seats": [{"bank": b, "total": 0} for b in banks]},
            "raw": raw or {}, "action": {"kind": kind, **({"letter": letter} if letter else {}),
                                         **({"answer": guess} if guess else {})},
            "result": {"outcome": outcome}, "wedge": {}}


def game_actions():
    """Round 1: bot #1 knows BREAK THE ICE, milks, hits Bankrupt, and Sol solves.
    Round 2: Sol solves SPARE TIRE early. Round 3: bot #2 milks HOT COCOA and solves with $1,200 more."""
    b1 = {"best": "BREAK THE ICE", "confidence": 0.99, "planner": "spin", "p_steal": 0.8}
    return [
        act(1, 1, "BREAK THE ICE", "Phrase", "", "call_consonant", "correct", letter="K", raw=b1),
        act(1, 1, "BREAK THE ICE", "Phrase", "K", "spin", "bankrupt", raw=b1, banks=(0, 700, 0)),
        act(2, 1, "BREAK THE ICE", "Phrase", "K", "call_consonant", "missing", letter="Z",
            raw={"best": "BREAK THE ICE", "confidence": 0.5}),
        act(0, 1, "BREAK THE ICE", "Phrase", "K", "solve", "solved", guess="BREAK THE ICE"),
        act(0, 2, "SPARE TIRE", "Thing", "", "call_consonant", "correct", letter="R"),
        act(0, 2, "SPARE TIRE", "Thing", "R", "solve", "wrong_solve", guess="SPARE WIRE"),
        act(1, 2, "SPARE TIRE", "Thing", "R", "call_consonant", "missing", letter="Z", raw={"best": "SPARE TIRE", "confidence": 0.4}),
        act(0, 2, "SPARE TIRE", "Thing", "R", "solve", "solved", guess="SPARE TIRE", banks=(600, 0, 0)),
        act(2, 3, "HOT COCOA", "Food & Drink", "", "spin", "landed",
            raw={"best": "HOT COCOA", "confidence": 0.99, "planner": "spin"}, banks=(0, 0, 500)),
        act(2, 3, "HOT COCOA", "Food & Drink", "", "call_consonant", "correct", letter="C", banks=(0, 0, 500)),
        act(2, 3, "HOT COCOA", "Food & Drink", "C", "solve", "solved", guess="HOT COCOA", banks=(0, 0, 1700),
            raw={"best": "HOT COCOA", "confidence": 0.999, "planner": "solve"}),
    ]


def write_game(folder, name="set000-perm0", set_index=0, entrants=(0, 1, 2), totals=(1600, 0, 1700), actions=None,
               finished=True):
    header = {"type": "header", "seats": [{"kind": KINDS[e]} for e in entrants], "puzzles": [], "bonus_puzzle": {},
              "tournament": {"set": set_index, "permutation": 0, "entrants": list(entrants), "names": NAMES,
                             "puzzles": "deck.json"}}
    rows = [header, *(game_actions() if actions is None else actions)]
    if finished:
        rows.append({"type": "summary", "totals": list(totals), "bonus": None, "usage": {"cost": 0.0}})
    (folder / f"{name}.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")


@pytest.fixture
def folder(tmp_path):
    write_game(tmp_path)
    write_game(tmp_path, "set000-perm1", finished=False)  # still playing: left out
    return tmp_path


# Reading logs


def test_games_are_the_finished_ones_with_each_seats_entrant(folder):
    games = list(common.games(folder))
    assert len(games) == 1
    g = games[0]
    assert g.names == NAMES and g.kind(0) == "llm" and g.winners() == [0.0, 0.0, 1.0]
    rounds = g.rounds()
    assert sorted(rounds) == [1, 2, 3] and common.solved_by(rounds[2])[0] == 0


def test_lineups_resolve_by_id_or_folder(tmp_path, folder):
    toml = tmp_path / "lineups.toml"
    toml.write_text(f'default = "x"\n[x]\n"2" = {{ folder = "seed707-abc", label = "Sol · bot · bot" }}\n')
    assert common.lineups(path=toml)["2"]["folder"] == common.TOURNAMENTS / "seed707-abc"
    assert common.resolve(["2", str(folder)], path=toml) == [("lineup 2", common.TOURNAMENTS / "seed707-abc"),
                                                            (folder.name, folder)]
    with pytest.raises(ValueError, match="nope"):
        common.resolve(["nope"], path=toml)
    with pytest.raises(ValueError, match="no phase"):
        common.lineups("y", path=toml)


# Per entrant detail


def test_detail_counts_rounds_banks_board_showing_and_wrong_solves(folder):
    stats = detail.seat_stats(folder)
    sol, bot2 = stats["llm:openai/gpt-6.1-sol"], stats["bot #2"]
    assert sol["games"] == 1 and sol["rounds_won"] == 2 and sol["wrong_solves"] == 1
    assert sol["median_bank"] == 300  # banks 0 and 600 at its two solves
    assert bot2["rounds_won"] == 1 and bot2["median_bank"] == 1700
    assert sol["median_shown"] == pytest.approx((1 / 11 + 2 / 9) / 2)  # one K of 11 letters, two Rs of 9


# Milking


def test_milking_follows_each_round_a_bot_spun_on_a_known_answer(folder):
    game = next(common.games(folder))
    rounds = milking.milked_rounds(game)
    assert [(r["round"], r["name"], r["outcome"]) for r in rounds] == [
        (1, "bot #1", "lost"), (3, "bot #2", "won")]
    lost, won = rounds
    assert lost["taker"] == "llm:openai/gpt-6.1-sol" and lost["lost_wheel"] == "bankrupt"
    assert won["gain"] == 1200  # $500 when it started milking, $1,700 at the solve
    summary = milking.summarize(rounds)
    assert summary["rounds"] == 2 and summary["won"] == 0.5


# Why the LLM wins its rounds


def test_rounds_the_focal_seat_won_are_sorted_by_what_the_bots_lacked(folder):
    game = next(common.games(folder))
    cases = reading_gap.cases(game, lambda name, kind: kind == "llm")
    assert [(c["round"], c["category"]) for c in cases] == [(1, reading_gap.KNEW), (2, None)]
    assert cases[0]["how"] == "bankrupt"
    assert cases[1]["board"] == ("SPARE TIRE", "Thing", "R", ("SPARE WIRE",))  # Sol's own wrong solve refuted SPARE WIRE


@pytest.mark.parametrize("best, confidence, expected", [
    ("SPARE WIRE", 0.9, reading_gap.WRONG),
    ("SPARE TIRE", 0.5, reading_gap.UNSURE),
    ("SPARE TIRE", 0.99, reading_gap.SURE),
])
def test_a_read_of_the_winning_board_names_the_gap(best, confidence, expected):
    calibrate = lambda c: c  # noqa: E731
    assert reading_gap.category("SPARE TIRE", {"best": best, "confidence": confidence}, calibrate, 0.95) == expected


# Letter choice


def test_letter_decisions_carry_the_board_they_were_made_on(folder):
    game = next(common.games(folder))
    rows = letters.decisions(game, "lineup x")
    assert [(r["player"], r["letter"], r["count"]) for r in rows] == [
        ("bot #1", "K", 1), ("bot #2", "Z", 0), ("llm:openai/gpt-6.1-sol", "R", 2), ("bot #1", "Z", 0), ("bot #2", "C", 2)]
    assert rows[0]["board"] == ["BREAK THE ICE", "Phrase", [], []]
    assert rows[3]["board"] == ["SPARE TIRE", "Thing", ["R"], ["SPARE WIRE"]]


def test_a_letter_is_scored_against_the_judges_odds_and_the_frequency_rule():
    row = {"kind": "consonant", "letter": "S", "count": 1, "board": ["SPARE TIRE", "Thing", ["R"], []],
           "judge": {"N": [0.6, 1.0], "T": [0.9, 1.0], "S": [0.8, 1.0]}}
    s = letters.score(row)
    assert s["p"] == 0.8 and s["best_p"] == 0.9 and not s["top"] and s["hit"]
    assert s["rule_hit"] and s["rule_copies"] == 1  # T, the first consonant in frequency order still open
    assert s["shown"] == pytest.approx(2 / 9)


# Logged odds against what happened


def test_a_lost_wheel_counts_as_stolen_when_an_opponent_solves_first(folder):
    game = next(common.games(folder))
    assert odds.steal_cases(game) == [{"p": 0.8, "stolen": True, "milking": True, "round": 1}]


# Progress, on a real tournament's logs


def test_progress_reports_each_entrant_and_gap(tmp_path):
    from test_tournament import run
    run(tmp_path)
    text = "\n".join(progress.lines("lineup x", tmp_path))
    assert "6 games in 1 sets" in text and "llm:a/one" in text and "decision" in text and " minus " in text
    assert progress.lines("empty", tmp_path / "nothing") == ["empty: no finished games yet"]


def test_logs_from_before_the_planner_was_logged_redo_its_test(tmp_path):
    # bot v1 has no confidence curve, so its known-answer threshold applies to the raw confidence
    old = [act(1, 1, "HOT COCOA", "Food & Drink", "", "spin", "landed", raw={"version": 1, "best": "HOT COCOA", "confidence": 0.97}),
           act(1, 1, "HOT COCOA", "Food & Drink", "", "spin", "bankrupt", raw={"version": 1, "best": "HOT COCOA", "confidence": 0.97}),
           act(2, 1, "HOT COCOA", "Food & Drink", "", "spin", "landed", raw={"version": 1, "best": "HOT COCOA", "confidence": 0.6}),
           act(0, 1, "HOT COCOA", "Food & Drink", "", "solve", "solved", guess="HOT COCOA")]
    write_game(tmp_path, actions=old, totals=(1000, 0, 0))
    game = next(common.games(tmp_path))
    assert not game.logs_planner
    assert [(r["name"], r["outcome"], r["lost_wheel"]) for r in milking.milked_rounds(game)] == [("bot #1", "lost", "bankrupt")]
    assert reading_gap.cases(game, lambda name, kind: kind == "llm")[0]["category"] == reading_gap.KNEW
