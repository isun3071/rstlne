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

    def read(self, view, refuted=frozenset(), suggested=None):
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


def test_an_entrant_can_change_how_it_reads():
    assert selfplay.Entrant.parse("x:phrase_odds=2").knobs(KNOBS).phrase_odds == 2  # it gets a reader of its own


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


def test_identical_seats_can_play_one_order_per_set(tmp_path, rules, wheel_spec):
    # with three copies of one bot, the six orders of a set replay the same game
    same = [selfplay.Entrant(name) for name in ("a", "b", "c")]
    path = selfplay.play_games(same, POOL, 2, 7, tmp_path, rules, wheel_spec, KNOBS, reader, orders="one")
    games = [json.loads(line) for line in path.read_text().splitlines()]
    assert [(g["set"], g["permutation"]) for g in games] == [(0, 0), (1, 0)]


def test_one_bot_against_two_copies_can_play_the_rotations_only(tmp_path, rules, wheel_spec):
    # against two copies of one bot, swapping the copies replays a game, so three rotations cover a set
    entrants = [selfplay.Entrant.parse(t) for t in ("x:eager_solve=0.65", "a", "b")]
    path = selfplay.play_games(entrants, POOL, 1, 7, tmp_path, rules, wheel_spec, KNOBS, reader, orders="cyclic")
    games = [json.loads(line) for line in path.read_text().splitlines()]
    assert len(games) == 3 and sorted(g["seats"].index("x") for g in games) == [0, 1, 2]


def test_an_entrant_can_start_from_a_frozen_version():
    base = versions.knobs(4)
    assert selfplay.Entrant.parse("v5:version=5").knobs(base) == versions.knobs(5)
    assert selfplay.Entrant.parse("r:version=5+express_vowels=false").knobs(base) == replace(versions.knobs(5), express_vowels=False)
    assert selfplay.Entrant.parse("e:express_vowels=true").knobs(base) == replace(base, express_vowels=True)
    with pytest.raises(ValueError, match="version 9"):
        selfplay.Entrant.parse("x:version=9").knobs(base)


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
        selfplay.main(["games", "--entrant", "x:nonsense=2", "--entrant", "b", "--entrant", "c",
                       "--puzzles", "puzzles/dev.json", "--sets", "1", "--seed", "1", "--out", str(tmp_path)])
    assert "nonsense" in str(stop.value)


# Tuning decisions


def test_a_change_is_adopted_only_when_it_clearly_wins():
    results = [{"value": 0.9, "gap": 0.04, "ci95": [-0.01, 0.09]}, {"value": 0.98, "gap": 0.06, "ci95": [0.01, 0.11]}]
    assert selfplay.pick(results) == 0.98
    assert selfplay.pick([{"value": 0.9, "gap": 0.05, "ci95": [-0.02, 0.12]}]) is None  # not clear of zero
    assert selfplay.pick([]) is None


def test_decision_tuning_plays_each_value_against_the_current_bot_and_resumes(tmp_path, rules, wheel_spec):
    grid = {"known_answer": [0.9], "tie_margin": [0.01]}
    lines = []
    changes = selfplay.tune_decisions(POOL, tmp_path, rules, wheel_spec, KNOBS, reader, sets=1, seed=4, grid=grid,
                                      say=lines.append)
    folders = sorted(p.name for p in tmp_path.iterdir() if p.is_dir())
    assert folders == ["known_answer=0.9", "tie_margin=0.01"]
    seats = {tuple(sorted(json.loads(line)["seats"])) for line in (tmp_path / "known_answer=0.9" / "games-shard1of1.jsonl").read_text().splitlines()}
    assert seats == {("current", "eager", "variant")}
    saved = json.loads((tmp_path / "tune-decisions.json").read_text())
    assert {r["knob"] for r in saved["comparisons"]} == {"known_answer", "tie_margin"}
    assert saved["changes"] == list(changes)
    assert any("variant minus current" in line for line in lines)
    before = len(lines)
    selfplay.tune_decisions(POOL, tmp_path, rules, wheel_spec, KNOBS, reader, sets=1, seed=4, grid=grid, say=lines.append)
    assert any("already played" in line for line in lines[before:])


def test_decision_tuning_can_be_limited_to_some_knobs():
    assert selfplay.grid_for("tie_margin,known_answer") == {"tie_margin": [0.002, 0.01], "known_answer": [0.9, 0.98]}
    assert selfplay.grid_for(None) == selfplay.DECISION_GRID
    with pytest.raises(ValueError, match="nonsense"):
        selfplay.grid_for("nonsense")


