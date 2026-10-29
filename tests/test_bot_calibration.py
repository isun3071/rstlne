import random

import pytest
from bot_fixtures import belief, view_at

from rstlne.players.bot import calibration, versions
from rstlne.players.bot.objective import Objective
from rstlne.players.bot.player import BotPlayer
from rstlne.players.bot.reader import FrequencyReader
from rstlne.players.bot.steal import Odds
from rstlne.players.bot.value import Situation


def test_no_points_means_no_change():
    curve = calibration.curve(())
    assert [curve(x) for x in (0.0, 0.37, 1.0)] == [0.0, 0.37, 1.0]


def test_the_curve_interpolates_between_points_and_holds_at_the_ends():
    curve = calibration.curve(((0.2, 0.1), (0.6, 0.5), (0.9, 0.95)))
    assert curve(0.4) == pytest.approx(0.3) and curve(0.0) == 0.1 and curve(1.0) == 0.95


def test_a_fit_learns_how_often_a_confidence_is_really_right():
    rng = random.Random(1)
    pairs = []
    for _ in range(20_000):
        c = rng.random()
        pairs.append((c, rng.random() < c * c))  # overconfident: right only c² of the time
    points = calibration.fit(pairs)
    assert 2 <= len(points) <= 21
    ys = [y for _, y in points]
    assert ys == sorted(ys)  # never decreasing
    curve = calibration.curve(points)
    for c in (0.3, 0.5, 0.8):
        assert curve(c) == pytest.approx(c * c, abs=0.05)


def test_honesty_measures(rules, wheel_spec):
    honest = [(0.8, True)] * 8 + [(0.8, False)] * 2
    assert calibration.error(honest, lambda c: c) == pytest.approx(0.0)
    assert calibration.error(honest, lambda c: 0.5) == pytest.approx(0.3)
    assert calibration.brier(honest, lambda c: c) == pytest.approx(0.16)


def test_the_bot_decides_with_calibrated_confidence(rules, wheel_spec):
    knobs = versions.knobs(1)
    halve = versions.Knobs(**{**knobs.__dict__, "calibration": ((0.0, 0.0), (1.0, 0.5))})
    bot = BotPlayer(0, rules, wheel_spec, FrequencyReader(), knobs=halve)
    view, _ = view_at(rules, wheel_spec)
    sure = belief([("WHEEL OF FORTUNE", 0.9)], oov=0.1)
    s = bot._situation(view, sure)
    assert s.c == pytest.approx(0.45)  # the decision layer sees the corrected number


def test_knob_overrides_read_calibration_points():
    from rstlne import selfplay
    knobs = selfplay.override(versions.knobs(1), ["calibration=0:0.05,0.5:0.4,1:0.9"])
    assert knobs.calibration == ((0.0, 0.05), (0.5, 0.4), (1.0, 0.9))
