import json
from datetime import datetime

import pytest
from fakes import FakeDecisions, board_reader, decide_by, router, solvable_when_full

from rstlne import cli, settings


def test_parse_seats():
    assert cli.parse_seats("human,llm:openai/gpt-x,llm:anthropic/claude-y") == [
        ("human", None),
        ("llm", "openai/gpt-x"),
        ("llm", "anthropic/claude-y"),
    ]
    assert cli.parse_seats("decision,decision:typesafe/jev-1.13,human") == [
        ("decision", None),
        ("decision", "typesafe/jev-1.13"),
        ("human", None),
    ]


def test_a_decision_seat_can_name_its_solver_after_an_at_sign(rules, wheel_spec):
    assert cli.parse_seat("decision:liquid/d1-ultra@anthropic/claude-haiku-5.5") == (
        "decision", "liquid/d1-ultra@anthropic/claude-haiku-5.5")
    config = settings.load_config()
    named, default = cli.build_players([("decision", "liquid/d1-ultra@anthropic/claude-haiku-5.5"),
                                        ("decision", "liquid/d1-ultra"), ("bot", None)][:2],
                                       rules, wheel_spec, config, None, None, "s")
    assert (named.model, named.solver.model) == ("liquid/d1-ultra", "anthropic/claude-haiku-5.5")
    assert (default.model, default.solver.model) == ("liquid/d1-ultra", config["decision"]["solver_model"])
    assert named.describe()["solver"] == "anthropic/claude-haiku-5.5"


def test_a_tournament_pins_the_solver_a_decision_seat_names():
    from rstlne.tournament import _seated_models
    config = settings.load_config()
    assert _seated_models(["decision:liquid/d1-ultra@anthropic/claude-haiku-5.5", "bot", "bot"], config) == {
        "liquid/d1-ultra", "anthropic/claude-haiku-5.5"}
    assert _seated_models(["decision:liquid/d1-ultra", "bot", "bot"], config) == {
        "liquid/d1-ultra", config["decision"]["solver_model"]}


@pytest.mark.parametrize("seats, message", [
    ("human,human", "three seats"),
    ("bot:v2,human,human", "bot:v2"),
    ("human,llm:,human", "slug"),
    ("human,robot,human", "robot"),
    ("decision:liquid/d1-ultra@,bot,bot", "solver"),
    ("decision:@anthropic/claude-haiku-5.5,bot,bot", "decision model"),
])
def test_bad_seats_are_explained(seats, message):
    with pytest.raises(ValueError, match=message):
        cli.parse_seats(seats)


def test_puzzle_picks_are_seeded_and_never_repeat():
    puzzles = settings.load_puzzles(settings.ROOT / "puzzles" / "dev.json")
    first = cli.pick_puzzles(puzzles, 4, seed=11)
    assert first == cli.pick_puzzles(puzzles, 4, seed=11)
    main, bonus = first
    assert len(set(main)) == 4 and not any(p.bonus for p in main)
    assert bonus.bonus
    assert {cli.pick_puzzles(puzzles, 4, seed=s)[1] for s in range(30)} != {bonus}


def test_dev_puzzles_are_valid():
    raw = json.loads((settings.ROOT / "puzzles" / "dev.json").read_text())
    puzzles = settings.load_puzzles(settings.ROOT / "puzzles" / "dev.json")
    assert len(puzzles) == len(raw)
    assert sum(not p.bonus for p in puzzles) >= 20
    assert sum(p.bonus for p in puzzles) >= 8
    assert len({p.answer for p in puzzles}) == len(puzzles)


def test_a_model_only_game_runs_from_the_command_line(tmp_path, capsys):
    argv = ["--seats", "llm:a/one,llm:b/two,llm:c/three", "--seed", "3", "--pause", "0", "--log-dir", str(tmp_path)]
    client = router(board_reader)
    final = cli.main(argv, client=client)
    assert final.phase.value == "game_over"
    out = capsys.readouterr().out
    assert "Final totals" in out
    assert out.index("Before the bonus round") < out.index("Final totals")  # the main-round sums, then with the bonus
    before = out.split("Before the bonus round")[1].split("Final totals")[0]
    bonus = final.bonus
    for i, seat in enumerate(final.seats):
        main = seat.total - (bonus.envelope if bonus.solved and bonus.seat == i else 0)
        assert f"${main:,}" in before
    logs = list(tmp_path.glob("*.jsonl"))
    assert len(logs) == 1
    records = [json.loads(line) for line in logs[0].read_text().splitlines()]
    assert records[0]["seats"][0] == {"kind": "llm", "model": "a/one", "temperature": None, "reasoning_effort": None,
                                      "provider": None, "tools": "all"}  # config.toml offers every tool
    assert records[-1]["type"] == "summary" and records[-1]["usage"]["calls"] > 0
    assert "cached_tokens" in records[-1]["usage"]
    sessions = {call["extra_body"]["session_id"] for call in client.client.calls}
    assert sessions == {f"{logs[0].stem}-seat{n}" for n in (1, 2, 3)}


