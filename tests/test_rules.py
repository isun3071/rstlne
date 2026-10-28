import copy
from dataclasses import replace

import pytest
from helpers import BONUS, PUZZLES, illegal, set_seat, solve, spin_to, start, to_round

from wof.engine.rules import apply, current_wheel, legal_actions, new_game, public_view
from wof.engine.state import (
    BuyVowel,
    CallConsonant,
    CallLetter,
    Choose,
    Forfeit,
    Phase,
    SeatState,
    Solve,
    Spin,
    UseWild,
)
from wof.engine.wheel import Kind, Wedge


@pytest.fixture
def game(rules, wheel_spec):
    return start(rules, wheel_spec)  # round 1: WHEEL OF FORTUNE, seat 0 up


@pytest.fixture
def round2(game):
    return to_round(game, 2)  # BANANA SPLIT, seat 1 up


@pytest.fixture
def round3(game):
    return to_round(game, 3)  # GOLDEN GATE BRIDGE, seat 2 up


def at(state, number, third=0):
    return current_wheel(state)[(number - 1) * 3 + third]


def picked_up_wild(game):
    """Seat 0 claims the Wild Card on wedge 2 ($800) with two Fs."""
    return apply(spin_to(game, 2), CallConsonant("F"))


def on_express(round3):
    """Seat 2 lands on Express and calls three Gs."""
    return apply(spin_to(round3, 12), CallConsonant("G"))


def other_mystery(state):
    return ({5, 17} - {state.round.mystery_prize}).pop()


# Setup


def test_new_game_starts_round_1_with_seat_0(game):
    assert game.phase is Phase.TURN
    assert game.seat == 0
    assert game.round.number == 1
    assert all(s == SeatState() for s in game.seats)


def test_new_game_needs_a_puzzle_per_round(rules, wheel_spec):
    with pytest.raises(ValueError):
        new_game(7, rules, wheel_spec, PUZZLES[:3], BONUS)


def test_starting_seat_rotates_each_round(game):
    starts = []
    state = game
    for _ in range(4):
        starts.append(state.seat)
        state = solve(state)
    assert starts == [0, 1, 2, 0]


# Spinning and consonants


def test_correct_consonant_pays_value_times_count_and_keeps_turn(game):
    state = spin_to(game, 3)
    assert state.phase is Phase.CALL_CONSONANT
    assert state.round.wedge == Wedge(3, Kind.CASH, 600)
    state = apply(state, CallConsonant("F"))
    assert state.seats[0].bank == 1200
    assert state.seat == 0 and state.phase is Phase.TURN
    assert "F" in state.round.used


def test_missing_consonant_passes_turn(game):
    state = apply(spin_to(game, 3), CallConsonant("Z"))
    assert state.seats[0].bank == 0
    assert state.seat == 1 and state.phase is Phase.TURN


def test_repeated_consonant_passes_turn(game):
    state = apply(spin_to(game, 3), CallConsonant("F"))
    state = apply(spin_to(state, 3), CallConsonant("F"))
    assert state.seats[0].bank == 1200
    assert state.seat == 1
    assert state.last.outcome == "repeated"


def test_vowel_after_a_spin_is_illegal(game):
    illegal(spin_to(game, 3), CallConsonant("E"), "vowel_on_spin")


def test_non_letter_is_illegal(game):
    illegal(spin_to(game, 3), CallConsonant("7"), "not_a_letter")


def test_lowercase_letters_are_accepted(game):
    assert apply(spin_to(game, 3), CallConsonant("f")).seats[0].bank == 1200


@pytest.mark.parametrize("round_number, top", [(1, 2500), (2, 3500), (3, 3500), (4, 5000)])
def test_top_wedge_pays_the_round_top_value(game, round_number, top):
    state = to_round(game, round_number)
    seat = state.seat
    state = apply(spin_to(state, 1), CallConsonant("T"))  # one T in every test puzzle
    assert state.seats[seat].bank == top


def test_bankrupt_zeroes_round_bank_and_cards_but_not_totals(game):
    state = set_seat(game, 0, bank=1500, total=3000, wild=True, million=True)
    state = spin_to(state, 14)
    assert state.seats[0] == SeatState(total=3000, bank=0, wild=False, million=False)
    assert state.seat == 1
    assert state.last.outcome == "bankrupt"


def test_lose_a_turn_passes_turn(game):
    state = spin_to(set_seat(game, 0, bank=1500), 18)
    assert state.seat == 1 and state.seats[0].bank == 1500