def test_decision_tuning_tunes_the_steal_pseudo_count_first():
    # version 6's retune: the steal odds' pseudo-count goes first, so the other knobs tune on the final steal odds
    assert list(selfplay.DECISION_GRID)[0] == "steal_pseudo"
    assert selfplay.DECISION_GRID["steal_pseudo"] == [1.0, 4.0]
    assert selfplay.grid_for("steal_pseudo") == {"steal_pseudo": [1.0, 4.0]}


def test_v1_plays_with_the_steal_curve_measured_from_llm_play():
    # From 4,303 turns of three LLMs on fresh puzzles (logs/selfplay/steal-preview), with the reader's knobs kept
    assert versions.knobs(1).steal_prior == (-3.27, 2.61, 1.92)


def test_the_tuning_command_starts_from_the_configured_bot_plus_its_knobs(tmp_path, monkeypatch):
    table = tmp_path / "win-table.json"
    table.write_text(json.dumps({"knob": [[1, [[-1000.0, 0.2], [1000.0, 0.8]]]]}))
    seen = {}
    monkeypatch.setattr(selfplay, "tune_decisions", lambda pool, out, rules, spec, base, make_reader, sets, seed, grid,
                        workers, say: seen.update(base=base, grid=grid, rules=rules, sets=sets))
    selfplay.main(["tune-decisions", "--puzzles", "puzzles/dev.json", "--out", str(tmp_path / "t"), "--sets", "2",
                   "--knob", f"win_table=@{table}", "--knobs", "tie_margin"])
    assert seen["base"].win_table == ((1, ((-1000.0, 0.2), (1000.0, 0.8))),)
    assert seen["base"].steal_prior == versions.knobs(1).steal_prior
    assert seen["grid"] == {"tie_margin": [0.002, 0.01]}
    assert seen["rules"].main_rounds > 0 and seen["sets"] == 2


# The stealer's gain


def test_round_banks_games_record_gain_points_and_name_their_puzzles(tmp_path, rules, wheel_spec):
    puzzles = tmp_path / "tuning-test.json"
    puzzles.write_text(json.dumps([{"category": p.category, "answer": p.answer, "bonus": p.bonus} for p in POOL]))
    path = selfplay.round_banks(puzzles, 1, 7, tmp_path / "rb", rules, wheel_spec, KNOBS, reader)
    games = [json.loads(line) for line in path.read_text().splitlines()]
    points = [p for g in games for p in g["gains"]]
    assert len(games) == 6 and points and all(len(p) == 3 and 1 <= p[0] <= rules.main_rounds for p in points)
    assert selfplay.games_gain_points([tmp_path / "rb"]) == [tuple(p) for p in points]
    grading = tmp_path / "grading-9.json"
    grading.write_text(puzzles.read_text())
    with pytest.raises(ValueError, match="grading"):
        selfplay.round_banks(grading, 1, 7, tmp_path / "no", rules, wheel_spec, KNOBS, reader)


def test_games_count_when_a_bot_thought_the_result_settled(tmp_path, rules, wheel_spec):
    path = play(tmp_path, rules, wheel_spec)
    g = json.loads(path.read_text().splitlines()[0])
    assert {"certain_win", "certain_loss", "flat"} <= set(g["seat_stats"][0])
    e = selfplay.games_summary(tmp_path)["entrants"][0]
    assert {"certain_win", "certain_win_lost", "certain_loss", "certain_loss_won", "flat_per_game"} <= set(e)


def test_games_report_how_llm_like_each_v4_seat_found_each_opponent(tmp_path, rules, wheel_spec):
    tables = ((1, ((0, (0.0,) * 20),)),)
    files = {}
    for name, knob in (("llm", tables), ("bot", tables), ("steal", (-6.0, 2.0, 1.0))):
        files[name] = tmp_path / f"{name}.json"
        files[name].write_text(json.dumps({"knob": knob}))
    four = selfplay.Entrant.parse(f"v4:stealer_gain_llm=@{files['llm']}+stealer_gain_bot=@{files['bot']}+steal_bot=@{files['steal']}")
    entrants = [four, selfplay.Entrant("plain"), selfplay.Entrant.parse("eager:eager_solve=0.65")]
    path = selfplay.play_games(entrants, POOL, 1, 7, tmp_path, rules, wheel_spec, KNOBS, reader)
    g = json.loads(path.read_text().splitlines()[0])
    seat = g["seats"].index("v4")
    assert set(g["seat_stats"][seat]["llm_like"]) == {str(s + 1) for s in range(3) if s != seat}
    e = {r["entrant"]: r for r in selfplay.games_summary(tmp_path)["entrants"]}
    assert set(e["v4"]["llm_like"]) == {"plain", "eager"} and all(0 <= w <= 1 for w in e["v4"]["llm_like"].values())
    assert e["plain"]["llm_like"] == {}
    assert any("plays like an LLM" in line for line in selfplay.summary_lines(selfplay.games_summary(tmp_path)))


