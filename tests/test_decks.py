import csv
import json

import pytest

from rstlne import settings
from rstlne.engine.puzzle import round_pools
from rstlne.decks import build_mega, season_of


def write_csv(path, rows):
    with path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["Puzzle", "Category", "Date", "Episode_Number", "Round"])
        w.writerows(rows)


@pytest.fixture
def sources(tmp_path):
    archive = tmp_path / "aired.csv"
    write_csv(archive, [
        ["ANYTHING IS POSSIBLE", "Phrase", "9/16/13", "#5851", "T1"],                 # a toss-up: left out
        ["SPARE TIRE", "Thing", "9/16/13", "#5851", "R1"],
        ["HOT COCOA", "Food & Drink", "2/3/14", "#5950", "R2^"],
        ["PIECE OF CAKE", "Phrase", "3/3/15", "#6100", "R3*"],
        ["BREAK THE ICE", "Phrase", "10/1/20", "#7101", "R4"],
        ["BREAK THE ICE", "Phrase", "1/5/24", "#7700", "R6"],                        # aired twice: one puzzle, two airings
        ["BREAK THE ICE", "Phrase", "1/5/24", "#7700", "R6"],                        # the archive's duplicate row: no third airing
        ["GOOD LUCK", "Phrase", "9/16/13", "#5851", "BR"],
        ["", "", "6/6/25", "#8205", "BR"],                                           # an empty row
        ["A" * 60, "Phrase", "6/6/25", "#8205", "R1"],                              # doesn't fit the board
    ])
    gen = tmp_path / "generated"
    gen.mkdir()
    (gen / "deck-a.json").write_text(json.dumps({"generator": "m", "puzzles": [
        {"category": "Thing", "answer": "RICKETY GAZEBO", "bonus": True},
        {"category": "Phrase", "answer": "A PENNY FOR YOUR THOUGHTS", "bonus": False},
        {"category": "Event", "answer": "SNOW DAY", "bonus": False},
        {"category": "Thing", "answer": "SPARE TIRE", "bonus": False},                # also aired: the aired copy wins
    ]}))
    (gen / "deck-b.json").write_text(json.dumps({"generator": "m", "puzzles": [
        {"category": "Phrase", "answer": "A PENNY FOR YOUR THOUGHTS", "bonus": False, "round": 2},  # repeats deck-a
    ]}))
    (gen / "seen.txt").write_text("not a deck")
    return archive, gen


def test_seasons_start_in_september():
    assert season_of(2013, 9) == 31 and season_of(2014, 2) == 31 and season_of(2014, 9) == 32 and season_of(1983, 9) == 1


def test_the_mega_deck_joins_aired_and_generated_puzzles_with_where_each_came_from(sources, tmp_path):
    archive, gen = sources
    deck = build_mega(archive, sorted(gen.glob("*.json")))
    by = {(p["answer"], p["bonus"]): p for p in deck["puzzles"]}
    assert ("ANYTHING IS POSSIBLE", False) not in by and ("A" * 60, False) not in by
    tire = by[("SPARE TIRE", False)]
    assert tire["round"] == 1 and tire["source"]["kind"] == "aired"
    assert tire["source"]["airings"] == [{"season": 31, "episode": 5851, "season_episode": 1, "date": "2013-09-16", "round": "R1"}]
    cocoa = by[("HOT COCOA", False)]["source"]["airings"][0]
    assert cocoa["season"] == 31 and cocoa["season_episode"] == 2  # the season's second episode in the archive, in air order
    ice = by[("BREAK THE ICE", False)]
    assert ice["round"] == 4 and [a["episode"] for a in ice["source"]["airings"]] == [7101, 7700]
    assert by[("HOT COCOA", False)]["round"] == 2
    assert by[("GOOD LUCK", True)]["source"]["airings"][0]["round"] == "BR" and "round" not in by[("GOOD LUCK", True)]
    penny = by[("A PENNY FOR YOUR THOUGHTS", False)]
    assert penny["source"] == {"kind": "generated", "decks": ["deck-a", "deck-b"]} and penny["round"] in (1, 2, 3)
    assert by[("SNOW DAY", False)]["round"] == 4                                        # 18 letters or fewer: round 4
    assert by[("RICKETY GAZEBO", True)]["source"]["kind"] == "generated"
    assert deck["counts"] == {"aired_main": 4, "aired_bonus": 1, "generated_main": 2, "generated_bonus": 1}


def test_the_mega_deck_loads_and_deals_by_round(sources, tmp_path):
    archive, gen = sources
    path = tmp_path / "mega.json"
    path.write_text(json.dumps(build_mega(archive, sorted(gen.glob("*.json")))))
    puzzles = settings.load_puzzles(path)
    pools = round_pools([p for p in puzzles if not p.bonus], 4)
    assert pools is not None and all(pools)


def test_the_aired_deck_holds_only_aired_puzzles(sources):
    from rstlne.decks import build_aired
    archive, _ = sources
    deck = build_aired(archive)
    assert deck["name"] == "aired" and {p["source"]["kind"] for p in deck["puzzles"]} == {"aired"}
    assert deck["counts"]["generated_main"] == 0 and deck["counts"]["aired_main"] == 4 and deck["counts"]["aired_bonus"] == 1
