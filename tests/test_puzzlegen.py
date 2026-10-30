import json
import random

import pytest
from fakes import completion, router

from rstlne import puzzlegen
from rstlne.engine.puzzle import Puzzle

GEN, JUDGE = "mistralai/gen", "google/judge"
ROWS, BONUS_ROWS = (12, 14, 14, 12), (14, 14)


def fake(batches, verdicts=None):
    """A generator that hands out `batches` in turn, and a judge that says yes unless `verdicts` names the answer."""
    batches = iter(batches)
    verdicts = verdicts or {}

    def reply(request):
        if request["model"] == GEN:
            return completion(content=json.dumps({"answers": next(batches)}))
        answer = json.loads(request["messages"][-1]["content"].rsplit("\n", 1)[-1])["answer"]
        verdict = verdicts.get(answer, True)
        fits, common = (verdict, 5) if isinstance(verdict, bool) else (True, verdict)
        return completion(content=json.dumps({"fits": fits, "reason": "ok" if fits else "not that kind of thing",
                                              "common": common, "parts": []}))
    return router(reply)


def settings(**changes):
    base = dict(generator=GEN, judge=JUDGE, batch=3, rows=ROWS, bonus_rows=BONUS_ROWS, max_requests=10, main_min_letters=6,
                judges=1)
    return puzzlegen.Settings(**{**base, **changes})


# Checks in code


@pytest.mark.parametrize("answer, rows, fits", [
    ("A BLESSING IN DISGUISE", ROWS, True),
    ("SUPERCALIFRAGILISTIC", ROWS, False),  # 20 letters: no row holds it
    ("ONE TWO THREE FOUR FIVE SIX SEVEN EIGHT NINE TEN ELEVEN TWELVE", ROWS, False),
    ("HOT COCOA", BONUS_ROWS, True),
    ("A VERY LONG BONUS PUZZLE THAT RUNS ON", BONUS_ROWS, False),
])
def test_answers_must_fit_the_board_without_splitting_a_word(answer, rows, fits):
    assert puzzlegen.fits_rows(answer, rows) is fits


@pytest.mark.parametrize("category, answer, ok", [
    ("Same Letter", "FRESH FRUIT FROM FLORIDA", True),
    ("Same Letter", "FRESH APPLES FROM FLORIDA", False),
    ("Same Letter", "CRAZY CRAZY CRAZY", False),  # one word, said three times
    ("Rhyme Time", "WEAR AND TEAR", True),
    ("Rhyme Time", "WEAR AND SHIRT", False),
    ("Same Name", "BIRTHDAY & WEDDING CAKE", True),
    ("Same Name", "WEDDING CAKE", False),
    ("Same Name", "MELANIE & SULLIVAN", False),  # nothing after the & for the halves to share
    ("Before & After", "PIECE OF CAKE WALK", True),
    ("Before & After", "CAKE WALK", False),
    ("What Are You Doing?", "WALKING THE DOG", True),
    ("What Are You Doing?", "THE DOG WALK", False),
    ("Thing", "A ROUND TABLE", True),
])
def test_structural_categories_are_checked_in_code(category, answer, ok):
    rhymes = {"WEAR": {"EH1 R"}, "TEAR": {"EH1 R"}, "SHIRT": {"ER1 T"}}
    assert puzzlegen.structure_ok(category, answer, rhymes) is ok


def test_near_duplicates_ignore_articles_case_and_spacing():
    assert puzzlegen.near(puzzlegen.NearKey.of("A Blessing  in Disguise"), puzzlegen.NearKey.of("BLESSING IN DISGUISE"))
    assert not puzzlegen.near(puzzlegen.NearKey.of("THE BACK PORCH"), puzzlegen.NearKey.of("BACK DOOR"))


# Generation


def test_generated_puzzles_pass_every_check_and_are_never_reused(tmp_path):
    seen = tmp_path / "seen.txt"
    seen.write_text("BACK PORCH\n")
    known = [Puzzle("Phrase", "BETTER LATE THAN NEVER")]
    client = fake([
        ["Better late than never", "a back porch", "Rainy day fund", "rainy day fund", "SUPERCALIFRAGILISTICEXPIALIDOCIOUS"],
        ["Round table", "Spare tire", "Kitchen sink"],
    ], verdicts={"ROUND TABLE": False})
    result = puzzlegen.generate(client, settings(max_requests=2), [("Thing", 4)], [], seed=1, known=known, seen_path=seen)
    answers = [p.answer for p in result.puzzles]
    assert sorted(answers) == ["KITCHEN SINK", "RAINY DAY FUND", "SPARE TIRE"]  # three of the four asked for: the requests ran out
    assert result.rejected == {"already used": 2, "duplicate in this batch": 1, "doesn't fit the board": 1,
                               "judge: doesn't fit the category": 1}
    assert result.judged_out == [("Thing", "ROUND TABLE", "not that kind of thing")]
    assert seen.read_text().splitlines()[0] == "BACK PORCH"
    assert sorted(seen.read_text().splitlines()[1:]) == ["KITCHEN SINK", "RAINY DAY FUND", "SPARE TIRE"]


