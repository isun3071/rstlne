"""Self-play variants of the bot: vowels first, and milking whatever the risk. No frozen version turns either on."""

from dataclasses import fields, replace

import pytest
from bot_fixtures import LOST, SURE, view_at

from rstlne import selfplay
from rstlne.engine.state import BuyVowel, Solve, Spin
from rstlne.players.bot import versions
from rstlne.players.bot.player import BotPlayer

V6 = versions.knobs(6)


class Fixed:
    """A reader that always believes the same thing, so a test pins down the decision alone."""
    name = "fixed"

    def __init__(self, belief):
        self.belief = belief

    def read(self, view, refuted=frozenset(), suggested=None):
        return self.belief


def decide(rules, spec, belief, knobs, bank=0, legal=None):
    view, _ = view_at(rules, spec, round_number=1, bank=bank)
    if legal is not None:
        view = replace(view, legal_actions=legal)
    bot = BotPlayer(0, rules, spec, Fixed(belief), version=6, knobs=knobs)
    return bot.decide(view), bot


def test_no_frozen_version_turns_a_variant_on():
    for number in versions.VERSIONS:
        k = versions.knobs(number)
        assert k.vowel_first is None and k.milk_all is False


def test_milking_whatever_the_risk_spins_where_the_bot_would_bank_its_round(rules, wheel_spec):
    plain, _ = decide(rules, wheel_spec, SURE, V6, bank=20_000)
    assert isinstance(plain, Solve)  # $20,000 at stake: one Bankrupt costs more than any spin earns
    milked, bot = decide(rules, wheel_spec, SURE, replace(V6, milk_all=True), bank=20_000)
    assert milked == Spin()
    assert bot.last_call.raw["planner"] == "spin"
    assert bot.experiment


def test_milking_whatever_the_risk_solves_once_spinning_is_over(rules, wheel_spec):
    action, _ = decide(rules, wheel_spec, SURE, replace(V6, milk_all=True), bank=20_000, legal=("buy_vowel", "solve"))
    assert action == Solve("WHEEL OF FORTUNE")  # no vowels: a vowel earns nothing


def test_milking_whatever_the_risk_waits_until_the_bot_knows_the_answer(rules, wheel_spec):
    plain, _ = decide(rules, wheel_spec, LOST, V6, bank=1000)
    action, _ = decide(rules, wheel_spec, LOST, replace(V6, milk_all=True), bank=1000)
    assert action == plain


def test_vowels_first_buys_the_likeliest_vowel_before_anything_else(rules, wheel_spec):
    action, bot = decide(rules, wheel_spec, LOST, replace(V6, vowel_first=0.5), bank=1000)
    assert action == BuyVowel("E")  # E at 60% beats A at 50%
    assert bot.last_call.raw["chose"] == "buy_vowel" and bot.last_call.raw.get("vowel_first") is True


def test_vowels_first_leaves_a_vowel_below_its_bar_to_the_value_function(rules, wheel_spec):
    plain, _ = decide(rules, wheel_spec, LOST, V6, bank=1000)
    action, _ = decide(rules, wheel_spec, LOST, replace(V6, vowel_first=0.7), bank=1000)
    assert action == plain


def test_vowels_first_needs_the_money_for_a_vowel(rules, wheel_spec):
    action, _ = decide(rules, wheel_spec, LOST, replace(V6, vowel_first=0.5), bank=0)
    assert not isinstance(action, BuyVowel)


def test_vowels_first_gives_way_to_the_planner_once_the_answer_is_known(rules, wheel_spec):
    plain, _ = decide(rules, wheel_spec, SURE, V6, bank=1000)
    action, bot = decide(rules, wheel_spec, SURE, replace(V6, vowel_first=0.5), bank=1000)
    assert action == plain and not isinstance(action, BuyVowel)
    assert "planner" in bot.last_call.raw


@pytest.mark.parametrize("pair, knob, value", [("milk_all=true", "milk_all", True), ("vowel_first=0.5", "vowel_first", 0.5)])
def test_self_play_entrants_set_the_variant_knobs(pair, knob, value):
    assert knob in {f.name for f in fields(versions.Knobs)}
    assert getattr(selfplay.Entrant.parse(f"x:version=6+{pair}").knobs(V6), knob) == value
