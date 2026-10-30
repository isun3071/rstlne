import json
from dataclasses import replace

import pytest
from fakes import completion, router

from rstlne import calibrate, trust
from rstlne.engine.puzzle import LETTERS
from rstlne.players.bot import versions
from rstlne.players.bot.reader import WordListReader
from rstlne.players.hybrid import SYSTEM, ask_text
from rstlne.selfplay import view_of

KNOBS = replace(versions.knobs(1), samples=200)
PUZZLES = {"WHEEL OF FORTUNE": "Phrase", "BANANA SPLIT": "Food & Drink", "GOLDEN GATE": "Landmark", "BIG CITY": "Place"}
WORDS = {w: 50 for answer in PUZZLES for w in answer.split()} | {"WHOOL": 40, "GOLDEN": 30, "BANDANA": 5}
FILL = "ETAONRISHLDCUMWFGYPBVKJXQZ"


def action(seat, answer, used, kind="spin", outcome="landed", number=1, phase="turn", guess=None):
    state = {"phase": phase, "round": {"number": number, "puzzle": {"category": PUZZLES[answer], "answer": answer},
                                       "used": sorted(used)}}
    act = {"kind": kind} | ({"answer": guess} if guess else {})
    return {"type": "action", "seat": seat, "state": state, "action": act, "result": {"outcome": outcome}}


def write_game(folder, name, set_index, answer, wrong=None):
    """A logged round: letters called in frequency order, one turn each, solved once the board is full.
    With `wrong`, seat 2 solves that answer wrongly halfway through."""
    rows = [{"type": "game", "seats": [{"kind": "llm", "model": f"m/{i}"} for i in range(3)], "tournament": {"set": set_index}}]
    used = []
    letters = [c for c in FILL if c in answer]
    for k, c in enumerate(letters):
        rows.append(action(k % 3, answer, used))
        if wrong and k == len(letters) // 2:
            rows.append(action(2, answer, used, kind="solve", outcome="wrong_solve", guess=wrong))
        used.append(c)
    rows.append(action(0, answer, used, kind="solve", outcome="solved", guess=answer))
    rows.append({"type": "summary"})
    (folder / f"{name}.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")


@pytest.fixture
def logs(tmp_path):
    folder = tmp_path / "prior"
    folder.mkdir()
    for i, answer in enumerate(PUZZLES):
        write_game(folder, f"set00{i}-perm0", i, answer, wrong="WHOOL OF FORTUNE" if answer == "WHEEL OF FORTUNE" else None)
    (folder / "set009-perm0.jsonl").write_text(json.dumps({"type": "game", "seats": []}) + "\n")  # unfinished
    return folder


# Boards from logs


def test_boards_come_from_turns_with_the_answers_refuted_so_far(logs):
    turns = trust.collect([logs])
    assert {t.answer for t in turns} == set(PUZZLES)  # the unfinished game is skipped
    wheel = [t for t in turns if t.answer == "WHEEL OF FORTUNE"]
    assert wheel[0].refuted == () and wheel[-1].refuted == ("WHOOL OF FORTUNE",)
    assert [t.solved for t in wheel].count(1) == 1 and wheel[-1].shown == 1.0
    assert all(0 <= t.shown <= 1 for t in turns)


def test_sampling_takes_an_equal_share_of_each_tenth_with_a_seed(logs):
    turns = trust.collect([logs])
    sample = trust.sample(turns, 20, seed=3)
    assert sample == trust.sample(turns, 20, seed=3)
    tenths = [min(int(t.shown * 10), 9) for t in sample]
    for tenth in set(tenths):
        available = sum(1 for t in turns if min(int(t.shown * 10), 9) == tenth)
        assert tenths.count(tenth) == min(2, available)


# The measurement