def test_bonus_puzzles_are_marked_and_held_to_the_bonus_rows(tmp_path):
    client = fake([["Jumbo shrimp", "A very long bonus puzzle that runs on"]])
    result = puzzlegen.generate(client, settings(max_requests=1), [], [("Food & Drink", 1)], seed=2, known=[],
                                seen_path=tmp_path / "seen.txt")
    assert result.puzzles == [Puzzle("Food & Drink", "JUMBO SHRIMP", bonus=True)]


def test_a_bonus_puzzle_keeps_half_its_letters_hidden_after_the_usual_picks(tmp_path):
    # After R S T L N E and C D M A: LEATHER WALLET shows 85%, FUZZY SOCKS 30%; QUICK FIX has only 8 letters
    client = fake([["Leather wallet", "Fuzzy socks", "Quick fix"]])
    result = puzzlegen.generate(client, settings(max_requests=1), [], [("Thing", 3)], seed=2, known=[],
                                seen_path=tmp_path / "seen.txt")
    assert result.puzzles == [Puzzle("Thing", "FUZZY SOCKS", bonus=True)]
    assert result.rejected["too easy for a bonus puzzle"] == 1 and result.rejected["too short for a bonus puzzle"] == 1


def test_the_bonus_hidden_share_counts_letter_squares_only():
    s = settings()
    assert puzzlegen.hidden_after_picks("FUZZY SOCKS", s) == pytest.approx(0.7)
    assert puzzlegen.hidden_after_picks("FOOL'S GOLD", s) == pytest.approx(5 / 9)
    assert puzzlegen.hidden_after_picks("BOX OF CHOCOLATES", settings(bonus_picks="")) == pytest.approx(11 / 15)


def test_only_bonus_requests_ask_for_long_answers_in_uncommon_letters(tmp_path):
    client = fake([["Spare tire", "Kitchen sink", "Garden hose"], ["Fuzzy socks", "Jumbo shrimp", "Kiwi smoothie"]])
    puzzlegen.generate(client, settings(max_requests=2), [("Thing", 3)], [("Thing", 3)], seed=3, known=[],
                       seen_path=tmp_path / "seen.txt")
    main, bonus = [c["messages"][-1]["content"] for c in client.client.calls if c["model"] == GEN]
    assert "less common letters" not in main
    assert "less common letters" in bonus and "R, S, T, L, N, and E" in bonus
    assert "at least 10 letters" in bonus and "14 letters" not in bonus


def test_settings_read_the_bonus_difficulty_and_letters_from_config():
    config = {"bonus_letters": ["R", "S", "T", "L", "N", "E"],
              "puzzlegen": {"generator": GEN, "judge": JUDGE, "rows": [12, 14, 14, 12], "bonus_rows": [14, 14],
                            "bonus_min_letters": 7, "bonus_picks": "CDMA", "bonus_min_hidden": 0.55}}
    s = puzzlegen.Settings.from_config(config)
    assert (s.bonus_letters, s.bonus_picks, s.bonus_min_hidden, s.bonus_min_letters) == ("RSTLNE", "CDMA", 0.55, 7)


DICTIONARY = frozenset({"WAIKIKI", "BEACH", "JUMBO", "SHRIMP", "DON'T", "STOP", "ROCK", "ROLL"})


def test_unknown_words_are_the_ones_no_dictionary_or_name_list_holds():
    assert puzzlegen.unknown_words("WAKIKI BEACH", DICTIONARY) == ["WAKIKI"]
    assert puzzlegen.unknown_words("JUMBO SHRIMP", DICTIONARY) == []
    assert puzzlegen.unknown_words("DON'T STOP", DICTIONARY) == []
    assert puzzlegen.unknown_words("ROCK-AND-ROLL", DICTIONARY) == ["AND"]


def test_a_misspelled_answer_is_rejected_when_the_word_data_is_there(tmp_path):
    client = fake([["Wakiki beach", "Jumbo shrimp"]])
    result = puzzlegen.generate(client, settings(max_requests=1), [], [("Place", 2)], seed=2, known=[],
                                seen_path=tmp_path / "seen.txt", dictionary=DICTIONARY)
    assert [p.answer for p in result.puzzles] == ["JUMBO SHRIMP"]
    assert result.rejected["a word no dictionary or name list holds"] == 1


