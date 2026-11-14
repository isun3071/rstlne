"""Version 7's letter fixes: wheel credit, copy shrink, and the reveal fit. Each changes which consonant the bot calls
after a spin, never whether it spins; each is off in versions 1 to 6."""

from dataclasses import replace

from bot_fixtures import belief, view_at

from rstlne.engine.state import CallConsonant, Phase
from rstlne.engine.wheel import Kind, Wedge
from rstlne.players.bot import versions
from rstlne.players.bot.player import BotPlayer

V6 = versions.knobs(6)
CASH = Wedge(5, Kind.CASH, 900)
# T is likelier, R promises more copies: version 6 calls R
TRADE = belief([], oov=1.0, T=(0.9, 1.0), R=(0.5, 3.0), N=(0.3, 1.0), E=(0.6, 1.5))
BIG_GAIN = ((1, ((0, (5000.0,) * 20),)),)  # a bot table where a bot adds $5,000 before it solves


class Fixed:
    name = "fixed"

    def __init__(self, b):
        self.b = b

    def read(self, view, refuted=frozenset(), suggested=None):
        return self.b


def bot(rules, spec, b, knobs):
    return BotPlayer(0, rules, spec, Fixed(b), version=6, knobs=knobs)


def call_on(rules, spec, b, knobs, phase=Phase.CALL_CONSONANT):
    view, _ = view_at(rules, spec, round_number=1, bank=0)
    view = replace(view, phase=phase, wedge=CASH, legal_actions=("call_consonant",))
    player = bot(rules, spec, b, knobs)
    return player.decide(view), player


def situation(rules, spec, b, knobs):
    view, _ = view_at(rules, spec, round_number=1, bank=0)
    player = bot(rules, spec, b, knobs)
    return player._situation(view, b)


def test_wheel_credit_makes_a_miss_cost_the_spins_it_gives_up(rules, wheel_spec):
    assert call_on(rules, wheel_spec, TRADE, V6)[0] == CallConsonant("R")
    credited = replace(V6, wheel_credit=True, stealer_gain_bot=BIG_GAIN)
    assert call_on(rules, wheel_spec, TRADE, credited)[0] == CallConsonant("T")
    assert call_on(rules, wheel_spec, TRADE, credited, phase=Phase.WILD_CONSONANT)[0] == CallConsonant("T")


def test_wheel_credit_counts_the_bot_tables_mean_gain(rules, wheel_spec):
    s = situation(rules, wheel_spec, TRADE, replace(V6, wheel_credit=True, stealer_gain_bot=BIG_GAIN))
    assert s.own_gain() == 5000.0
    assert s.call("T", 900, fixes=True).main > s.call("T", 900).main  # the hit now banks the spins it keeps


def test_the_letter_fixes_leave_the_turn_choice_alone(rules, wheel_spec):
    view, _ = view_at(rules, wheel_spec, round_number=1, bank=1000)
    fixed = replace(V6, wheel_credit=True, stealer_gain_bot=BIG_GAIN, copy_shrink=0.0, reveal_fit=((0.0, 1.0), (1.0, 1.0)))
    plain, v7 = bot(rules, wheel_spec, TRADE, V6), bot(rules, wheel_spec, TRADE, fixed)
    assert plain.decide(view) == v7.decide(view)
    assert plain.last_call.raw["values"] == v7.last_call.raw["values"]  # the spin is worth the same: its calls use no fix


def test_copy_shrink_scales_the_copies_beyond_the_first(rules, wheel_spec):
    none, half, full = (situation(rules, wheel_spec, TRADE, replace(V6, copy_shrink=k)) for k in (0.0, 0.5, 1.0))
    r = [x.call("R", 900, fixes=True).main for x in (none, half, full)]
    assert r[0] < r[1] < r[2] and r[2] == full.call("R", 900).main  # 1, 2 and 3 copies; a shrink of 1 changes nothing
    assert none.call("T", 900, fixes=True).main == none.call("T", 900).main  # one copy expected: nothing to shrink
    assert call_on(rules, wheel_spec, TRADE, replace(V6, copy_shrink=0.0))[0] == CallConsonant("T")


def test_the_reveal_fit_reads_the_confidence_after_a_hit_off_its_curve(rules, wheel_spec):
    certain = replace(V6, reveal_fit=((0.0, 1.0), (1.0, 1.0)))  # every hit leaves the bot sure
    hopeless = replace(V6, reveal_fit=((0.0, 0.0), (1.0, 0.0)))  # no hit helps
    sure, lost = situation(rules, wheel_spec, TRADE, certain), situation(rules, wheel_spec, TRADE, hopeless)
    assert sure.call("T", 900, fixes=True).main > lost.call("T", 900, fixes=True).main
    assert sure.call("T", 900).main == lost.call("T", 900).main  # off the letter call, the curve is not read


def test_no_version_before_7_turns_a_letter_fix_on():
    for number in range(1, 7):
        k = versions.knobs(number)
        assert k.wheel_credit is False and k.copy_shrink is None and k.reveal_fit == ()