def test_spin_is_illegal_once_every_consonant_is_revealed(game):
    state = replace(game, round=replace(game.round, used=frozenset("WHLFRTN")))
    assert "spin" not in legal_actions(state)
    illegal(state, Spin(), "not_legal_now")


# Vowels


def test_buy_vowel_is_illegal_below_its_cost(game, rules):
    state = set_seat(game, 0, bank=rules.vowel_cost - 1)
    assert "buy_vowel" not in legal_actions(state)
    illegal(state, BuyVowel("E"), "insufficient_funds")


def test_present_vowel_costs_and_keeps_turn(game, rules):
    state = apply(set_seat(game, 0, bank=1000), BuyVowel("E"))
    assert state.seats[0].bank == 1000 - rules.vowel_cost
    assert state.seat == 0 and "E" in state.round.used


def test_missing_vowel_costs_and_passes_turn(game, rules):
    state = apply(set_seat(game, 0, bank=1000), BuyVowel("A"))
    assert state.seats[0].bank == 1000 - rules.vowel_cost
    assert state.seat == 1


def test_repeated_vowel_passes_turn(game):
    state = apply(set_seat(game, 0, bank=1000), BuyVowel("E"))
    state = apply(state, BuyVowel("E"))
    assert state.seat == 1 and state.last.outcome == "repeated"


def test_consonant_on_a_vowel_buy_is_illegal(game):
    illegal(set_seat(game, 0, bank=1000), BuyVowel("T"), "consonant_on_vowel_buy")


def test_buy_vowel_is_illegal_once_every_vowel_is_revealed(game):
    state = set_seat(game, 0, bank=1000)
    state = replace(state, round=replace(state.round, used=frozenset("EOU")))
    assert "buy_vowel" not in legal_actions(state)
    illegal(state, BuyVowel("A"), "not_legal_now")


# Solving


def test_correct_solve_banks_the_round_and_starts_the_next(game):
    state = apply(set_seat(game, 0, bank=2000), Solve("wheel of fortune"))
    assert state.seats[0].total == 2000
    assert state.round.number == 2
    assert all(s.bank == 0 for s in state.seats)
    assert "round_over" in state.last.events


def test_solver_under_the_minimum_is_raised(game, rules):
    state = apply(set_seat(game, 0, bank=300), Solve("WHEEL OF FORTUNE"))
    assert state.seats[0].total == rules.solve_minimum


def test_only_the_solver_banks(game, rules):
    state = solve(set_seat(set_seat(game, 1, bank=4000), 2, bank=5000))
    assert [s.total for s in state.seats] == [rules.solve_minimum, 0, 0]


def test_wrong_solve_passes_turn(game):
    state = apply(set_seat(game, 0, bank=700), Solve("WHEEL OF FORTUNES"))
    assert state.seat == 1 and state.seats[0].bank == 700


def test_empty_solve_is_malformed(game):
    illegal(game, Solve("   "), "malformed_solve")


def test_solve_must_keep_punctuation(game):
    state = to_round(game, 4)  # WELL-KNOWN FACT
    seat = state.seat
    state = apply(state, Solve("WELL KNOWN FACT"))
    assert state.round.number == 4 and state.seat != seat


# Free Play


def test_free_play_consonant_pays_its_value(game, wheel_spec):
    state = spin_to(game, 16)
    assert state.phase is Phase.FREE_PLAY
    state = apply(state, CallLetter("F"))
    assert state.seats[0].bank == wheel_spec.free_play * 2
    assert state.seat == 0 and state.phase is Phase.TURN


def test_free_play_vowel_is_free(game):
    state = apply(spin_to(game, 16), CallLetter("E"))
    assert state.seats[0].bank == 0 and "E" in state.round.used and state.seat == 0


@pytest.mark.parametrize("letter", ["Z", "A"])
def test_free_play_wrong_letter_keeps_turn(game, letter):
    state = apply(spin_to(game, 16), CallLetter(letter))
    assert state.seat == 0 and state.phase is Phase.TURN


def test_free_play_repeated_letter_keeps_turn(game):
    state = apply(spin_to(game, 3), CallConsonant("F"))
    state = apply(spin_to(state, 16), CallLetter("F"))
    assert state.seat == 0 and state.seats[0].bank == 1200
    assert state.last.outcome == "repeated"


def test_free_play_takes_a_letter_not_a_solve(game):
    state = spin_to(game, 16)
    assert set(legal_actions(state)) == {"call_letter", "forfeit"}
    illegal(state, Solve("WHEEL OF FORTUNE"), "not_legal_now")


def test_wild_card_is_not_offered_on_free_play(game):
    state = apply(spin_to(set_seat(game, 0, wild=True), 16), CallLetter("F"))
    assert state.phase is Phase.TURN