def test_without_word_data_the_spelling_check_is_off(tmp_path):
    assert puzzlegen.load_dictionary() is None  # tests never read data/
    client = fake([["Wakiki beach"]])
    result = puzzlegen.generate(client, settings(max_requests=1), [], [("Place", 1)], seed=2, known=[],
                                seen_path=tmp_path / "seen.txt")
    assert [p.answer for p in result.puzzles] == ["WAKIKI BEACH"]


def test_recheck_drops_misspelled_answers(tmp_path):
    path = tmp_path / "batch.json"
    puzzlegen.save_pool(path, [Puzzle("Place", "WAKIKI BEACH", bonus=True), Puzzle("Place", "WAIKIKI BEACH", bonus=True)],
                        settings(bonus_min_hidden=0.0), seed=1, rejected={}, cost=0.0)
    dropped = puzzlegen.recheck(fake([]), settings(bonus_min_hidden=0.0), path, against=[], known=[], dictionary=DICTIONARY)
    assert dropped == ["WAKIKI BEACH"]


def test_every_request_stands_alone_and_never_names_the_show(tmp_path):
    client = fake([["Spare tire", "Kitchen sink", "Garden hose"]])
    puzzlegen.generate(client, settings(), [("Thing", 3)], [], seed=3, known=[], seen_path=tmp_path / "seen.txt")
    for call in client.client.calls:
        text = json.dumps(call["messages"]).upper()
        assert "WHEEL OF FORTUNE" not in text and "WHEEL" not in text
        assert len(call["messages"]) == 2  # a system prompt and one request, nothing carried over
        assert call["response_format"]["type"] == "json_schema"
    judged = [c for c in client.client.calls if c["model"] == JUDGE]
    assert len(judged) == 3


def test_requests_carry_seeded_inspiration_words(tmp_path):
    prompts = []
    for _ in range(2):
        client = fake([["Spare tire", "Kitchen sink", "Garden hose"]])
        puzzlegen.generate(client, settings(), [("Thing", 3)], [], seed=9, known=[], seen_path=tmp_path / f"s{_}.txt")
        prompts.append(next(c for c in client.client.calls if c["model"] == GEN)["messages"][-1]["content"])
    assert prompts[0] == prompts[1] and "may suggest topics, but never force them in" in prompts[0]
    topics = prompts[0].split("never force them in: ")[1].split(".")[0].split(", ")
    assert set(topics) <= {t.upper() for t in puzzlegen.TOPICS}  # everyday topics, never random rare words


def test_replies_parse_through_code_fences_and_stray_text():
    assert puzzlegen.parse_answers('Sure!\n```json\n{"answers": ["Spare tire"]}\n```') == ["Spare tire"]
    assert puzzlegen.parse_answers("not json at all") == []


def test_the_category_mix_splits_a_count_by_weight():
    mix = puzzlegen.split(10, {"Phrase": 3, "Thing": 1, "Place": 1}, random.Random(0))
    assert sum(n for _, n in mix) == 10 and dict(mix)["Phrase"] >= 5


def test_a_pool_file_records_how_it_was_made(tmp_path):
    path = tmp_path / "puzzles.json"
    pool = [Puzzle("Thing", "SPARE TIRE"), Puzzle("Food & Drink", "HOT COCOA", bonus=True)]
    puzzlegen.save_pool(path, pool, settings(), seed=4, rejected={"already used": 1}, cost=0.002)
    data = json.loads(path.read_text())
    assert data["generator"] == GEN and data["judge"] == JUDGE and data["seed"] == 4
    assert puzzlegen.load_pool(path) == pool


# Tournaments with generated puzzles


from fakes import board_reader  # noqa: E402

from rstlne import settings as project  # noqa: E402
from rstlne.tournament import run_tournament  # noqa: E402

CONFIG = project.load_config()["puzzlegen"]


