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


def test_solving_on_sight_takes_the_round_the_moment_the_answer_is_known(rules, wheel_spec):
    """eager_solve at the known-answer level: the self-play variant that never milks."""
    plain, _ = decide(rules, wheel_spec, SURE, V6, bank=0)
    assert plain == Spin()  # nothing banked yet: the planner spins for the consonants
    action, bot = decide(rules, wheel_spec, SURE, replace(V6, eager_solve=V6.known_answer), bank=0)
    assert action == Solve("WHEEL OF FORTUNE") and bot.experiment
    lost, _ = decide(rules, wheel_spec, LOST, replace(V6, eager_solve=V6.known_answer), bank=0)
    assert lost == decide(rules, wheel_spec, LOST, V6, bank=0)[0]  # not sure yet: plays as the plain bot


# Vowel variants (Ian, 2026-11-13): whenever affordable, until every word shows one, or never

from rstlne.engine.rules import public_view as _public_view
from rstlne.engine.state import CallLetter, Phase


def turn(rules, spec, belief, knobs, used="", bank=1000, phase=None, legal=None):
    view, state = view_at(rules, spec, round_number=1, bank=bank)
    if used:
        state = replace(state, round=replace(state.round, used=frozenset(used)))
        view = _public_view(state, 0)
    if phase is not None:
        view = replace(view, phase=phase)
    if legal is not None:
        view = replace(view, legal_actions=legal)
    return BotPlayer(0, rules, spec, Fixed(belief), version=6, knobs=knobs).decide(view)


def test_never_buying_vowels_takes_buy_a_vowel_off_the_table(rules, wheel_spec):
    keen = turn(rules, wheel_spec, LOST, replace(V6, vowel_first=0.1))
    assert isinstance(keen, BuyVowel)  # a bot that would buy one here
    assert not isinstance(turn(rules, wheel_spec, LOST, replace(V6, vowel_first=0.1, never_vowel=True)), BuyVowel)
    action = turn(rules, wheel_spec, LOST, replace(V6, never_vowel=True), legal=("buy_vowel", "solve"))
    assert not isinstance(action, BuyVowel)  # with only a vowel or a solve legal, it solves


def test_covering_buys_vowels_until_every_word_shows_one_then_stops(rules, wheel_spec):
    knobs = replace(V6, vowel_cover=0.1)
    assert turn(rules, wheel_spec, LOST, knobs) == BuyVowel("E")  # WHEEL OF FORTUNE, nothing showing
    assert turn(rules, wheel_spec, LOST, knobs, used="E") == BuyVowel("A")  # E used, OF still shows none: the next likeliest
    covered = turn(rules, wheel_spec, LOST, knobs, used="EO")  # every word shows a vowel
    assert not isinstance(covered, BuyVowel)


def test_covering_respects_its_floor(rules, wheel_spec):
    unlikely = replace(LOST, letters={**LOST.letters, "E": replace(LOST.letters["E"], p_hit=0.05),
                                      "A": replace(LOST.letters["A"], p_hit=0.05)})
    assert not isinstance(turn(rules, wheel_spec, unlikely, replace(V6, vowel_cover=0.1)), BuyVowel)


def test_free_play_calls_the_likeliest_vowel_while_the_answer_is_unknown(rules, wheel_spec):
    plain = turn(rules, wheel_spec, LOST, V6, phase=Phase.FREE_PLAY, legal=("call_letter",))
    vowel = turn(rules, wheel_spec, LOST, replace(V6, free_play_vowel=True), phase=Phase.FREE_PLAY, legal=("call_letter",))
    assert vowel == CallLetter("E") and plain != vowel
    known = turn(rules, wheel_spec, SURE, replace(V6, free_play_vowel=True), phase=Phase.FREE_PLAY, legal=("call_letter",))
    assert known == turn(rules, wheel_spec, SURE, V6, phase=Phase.FREE_PLAY, legal=("call_letter",))


def test_no_frozen_version_turns_on_the_vowel_variants():
    for number in versions.VERSIONS:
        k = versions.knobs(number)
        assert k.free_play_vowel is False and k.vowel_cover is None and k.never_vowel is False


def test_free_play_goes_back_to_consonants_once_every_word_shows_a_vowel(rules, wheel_spec):
    knobs = replace(V6, free_play_vowel=True)
    fp = dict(phase=Phase.FREE_PLAY, legal=("call_letter",))
    covered = turn(rules, wheel_spec, LOST, knobs, used="EO", **fp)
    assert covered == turn(rules, wheel_spec, LOST, V6, used="EO", **fp)


# Hit first (Ian, 2026-11-14): on a consonant call after a spin, the likeliest consonant, before the answer is known

from bot_fixtures import belief as _belief

from rstlne.engine.state import CallConsonant
from rstlne.engine.wheel import Kind, Wedge

# T is likelier, R promises more copies: the plain bot's value function takes R
TRADE = _belief([], oov=1.0, T=(0.9, 1.0), R=(0.5, 3.0), N=(0.3, 1.0), E=(0.6, 1.5))


def on_wedge(rules, spec, belief, knobs, wedge=Wedge(5, Kind.CASH, 900), phase=Phase.CALL_CONSONANT):
    view, _ = view_at(rules, spec, round_number=1, bank=0)
    view = replace(view, phase=phase, wedge=wedge, legal_actions=("call_consonant",))
    bot = BotPlayer(0, rules, spec, Fixed(belief), version=6, knobs=knobs)
    return bot.decide(view), bot


def test_hit_first_calls_the_likeliest_consonant_where_the_bot_would_chase_copies(rules, wheel_spec):
    plain, _ = on_wedge(rules, wheel_spec, TRADE, V6)
    assert plain == CallConsonant("R")  # the trade the variant tests
    action, bot = on_wedge(rules, wheel_spec, TRADE, replace(V6, hit_first=True))
    assert action == CallConsonant("T") and bot.last_call.raw.get("hit_first") is True and bot.experiment


def test_hit_first_breaks_a_tie_in_hit_chance_by_expected_copies(rules, wheel_spec):
    tie = _belief([], oov=1.0, T=(0.8, 1.0), R=(0.8, 2.0), E=(0.6, 1.5))
    action, _ = on_wedge(rules, wheel_spec, tie, replace(V6, hit_first=True))
    assert action == CallConsonant("R")


def test_hit_first_covers_the_wild_cards_extra_consonant(rules, wheel_spec):
    action, _ = on_wedge(rules, wheel_spec, TRADE, replace(V6, hit_first=True), phase=Phase.WILD_CONSONANT)
    assert action == CallConsonant("T")


def test_hit_first_leaves_known_answers_and_free_play_alone(rules, wheel_spec):
    knobs = replace(V6, hit_first=True)
    assert on_wedge(rules, wheel_spec, SURE, knobs)[0] == on_wedge(rules, wheel_spec, SURE, V6)[0]  # the answer is known
    fp = dict(phase=Phase.FREE_PLAY, legal=("call_letter",))
    assert turn(rules, wheel_spec, TRADE, knobs, **fp) == turn(rules, wheel_spec, TRADE, V6, **fp)  # a miss keeps the wheel


def test_no_frozen_version_calls_hit_first_and_a_self_play_entrant_can():
    assert all(versions.knobs(n).hit_first is False for n in versions.VERSIONS)
    assert selfplay.Entrant.parse("hit:version=6+hit_first=true").knobs(V6).hit_first is True
