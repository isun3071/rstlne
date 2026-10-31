"""Bot version 4: each opponent's own stealer's gain, mixed from LLM and bot tables by how LLM-like it plays."""

import json
import math
from dataclasses import replace

import pytest
from bot_fixtures import view_at

from rstlne import selfplay
from rstlne.players.bot import versions
from rstlne.players.bot.objective import Objective
from rstlne.players.bot.steal import Steal

V3 = versions.knobs(3)
LLM_TABLE = ((1, ((0, (0.0,) * 20),)),)  # LLM opponents add nothing before solving
BOT_TABLE = ((1, ((0, (3000.0,) * 20),)),)  # bot opponents add $3,000
STEAL_BOT = (-6.0, 2.0, 1.0)  # bots solve much less often than LLMs at the same board
V4 = replace(V3, stealer_gain_llm=LLM_TABLE, stealer_gain_bot=BOT_TABLE, steal_bot=STEAL_BOT)


def logistic(x):
    return 1 / (1 + math.exp(-x))


# How LLM-like each seat plays


def test_every_seat_starts_halfway_and_v3_never_learns_it():
    assert Steal(0, V4).llm_share(1) == 0.5
    assert Steal(0, V3).llm_share(1) is None


def test_a_seat_that_solves_early_looks_like_an_llm_and_one_that_waits_looks_like_a_bot():
    steal = Steal(0, V4)
    steal.note(1, 0.4, 0.5, solved=True)
    q_llm = logistic(sum(w * x for w, x in zip(V4.steal_prior, (1, 0.4, 0.5))))
    q_bot = logistic(sum(w * x for w, x in zip(STEAL_BOT, (1, 0.4, 0.5))))
    assert steal.llm_share(1) == pytest.approx(q_llm / (q_llm + q_bot))
    for _ in range(6):
        steal.note(2, 0.7, 0.9, solved=False)  # passing up a board it could read
    assert steal.llm_share(2) < 0.5 < steal.llm_share(1)


# Using it


def goal(rules, wheel_spec, knobs, shares):
    view, _ = view_at(rules, wheel_spec, 3, totals=(4000, 0, 2000))
    return Objective(view, rules, wheel_spec, knobs, llm_share=shares)


def test_the_gain_mixes_the_two_tables_by_the_seats_weight(rules, wheel_spec):
    llm = goal(rules, wheel_spec, V4, {1: 1.0, 2: 1.0}).lose_round(False, {2: 1.0}).main
    bot = goal(rules, wheel_spec, V4, {1: 0.0, 2: 0.0}).lose_round(False, {2: 1.0}).main
    half = goal(rules, wheel_spec, V4, {1: 0.5, 2: 0.5}).lose_round(False, {2: 1.0}).main
    assert llm > half > bot  # an LLM-like stealer banks little, so the bot's lead is safer
    assert half == pytest.approx((llm + bot) / 2)


def test_without_the_v4_knobs_the_gain_is_v3s(rules, wheel_spec):
    v3 = goal(rules, wheel_spec, V3, None).lose_round(False, {2: 1.0}).main
    view, _ = view_at(rules, wheel_spec, 3, totals=(4000, 0, 2000))
    assert v3 == Objective(view, rules, wheel_spec, V3).lose_round(False, {2: 1.0}).main


def test_the_bot_logs_each_opponents_weight(rules, wheel_spec):
    from bot_fixtures import belief
    from rstlne.engine.rules import public_view
    from rstlne.players.bot.player import BotPlayer

    class Fixed:
        name = "fixed"

        def read(self, view, refuted=frozenset(), suggested=None):
            return belief([("WHEEL OF FORTUNE", 0.3)], T=(0.9, 1.0))

    view, state = view_at(rules, wheel_spec, 3, totals=(4000, 0, 2000))
    bot = BotPlayer(0, rules, wheel_spec, Fixed(), knobs=V4)
    bot.decide(public_view(state, 0))
    assert bot.last_call.raw["llm_like"] == {"2": 0.5, "3": 0.5}  # seats 2 and 3, by their number at the table


# Fitting


def test_round_banks_games_record_every_chance_to_solve(tmp_path, rules, wheel_spec):
    from test_selfplay_games import KNOBS, POOL, reader
    puzzles = tmp_path / "tuning-test.json"
    puzzles.write_text(json.dumps([{"category": p.category, "answer": p.answer, "bonus": p.bonus} for p in POOL]))
    path = selfplay.round_banks(puzzles, 1, 7, tmp_path / "rb", rules, wheel_spec, KNOBS, reader)
    g = json.loads(path.read_text().splitlines()[0])
    assert g["chances"] and all(len(c) == 3 and 0 <= c[0] <= 1 and 0 <= c[1] <= 1 and c[2] in (0, 1) for c in g["chances"])
    assert sum(c[2] for c in g["chances"]) == sum(s["right"] for s in g["seat_stats"])  # every correct solve is one


def test_the_bot_solve_curve_fits_from_round_banks_chances(tmp_path):
    import random
    rng = random.Random(1)
    rows = []
    for k in range(4000):
        shown, conf = rng.random(), rng.random()
        rows.append([shown, conf, int(rng.random() < logistic(-5 + 2 * shown + 3 * conf))])
    folder = tmp_path / "rb"
    folder.mkdir()
    (folder / "round-banks.json").write_text(json.dumps({"puzzles": "puzzles/generated/tuning-101.json"}))
    (folder / "games-shard1of1.jsonl").write_text(json.dumps({"set": 0, "chances": rows, "gains": []}) + "\n")
    fit = selfplay.fit_steal_bot([folder], resamples=0)
    assert fit["a"] == pytest.approx(-5, abs=0.5) and fit["c"] == pytest.approx(3, abs=0.5)
