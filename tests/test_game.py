from dataclasses import fields

from helpers import solve, start

from rstlne.engine.rules import apply, public_view
from rstlne.engine.state import (
    BonusPicks,
    BonusSolve,
    BuyVowel,
    CallConsonant,
    CallLetter,
    Choose,
    Phase,
    Solve,
    Spin,
    UseWild,
)

FREQUENCY = "TNSHRDLCMWFGYPBVKJXQZ"
VIEW_FIELDS = {
    "seat", "phase", "round_number", "category", "board", "used_letters", "banks", "totals",
    "wild_cards", "million_cards", "turn", "wedge", "express", "legal_actions",
    "bonus_consonants", "envelope",
}


def policy(state):
    """A scripted player that wanders into every special wedge path. It peeks at
    the answer only to end rounds, which a real player never can."""
    view = public_view(state, state.seat)
    legal = view.legal_actions
    used = set(view.used_letters)
    fresh = [c for c in FREQUENCY if c not in used]
    answer = (state.round or state.bonus).puzzle.answer
    bank = view.banks[state.seat]
    coin = (state.round.spin_index if state.round else state.seed) % 2

    if "bonus_picks" in legal:
        return BonusPicks(tuple(fresh[: view.bonus_consonants]), next(v for v in "AIOU" if v not in used))
    if "bonus_solve" in legal:
        return BonusSolve(answer if coin else "NOT IT")
    if "call_consonant" in legal:
        return CallConsonant(fresh[0] if fresh else "Z")
    if "call_letter" in legal:
        return CallLetter(fresh[0] if fresh else "A")
    if "keep" in legal:
        return Choose("flip" if coin else "keep")
    if "play" in legal:
        return Choose("play" if coin else "pass")
    if "use_wild" in legal:
        return UseWild(bool(coin))
    if "spin" in legal and bank < 5000:
        return Spin()
    if "buy_vowel" in legal:
        return BuyVowel(next(v for v in "EAOIU" if v not in used))
    return Solve(answer)


def play(seed, rules, wheel_spec):
    state = start(rules, wheel_spec, seed=seed)
    history = [state]
    while state.phase is not Phase.GAME_OVER:
        state = apply(state, policy(state))
        history.append(state)
        assert len(history) < 5000, "game did not finish"
    return history


def test_a_full_game_runs_four_rounds_then_the_bonus(rules, wheel_spec):
    state = start(rules, wheel_spec)
    for _ in range(4):
        state = solve(state)
    m = rules.solve_minimum
    assert [s.total for s in state.seats] == [2 * m, m, m]
    assert state.phase is Phase.BONUS_PICKS and state.seat == 0
    state = apply(state, BonusPicks(("B", "G", "C"), "I"))
    envelope = state.bonus.envelope
    state = apply(state, BonusSolve("BIG CITY"))
    assert state.phase is Phase.GAME_OVER
    assert state.seats[0].total == 2 * m + envelope


def test_no_bonus_round_when_config_turns_it_off(rules, wheel_spec):
    state = start(rules, wheel_spec, bonus_round=False)
    for _ in range(4):
        state = solve(state)
    assert state.phase is Phase.GAME_OVER


def test_main_round_count_comes_from_config(rules, wheel_spec):
    state = solve(solve(start(rules, wheel_spec, main_rounds=2)))
    assert state.phase is Phase.BONUS_PICKS


def test_seeded_games_finish_and_replay_identically(rules, wheel_spec):
    seen = set()
    for seed in range(60):
        history = play(seed, rules, wheel_spec)
        assert history == play(seed, rules, wheel_spec)
        for before, after in zip(history, history[1:]):
            assert all(s.bank >= 0 for s in after.seats)
            assert all(a.total >= b.total for a, b in zip(after.seats, before.seats))
            seen.add(after.last.outcome)
            seen.update(after.last.events)
    assert {
        "bankrupt", "lose_a_turn", "kept", "flipped_prize", "flipped_bankrupt",
        "passed_express", "rode_express", "wild_card", "used_wild", "declined_wild",
        "million_card", "bonus_solved", "bonus_missed",
    } <= seen


def test_views_never_leak_hidden_information(rules, wheel_spec):
    for seed in range(20):
        for state in play(seed, rules, wheel_spec):
            puzzle = (state.round or state.bonus).puzzle
            for seat in range(3):
                view = public_view(state, seat)
                assert {f.name for f in fields(view)} == VIEW_FIELDS
                if state.phase is not Phase.GAME_OVER:
                    assert puzzle.answer not in repr(view)
                    assert view.envelope is None
