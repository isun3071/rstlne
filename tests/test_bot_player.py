import json
from dataclasses import replace

import pytest
from helpers import BONUS, PUZZLES, spin_to, start

from rstlne import cli, settings
from rstlne.engine.puzzle import LETTERS
from rstlne.engine.rules import public_view
from rstlne.engine.state import Phase
from rstlne.players.bot import versions
from rstlne.players.bot.player import BotPlayer, explain, guess
from rstlne.players.bot.reader import FrequencyReader, WordListReader
from rstlne.runner import GameLog, play_game, play_turn
from rstlne.tournament import run_tournament

KNOBS = replace(versions.knobs(1), samples=120)
WORDS = {w: 50 for p in (*PUZZLES, BONUS) for w in p.answer.replace("-", " ").split()}
WORDS.update({"WELL-KNOWN": 40, "WHEAT": 30, "BANANAS": 20, "GOLDEN": 30, "FRACTURE": 5, "BIG": 60, "DIG": 20})


def bots(rules, spec, reader=None, knobs=KNOBS):
    reader = reader or WordListReader(WORDS, knobs)
    return [BotPlayer(i, rules, spec, reader, knobs=knobs) for i in range(3)]


def test_three_bots_finish_a_game_and_replay_it_exactly(rules, wheel_spec, tmp_path):
    finals = []
    for run in range(2):
        path = tmp_path / f"game{run}.jsonl"
        with GameLog(path, start(rules, wheel_spec), bots(rules, wheel_spec)) as log:
            finals.append(play_game(start(rules, wheel_spec), bots(rules, wheel_spec), log))
    assert finals[0].phase is Phase.GAME_OVER and finals[0] == finals[1]
    lines = [json.loads(line) for line in (tmp_path / "game0.jsonl").read_text().splitlines()]
    assert not [r for r in lines if r["type"] == "invalid"]  # the bot never makes an invalid move
    assert not [r for r in lines if r.get("fits_board") is False]  # and never a solve that doesn't fit
    assert lines[0]["seats"][0] == {"kind": "bot", "version": 1, "reader": "word list", "experiment": True}


def test_a_bot_with_a_word_list_solves_before_the_board_fills(rules, wheel_spec, tmp_path):
    path = tmp_path / "game.jsonl"
    with GameLog(path, start(rules, wheel_spec), bots(rules, wheel_spec)) as log:
        play_game(start(rules, wheel_spec), bots(rules, wheel_spec), log)
    moves = [json.loads(line) for line in path.read_text().splitlines()]
    shown = [m["solve_timing"]["board_shown"] for m in moves
             if m["type"] == "action" and "solve_timing" in m and m["result"]["outcome"] == "solved"]
    assert shown and min(shown) < 1.0


def test_bots_that_only_know_letter_frequency_still_finish(rules, wheel_spec):
    final = play_game(start(rules, wheel_spec), bots(rules, wheel_spec, reader=FrequencyReader()))
    assert final.phase is Phase.GAME_OVER


def test_the_bot_learns_steal_odds_from_what_opponents_do(rules, wheel_spec):
    players = bots(rules, wheel_spec)
    play_game(start(rules, wheel_spec), players)
    watcher = players[0]
    assert sum(watcher.steal.solves) >= 1 and watcher.steal.solves[0] == 0  # it never counts its own solves
    assert watcher.steal.expected[1] > 0 and watcher.steal.expected[2] > 0


def test_a_guess_with_no_answer_still_fits_the_board(rules, wheel_spec):
    state = start(rules, wheel_spec)
    state = replace(state, round=replace(state.round, used=frozenset("ETAOINSHRDLCUMWFGYPBVKJXQZ") - {"U"}))
    view = public_view(state, 0)
    assert guess(FrequencyReader().read(view), view) == "WHEEL OF FORTUNE"  # the one unused letter fills the gap


def only_vowels_hidden(rules, wheel_spec):
    """WH__L _F F_RT_N_ with every seat broke: solving is the only legal move."""
    state = start(rules, wheel_spec)
    return replace(state, round=replace(state.round, used=frozenset(LETTERS - set("AEIOU"))))


