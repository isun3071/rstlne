import json
from dataclasses import replace

import pytest
from helpers import BONUS, PUZZLES, start

from rstlne import cli, settings
from rstlne.engine.rules import public_view
from rstlne.engine.state import Phase
from rstlne.players.bot import versions
from rstlne.players.bot.player import BotPlayer, guess
from rstlne.players.bot.reader import FrequencyReader, WordListReader
from rstlne.runner import GameLog, play_game
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