def table_client(fresh):
    """Plays games like board_reader, writes puzzles from `fresh`, and approves every one."""
    def reply(request):
        if request["model"] == CONFIG["generator"]:
            text = request["messages"][-1]["content"]
            category = text.split("\n")[0].removeprefix("Category: ")
            words = {"Same Letter": ["BIG BLUE BUBBLES"], "Rhyme Time": ["FAT CAT NAP"], "Same Name": ["APPLE & PUMPKIN PIE"],
                     "Before & After": ["PIECE OF CAKE WALK"], "What Are You Doing?": ["WALKING THE DOG"]}
            special = words.get(category, [])
            return completion(content=json.dumps({"answers": [next(fresh) for _ in range(3)] + special}))
        if request["model"] == CONFIG["judge"]:
            answer = json.loads(request["messages"][-1]["content"].rsplit("\n", 1)[-1])["answer"]
            parts = {"PIECE OF CAKE WALK": ["PIECE OF CAKE", "CAKE WALK"],
                     "APPLE & PUMPKIN PIE": ["APPLE PIE", "PUMPKIN PIE"]}.get(answer, [])
            return completion(content=json.dumps({"fits": True, "reason": "fine", "common": 5, "parts": parts}))
        return board_reader(request)
    return router(reply)


@pytest.fixture
def seen(tmp_path, monkeypatch):
    path = tmp_path / "seen.txt"
    monkeypatch.setattr(puzzlegen, "SEEN", path)
    return path


def test_a_tournament_on_a_saved_batch_records_who_made_it(tmp_path, seen):
    answers = ["CRIMSON BARN", "COBALT DOOR", "GOLDEN KITE", "SCARLET LAMP"]
    batch = tmp_path / "grading-1.json"
    batch.write_text(json.dumps({"generator": "maker/gen", "judge": "maker/judge", "puzzles": [
        *({"category": "Thing", "answer": a, "bonus": False} for a in answers),
        {"category": "Thing", "answer": "SILVER MUG", "bonus": True}]}))
    out = tmp_path / "t"
    result = run_tournament(["llm:a/one", "llm:b/two", "llm:c/three"], sets=1, seed=5, puzzles_path=batch,
                            out_dir=out, parallel=3, client=table_client(iter(())), write=lambda line: None, heartbeat=600)
    header = json.loads(next(out.glob("set000-perm0.jsonl")).read_text().splitlines()[0])
    assert header["tournament"]["generated_by"] == {"generator": "maker/gen", "judge": "maker/judge"}
    assert not result["dev_run"] and result["generated_by"]["judge"] == "maker/judge"


def test_a_tournament_generates_its_puzzles_once_and_records_how(tmp_path, seen):
    fresh = iter(f"{a} {b}" for a in ("CRIMSON", "COBALT", "GOLDEN", "SCARLET", "SILVER", "VIOLET", "AMBER", "COPPER", "MAROON", "INDIGO")
                 for b in ("BARN", "DOOR", "KITE", "LAMP", "MUG", "SOCK", "VASE", "YARN", "BELL", "COAT"))
    out = tmp_path / "t"
    client = table_client(fresh)
    lines = []
    result = run_tournament(["llm:a/one", "llm:b/two", "llm:c/three"], sets=1, seed=5, puzzles_path="generate",
                            out_dir=out, parallel=3, client=client, write=lines.append, heartbeat=600)
    pool = json.loads((out / "puzzles.json").read_text())
    assert pool["generator"] == CONFIG["generator"] and pool["judge"] == CONFIG["judge"]
    assert len([p for p in pool["puzzles"] if not p["bonus"]]) == 4 and len([p for p in pool["puzzles"] if p["bonus"]]) == 1
    header = json.loads(next(out.glob("set000-perm0.jsonl")).read_text().splitlines()[0])
    assert header["tournament"]["generated_by"] == {"generator": CONFIG["generator"], "judge": CONFIG["judge"]}
    assert not result["dev_run"] and result["generated_by"]["generator"] == CONFIG["generator"]
    assert any("Generating 4 main and 1 bonus" in line for line in lines)
    assert len(seen.read_text().splitlines()) == 5
    calls = len(client.client.calls)
    run_tournament(["llm:a/one", "llm:b/two", "llm:c/three"], sets=1, seed=5, puzzles_path="generate",
                   out_dir=out, parallel=3, client=client, write=lines.append, heartbeat=600)
    assert len(client.client.calls) == calls  # a rerun reuses the pool and the finished games


def test_a_short_pool_stops_before_any_game_and_tops_up_on_rerun(tmp_path, seen, monkeypatch):
    out = tmp_path / "t"
    stingy = iter(["CRIMSON BARN", "COBALT DOOR"])
    def reply(request):
        if request["model"] == CONFIG["generator"]:
            return completion(content=json.dumps({"answers": [next(stingy, "CRIMSON BARN")]}))
        return completion(content=json.dumps({"fits": True, "reason": "fine", "common": 5, "parts": []}))
    with pytest.raises(ValueError, match="2 of 4 main and 0 of 1 bonus"):
        run_tournament(["llm:a/one", "llm:b/two", "llm:c/three"], sets=1, seed=5, puzzles_path="generate",
                       out_dir=out, parallel=3, client=router(reply), write=lambda line: None, heartbeat=600,
                       generation_requests=4)
    assert not list(out.glob("set*.jsonl"))
    assert len(puzzlegen.load_pool(out / "puzzles.json")) == 2  # kept, so the rerun only tops up