def fake_model(request):
    """Right once half the board shows, wrong but fitting from a quarter, and unsure before that."""
    text = next(m["content"] for m in request["messages"] if m["role"] == "user")
    pattern = text.split("Pattern: ")[1].split(" (word lengths")[0]
    answer = next(a for a in PUZZLES if len(a) == len(pattern) and all(p in ("_", c) for p, c in zip(pattern, a)))
    squares = [c for c in pattern if c in LETTERS or c == "_"]
    shown = sum(c != "_" for c in squares) / len(squares)
    if shown >= 0.5:
        return completion(("read_board", {"solvable": True, "answer": answer}))
    if shown >= 0.25:  # a wrong guess that still fits: every hidden square a Z
        return completion(("read_board", {"solvable": True, "answer": pattern.replace("_", "Z")}))
    return completion(("read_board", {"solvable": False}))


def measure(logs, tmp_path, **options):
    client = router(fake_model)
    result = trust.measure(["model/a"], [logs], client=client, reader=WordListReader(WORDS, KNOBS), knobs=KNOBS,
                           count=400, seed=1, out_dir=tmp_path / "out", resamples=20, write=lambda line: None, **options)
    return result, client.client.calls


def test_each_board_gets_the_exact_hybrid_ask(logs, tmp_path):
    result, calls = measure(logs, tmp_path)
    first = calls[0]["messages"]
    assert first[0]["content"] == SYSTEM
    points = result["models"]["model/a"]["points"]
    asked = {(p["answer"], p["used"], tuple(p["refuted"])) for p in points}
    assert len(calls) == len(asked)  # one ask per distinct board
    p = next(p for p in points if p["refuted"])
    view = view_of(trust.Puzzle(PUZZLES[p["answer"]], p["answer"]), frozenset(p["used"]), *trust.rules_and_spec())
    assert any(c["messages"][1]["content"] == ask_text(view, frozenset(p["refuted"])) for c in calls)


def test_each_point_records_what_the_report_needs(logs, tmp_path):
    result, _ = measure(logs, tmp_path)
    point = result["models"]["model/a"]["points"][0]
    for key in ("shown", "solvable", "answer_given", "fits", "right", "reader_best", "reader_confidence", "agree",
                "p_reader", "solved", "prompt_tokens", "completion_tokens", "cost", "seconds", "status"):
        assert key in point


def test_the_fits_and_config_lines(logs, tmp_path):
    result, _ = measure(logs, tmp_path)
    model = result["models"]["model/a"]
    assert len(model["trust"]["coefficients"]) == 5 and len(model["steal"]["coefficients"]) == 4
    assert result["config_lines"]["trust"] == [f'"model/a" = {model["trust"]["config"]}']
    assert result["config_lines"]["steal"] == [f'"model/a" = {model["steal"]["config"]}']
    assert "ci95" in model["trust"] and "readable_effect" in model["steal"]


def test_the_report_counts_yes_rates_disagreements_misfits_and_cost(logs, tmp_path):
    result, _ = measure(logs, tmp_path)
    report = result["models"]["model/a"]["report"]
    tenths = report["by_tenth"]
    assert tenths[0]["said_solvable"] == 0 and tenths[-1]["said_solvable"] == 1
    assert {"boards", "model_right", "reader_right"} <= set(report["disagreements"])
    assert {"by_tenth", "confident_reader"} <= set(report["agreeing_and_wrong"])
    assert report["misfit_share"] == 0
    assert report["cost_per_ask"] > 0 and report["cost_per_game"] == pytest.approx(report["cost_per_ask"] * trust.ASKS_PER_GAME)


def test_results_are_saved_with_every_point(logs, tmp_path):
    result, _ = measure(logs, tmp_path)
    (saved,) = (tmp_path / "out").glob("trust-*.json")
    assert json.loads(saved.read_text()) == result