def test_a_decision_model_game_runs_from_the_command_line(tmp_path):
    argv = ["--seats", "decision,decision,llm:c/three", "--seed", "4", "--pause", "0", "--log-dir", str(tmp_path)]
    decisions = FakeDecisions(decide_by(solvable_when_full))
    final = cli.main(argv, client=router(board_reader), decisions=decisions)
    assert final.phase.value == "game_over"
    header = json.loads(next(tmp_path.glob("*.jsonl")).read_text().splitlines()[0])
    decision = settings.load_config()["decision"]
    choosing = decision.get("solve", "threshold") == "choice"
    threshold = None if choosing else decision["thresholds"].get(decision["decision_model"], decision["solve_threshold"])
    assert header["seats"][0] == {
        "kind": "decision", "model": decision["decision_model"], "solver": decision["solver_model"],
        "solve": "choice" if choosing else "threshold", "threshold": threshold,
    }
    assert {c["session_id"] for c in decisions.calls} >= {f"{next(tmp_path.glob('*.jsonl')).stem}-seat1"}


def test_show_puzzle_prints_the_table_after_every_move(tmp_path, capsys):
    argv = ["--seats", "llm:a/one,llm:b/two,llm:c/three", "--seed", "3", "--pause", "0",
            "--log-dir", str(tmp_path), "--show-puzzle"]
    cli.main(argv, client=router(board_reader))
    lines = capsys.readouterr().out.splitlines()
    first_move = next(i for i, line in enumerate(lines) if line.startswith("Seat 1 spun"))
    assert lines[first_move + 1].strip().startswith("Round 1. Category:")
    assert lines[first_move + 2].strip().startswith("Board:")
    moves = [line for line in lines if line.startswith("Seat ") and not line.startswith(("Seat 1 (", "Seat 2 (", "Seat 3 ("))]
    boards = [line for line in lines if line.strip().startswith("Board:")]
    solves = [line for line in moves if " solved it: " in line]  # each also prints the solved board
    assert len(boards) == len(moves) - 1 + len(solves)  # the move that ends the game is followed by the final totals instead


def test_without_show_puzzle_model_games_print_no_table(tmp_path, capsys):
    argv = ["--seats", "llm:a/one,llm:b/two,llm:c/three", "--seed", "3", "--pause", "0", "--log-dir", str(tmp_path)]
    cli.main(argv, client=router(board_reader))
    assert not any(line.strip().startswith("Board:") for line in capsys.readouterr().out.splitlines())


def test_one_model_can_get_its_own_reasoning_effort(rules, wheel_spec):
    from fakes import router
    from rstlne import settings
    config = settings.load_config()
    tuned = {**config, "llm": {**config["llm"], "effort": {"a/one": "medium"}}}
    seats = [("llm", "a/one"), ("llm", "b/two"), ("bot", None)]
    one, two, _ = cli.build_players(seats, rules, wheel_spec, tuned, router([]), None, "g")
    assert one.reasoning_effort == "medium" and two.reasoning_effort == config["llm"].get("reasoning_effort")
    with pytest.raises(ValueError, match="effort"):
        cli.build_players(seats, rules, wheel_spec, {**config, "llm": {**config["llm"], "effort": {"a/one": "lots"}}},
                          router([]), None, "g")


def test_a_deck_tagged_by_round_gives_each_round_one_of_its_own():
    from rstlne.engine.puzzle import Puzzle
    words = ("ONE", "TWO", "THREE", "FOUR")
    tagged = [Puzzle("Thing", f"ROUND {words[r - 1]} THING {c}", round=r) for r in (1, 2, 3, 4) for c in "ABC"]
    bonus = Puzzle("Thing", "FUZZY SOCKS", bonus=True)
    picks = [cli.pick_puzzles(tagged + [bonus], 4, seed=s)[0] for s in range(10)]
    assert all([p.round for p in main] == [1, 2, 3, 4] for main in picks)
    assert len({main[0] for main in picks}) > 1  # still a seeded draw within each round


