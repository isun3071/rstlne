import tomllib
from collections import Counter

import pytest

from wof import settings
from wof.engine import wheel
from wof.engine.wheel import Kind, Wedge, WheelSpec

SPINS = 720_000
TOLERANCE = 0.025  # relative, per CLAUDE.md

# Base template cash wedges from documentation.md.
BASE_CASH = {
    2: 800, 3: 600, 4: 700, 5: 600, 6: 650, 7: 500, 8: 700, 9: 800, 10: 600, 11: 550,
    12: 500, 13: 600, 15: 650, 17: 700, 19: 800, 20: 500, 21: 650, 22: 500, 23: 900,
}


def at(layout, number, third=1):
    return layout[(number - 1) * 3 + third]


def raw_wheel():
    with open(settings.ROOT / "wheel.toml", "rb") as f:
        return tomllib.load(f)


def test_base_template_matches_spec(wheel_spec):
    layout = wheel.layout(wheel_spec, 4)
    assert len(layout) == 72
    for number, value in BASE_CASH.items():
        for third in range(3):
            assert at(layout, number, third) == Wedge(number, Kind.CASH, value)
    assert at(layout, 14).kind is Kind.BANKRUPT
    assert at(layout, 24).kind is Kind.BANKRUPT
    assert at(layout, 16) == Wedge(16, Kind.FREE_PLAY, 500)
    assert at(layout, 18).kind is Kind.LOSE_A_TURN


@pytest.mark.parametrize("round_number, top", [(1, 2500), (2, 3500), (3, 3500), (4, 5000), (5, 5000)])
def test_top_value_per_round(wheel_spec, round_number, top):
    assert at(wheel.layout(wheel_spec, round_number), 1) == Wedge(1, Kind.CASH, top)


@pytest.mark.parametrize("round_number", [1, 2, 3])
def test_wild_and_million_sit_on_rounds_1_to_3(wheel_spec, round_number):
    layout = wheel.layout(wheel_spec, round_number)
    assert at(layout, 2) == Wedge(2, Kind.CASH, 800, wild=True)
    assert [at(layout, 9, t).kind for t in range(3)] == [Kind.BANKRUPT, Kind.MILLION, Kind.BANKRUPT]
    assert at(layout, 9, 1).value == 500


@pytest.mark.parametrize("round_number", [4, 5])
def test_no_overlays_from_round_4(wheel_spec, round_number):
    layout = wheel.layout(wheel_spec, round_number)
    assert at(layout, 2) == Wedge(2, Kind.CASH, 800)
    assert all(at(layout, 9, t) == Wedge(9, Kind.CASH, 800) for t in range(3))
    assert not any(w.wild or w.kind in (Kind.MYSTERY, Kind.EXPRESS, Kind.MILLION) for w in layout)


@pytest.mark.parametrize("round_number", [1, 2, 3, 4])
def test_mystery_only_in_round_2(wheel_spec, round_number):
    layout = wheel.layout(wheel_spec, round_number)
    mystery = sorted({w.number for w in layout if w.kind is Kind.MYSTERY})
    assert mystery == ([5, 17] if round_number == 2 else [])
    if round_number == 2:
        assert at(layout, 5) == Wedge(5, Kind.MYSTERY, 1000)
        assert at(layout, 17) == Wedge(17, Kind.MYSTERY, 1000)


@pytest.mark.parametrize("round_number", [1, 2, 3, 4])
def test_express_only_in_round_3(wheel_spec, round_number):
    layout = wheel.layout(wheel_spec, round_number)
    express = sorted({w.number for w in layout if w.kind is Kind.EXPRESS})
    assert express == ([12] if round_number == 3 else [])
    if round_number == 3:
        assert at(layout, 12) == Wedge(12, Kind.EXPRESS, 1000)


def test_claimed_wild_card_leaves_the_wheel(wheel_spec):
    assert at(wheel.layout(wheel_spec, 1, wild=False), 2) == Wedge(2, Kind.CASH, 800)


def test_claimed_million_wedge_leaves_whole(wheel_spec):
    layout = wheel.layout(wheel_spec, 1, million=False)
    assert all(at(layout, 9, t) == Wedge(9, Kind.CASH, 800) for t in range(3))


@pytest.mark.parametrize("flipped, other, face", [(5, 17, 600), (17, 5, 700)])
def test_flipped_mystery_leaves_and_the_other_turns_plain(wheel_spec, flipped, other, face):
    layout = wheel.layout(wheel_spec, 2, flipped=flipped)
    assert at(layout, flipped) == Wedge(flipped, Kind.CASH, face)
    assert at(layout, other) == Wedge(other, Kind.CASH, 1000)


def test_spin_is_deterministic():
    first = [wheel.spin(42, 1, i) for i in range(500)]
    assert first == [wheel.spin(42, 1, i) for i in range(500)]
    assert all(0 <= slot < wheel.SLOTS for slot in first)


def test_spin_depends_on_seed_round_and_index():
    base = [wheel.spin(42, 1, i) for i in range(50)]
    assert base != [wheel.spin(43, 1, i) for i in range(50)]
    assert base != [wheel.spin(42, 2, i) for i in range(50)]
    assert len(set(base)) > 20


@pytest.mark.parametrize(
    "round_number, p_bankrupt",
    [(1, 1 / 9), (2, 1 / 9), (3, 1 / 9), (4, 1 / 12), (5, 1 / 12)],
)
def test_spin_distribution(wheel_spec, round_number, p_bankrupt):
    layout = wheel.layout(wheel_spec, round_number)
    slots = Counter(wheel.spin(42, round_number, i) for i in range(SPINS))
    wedges = Counter()
    bankrupt = 0
    for slot, n in slots.items():
        wedges[layout[slot].number] += n
        if layout[slot].kind is Kind.BANKRUPT:
            bankrupt += n
    assert sorted(wedges) == list(range(1, 25))
    for number, n in wedges.items():
        assert abs(n / SPINS - 1 / 24) <= TOLERANCE / 24, f"wedge {number}: {n}"
    assert abs(bankrupt / SPINS - p_bankrupt) <= TOLERANCE * p_bankrupt


def test_mystery_prize_wedge_is_seeded():
    picks = [wheel.mystery_prize_wedge(seed, 2, (5, 17)) for seed in range(200)]
    assert picks == [wheel.mystery_prize_wedge(seed, 2, (5, 17)) for seed in range(200)]
    assert set(picks) == {5, 17}
    assert 60 < picks.count(5) < 140


def test_spec_rejects_a_wheel_without_24_wedges():
    data = raw_wheel()
    data["base"] = data["base"][:-1]
    with pytest.raises(ValueError):
        WheelSpec.from_dict(data)


def test_spec_rejects_an_overlay_off_a_cash_wedge():
    data = raw_wheel()
    data["rounds"][0]["wild"] = 14  # Bankrupt
    with pytest.raises(ValueError):
        WheelSpec.from_dict(data)


def test_spec_rejects_envelopes_that_do_not_total_24():
    data = raw_wheel()
    data["bonus"]["envelopes"][0]["count"] += 1
    with pytest.raises(ValueError):
        WheelSpec.from_dict(data)