@pytest.mark.parametrize("category, answer, parts, ok", [
    ("Before & After", "PIECE OF CAKE WALK", ["PIECE OF CAKE", "CAKE WALK"], True),
    ("Before & After", "JACK THE LADDER UP", ["JACK THE", "LADDER UP"], False),  # no shared word
    ("Before & After", "PIECE OF CAKE WALK", ["PIECE OF PIE", "PIE WALK"], False),  # doesn't rebuild the answer
    ("Same Name", "BIRTHDAY & WEDDING CAKE", ["BIRTHDAY CAKE", "WEDDING CAKE"], True),
    ("Same Name", "BIRTHDAY & WEDDING CAKE", ["BIRTHDAY PARTY", "WEDDING CAKE"], False),
    ("Thing", "COFFEE MUG", [], True),
])
def test_the_judge_names_the_two_phrases_and_code_checks_they_join(category, answer, parts, ok):
    assert puzzlegen.parts_ok(category, answer, parts) is ok


def test_answers_in_a_batch_are_tried_in_a_seeded_shuffle(tmp_path):
    picked = []
    for seed in (1, 2, 3, 4):
        client = fake([[f"ITEM {c}" for c in "ABCDEFGHIJ"]])
        result = puzzlegen.generate(client, settings(batch=10, max_requests=1, main_min_letters=0), [("Thing", 1)], [], seed=seed, known=[],
                                    seen_path=tmp_path / f"s{seed}.txt")
        picked.append(result.puzzles[0].answer)
    assert len(set(picked)) > 1  # not always the first, most typical answer


def test_the_judge_rates_how_familiar_an_answer_is_and_the_bar_is_four(tmp_path):
    client = fake([["Dreamy salad", "Garden salad"]], verdicts={"DREAMY SALAD": 2})
    result = puzzlegen.generate(client, settings(max_requests=1), [("Food & Drink", 2)], [], seed=1, known=[],
                                seen_path=tmp_path / "seen.txt")
    assert [p.answer for p in result.puzzles] == ["GARDEN SALAD"]
    assert result.judged_out[0][:2] == ("Food & Drink", "DREAMY SALAD") and "familiarity 2" in result.judged_out[0][2]


def test_main_puzzles_need_enough_letters(tmp_path):
    client = fake([["Pig", "Golden retriever"]])
    result = puzzlegen.generate(client, settings(max_requests=1, main_min_letters=8), [("Living Thing", 2)], [], seed=1,
                                known=[], seen_path=tmp_path / "seen.txt")
    assert [p.answer for p in result.puzzles] == ["GOLDEN RETRIEVER"] and result.rejected["too short for a main puzzle"] == 1


def test_a_generated_batch_file_loads_like_any_puzzle_file(tmp_path):
    path = tmp_path / "batch.json"
    pool = [Puzzle("Thing", "SPARE TIRE"), Puzzle("Food & Drink", "HOT COCOA", bonus=True)]
    puzzlegen.save_pool(path, pool, settings(), seed=4, rejected={}, cost=0.0)
    assert project.load_puzzles(path) == pool


def test_long_runs_print_a_status_line_every_so_often(tmp_path):
    now = [0.0]

    def clock():
        now[0] += 50  # every call to the clock is 50 seconds later
        return now[0]

    lines = []
    client = fake([["Spare tire", "Kitchen sink", "Garden hose"], ["Paper towel", "Coffee mug", "Light bulb"]])
    puzzlegen.generate(client, settings(max_requests=2), [("Thing", 6)], [], seed=1, known=[],
                       seen_path=tmp_path / "seen.txt", say=lines.append, heartbeat=120, clock=clock)
    status = [line for line in lines if "requests" in line and "overall" in line]
    assert status and all(" of 6" in line and "$" in line for line in status)
    assert lines[-1].strip().startswith("Thing: 6 of 6")


# Failures mid-run


import openai  # noqa: E402
import httpx2  # noqa: E402


def timeout():
    return openai.APITimeoutError(request=httpx2.Request("POST", "https://openrouter.ai/api/v1/chat/completions"))