def test_bots_drop_an_answer_once_a_wrong_solve_refutes_it(rules, wheel_spec):
    state = only_vowels_hidden(rules, wheel_spec)
    words = {"WHOOL": 50, "WHEEL": 10, "OF": 50, "FORTUNE": 50}
    players = bots(rules, wheel_spec, reader=WordListReader(words, KNOBS))
    guesses = []
    while state.round.number == 1:
        state = play_turn(state, players)
        guesses.append(state.last.action.answer)
    assert guesses == ["WHOOL OF FORTUNE", "WHEEL OF FORTUNE"]  # the next seat tries the answer still standing


def test_a_guess_with_no_answer_skips_fills_already_refuted(rules, wheel_spec):
    state = only_vowels_hidden(rules, wheel_spec)
    state = replace(state, round=replace(state.round, used=state.round.used | {"A", "I"}))
    view = public_view(state, 0)
    belief = FrequencyReader().read(view)
    assert guess(belief, view) == "WHEEL EF FERTENE"
    assert guess(belief, view, frozenset({"WHEEL EF FERTENE"})) == "WHOOL OF FORTONO"


def test_the_bot_explains_its_move(rules, wheel_spec):
    bot = bots(rules, wheel_spec)[0]
    bot.decide(public_view(start(rules, wheel_spec), 0))
    raw = bot.last_call.raw
    assert raw["version"] == 1 and "values" in raw and "confidence" in raw and "p_steal" in raw
    assert bot.last_call.usage.calls == 0
    assert bot.thoughts() and bot.label() == "bot v1"


def test_a_version_bot_is_not_an_experiment(rules, wheel_spec):
    bot = BotPlayer(0, rules, wheel_spec, FrequencyReader(), version=1)
    assert bot.describe() == {"kind": "bot", "version": 1, "reader": "frequency"}


def test_the_cli_seats_bots(tmp_path, capsys):
    assert cli.parse_seats("bot,llm:a/one,bot") == [("bot", None), ("llm", "a/one"), ("bot", None)]
    final = cli.main(["--seats", "bot,bot,bot", "--seed", "5", "--pause", "0", "--log-dir", str(tmp_path)])
    assert final.phase is Phase.GAME_OVER and "Final totals" in capsys.readouterr().out
    header = json.loads(next(tmp_path.glob("*.jsonl")).read_text().splitlines()[0])
    assert header["seats"][0]["kind"] == "bot" and header["seats"][0]["version"] == versions.current(settings.load_config())


def test_a_bot_tournament_plays_its_games_in_separate_processes(tmp_path):
    lines = []
    result = run_tournament(["bot", "bot", "bot"], sets=1, seed=3, puzzles_path=settings.ROOT / "puzzles" / "dev.json",
                            out_dir=tmp_path, parallel=3, write=lines.append, heartbeat=600)
    assert result["games"] == 6 and not [line for line in lines if "failed" in line]
    assert any("separate processes" in line for line in lines)


def test_a_frequency_bot_never_guesses_unless_it_must(rules, wheel_spec, tmp_path):
    path = tmp_path / "game.jsonl"
    players = bots(rules, wheel_spec, reader=FrequencyReader())
    with GameLog(path, start(rules, wheel_spec), players) as log:
        play_game(start(rules, wheel_spec), players, log)
    moves = [json.loads(line) for line in path.read_text().splitlines()]
    solves = [m for m in moves if m["type"] == "action" and m["action"]["kind"] == "solve"]
    wrong = [s for s in solves if s["result"]["outcome"] != "solved"]
    assert solves and all(set(s["raw"]["values"]) <= {"solve"} for s in wrong)  # forced: nothing else was legal


# What the bot says it's thinking, for --show-thinking and --live

def test_the_bot_says_what_it_reads_and_how_it_weighed_its_moves():
    record = {"answers": [["WHEEL OF FORTUNE", 0.6], ["WHOOL OF FORTUNE", 0.25]], "oov": 0.05, "p_steal": 0.3,
              "values": {"spin": 1234.4, "buy_vowel": 980.0, "solve": 1000.0}, "win_mode": False}
    assert explain(record) == [
        "Reads WHEEL OF FORTUNE 60%, then WHOOL OF FORTUNE 25% · 5% chance it's outside its word lists",
        "Chance an opponent solves before its next turn: 30%",
        "Worth: spin $1,234, buy a vowel $980, solve $1,000 → spin",
    ]


