import pytest

from rstlne.analysis import play

from test_tournament import run


def test_a_wrong_solve_is_sorted_by_how_it_went_wrong():
    used = frozenset("RSTE")
    answer = "SPARE TIRE"  # board: S _ _ R E   T _ R E
    assert play.wrong_kind(answer, "SPARE WIRE", used, frozenset()) == "contradicts a shown letter"  # W where T shows
    assert play.wrong_kind(answer, "STARE TIRE", used, frozenset()) == "called letter in a blank"     # T is called, hidden there
    assert play.wrong_kind(answer, "SPARE TIRES", used, frozenset()) == "wrong shape"
    assert play.wrong_kind(answer, "SCARE TIRE", used, frozenset()) == "fits, but wrong"
    assert play.wrong_kind(answer, "SCARE TIRE", used, frozenset({"SCARE TIRE"})) == "already ruled wrong"


@pytest.mark.parametrize("shown, stage", [(0.0, "open"), (0.24, "open"), (0.25, "middle"), (0.49, "middle"), (0.5, "late"), (1.0, "late")])
def test_stages_of_a_round_split_at_a_quarter_and_a_half_showing(shown, stage):
    assert play.stage(shown) == stage


def test_a_lead_lands_in_its_band():
    assert play.band(0) == "under $2,500" and play.band(2499) == "under $2,500"
    assert play.band(2500) == "$2,500–5,000" and play.band(15000) == "$15,000 or more"


@pytest.fixture(scope="module")
def played(tmp_path_factory):
    folder = tmp_path_factory.mktemp("lineup")
    run(folder, sets=2)
    return folder


def test_every_entrant_gets_stages_lengths_specials_and_wrong_solves(played):
    stats = play.play_stats(played)
    assert set(stats) == {"llm:a/one", "llm:b/two", "decision"}
    for s in stats.values():
        assert set(s["stages"]) == {"open", "middle", "late"}
        assert {"consonants", "hits", "copies", "vowels", "solve_tries", "solves_right"} <= set(s["stages"]["open"])
        assert sum(s["wrong_solves"].values()) == s["wrong_solves_total"]
        assert {"mystery", "express", "wild"} <= set(s["specials"])
        assert set(s["by_length"]) <= {"17 letters or fewer", "18 to 22", "23 to 26", "27 or more"}
        assert s["forfeits"] >= 0


def test_comebacks_count_leaders_and_trailers_from_rounds_3_and_4(played):
    out = play.comebacks([played])
    for n in ("3", "4"):
        held = out[n]["held"]
        games = sum(b["games"] for b in held.values())
        assert games <= 12 and all(0 <= b["held"] <= 1 for b in held.values())
        assert all(0 <= b["came_back"] <= 1 for b in out[n]["came_back"].values())