def flaky(replies):
    """Hands out `replies` in turn: a list of answers is a generator reply, None a stall, True a yes from the judge."""
    replies = iter(replies)

    def reply(request):
        if request["model"] == JUDGE:
            return completion(content=json.dumps({"fits": True, "reason": "ok", "common": 5, "parts": []}))
        r = next(replies)
        if r is None:
            raise timeout()
        return completion(content=json.dumps({"answers": r}))
    return router(reply, retries=0)


def test_a_failed_request_is_skipped_and_the_run_goes_on(tmp_path):
    client = flaky([None, ["Spare tire", "Kitchen sink"]])
    result = puzzlegen.generate(client, settings(max_requests=5), [("Thing", 2)], [], seed=1, known=[],
                                seen_path=tmp_path / "seen.txt")
    assert sorted(p.answer for p in result.puzzles) == ["KITCHEN SINK", "SPARE TIRE"]
    assert result.rejected["generator request failed"] == 1


def test_too_many_failures_in_a_row_stop_the_run_with_what_it_has(tmp_path):
    client = flaky([["Spare tire"], None, None, None, None, None, ["Kitchen sink"]])
    lines = []
    result = puzzlegen.generate(client, settings(max_requests=20), [("Thing", 3)], [], seed=1, known=[],
                                seen_path=tmp_path / "seen.txt", say=lines.append)
    assert [p.answer for p in result.puzzles] == ["SPARE TIRE"] and result.stopped
    assert any("5 requests in a row failed" in line for line in lines)


def test_every_accepted_puzzle_reaches_the_file_at_once(tmp_path):
    saved = []
    client = flaky([["Spare tire", "Kitchen sink"]])
    puzzlegen.generate(client, settings(max_requests=1), [("Thing", 2)], [], seed=1, known=[],
                       seen_path=tmp_path / "seen.txt", on_accept=lambda puzzles: saved.append(len(puzzles)))
    assert saved == [1, 2]


def test_rerunning_the_command_tops_the_file_up(tmp_path, monkeypatch):
    out = tmp_path / "batch.json"
    monkeypatch.setattr(puzzlegen, "SEEN", tmp_path / "seen.txt")
    first = [Puzzle("Thing", "SPARE TIRE"), Puzzle("Food & Drink", "HOT COCOA", bonus=True)]
    puzzlegen.save_pool(out, first, settings(), seed=7, rejected={}, cost=0.0)
    calls = []

    def fake_generate(client, s, main, bonus, seed, known, **options):
        calls.append((main, bonus, [p.answer for p in known]))
        return puzzlegen.Result(puzzles=[Puzzle("Thing", "KITCHEN SINK")])
    monkeypatch.setattr(puzzlegen, "generate", fake_generate)
    monkeypatch.setattr(puzzlegen, "_client", lambda: None)
    puzzlegen.main(["--main", "2", "--bonus", "1", "--seed", "7", "--out", str(out)])
    (main, bonus, known), = calls
    assert sum(n for _, n in main) == 1 and bonus == [] and "SPARE TIRE" in known
    assert [p.answer for p in puzzlegen.load_pool(out)] == ["SPARE TIRE", "HOT COCOA", "KITCHEN SINK"]


# Request size, hosts, and parallel judging


import threading  # noqa: E402


def test_each_request_asks_for_one_batch_with_fresh_topics(tmp_path):
    client = fake([["Spare tire", "Kitchen sink", "Garden hose"], ["Paper towel", "Coffee mug", "Light bulb"]])
    puzzlegen.generate(client, settings(batch=3, max_requests=2), [("Thing", 6)], [], seed=1, known=[],
                       seen_path=tmp_path / "seen.txt")
    asks = [c["messages"][-1]["content"] for c in client.client.calls if c["model"] == GEN]
    assert len(asks) == 2 and all("Write 3 different answers" in a for a in asks)
    topics = [a.split("never force them in: ")[1] for a in asks]
    assert topics[0] != topics[1]


def test_requests_go_to_the_pinned_host(tmp_path):
    client = fake([["Spare tire"]])
    pins = {GEN: "deepinfra/fp8", JUDGE: "deepinfra/fp8"}
    puzzlegen.generate(client, settings(max_requests=1, providers=pins), [("Thing", 1)], [], seed=1, known=[],
                       seen_path=tmp_path / "seen.txt")
    for call in client.client.calls:
        assert call["extra_body"]["provider"] == {"order": ["deepinfra/fp8"], "allow_fallbacks": False}