def test_the_bot_names_its_top_two_answers_and_how_many_others_it_sampled():
    record = {"answers": [["WHEEL OF FORTUNE", 0.6], ["WHOOL OF FORTUNE", 0.25], ["WHEEL OF FURTUNE", 0.05]],
              "distinct": 9, "oov": 0.05, "p_steal": None, "values": {}}
    assert explain(record)[0] == ("Reads WHEEL OF FORTUNE 60%, then WHOOL OF FORTUNE 25%, and 7 other answers (10%)"
                                  " · 5% chance it's outside its word lists")
    one = {"answers": [["WHEEL OF FORTUNE", 0.6], ["WHOOL OF FORTUNE", 0.4]], "distinct": 2, "oov": 0.0, "values": {}}
    assert explain(one)[0] == "Reads WHEEL OF FORTUNE 60%, then WHOOL OF FORTUNE 40% · 0% chance it's outside its word lists"
    single = {"answers": [["WHEEL OF FORTUNE", 0.9]], "distinct": 2, "oov": 0.0, "values": {}}
    assert explain(single)[0].startswith("Reads WHEEL OF FORTUNE 90%, and 1 other answer (10%)")


def test_the_reader_counts_the_distinct_answers_it_sampled():
    from rstlne.players.bot.reader import summarize
    from rstlne.players.bot.versions import knobs
    samples = ["AB", "AB", "AC", "AD", "AE"]
    belief = summarize(samples, [False] * 4 + [True], "A_", list("BCDE"), knobs(6))
    assert belief.distinct == 3  # AB, AC, AD; AE has an unknown word and counts toward oov only
    assert summarize(samples, [False] * 5, "A_", list("BCDE"), knobs(6), refuted=frozenset({"AB"})).distinct == 3


def test_from_round_3_the_bot_weighs_its_chance_to_win():
    record = {"answers": [], "oov": 0.4, "p_steal": None, "values": {"spin": 0.612, "solve": 0.608}, "win_mode": True}
    assert explain(record) == [
        "No answer in sight yet · 40% chance it's outside its word lists",
        "Chance to win: spin 61.2%, solve 60.8% → spin",
    ]


@pytest.mark.parametrize("kind, line", [("spin", "Knows the answer: spins to build its bank first"),
                                        ("solve", "Knows the answer: solves now")])
def test_with_the_answer_known_the_bot_says_whether_it_milks_or_solves(kind, line):
    record = {"answers": [["WHEEL OF FORTUNE", 0.98]], "oov": 0.0, "p_steal": 0.5, "values": {}, "planner": kind}
    assert explain(record)[-1] == line


def test_a_decision_records_what_explain_reads(rules, wheel_spec):
    bot = bots(rules, wheel_spec)[0]
    bot.decide(public_view(start(rules, wheel_spec), 0))
    raw = bot.last_call.raw
    assert "answers" in raw and raw["win_mode"] is False
    assert bot.thoughts() == explain(raw)


def test_how_the_bot_weighed_its_turn_stays_up_through_the_consonant_call(rules, wheel_spec):
    bot = bots(rules, wheel_spec)[0]
    state = start(rules, wheel_spec)
    bot.decide(public_view(state, 0))
    weighed = bot.thoughts()[-1]
    assert weighed.startswith("Worth: ")
    bot.decide(public_view(spin_to(state, 3), 0))  # the consonant call weighs no moves
    assert bot.last_call.raw["values"] == {}  # the log keeps only what this decision weighed
    lines = bot.thoughts()
    assert lines[-2] == weighed and lines[-1].startswith("Calls ")


def test_a_new_round_drops_the_last_rounds_weighing(rules, wheel_spec):
    from helpers import solve
    bot = bots(rules, wheel_spec)[0]
    state = start(rules, wheel_spec)
    bot.decide(public_view(state, 0))
    after = spin_to(replace(solve(state), seat=0), 3)  # round 2, seat 1 holding a cash wedge
    bot.decide(public_view(after, 0))
    assert not any(line.startswith(("Worth", "Chance to win")) for line in bot.thoughts())