# Wild Card


def test_wild_card_pickup_pays_and_leaves_the_wheel(game):
    state = spin_to(game, 2)
    assert state.round.wedge.wild
    state = apply(state, CallConsonant("F"))
    assert state.seats[0].bank == 1600
    assert state.seats[0].wild
    assert not state.round.wild_on_wheel
    assert state.phase is Phase.WILD_CHOICE  # spendable on the spin that claimed it
    state = spin_to(apply(state, UseWild(False)), 2)
    assert state.round.wedge == Wedge(2, Kind.CASH, 800)


def test_spending_the_wild_card_calls_an_extra_consonant_at_the_same_value(game):
    state = apply(picked_up_wild(game), UseWild(True))
    assert state.phase is Phase.WILD_CONSONANT and not state.seats[0].wild
    state = apply(state, CallConsonant("T"))
    assert state.seats[0].bank == 1600 + 800
    assert state.seat == 0 and state.phase is Phase.TURN


@pytest.mark.parametrize("letter", ["Z", "F"])
def test_missing_or_repeated_wild_consonant_passes_turn_and_spends_the_card(game, letter):
    state = apply(apply(picked_up_wild(game), UseWild(True)), CallConsonant(letter))
    assert state.seat == 1 and not state.seats[0].wild
    assert state.seats[0].bank == 1600


def test_declining_keeps_the_wild_card(game):
    state = apply(picked_up_wild(game), UseWild(False))
    assert state.phase is Phase.TURN and state.seats[0].wild


@pytest.mark.parametrize("number", [1, 3])  # TOP and a cash wedge
def test_wild_card_is_offered_on_plain_dollar_wedges(game, number):
    state = apply(spin_to(set_seat(game, 0, wild=True), number), CallConsonant("F"))
    assert state.phase is Phase.WILD_CHOICE


def test_wild_card_stays_across_rounds_without_solving(game):
    state = apply(picked_up_wild(game), UseWild(False))
    state = solve(apply(state, Solve("WRONG")))  # seat 0 misses, seat 1 solves
    assert state.round.number == 2
    assert state.seats[0].wild
    assert not state.round.wild_on_wheel
    assert not at(state, 2).wild


def test_wild_card_lost_to_bankrupt_returns_next_round(game):
    state = solve(apply(picked_up_wild(game), UseWild(False)))  # round 2, seat 1 up
    state = apply(apply(state, Forfeit()), Forfeit())
    assert state.seat == 0
    state = spin_to(state, 14)
    assert not state.seats[0].wild
    assert not state.round.wild_on_wheel  # off for the rest of the round
    state = solve(state)
    assert state.round.number == 3 and state.round.wild_on_wheel
    assert at(state, 2).wild


# Million wedge


@pytest.mark.parametrize("third", [0, 2])
def test_million_outer_thirds_are_bankrupt(game, third):
    state = spin_to(set_seat(game, 0, bank=900), 9, third=third)
    assert state.last.outcome == "bankrupt"
    assert state.seats[0].bank == 0 and state.seat == 1


def test_million_center_pays_its_value_and_hands_the_card(game, wheel_spec):
    state = apply(spin_to(set_seat(game, 0, wild=True), 9, third=1), CallConsonant("F"))
    assert state.seats[0].bank == wheel_spec.million_center * 2
    assert state.seats[0].million
    assert state.phase is Phase.TURN  # no Wild Card offer on the Million wedge


def test_whole_million_wedge_leaves_after_pickup(game):
    state = apply(spin_to(game, 9, third=1), CallConsonant("F"))
    assert [at(state, 9, t) for t in range(3)] == [Wedge(9, Kind.CASH, 800)] * 3
    state = spin_to(state, 9, third=0)
    assert state.round.wedge == Wedge(9, Kind.CASH, 800)


def test_million_card_is_kept_by_solving_the_round(game):
    state = solve(apply(spin_to(game, 9, third=1), CallConsonant("F")))
    assert state.seats[0].million
    assert not state.round.million_on_wheel


def test_million_card_is_lost_when_another_seat_solves(game):
    state = apply(spin_to(game, 9, third=1), CallConsonant("F"))
    state = solve(apply(state, Forfeit()))  # seat 0 passes, seat 1 solves
    assert not state.seats[0].million
    assert state.round.million_on_wheel


def test_million_card_lost_to_bankrupt_across_rounds(game):
    state = solve(apply(spin_to(game, 9, third=1), CallConsonant("F")))  # round 2, seat 1 up
    state = apply(apply(state, Forfeit()), Forfeit())
    state = spin_to(state, 14)
    assert not state.seats[0].million
    assert not state.round.million_on_wheel
    state = solve(state)
    assert state.round.number == 3 and state.round.million_on_wheel