def test_judges_work_in_parallel(tmp_path):
    together = threading.Barrier(2, timeout=5)  # two judge calls must be in flight at once, or this breaks

    def reply(request):
        if request["model"] == GEN:
            return completion(content=json.dumps({"answers": ["Spare tire", "Kitchen sink"]}))
        together.wait()
        return completion(content=json.dumps({"fits": True, "reason": "ok", "common": 5, "parts": []}))
    result = puzzlegen.generate(router(reply), settings(max_requests=1, judges=2), [("Thing", 2)], [], seed=1,
                                known=[], seen_path=tmp_path / "seen.txt")
    assert sorted(p.answer for p in result.puzzles) == ["KITCHEN SINK", "SPARE TIRE"]


# Near repeats, contractions, and rechecking


@pytest.mark.parametrize("a, b, near", [
    ("IT'S RAINING CATS AND DOGS", "ITS RAINING CATS AND DOGS", True),  # punctuation
    ("BIG BROWN BEAR", "BIG BROWN BEARS", True),  # a plural
    ("COFFEE & TEA BREAK", "TEA & COFFEE BREAK", True),  # the same words reordered
    ("LET SLEEPING DOGS LIE", "LET SLEEPING DOGS", True),  # a truncation
    ("BIRDS OF A FEATHER FLOCK TOGETHER", "BIRDS OF A FEATHER", True),
    ("THE GOLDEN GATE BRIDGE", "GOLDEN GATE", True),
    ("SEA LIONS SUNBATHING ON THE ROCKS", "ON THE ROCKS", False),  # under half the longer one's words
    ("APPLE PIE CHART", "CHART TOPPER", False),
])
def test_near_repeats(a, b, near):
    assert puzzlegen.near(puzzlegen.NearKey.of(a), puzzlegen.NearKey.of(b)) is near
    assert puzzlegen.near(puzzlegen.NearKey.of(b), puzzlegen.NearKey.of(a)) is near


def test_contractions_need_their_apostrophe():
    assert puzzlegen.missing_apostrophe("DONT JUDGE A BOOK") and puzzlegen.missing_apostrophe("ITS NOT ROCKET SCIENCE")
    assert not puzzlegen.missing_apostrophe("DON'T JUDGE A BOOK") and not puzzlegen.missing_apostrophe("ITS OWN REWARD")


def test_generation_rejects_near_repeats_of_anything_seen(tmp_path):
    seen = tmp_path / "seen.txt"
    seen.write_text("LET SLEEPING DOGS LIE\n")
    client = fake([["Let sleeping dogs", "Dont count your chickens", "A penny saved"]])
    result = puzzlegen.generate(client, settings(max_requests=1), [("Phrase", 3)], [], seed=1, known=[], seen_path=seen)
    assert [p.answer for p in result.puzzles] == ["A PENNY SAVED"]
    assert result.rejected["already used"] == 1 and result.rejected["contraction without its apostrophe"] == 1


def test_rhyme_time_needs_the_top_familiarity(tmp_path):
    client = fake([["Eat and meat", "Wear and tear"]], verdicts={"EAT AND MEAT": 4})
    rhymes = {"EAT": {"IY1 T"}, "MEAT": {"IY1 T"}, "WEAR": {"EH1 R"}, "TEAR": {"EH1 R"}}
    result = puzzlegen.generate(client, settings(max_requests=1), [("Rhyme Time", 2)], [], seed=1, known=[],
                                seen_path=tmp_path / "seen.txt", rhymes=rhymes)
    assert [p.answer for p in result.puzzles] == ["WEAR AND TEAR"]


def test_recheck_drops_what_fails_the_new_checks_and_keeps_grading_apart(tmp_path):
    tuning, grading = tmp_path / "tuning.json", tmp_path / "grading.json"
    puzzlegen.save_pool(tuning, [Puzzle("Phrase", "BIRDS OF A FEATHER FLOCK TOGETHER"), Puzzle("Thing", "BIG BROWN BEAR"),
                                 Puzzle("Thing", "BIG BROWN BEARS"), Puzzle("Phrase", "DONT JUDGE A BOOK"),
                                 Puzzle("Rhyme Time", "EAT AND MEAT"), Puzzle("Rhyme Time", "WEAR AND TEAR")],
                        settings(), seed=1, rejected={}, cost=0.0)
    puzzlegen.save_pool(grading, [Puzzle("Phrase", "BIRDS OF A FEATHER"), Puzzle("Thing", "PAPER TOWEL")],
                        settings(), seed=2, rejected={}, cost=0.0)
    client = fake([], verdicts={"EAT AND MEAT": 4})
    dropped = puzzlegen.recheck(client, settings(), tuning, against=[], known=[Puzzle("Phrase", "BIG BROWN BEAR")])
    assert sorted(dropped) == ["BIG BROWN BEAR", "BIG BROWN BEARS", "DONT JUDGE A BOOK", "EAT AND MEAT"]
    assert [p.answer for p in puzzlegen.load_pool(tuning)] == ["BIRDS OF A FEATHER FLOCK TOGETHER", "WEAR AND TEAR"]
    dropped = puzzlegen.recheck(client, settings(), grading, against=[tuning], known=[])
    assert dropped == ["BIRDS OF A FEATHER"]