def test_the_bot_says_why_it_picked_its_letter():
    record = {"answers": [], "oov": 0.1, "p_steal": None, "values": {},
              "letter_pick": {"verb": "Calls", "ranked": [["T", 0.9, 1.84], ["N", 0.75, 1.0], ["S", 0.6, 1.2]]}}
    assert explain(record)[-1] == "Calls T: 90% likely, about 1.8 copies (then N 75%, S 60%)"


def test_a_consonant_call_records_its_top_letters(rules, wheel_spec):
    bot = bots(rules, wheel_spec)[0]
    bot.decide(public_view(spin_to(start(rules, wheel_spec), 3), 0))
    pick = bot.last_call.raw["letter_pick"]
    assert pick["verb"] == "Calls" and 1 <= len(pick["ranked"]) <= 3
    assert all(letter not in "AEIOU" and 0 <= p <= 1 for letter, p, *_ in pick["ranked"])


def test_a_vowel_bought_on_the_express_is_one_the_engine_takes(rules, wheel_spec, monkeypatch):
    from helpers import to_round
    from rstlne.engine.rules import apply
    from rstlne.engine.state import BuyVowel, CallConsonant, Choose, Phase
    from rstlne.players.bot.value import Situation
    state = apply(apply(spin_to(to_round(start(rules, wheel_spec), 3), 12), CallConsonant("G")), Choose("play"))
    assert state.phase is Phase.EXPRESS
    monkeypatch.setattr(Situation, "express_move", lambda self, legal: ("buy_vowel", "E"))
    bot = BotPlayer(state.seat, rules, wheel_spec, FrequencyReader(), knobs=replace(KNOBS, express_vowels=True))
    action = bot.decide(public_view(state, state.seat))
    assert action == BuyVowel("E") and bot.thoughts()[-1].startswith("Buys E")
    assert apply(state, action).phase is Phase.EXPRESS  # still riding


def test_a_per_turn_bot_counts_each_opponent_turn_once(rules, wheel_spec):
    from rstlne.players.bot import versions
    knobs = replace(versions.knobs(5), steal_turn=(-1.4, 2.7, 0.9), steal_turn_bot=(-1.4, 3.4, 0.7))
    players = bots(rules, wheel_spec, knobs=knobs)
    final = play_game(start(rules, wheel_spec), players)
    assert final.phase is Phase.GAME_OVER
    watcher = players[0]
    assert watcher.steal._turn is None  # every turn it watched was closed
    assert sum(watcher.steal.solves) >= 1 and watcher.steal.solves[0] == 0
    assert 0 < watcher.steal.expected[1] < 30 and 0 < watcher.steal.expected[2] < 30


# Each letter's worth beside its odds, and --verbose: every worth as its formula, with the numbers in

def test_the_letter_line_gives_each_letters_worth_so_a_less_likely_pick_makes_sense():
    record = {"answers": [], "oov": 0.1, "p_steal": None, "values": {},
              "letter_pick": {"verb": "Calls", "win_mode": False,
                              "ranked": [["N", 0.95, 2.4, 1640.0], ["R", 0.98, 1.1, 1580.0], ["T", 0.99, 1.2, 1560.0]]}}
    assert explain(record)[-1] == ("Calls N, worth $1,640: 95% likely, about 2.4 copies. "
                                   "Next best: R $1,580 (98%, 1.1 copies), T $1,560 (99%, 1.2 copies)")
    win = {**record, "letter_pick": {**record["letter_pick"], "win_mode": True,
                                     "ranked": [["N", 0.95, 2.4, 0.612], ["R", 0.98, 1.1, 0.608]]}}
    assert explain(win)[-1] == ("Calls N, worth 61.2% to win: 95% likely, about 2.4 copies. "
                                "Next best: R 60.8% (98%, 1.1 copies)")