def test_games_started_together_on_one_seed_get_their_own_logs(tmp_path):
    # Two games launched in the same second on the same seed once wrote into one file and garbled both
    now = datetime(2026, 11, 6, 15, 18, 0)
    first, second = cli.log_path(tmp_path, 707, now), cli.log_path(tmp_path, 707, now)
    assert first.name == "20261106-151800-seed707.jsonl"
    assert second.name == "20261106-151800-seed707-2.jsonl"
    assert first.exists() and second.exists()  # each name is claimed as it's handed out


def test_verbose_thinking_asks_each_seat_for_its_formulas(rules, wheel_spec):
    from helpers import start
    from rstlne.engine.rules import apply
    from rstlne.engine.state import Spin
    from rstlne.players.base import Player
    from rstlne.show import Show

    class Thinker(Player):
        def thoughts(self, verbose=False):
            return ["plain"] + (["formula"] if verbose else [])

    state = apply(start(rules, wheel_spec), Spin())
    for verbose, expected in ((False, ["plain"]), (True, ["plain", "formula"])):
        out = []
        show = Show([Thinker()] * 3, 0, thinking=True, verbose=verbose, write=out.append, sleep=lambda s: None)
        show.names = ["a", "b", "c"]
        show.result(state)
        assert [line.split("] ", 1)[1] for line in out if line.startswith("    [")] == expected
    assert cli._arguments(["--seats", "bot,bot,bot", "--verbose"]).verbose


# A bot seat may name a strategy: one of the self-play variants, for play; plain `bot` stays the version's own

def test_a_bot_seat_may_name_a_strategy(rules, wheel_spec):
    from rstlne.players.bot import versions
    assert cli.parse_seat("bot") == ("bot", None)
    assert cli.parse_seat("bot:solve_on_sight") == ("bot", "solve_on_sight")
    with pytest.raises(ValueError, match="never_vowel"):  # the error lists the strategies
        cli.parse_seat("bot:greedy")
    with pytest.raises(ValueError, match="hybrid"):  # a hybrid keeps the standard strategy
        cli.parse_seat("hybrid:a/one+solve_on_sight")
    config = settings.load_config()
    version = versions.current(config)
    plain, sight, milk, afford, cover, never = cli.build_players(
        [("bot", None), ("bot", "solve_on_sight"), ("bot", "milk_all"), ("bot", "vowels_affordable"),
         ("bot", "vowel_cover"), ("bot", "never_vowel")], rules, wheel_spec, config, None, None, "g")
    assert plain.knobs == versions.knobs(version) and plain.label() == f"bot v{version}"
    assert "strategy" not in plain.describe()
    assert sight.knobs.eager_solve == versions.knobs(version).known_answer  # solves the moment it's sure
    assert milk.knobs.milk_all and never.knobs.never_vowel
    assert (afford.knobs.vowel_first, afford.knobs.free_play_vowel) == (0.1, True) and cover.knobs.vowel_cover == 0.1
    assert sight.label() == f"bot v{version} (closes out when sure)"
    assert sight.describe()["strategy"] == "solve_on_sight"
    hit = cli.build_players([("bot", "hit_first")], rules, wheel_spec, config, None, None, "g")[0]
    assert hit.knobs.hit_first and hit.label() == f"bot v{version} (calls the likeliest consonant)"
    for player in (sight, milk, afford, cover, never, hit):  # everything but the strategy is the version's own
        assert player.knobs.known_answer == versions.knobs(version).known_answer and player.version == version


def test_a_bot_strategy_counts_as_a_bot_in_tournaments_and_names_its_own_folder():
    from rstlne import tournament
    config = settings.load_config()
    assert tournament._plays_bot("bot:milk_all")
    plain = tournament.folder_name(["llm:a/one", "bot", "bot"], 707, "deck.json", config)
    milk = tournament.folder_name(["llm:a/one", "bot:milk_all", "bot"], 707, "deck.json", config)
    assert plain != milk


def test_a_replayed_bot_with_a_strategy_keeps_its_label():
    from rstlne.web.replay import label_of
    assert label_of({"kind": "bot", "version": 6}) == "bot v6"
    assert label_of({"kind": "bot", "version": 6, "strategy": "never_vowel"}) == "bot v6 (never buys a vowel)"
