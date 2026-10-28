import pytest
from bot_fixtures import LOST, SURE, belief, view_at

from rstlne.engine.wheel import Kind, Wedge
from rstlne.players.bot import versions
from rstlne.players.bot.objective import Objective
from rstlne.players.bot.steal import Odds
from rstlne.players.bot.value import Situation

KNOBS = versions.knobs(1)
CALM = Odds((1, 2), 0.0, 0.0)  # nobody ever steals
RISKY = Odds((1, 2), 0.5, 0.5)


def situation(rules, spec, b, odds=CALM, wheel=None, **view):
    v, _ = view_at(rules, spec, **view)
    return Situation(v, b, Objective(v, rules, spec, KNOBS), odds, rules, spec, KNOBS, wheel=wheel)


def only(*wedges):
    """A wheel of these wedges, each on an equal share of the 72 thirds."""
    thirds = []
    for w in wedges:
        thirds += [w] * (72 // len(wedges))
    return tuple(thirds)


CASH = Wedge(3, Kind.CASH, 600)
BANKRUPT = Wedge(14, Kind.BANKRUPT)


def test_the_race_from_a_board(rules, wheel_spec):
    s = situation(rules, wheel_spec, LOST, odds=RISKY)
    p = RISKY.total
    assert s.race(0.6) == pytest.approx(0.6 / (0.6 + 0.4 * p))
    assert s.race(1.0) == 1.0 and s.race(0.0) == 0.0
    assert situation(rules, wheel_spec, LOST).race(0.1) == 1.0  # with no steals the bot wins eventually


def test_a_sure_answer_solves_and_banks_at_least_the_minimum(rules, wheel_spec):
    s = situation(rules, wheel_spec, SURE, odds=RISKY, wheel=only(CASH, BANKRUPT))  # a $600 hit adds nothing under the minimum
    assert s.solve().main == 1000
    assert s.choose_turn(("spin", "solve")) == "solve"


def test_losing_control_costs_the_whole_round_including_the_minimum(rules, wheel_spec):
    s = situation(rules, wheel_spec, SURE, odds=Odds((1, 2), 1.0, 0.0), bank=0)
    assert s.lose_wheel(0, 1.0, wild=False, million=False).main == 0  # the next seat always steals


def test_a_spin_counts_bankrupt_once_in_its_own_branch(rules, wheel_spec):
    s = situation(rules, wheel_spec, LOST, odds=RISKY, wheel=only(BANKRUPT), bank=3000)
    assert s.spin() == s.lose_wheel(0, s.c, wild=False, million=False)


def test_a_call_pays_p_hit_times_value_times_count_given_a_hit(rules, wheel_spec):
    b = belief([], oov=1.0, T=(0.5, 2.0), N=(1.0, 1.0))
    s = situation(rules, wheel_spec, b, wheel=only(CASH), bank=2000)  # no steals: the race is 1, and no minimum
    gain = s.call("T", 600).main - s.call("Z", 600).main
    assert gain == pytest.approx(0.5 * 600 * 2.0)


def test_held_cards_count_in_the_bank_and_bankrupt_takes_them(rules, wheel_spec):
    with_card = situation(rules, wheel_spec, LOST, odds=RISKY, wheel=only(BANKRUPT), wild=True)
    without = situation(rules, wheel_spec, LOST, odds=RISKY, wheel=only(BANKRUPT))
    assert with_card.spin() == without.spin()  # Bankrupt took the card
    assert with_card.leaf(0, 0.5, wild=True, million=False).main > without.leaf(0, 0.5, wild=False, million=False).main


def test_spin_while_unsure_and_the_wheel_is_kind(rules, wheel_spec):
    b = belief([("WHEEL OF FORTUNE", 0.3)], oov=0.7, T=(0.95, 1.0), N=(0.9, 1.0), E=(0.9, 3.0))
    s = situation(rules, wheel_spec, b, odds=Odds((1, 2), 0.05, 0.05), wheel=only(CASH))
    assert s.choose_turn(("spin", "solve")) == "spin"


def test_the_vowel_bought_is_the_one_that_tells_answers_apart(rules, wheel_spec):
    b = belief([("CAT", 0.5), ("COT", 0.5)], A=(0.5, 1.0), O=(0.5, 1.0), E=(0.0, 0.0))
    s = situation(rules, wheel_spec, b, odds=RISKY, bank=2000)
    letter, value = s.vowel()
    assert letter in ("A", "O")
    assert value.main > s.vowel_value("E").main
    hit = s.leaf(1750, 1.0, wild=False, million=False)  # the $250 is paid either way, and the bot is then sure
    miss = s.lose_wheel(1750, 1.0, wild=False, million=False)  # but a miss passes the wheel
    assert value.main == pytest.approx(0.5 * hit.main + 0.5 * miss.main)


def test_a_commanding_lead_solves_at_once_in_the_last_round(rules, wheel_spec):
    b = belief([("WHEEL OF FORTUNE", 0.7)], oov=0.3, T=(0.9, 1.0), N=(0.9, 1.0))
    s = situation(rules, wheel_spec, b, odds=Odds((1, 2), 0.5, 0.3), round_number=4, totals=(9000, 8000, 0),
                  wheel=only(CASH, BANKRUPT))
    assert s.goal.win_mode
    assert s.choose_turn(("spin", "buy_vowel", "solve")) == "solve"


def test_mystery_flips_a_small_bank_and_keeps_a_big_one(rules, wheel_spec):
    assert situation(rules, wheel_spec, LOST, round_number=2, bank=500).mystery(k=1) == "flip"
    half = belief([("WHEEL OF FORTUNE", 0.5)], oov=0.5)
    assert situation(rules, wheel_spec, half, odds=RISKY, round_number=2, bank=15000).mystery(k=2) == "keep"


def test_board_the_express_only_when_sure_enough_to_succeed(rules, wheel_spec):
    sure = belief([("WHEEL OF FORTUNE", 0.98)], oov=0.02, W=(1.0, 1.0), H=(1.0, 1.0), F=(1.0, 1.0), R=(1.0, 1.0))
    unsure = belief([("WHEEL OF FORTUNE", 0.3)], oov=0.7, T=(0.6, 1.0))
    assert situation(rules, wheel_spec, sure, odds=RISKY, round_number=3, bank=1000).express() == "play"
    assert situation(rules, wheel_spec, unsure, odds=RISKY, round_number=3, bank=1000).express() == "pass"


def test_ride_the_express_on_safe_consonants_then_solve(rules, wheel_spec):
    b = belief([("WHEEL OF FORTUNE", 0.9)], oov=0.1, W=(1.0, 1.0), H=(0.995, 1.0), T=(0.5, 1.0))
    s = situation(rules, wheel_spec, b, round_number=3)
    assert s.express_move(("call_consonant", "buy_vowel", "solve")) == ("call_consonant", "W")
    done = belief([("WHEEL OF FORTUNE", 0.9)], oov=0.1, T=(0.5, 1.0))
    assert situation(rules, wheel_spec, done, round_number=3).express_move(("call_consonant", "buy_vowel", "solve")) == ("solve", None)


def test_the_wild_card_is_spent_when_the_call_beats_its_value_and_kept_on_a_near_tie_later(rules, wheel_spec):
    sure_hit = belief([], oov=1.0, T=(1.0, 3.0))
    early = situation(rules, wheel_spec, sure_hit, wild=True)
    assert early.wild(Wedge(1, Kind.CASH, 2500)) is True  # $7,500 for sure beats the card's bonus value
    assert early.wild(Wedge(3, Kind.CASH, 600)) is False  # $1,800 doesn't
    long_shot = belief([], oov=1.0, T=(0.3, 1.0))
    late = situation(rules, wheel_spec, long_shot, odds=RISKY, round_number=3, totals=(20000, 0, 0), wild=True)
    assert late.wild(Wedge(3, Kind.CASH, 900)) is False


def test_free_play_misses_keep_the_wheel(rules, wheel_spec):
    b = belief([], oov=1.0, T=(0.5, 1.0), E=(0.9, 2.0))
    s = situation(rules, wheel_spec, b, bank=2000)
    letter, value = s.free_play()
    assert letter == "T"  # money on a consonant; a vowel is free but earns nothing
    assert value.main >= s.leaf(0, s.c, wild=False, million=False).main


def test_holding_the_wheel_counts_for_more_than_c_alone(rules, wheel_spec):
    """With nothing recognized yet, the bot can still reveal letters on its turn, so it races at the seats' prior."""
    v, _ = view_at(rules, wheel_spec, bank=2000)
    goal = Objective(v, rules, wheel_spec, KNOBS)
    flat = Situation(v, LOST, goal, RISKY, rules, wheel_spec, KNOBS)
    keen = Situation(v, LOST, goal, RISKY, rules, wheel_spec, KNOBS, turn_chance=lambda c: max(c, 0.2))
    assert flat.race(0.0) == 0.0 and keen.race(0.0) > 0
    assert keen.leaf(2000, 0.0, False, False).main > keen.lose_wheel(2000, 0.0, False, False).main


def test_with_no_answer_the_bot_never_wastes_its_turn_on_a_guess(rules, wheel_spec):
    s = situation(rules, wheel_spec, LOST, odds=RISKY, bank=2000)
    assert "solve" not in s.turn_options(("spin", "buy_vowel", "solve"))
    assert s.turn_options(("solve",)).keys() == {"solve"}  # unless solving is the only move