def test_recheck_drops_bonus_puzzles_that_are_too_easy_or_too_short(tmp_path):
    path = tmp_path / "batch.json"
    puzzlegen.save_pool(path, [Puzzle("Thing", "LEATHER WALLET", bonus=True), Puzzle("Thing", "FUZZY SOCKS", bonus=True),
                               Puzzle("Thing", "JUG", bonus=True), Puzzle("Thing", "LEATHER WALLET STRAP")],
                        settings(), seed=1, rejected={}, cost=0.0)
    dropped = puzzlegen.recheck(fake([]), settings(), path, against=[], known=[])
    assert sorted(dropped) == ["JUG", "LEATHER WALLET"]  # a main puzzle isn't held to the bonus rule
    assert puzzlegen.PROMPT_VERSION == 5


def test_rejudging_sends_every_puzzle_back_to_the_judge(tmp_path):
    path = tmp_path / "batch.json"
    puzzles = [Puzzle("Phrase", "BUMP IN ROAD"), Puzzle("Phrase", "SPILL THE BEANS"), Puzzle("Thing", "GOAL POST NET"),
               Puzzle("Thing", "WATERING CAN")]
    puzzlegen.save_pool(path, puzzles, settings(judge="google/old-judge"), seed=1, rejected={}, cost=0.0)
    client = fake([], verdicts={"BUMP IN ROAD": False, "GOAL POST NET": 3})
    assert puzzlegen.recheck(client, settings(), path, against=[], known=[]) == []  # only raised bars get judged
    dropped = puzzlegen.recheck(client, settings(judges=2), path, against=[], known=[], rejudge=True)
    assert sorted(dropped) == ["BUMP IN ROAD", "GOAL POST NET"]
    assert [p.answer for p in puzzlegen.load_pool(path)] == ["SPILL THE BEANS", "WATERING CAN"]
    data = json.loads(path.read_text())
    last = data["rechecked"][-1]
    assert last["rejudged_by"] == JUDGE and last["dropped"] == dropped
    assert data["judge"] == JUDGE  # every puzzle left has passed this judge, so reports name it


def test_the_rejudge_flag_reaches_recheck(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr(puzzlegen, "recheck", lambda *a, **kw: seen.update(kw) or [])
    monkeypatch.setattr(puzzlegen, "_client", lambda: None)
    path = tmp_path / "batch.json"
    puzzlegen.save_pool(path, [Puzzle("Thing", "WATERING CAN")], settings(), seed=1, rejected={}, cost=0.0)
    puzzlegen.main(["--recheck", str(path), "--rejudge"])
    assert seen["rejudge"] is True


def test_a_batch_file_keeps_its_history_across_rechecks_and_top_ups(tmp_path):
    path = tmp_path / "batch.json"
    puzzlegen.save_pool(path, [Puzzle("Thing", "SPARE TIRE")], settings(), seed=4, rejected={"already used": 3}, cost=0.01)
    client = fake([])
    puzzlegen.recheck(client, settings(), path, against=[], known=[Puzzle("Thing", "SPARE TIRES")])
    puzzlegen.save_pool(path, [Puzzle("Thing", "KITCHEN SINK")], settings(), seed=4, rejected={"judge": 1}, cost=0.02)
    data = json.loads(path.read_text())
    assert data["rechecked"][0]["dropped"] == ["SPARE TIRE"]
    assert [run["rejected"] for run in data["runs"]] == [{"already used": 3}, {"judge": 1}]
    assert data["cost"] == pytest.approx(0.03)


def test_puzzle_runs_show_elapsed_time(tmp_path):
    now = [0.0]

    def clock():
        now[0] += 50
        return now[0]

    lines = []
    client = fake([["Spare tire", "Kitchen sink", "Garden hose"], ["Paper towel", "Coffee mug", "Light bulb"]])
    puzzlegen.generate(client, settings(max_requests=2), [("Thing", 6)], [], seed=1, known=[],
                       seen_path=tmp_path / "seen.txt", say=lines.append, heartbeat=120, clock=clock)
    status = [line for line in lines if "overall" in line]
    assert status and all("elapsed" in line for line in status)