def test_the_llm_likeness_a_v4_seat_records_never_stands_in_for_its_wins(tmp_path):
    game = {"set": 0, "seats": ["v4", "v3", "eager"], "totals": [0, 9000, 100], "round_totals": [], "bonus": None,
            "seat_stats": [{"attempts": 0, "right": 0, "shown": [], "bankrupts": 0, "llm_like": {"2": 0.3, "3": 0.6}},
                           {"attempts": 0, "right": 0, "shown": [], "bankrupts": 0},
                           {"attempts": 0, "right": 0, "shown": [], "bankrupts": 0}]}
    (tmp_path / "games-shard1of1.jsonl").write_text(json.dumps(game) + "\n")
    s = selfplay.games_summary(tmp_path, resamples=10)
    e = {r["entrant"]: r for r in s["entrants"]}
    assert e["v4"]["win_rate"] == 0 and e["v4"]["ci95"] == [0, 0]  # v4 lost; its 0.6 for eager is no win
    gap = next(p for p in s["pairwise"] if {p["a"], p["b"]} == {"v3", "v4"})
    assert gap["gap"] == (1 if gap["a"] == "v3" else -1)


def test_each_pair_gets_a_main_money_gap_with_an_interval_over_sets(tmp_path):
    stats = [{"attempts": 0, "right": 0, "shown": [], "bankrupts": 0}] * 3
    games = [{"set": 0, "seats": ["a", "b", "c"], "totals": [0, 0, 0], "round_totals": [[1000, 0, 0], [4000, 1000, 0]],
              "bonus": None, "seat_stats": stats},
             {"set": 1, "seats": ["b", "c", "a"], "totals": [0, 0, 0], "round_totals": [[3000, 0, 2000]],
              "bonus": None, "seat_stats": stats}]
    (tmp_path / "games-shard1of1.jsonl").write_text("".join(json.dumps(g) + "\n" for g in games))
    s = selfplay.games_summary(tmp_path, resamples=50)
    ab = next(p for p in s["pairwise"] if (p["a"], p["b"]) == ("a", "b"))
    assert ab["main_gap"] == (4000 + 2000) / 2 - (1000 + 3000) / 2  # main money is the last round's running total
    lo, hi = ab["main_ci95"]
    assert lo <= ab["main_gap"] <= hi and lo >= -1000 and hi <= 3000  # set 0 gives +3000, set 1 gives -1000


# Version 5 against version 4: each reading setup gets its own reader

def test_entrants_that_read_differently_each_get_their_own_reader(tmp_path, rules, wheel_spec):
    built = []

    def make(knobs):
        built.append((knobs.fit_weight, knobs.coherence_weight))
        return WordListReader(WORDS, knobs)

    entrants = [selfplay.Entrant("four"), selfplay.Entrant.parse("five:fit_weight=6+coherence_weight=4"),
                selfplay.Entrant.parse("eager:eager_solve=0.65")]
    selfplay.play_games(entrants, POOL, 1, 5, tmp_path, rules, wheel_spec, KNOBS, make, say=lambda line: None)
    assert sorted(set(built)) == [(4.0, 0.0), (6.0, 4.0)]  # eager reads like four: one reader for both
    assert len(built) == 2  # built once each, not once per game


def test_version_5_s_reading_knobs_count_as_reading_knobs():
    for knob in ("cased_lexicon", "one_letter", "ngrams", "triple_weight", "triple_smoothing", "vector_pair_weight",
                 "single_fit_weight", "coherence_weight"):
        assert knob in selfplay.READER_KNOBS
    assert "express_vowels" not in selfplay.READER_KNOBS  # a decision knob


# Version 5, E2: Express rides, estimated and measured


def test_games_record_each_express_ride_against_its_estimate(tmp_path, rules, wheel_spec):
    path = play(tmp_path, rules, wheel_spec)
    games = [json.loads(line) for line in path.read_text().splitlines()]
    assert all("rides" in g and "express_passes" in g["seat_stats"][0] for g in games)


RIDE_RAW = {"confidence": 0.9, "ride": {"estimate": 0.8, "chance": 0.8, "letters": 2, "plan": "consonants"}}


