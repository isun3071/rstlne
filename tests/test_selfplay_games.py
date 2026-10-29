import json
from dataclasses import replace

import pytest
from bot_fixtures import belief
from helpers import BONUS, PUZZLES, start

from rstlne import selfplay
from rstlne.engine.puzzle import Puzzle
from rstlne.engine.rules import public_view
from rstlne.engine.state import Solve
from rstlne.players.bot import versions
from rstlne.players.bot.player import BotPlayer
from rstlne.players.bot.reader import WordListReader

KNOBS = replace(versions.knobs(1), samples=40)  # enough to play; fewer samples keep the games fast
WORDS = {w: 50 for p in (*PUZZLES, BONUS) for w in p.answer.replace("-", " ").split()}
POOL = [*PUZZLES, Puzzle("Thing", "BIG CITY"), BONUS, Puzzle("Thing", "WELL KNOWN", bonus=True)]
WORDS.update({"WELL": 30, "KNOWN": 30})


def reader(knobs):
    return WordListReader(WORDS, knobs)


class Fixed:
    """A reader that always believes the same thing."""
    name = "fixed"

    def __init__(self, b):
        self.b = b

    def read(self, view):
        return self.b


# The eager variant


def test_an_eager_bot_solves_as_soon_as_it_is_sure_enough(rules, wheel_spec):
    view = public_view(start(rules, wheel_spec), 0)
    fairly_sure = belief([("WHEEL OF FORTUNE", 0.7)], oov=0.3, T=(0.9, 1.0), N=(0.9, 1.0))
    eager = BotPlayer(0, rules, wheel_spec, Fixed(fairly_sure), knobs=replace(KNOBS, eager_solve=0.65))
    assert eager.decide(view) == Solve("WHEEL OF FORTUNE")
    base = BotPlayer(0, rules, wheel_spec, Fixed(fairly_sure), knobs=KNOBS)
    cautious = BotPlayer(0, rules, wheel_spec, Fixed(fairly_sure), knobs=replace(KNOBS, eager_solve=0.9))
    assert cautious.decide(view) == base.decide(view)  # below its bar, it plays like the base bot


# Entrants


def test_entrants_are_a_name_and_knob_changes():
    e = selfplay.Entrant.parse("eager:eager_solve=0.65")
    assert e.name == "eager" and e.knobs(KNOBS).eager_solve == 0.65
    assert selfplay.Entrant.parse("base").knobs(KNOBS) == KNOBS
    two = selfplay.Entrant.parse("v:known_answer=0.9+tie_margin=0.01").knobs(KNOBS)
    assert two.known_answer == 0.9 and two.tie_margin == 0.01


def test_entrants_share_one_reader_so_they_can_only_change_decisions():
    with pytest.raises(ValueError, match="reader"):
        selfplay.Entrant.parse("x:phrase_odds=2").knobs(KNOBS)


# Playing games


ENTRANTS = [selfplay.Entrant.parse(t) for t in ("base", "eager:eager_solve=0.65", "slow:eager_solve=0.99")]


def play(out, rules, wheel_spec, **options):
    return selfplay.play_games(ENTRANTS, POOL, 1, 7, out, rules, wheel_spec, KNOBS, reader, **options)


def test_a_set_plays_every_seat_order_and_records_each_game(tmp_path, rules, wheel_spec):
    lines = []
    path = play(tmp_path, rules, wheel_spec, say=lines.append)
    games = [json.loads(line) for line in path.read_text().splitlines()]
    assert len(games) == 6 and len({tuple(g["seats"]) for g in games}) == 6
    g = games[0]
    assert {"game", "set", "seats", "seed", "totals", "round_totals", "bonus", "moves", "seconds", "seat_stats"} <= set(g)
    assert len(g["round_totals"]) == rules.main_rounds and all(len(t) == 3 for t in g["round_totals"])
    assert all(final >= after_main for final, after_main in zip(g["totals"], g["round_totals"][-1]))  # the bonus only adds
    assert {"attempts", "right", "shown", "bankrupts"} <= set(g["seat_stats"][0])
    assert any(line.startswith("Played 6 games") for line in lines)


def test_games_replay_exactly_and_resume(tmp_path, rules, wheel_spec):
    first = play(tmp_path / "a", rules, wheel_spec)
    second = play(tmp_path / "b", rules, wheel_spec)
    strip = lambda p: [{k: v for k, v in json.loads(line).items() if k != "seconds"} for line in p.read_text().splitlines()]
    assert sorted(strip(first), key=lambda g: g["game"]) == sorted(strip(second), key=lambda g: g["game"])
    lines = []
    play(tmp_path / "a", rules, wheel_spec, say=lines.append)
    assert len(first.read_text().splitlines()) == 6 and any("already played" in line for line in lines)


def test_shards_split_the_games(tmp_path, rules, wheel_spec):
    a = play(tmp_path, rules, wheel_spec, shard=(1, 2))
    b = play(tmp_path, rules, wheel_spec, shard=(2, 2))
    names = [json.loads(line)["game"] for p in (a, b) for line in p.read_text().splitlines()]
    assert len(names) == 6 and len(set(names)) == 6


def test_the_summary_compares_entrants_with_intervals_from_sets(tmp_path, rules, wheel_spec):
    play(tmp_path, rules, wheel_spec)
    summary = selfplay.games_summary(tmp_path)
    assert {e["entrant"] for e in summary["entrants"]} == {"base", "eager", "slow"}
    assert sum(e["wins"] for e in summary["entrants"]) == pytest.approx(6)
    e = summary["entrants"][0]
    assert {"win_rate", "ci95", "by_seat", "avg_total", "avg_main", "solve_accuracy", "shown_median", "bankrupts_per_game"} <= set(e)
    assert len(summary["pairwise"]) == 3


def test_the_command_checks_entrants_before_playing(tmp_path, capsys):
    with pytest.raises(SystemExit) as stop:
        selfplay.main(["games", "--entrant", "x:phrase_odds=2", "--entrant", "b", "--entrant", "c",
                       "--puzzles", "puzzles/dev.json", "--sets", "1", "--seed", "1", "--out", str(tmp_path)])
    assert "reader" in str(stop.value)