def test_a_letter_line_from_an_older_log_reads_as_before():
    record = {"answers": [], "oov": 0.1, "p_steal": None, "values": {},
              "letter_pick": {"verb": "Calls", "ranked": [["T", 0.9, 1.84], ["N", 0.75, 1.0]]}}
    assert explain(record)[-1] == "Calls T: 90% likely, about 1.8 copies (then N 75%)"


def test_the_known_answer_line_says_what_solving_and_spinning_were_worth():
    record = {"answers": [["WHEEL OF FORTUNE", 0.99]], "oov": 0.0, "p_steal": 0.77, "values": {},
              "planner": "solve", "planner_values": {"solve": 3450.0, "spin": 3100.0}, "win_mode": False}
    assert explain(record)[-1] == "Knows the answer: solves now (solve $3,450, spin again $3,100)"


def _turn(rules, wheel_spec):
    bot = bots(rules, wheel_spec)[0]
    state = start(rules, wheel_spec)
    return bot, state, bot._situation(public_view(state, 0), bot._read(public_view(state, 0)))


def test_each_breakdown_adds_up_to_the_value_the_bot_chose_by(rules, wheel_spec):
    from rstlne.engine.wheel import Kind
    bot, state, s = _turn(rules, wheel_spec)
    solve = s.solve_parts()
    assert solve["total"] == pytest.approx(s.solve().main)
    assert solve["c"] * solve["win"] + (1 - solve["c"]) * solve["after_wrong"] == pytest.approx(solve["total"])
    assert solve["after_wrong"] == pytest.approx(solve["steal"] * solve["stolen"] + (1 - solve["steal"]) * solve["back"])
    spin = s.spin_parts()
    assert sum(g["n"] for g in spin) == len(s.wheel)
    assert sum(g["n"] * g["value"] for g in spin) / len(s.wheel) == pytest.approx(s.spin().main)
    cash = next(w for w in s.wheel if w.kind is Kind.CASH)
    for letter in s.consonants[:5]:
        parts = s.letter_parts(letter, s.bank, cash.value, claim_wild=cash.wild)
        assert parts["total"] == pytest.approx(s.call(letter, cash.value, claim_wild=cash.wild).main)
        assert parts["p"] * parts["hit"] + (1 - parts["p"]) * parts["miss"] == pytest.approx(parts["total"])
    for vowel in s.vowels:
        parts = s.letter_parts(vowel, s.bank - rules.vowel_cost, 0)
        assert parts["total"] == pytest.approx(s.vowel_value(vowel).main)


def test_the_planners_values_are_the_ones_it_chose_by(rules, wheel_spec):
    from rstlne.players.bot import planner
    bot, state, s = _turn(rules, wheel_spec)
    if s.belief.best is None:
        s.belief = replace(s.belief, answers=(("WHEEL OF FORTUNE", 0.9),))
    plan = planner.plan(s, ("spin", "solve"))
    assert planner.decide(s, ("spin", "solve")) == s.goal.choose(plan.options)
    if "spin" in plan.options:
        assert sum(g["share"] * g["value"] for g in plan.spin) == pytest.approx(plan.options["spin"].main)


def test_verbose_thoughts_show_the_formulas_and_plain_ones_dont(rules, wheel_spec):
    bot = bots(rules, wheel_spec)[0]
    state = start(rules, wheel_spec)
    bot.decide(public_view(state, 0))
    plain, verbose = bot.thoughts(), bot.thoughts(verbose=True)
    assert plain == explain(bot.last_call.raw)
    extra = [line for line in verbose if line not in plain]
    assert any(line.strip().startswith("spin = average over the 24 wedges") for line in extra)
    bot.decide(public_view(spin_to(state, 3), 0))  # a consonant call on a cash wedge
    letter = bot.last_call.raw["letter_pick"]["ranked"][0][0]
    assert any(line.strip().startswith(f"{letter} at $") for line in bot.thoughts(verbose=True))


def test_wedge_counts_read_in_wedges_with_the_millions_thirds():
    from rstlne.players.bot.breakdown import wedges
    assert wedges(12, 72) == "×4" and wedges(1, 72) == "×⅓" and wedges(8, 72) == "×2⅔" and wedges(3, 24) == "×3"
