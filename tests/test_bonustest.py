"""The bonus test: every player meets every bonus puzzle in a file, alone, with no wheel or opponents."""

import json
import re

import pytest
from fakes import board_reader, completion, router

from rstlne import bonustest, settings
from rstlne.engine.puzzle import Puzzle
from rstlne.engine.state import Phase

DEV = settings.ROOT / "puzzles" / "dev.json"
BONUS = [p for p in settings.load_puzzles(DEV) if p.bonus]


def oracle(request):
    """A fake model that knows every dev bonus answer: it picks letters, then solves the puzzle its session names."""
    text = next(m["content"] for m in reversed(request["messages"]) if isinstance(m.get("content"), str) and "Board: " in m["content"])
    if "bonus_picks" in re.search(r"^Your move\. Legal: (.*)\.$", text, re.M).group(1):
        return completion(("bonus_picks", {"consonants": ["C", "D", "M"], "vowel": "A"}))
    puzzle = int(re.search(r"-(\d{3})-seat1$", request["extra_body"]["session_id"]).group(1))
    return completion(("bonus_solve", {"answer": BONUS[puzzle].answer}))


def run(tmp_path, entrants=("llm:a/one", "llm:b/two"), client=None, **options):
    return bonustest.run_bonus_test(
        list(entrants), DEV, seed=7, out_dir=tmp_path, client=client or router(board_reader),
        write=lambda line: None, **options,
    )


def test_a_bonus_game_opens_at_the_picks_with_rstlne_shown_for_seat_one(rules, wheel_spec):
    state = bonustest.bonus_game(7, rules, wheel_spec, Puzzle("Phrase", "GOOD JOB", bonus=True))
    assert state.phase is Phase.BONUS_PICKS and state.seat == 0 and state.bonus.seat == 0
    assert state.bonus.used == frozenset(rules.bonus_letters)
    assert not any(s.wild or s.million for s in state.seats)  # no cards: three consonants, ordinary envelopes


def test_every_player_meets_every_bonus_puzzle_once(tmp_path):
    result = run(tmp_path)
    for entrant in ("llm:a/one", "llm:b/two"):
        logs = sorted((tmp_path / bonustest.safe(entrant)).glob("puzzle*.jsonl"))
        assert len(logs) == len(BONUS)
        headers = [json.loads(p.read_text().splitlines()[0])["bonus_test"] for p in logs]
        assert [h["puzzle"] for h in headers] == list(range(len(BONUS))) and {h["entrant"] for h in headers} == {entrant}
    assert [e["puzzles"] for e in result["entrants"]] == [len(BONUS)] * 2


def test_the_same_puzzle_gets_the_same_envelope_for_every_player(tmp_path):
    run(tmp_path)
    envelopes = [
        [json.loads(p.read_text().splitlines()[-1])["bonus"]["envelope"] for p in sorted((tmp_path / bonustest.safe(e)).glob("*.jsonl"))]
        for e in ("llm:a/one", "llm:b/two")
    ]
    assert envelopes[0] == envelopes[1]


def test_rerunning_skips_finished_puzzles(tmp_path):
    run(tmp_path)
    client = router(board_reader)
    run(tmp_path, client=client)
    assert client.client.calls == []


def test_the_budget_cap_stops_new_puzzles(tmp_path):
    result = run(tmp_path, entrants=("llm:a/one",), max_cost=0.01, parallel=1)  # each fake call costs $0.001, two calls a puzzle
    assert result["stopped_by_budget"] and result["entrants"][0]["puzzles"] == 5


def test_the_report_counts_solves_picks_and_cost(tmp_path):
    result = run(tmp_path, entrants=("llm:a/one",), client=router(oracle))
    e = result["entrants"][0]
    assert e["solved"] == e["puzzles"] == len(BONUS) and e["rate"] == 1.0
    assert e["ci95"][0] > 0.85 and e["ci95"][1] == 1.0
    assert e["consonants"]["C"] == e["consonants"]["D"] == e["consonants"]["M"] == len(BONUS) and e["vowels"] == {"A": len(BONUS)}
    assert e["cost"] == pytest.approx(0.002 * len(BONUS))
    assert 0 < e["shown_after_picks"] < 1


def test_a_solve_that_does_not_fit_the_board_is_a_misfit_not_an_invalid_response(tmp_path):
    def wrong(request):
        if "bonus_picks" in request["messages"][-1]["content"]:
            return board_reader(request)
        return completion(("bonus_solve", {"answer": "ZZZ"}))

    e = run(tmp_path, entrants=("llm:a/one",), client=router(wrong), limit=2)["entrants"][0]
    assert (e["solved"], e["misfits"], e["invalid"]) == (0, 2, 0)


def test_paired_gaps_compare_the_same_puzzles(tmp_path):
    def mixed(request):  # a/one knows every answer, b/two reads only the board
        return oracle(request) if request["model"] == "a/one" else board_reader(request)

    result = run(tmp_path, client=router(mixed))
    gap = result["pairwise"][0]
    a, b = result["entrants"]
    assert (gap["a"], gap["b"]) == ("llm:a/one", "llm:b/two")
    assert gap["gap"] == pytest.approx(a["rate"] - b["rate"], abs=1e-4) and gap["gap"] > 0
    assert gap["ci95"][0] <= gap["gap"] <= gap["ci95"][1]


def test_the_bot_takes_the_test_with_no_api_calls(tmp_path):
    client = router(board_reader)
    result = run(tmp_path, entrants=("bot",), client=client, limit=3)
    assert result["entrants"][0]["puzzles"] == 3 and client.client.calls == []


def test_a_human_seat_is_refused(tmp_path):
    with pytest.raises(ValueError, match="human"):
        run(tmp_path, entrants=("human",))


def test_the_table_lists_every_player(tmp_path):
    lines = bonustest.table(run(tmp_path))
    assert any("llm:a/one" in line for line in lines) and any("llm:b/two" in line for line in lines)