# Mystery


def test_mystery_keep_pays_face_value(round2, wheel_spec):
    state = apply(spin_to(round2, 5), CallConsonant("N"))
    assert state.phase is Phase.MYSTERY_CHOICE and state.seats[1].bank == 0
    state = apply(state, Choose("keep"))
    assert state.seats[1].bank == wheel_spec.mystery_face * 2
    assert state.phase is Phase.TURN and state.seat == 1


def test_mystery_flip_to_the_prize_keeps_the_turn(round2, wheel_spec):
    state = set_seat(round2, 1, bank=700)
    state = apply(spin_to(state, round2.round.mystery_prize), CallConsonant("N"))
    state = apply(state, Choose("flip"))
    assert state.seats[1].bank == 700 + wheel_spec.mystery_prize
    assert state.seat == 1 and state.phase is Phase.TURN
    assert state.last.outcome == "flipped_prize"


def test_mystery_flip_to_bankrupt(round2):
    state = set_seat(round2, 1, bank=700, wild=True)
    state = apply(spin_to(state, other_mystery(round2)), CallConsonant("N"))
    state = apply(state, Choose("flip"))
    assert state.seats[1].bank == 0 and not state.seats[1].wild
    assert state.seat == 2
    assert state.last.outcome == "flipped_bankrupt"


@pytest.mark.parametrize("flip_prize", [True, False])
def test_after_a_flip_the_flipped_wedge_leaves_and_the_other_plays_plain(round2, wheel_spec, flip_prize):
    flipped = round2.round.mystery_prize if flip_prize else other_mystery(round2)
    other = ({5, 17} - {flipped}).pop()
    state = apply(spin_to(round2, flipped), CallConsonant("N"))
    state = apply(state, Choose("flip"))
    assert at(state, flipped) == Wedge(flipped, Kind.CASH, {5: 600, 17: 700}[flipped])
    state = spin_to(state, other)
    assert state.round.wedge == Wedge(other, Kind.CASH, wheel_spec.mystery_face)
    seat, before = state.seat, state.seats[state.seat].bank
    state = apply(state, CallConsonant("B"))
    assert state.phase is Phase.TURN  # no keep or flip this time
    assert state.seats[seat].bank == before + wheel_spec.mystery_face


def test_wild_card_is_offered_on_the_plain_second_mystery(round2):
    state = set_seat(round2, 1, wild=True)
    state = apply(spin_to(state, round2.round.mystery_prize), CallConsonant("N"))
    state = apply(state, Choose("flip"))
    state = apply(spin_to(state, other_mystery(round2)), CallConsonant("B"))
    assert state.phase is Phase.WILD_CHOICE


def test_wild_card_is_not_offered_after_a_mystery_keep(round2):
    state = apply(spin_to(set_seat(round2, 1, wild=True), 5), CallConsonant("N"))
    assert apply(state, Choose("keep")).phase is Phase.TURN


# Express


def test_express_consonant_pays_and_offers_pass_or_play(round3, wheel_spec):
    state = on_express(round3)
    assert state.seats[2].bank == wheel_spec.express * 3
    assert state.phase is Phase.EXPRESS_CHOICE
    assert set(legal_actions(state)) == {"pass", "play", "forfeit"}


def test_express_pass_continues_normal_play(round3):
    state = apply(on_express(set_seat(round3, 2, wild=True)), Choose("pass"))
    assert state.phase is Phase.TURN  # no Wild Card offer on Express
    assert state.seat == 2 and not state.round.express


def test_express_ride_calls_and_buys_without_spinning(round3, rules, wheel_spec):
    state = apply(on_express(round3), Choose("play"))
    assert state.phase is Phase.EXPRESS and state.round.express
    assert set(legal_actions(state)) == {"call_consonant", "buy_vowel", "solve", "forfeit"}
    state = apply(state, CallConsonant("D"))
    assert state.seats[2].bank == wheel_spec.express * 5
    state = apply(state, BuyVowel("E"))
    assert state.seats[2].bank == wheel_spec.express * 5 - rules.express_vowel_cost
    assert state.phase is Phase.EXPRESS
    state = apply(state, Solve("golden gate bridge"))
    assert state.seats[2].total == wheel_spec.express * 5 - rules.express_vowel_cost
    assert state.round.number == 4