def on_the_express(rules, wheel_spec):
    from helpers import spin_to, to_round

    from rstlne.engine.rules import apply
    from rstlne.engine.state import CallConsonant
    return apply(spin_to(to_round(start(rules, wheel_spec), 3), 12), CallConsonant("G"))  # GOLDEN GATE BRIDGE, seat 2


def test_a_ride_is_filed_with_its_boarding_estimate_once_it_ends(rules, wheel_spec):
    from helpers import solve

    from rstlne.engine.rules import apply
    from rstlne.engine.state import CallConsonant, Choose
    express = on_the_express(rules, wheel_spec)
    riding, rides, stat = {}, [], {"express_passes": 0}
    boarded = apply(express, Choose("play"))
    selfplay._follow_ride(riding, rides, stat, "v5", express, boarded, RIDE_RAW)
    called = apply(boarded, CallConsonant("D"))
    selfplay._follow_ride(riding, rides, stat, "v5", boarded, called, {})
    assert riding[2]["calls"] == 1 and not rides
    selfplay._follow_ride(riding, rides, stat, "v5", called, solve(called), {})
    assert not riding and rides == [{"seat": 2, "entrant": "v5", "estimate": 0.8, "chance": 0.8, "letters": 2,
                                     "plan": "consonants", "confidence": 0.9, "shown": rides[0]["shown"], "calls": 1,
                                     "vowels": 0, "solved": True, "ended": "solve solved"}]
    assert 0 < rides[0]["shown"] < 1 and stat["express_passes"] == 0


def test_a_missed_call_ends_a_ride_unsolved_and_a_pass_is_counted(rules, wheel_spec):
    from rstlne.engine.rules import apply
    from rstlne.engine.state import CallConsonant, Choose
    express = on_the_express(rules, wheel_spec)
    riding, rides, stat = {}, [], {"express_passes": 0}
    boarded = apply(express, Choose("play"))
    selfplay._follow_ride(riding, rides, stat, "v5", express, boarded, RIDE_RAW)
    selfplay._follow_ride(riding, rides, stat, "v5", boarded, apply(boarded, CallConsonant("Z")), {})
    assert rides[0]["solved"] is False and rides[0]["ended"] == "call_consonant missing"
    selfplay._follow_ride(riding, rides, stat, "v5", express, apply(express, Choose("pass")), RIDE_RAW)
    assert stat["express_passes"] == 1 and len(rides) == 1


def write_rides(folder, rides_by_set):
    folder.mkdir()
    with open(folder / "games-shard1of1.jsonl", "w") as f:
        for s, rides in rides_by_set.items():
            f.write(json.dumps({"game": f"set{s}", "set": s, "rides": rides}) + "\n")


def test_the_ride_fit_checks_estimates_against_rides_and_fits_a_correction(tmp_path):
    high = [{"entrant": "v5", "estimate": 0.8, "plan": "consonants", "solved": i % 2 == 0} for i in range(4)]  # 80% said, half came good
    other = [{"entrant": "v4", "estimate": 0.8, "plan": "consonants", "solved": True}]
    write_rides(tmp_path / "g", {0: high + other, 1: high, 2: high, 3: high})
    result = selfplay.fit_rides([tmp_path / "g"], tmp_path / "out", entrant="v5")
    assert result["rides"] == 16 and result["solved"] == pytest.approx(0.5) and result["mean_estimate"] == pytest.approx(0.8)
    assert dict(map(tuple, result["points"]))[0.8] == pytest.approx(0.5)
    assert result["held_out"]["after"]["error"] < result["held_out"]["before"]["error"]  # fit on even sets, checked on odd
    knobs = selfplay.override(versions.knobs(4), [f"express_calibration=@{tmp_path / 'out' / 'express-fit.json'}"])
    assert knobs.express_calibration == tuple(map(tuple, result["points"]))


def test_ride_corrections_parse_as_points():
    knobs = selfplay.override(versions.knobs(4), ["express_calibration=0:0,0.5:0.3,1:0.8"])
    assert knobs.express_calibration == ((0.0, 0.0), (0.5, 0.3), (1.0, 0.8))


def test_self_play_deals_by_round_tag_like_tournaments(tmp_path, rules, wheel_spec, monkeypatch):
    from rstlne import tournament
    calls, real = [], tournament.deal_main
    monkeypatch.setattr(tournament, "deal_main", lambda *a, **k: calls.append(a) or real(*a, **k))
    play(tmp_path, rules, wheel_spec)
    assert len(calls) == 1 and calls[0][1] == rules.main_rounds