def test_a_held_out_check_scores_the_fitted_curve_without_refitting(logs, tmp_path):
    result, calls = measure(logs, tmp_path, held_out=[logs])
    check = result["models"]["model/a"]["held_out"]
    assert check["boards"] > 0 and check["bands"]
    assert all({"asks", "predicted", "right"} <= set(band) for band in check["bands"])
    assert result["models"]["model/a"]["trust"]["coefficients"] == measure(logs, tmp_path)[0]["models"]["model/a"]["trust"]["coefficients"]


def test_the_calibrate_command_routes_trust(monkeypatch, logs):
    seen = {}
    monkeypatch.setattr(trust, "measure", lambda models, folders, **kw: seen.update(models=models, folders=folders, **kw) or {})
    calibrate.main(["trust", "--models", "a/one, b/two", "--logs", str(logs), "--count", "50", "--seed", "4"])
    assert seen["models"] == ["a/one", "b/two"] and seen["count"] == 50 and seen["seed"] == 4
    assert [str(f) for f in seen["folders"]] == [str(logs)]


def test_long_steps_print_status_lines(logs, tmp_path):
    lines = []
    trust.measure(["model/a"], [logs], client=router(fake_model), reader=WordListReader(WORDS, KNOBS), knobs=KNOBS,
                  count=40, seed=1, out_dir=tmp_path, resamples=0, write=lines.append, heartbeat=0)
    reading = [line for line in lines if line.startswith("  read ")]
    asking = [line for line in lines if line.startswith("  model/a: ")]
    assert reading and "of" in reading[-1] and "finish in about" in reading[0]
    assert asking and "$" in asking[-1] and "asks" in asking[-1]
    assert any(line.startswith("Asking model/a") for line in lines)


def test_a_rerun_reuses_every_saved_ask(logs, tmp_path):
    first, calls = measure(logs, tmp_path)
    again, more = measure(logs, tmp_path)
    assert calls and more == []  # every ask came from disk
    assert again["models"]["model/a"]["points"] == first["models"]["model/a"]["points"]


def test_a_stopped_run_asks_only_what_is_missing(logs, tmp_path):
    _, calls = measure(logs, tmp_path)
    saved = next((tmp_path / "out" / "trust-asks").glob("*.jsonl"))
    lines = saved.read_text().splitlines()
    saved.write_text("\n".join(lines[:5]) + "\n")  # as if stopped after 5 asks
    _, more = measure(logs, tmp_path)
    assert len(more) == len(calls) - 5


def test_saved_asks_are_kept_apart_by_how_the_model_was_run(logs, tmp_path, monkeypatch):
    measure(logs, tmp_path)
    config = trust.settings.load_config()
    monkeypatch.setattr(trust.settings, "load_config", lambda: {**config, "llm": {**config["llm"], "reasoning_effort": "low"}})
    _, more = measure(logs, tmp_path)
    assert more  # another effort level is another measurement


def test_a_board_that_gets_no_reply_is_skipped_and_asked_again_next_run(logs, tmp_path):
    import httpx2
    import openai

    def flaky(request):
        text = next(m["content"] for m in request["messages"] if m["role"] == "user")
        if "Category: Place" in text:  # every BIG CITY board times out
            return openai.APITimeoutError(request=httpx2.Request("POST", "https://openrouter.ai/api/v1/chat/completions"))
        return fake_model(request)

    lines = []
    result = trust.measure(["model/a"], [logs], client=router(flaky), reader=WordListReader(WORDS, KNOBS), knobs=KNOBS,
                           count=400, seed=1, out_dir=tmp_path / "out", resamples=0, write=lines.append, heartbeat=0)
    points = result["models"]["model/a"]["points"]
    assert points and not any(p["answer"] == "BIG CITY" for p in points)
    unanswered = result["models"]["model/a"]["report"]["unanswered"]
    assert unanswered > 0 and any("rerun" in line.lower() for line in lines)
    _, calls = measure(logs, tmp_path)
    assert calls and all("Category: Place" in c["messages"][1]["content"] for c in calls)  # only those boards again
