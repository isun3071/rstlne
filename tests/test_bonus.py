import pytest
from helpers import illegal, set_seat, solve, start

from wof.engine import bonus
from wof.engine.rules import apply, legal_actions, public_view
from wof.engine.state import BonusPicks, BonusSolve, Forfeit, Phase

# The bonus puzzle in helpers is BIG CITY. RSTLNE reveals the T.
PICKS = BonusPicks(("B", "G", "C"), "I")


def to_bonus(rules, wheel_spec, totals=None, seed=7, **cards):
    """A one-round game that seat 0 solves, ending with these game totals."""
    totals = totals or (rules.solve_minimum, 0, 0)
    state = start(rules, wheel_spec, seed=seed, main_rounds=1)
    state = set_seat(state, 0, total=totals[0] - rules.solve_minimum, **cards)
    state = set_seat(set_seat(state, 1, total=totals[1]), 2, total=totals[2])
    return solve(state)


def test_highest_total_plays_the_bonus(rules, wheel_spec):
    state = to_bonus(rules, wheel_spec, totals=(1000, 5000, 3000))
    assert state.phase is Phase.BONUS_PICKS
    assert state.seat == 1
    assert state.round is None


def test_ties_break_by_a_seeded_draw(rules, wheel_spec):
    def player(seed):
        return to_bonus(rules, wheel_spec, totals=(4000, 4000, 1000), seed=seed).seat

    assert {player(seed) for seed in range(40)} == {0, 1}
    assert [player(seed) for seed in range(10)] == [player(seed) for seed in range(10)]


def test_bonus_reveals_rstlne_and_hides_the_envelope(rules, wheel_spec):
    view = public_view(to_bonus(rules, wheel_spec), 0)
    assert view.round_number is None
    assert view.board == "_ _ _   _ _ T _"
    assert view.used_letters == tuple(sorted("RSTLNE"))
    assert view.bonus_consonants == rules.bonus_consonants
    assert view.envelope is None
    assert view.legal_actions == ("bonus_picks",)


def test_picks_reveal_their_letters(rules, wheel_spec):
    state = apply(to_bonus(rules, wheel_spec), PICKS)
    assert state.phase is Phase.BONUS_SOLVE
    assert public_view(state, 0).board == "B I G   C I T _"


@pytest.mark.parametrize(
    "consonants, vowel",
    [
        (("B", "G"), "I"),
        (("B", "G", "C", "D"), "I"),
        (("B", "G", "T"), "I"),
        (("B", "G", "A"), "I"),
        (("B", "G", "C"), "E"),
        (("B", "G", "C"), "D"),
        (("B", "B", "C"), "I"),
        (("B", "G", "7"), "I"),
    ],
    ids=["too few", "too many", "given T", "vowel as consonant", "given E",
         "consonant as vowel", "repeat", "not a letter"],
)
def test_bad_picks_are_rejected(rules, wheel_spec, consonants, vowel):
    illegal(to_bonus(rules, wheel_spec), BonusPicks(consonants, vowel), "bad_picks")


def test_wild_card_adds_a_fourth_consonant(rules, wheel_spec):
    state = to_bonus(rules, wheel_spec, wild=True)
    assert public_view(state, 0).bonus_consonants == rules.bonus_consonants + 1
    illegal(state, PICKS, "bad_picks")
    state = apply(state, BonusPicks(("B", "G", "C", "Y"), "I"))
    assert not state.seats[0].wild
    assert public_view(state, 0).board == "B I G   C I T Y"


def test_bonus_wheel_holds_the_spec_envelopes(wheel_spec):
    expected = [40000] * 6 + [45000] * 6 + [50000] * 6 + [55000] * 5 + [100000]
    assert sorted(bonus.envelopes(wheel_spec, million=False)) == sorted(expected)


def test_million_card_swaps_the_top_envelope(wheel_spec):
    envelopes = bonus.envelopes(wheel_spec, million=True)
    assert len(envelopes) == 24
    assert 100000 not in envelopes
    assert envelopes.count(1_000_000) == 1


def test_envelope_is_seeded(rules, wheel_spec):
    def envelope(seed):
        return to_bonus(rules, wheel_spec, seed=seed).bonus.envelope

    assert envelope(5) == envelope(5)
    assert len({envelope(seed) for seed in range(60)}) > 2


def test_correct_bonus_solve_adds_the_envelope(rules, wheel_spec):
    state = apply(to_bonus(rules, wheel_spec), PICKS)
    envelope, before = state.bonus.envelope, state.seats[0].total
    state = apply(state, BonusSolve("big city"))
    assert state.phase is Phase.GAME_OVER
    assert state.seats[0].total == before + envelope
    assert public_view(state, 0).envelope == envelope
    assert legal_actions(state) == ()


def test_wrong_bonus_solve_adds_nothing(rules, wheel_spec):
    state = apply(to_bonus(rules, wheel_spec), PICKS)
    before = state.seats[0].total
    state = apply(state, BonusSolve("BIG CATS"))
    assert state.phase is Phase.GAME_OVER
    assert state.seats[0].total == before
    assert state.last.outcome == "bonus_missed"


def test_empty_bonus_solve_is_malformed(rules, wheel_spec):
    illegal(apply(to_bonus(rules, wheel_spec), PICKS), BonusSolve(""), "malformed_solve")


def test_forfeited_picks_reveal_nothing_but_the_solve_still_happens(rules, wheel_spec):
    state = apply(to_bonus(rules, wheel_spec), Forfeit())
    assert state.phase is Phase.BONUS_SOLVE
    assert public_view(state, 0).board == "_ _ _   _ _ T _"
    envelope, before = state.bonus.envelope, state.seats[0].total
    assert apply(state, BonusSolve("BIG CITY")).seats[0].total == before + envelope


def test_forfeited_bonus_solve_counts_as_wrong(rules, wheel_spec):
    state = apply(to_bonus(rules, wheel_spec), PICKS)
    before = state.seats[0].total
    state = apply(state, Forfeit())
    assert state.phase is Phase.GAME_OVER and state.seats[0].total == before


def test_million_holder_can_win_the_million(rules, wheel_spec):
    for seed in range(2000):
        state = to_bonus(rules, wheel_spec, seed=seed, million=True)
        if state.bonus.envelope == 1_000_000:
            break
    else:
        pytest.fail("no seed drew the Million envelope")
    before = state.seats[0].total
    state = apply(apply(state, PICKS), BonusSolve("BIG CITY"))
    assert state.seats[0].total == before + 1_000_000