@pytest.mark.parametrize(
    "action",
    [CallConsonant("Z"), CallConsonant("G"), BuyVowel("U"), Solve("GOLDEN GATE PARK"), Forfeit()],
    ids=["wrong letter", "repeated letter", "wrong vowel", "wrong solve", "forfeit"],
)
def test_express_bust_counts_as_bankrupt(round3, action):
    state = apply(on_express(set_seat(round3, 2, million=True)), Choose("play"))
    state = apply(state, action)
    assert state.seats[2].bank == 0 and not state.seats[2].million
    assert state.seat == 0 and not state.round.express
    assert "bankrupt" in state.last.events


def test_express_consonant_call_is_illegal_once_consonants_run_out(round3):
    state = apply(on_express(round3), Choose("play"))
    state = replace(state, round=replace(state.round, used=state.round.used | frozenset("GLDNTBR")))
    assert "call_consonant" not in legal_actions(state)
    illegal(state, CallConsonant("Z"), "not_legal_now")


def test_express_vowel_buy_needs_its_cost(round3, rules):
    state = apply(on_express(round3), Choose("play"))
    state = set_seat(state, 2, bank=rules.express_vowel_cost - 1)
    illegal(state, BuyVowel("E"), "insufficient_funds")


# Forfeits after a third invalid response


def test_forfeit_at_the_start_of_a_turn_passes_it(game):
    state = apply(set_seat(game, 0, bank=900), Forfeit())
    assert state.seat == 1 and state.seats[0].bank == 900


def test_forfeit_after_a_spin_passes_the_turn(game):
    assert apply(spin_to(game, 3), Forfeit()).seat == 1


def test_forfeit_on_mystery_keeps_then_passes(round2, wheel_spec):
    state = apply(apply(spin_to(round2, 5), CallConsonant("N")), Forfeit())
    assert state.seats[1].bank == wheel_spec.mystery_face * 2
    assert state.seat == 2


def test_forfeit_on_express_passes_the_ride_and_the_turn(round3, wheel_spec):
    state = apply(on_express(round3), Forfeit())
    assert state.seats[2].bank == wheel_spec.express * 3
    assert state.seat == 0 and not state.round.express


def test_forfeit_on_the_wild_card_keeps_it_and_passes(game):
    state = apply(picked_up_wild(game), Forfeit())
    assert state.seats[0].wild and state.seat == 1


# Turn cap


def test_round_ends_with_no_solver_at_the_turn_cap(rules, wheel_spec):
    state = start(rules, wheel_spec, max_turns_per_round=3)
    state = apply(spin_to(state, 9, third=1), CallConsonant("F"))  # seat 0 claims the Million card
    for _ in range(3):
        state = apply(state, Forfeit())
    assert state.round.number == 2
    assert [s.total for s in state.seats] == [0, 0, 0]
    assert not state.seats[0].million
    assert "turn_cap" in state.last.events


# Engine contract


def test_apply_never_mutates_the_old_state(game):
    landed = spin_to(game, 2)
    snapshot = copy.deepcopy(landed)
    apply(landed, CallConsonant("F"))
    apply(landed, Forfeit())
    assert landed == snapshot


def test_actions_outside_the_legal_list_are_rejected(game):
    illegal(game, Choose("keep"), "not_legal_now")
    illegal(game, CallConsonant("T"), "not_legal_now")
    illegal(spin_to(game, 3), Spin(), "not_legal_now")
    illegal(picked_up_wild(game), Choose("maybe"), "not_legal_now")


# Public view


def test_view_shows_the_public_table(game):
    state = apply(spin_to(set_seat(game, 2, total=1000), 3), CallConsonant("F"))
    view = public_view(state, 0)
    assert view.round_number == 1
    assert view.category == "Phrase"
    assert view.board == "_ _ _ _ _   _ F   F _ _ _ _ _ _"
    assert view.used_letters == ("F",)
    assert view.banks == (1200, 0, 0)
    assert view.totals == (0, 0, 1000)
    assert view.turn == 0
    assert view.wedge == Wedge(3, Kind.CASH, 600)
    assert view.legal_actions == ("spin", "buy_vowel", "solve")


def test_only_the_acting_seat_sees_legal_actions_and_never_forfeit(game):
    assert public_view(game, 1).legal_actions == ()
    assert "forfeit" not in public_view(game, 0).legal_actions


def test_view_shows_held_cards(game):
    state = apply(picked_up_wild(game), UseWild(False))
    view = public_view(state, 1)
    assert view.wild_cards == (True, False, False)
    assert view.million_cards == (False, False, False)


def test_express_view_says_so(round3):
    view = public_view(apply(on_express(round3), Choose("play")), 2)
    assert view.express
    assert set(view.legal_actions) == {"call_consonant", "buy_vowel", "solve"}
