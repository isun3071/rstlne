"""Bonus wheel and bonus round flow."""

from __future__ import annotations

from dataclasses import replace

from rstlne.engine import wheel
from rstlne.engine.puzzle import CONSONANTS, VOWELS, solve_matches
from rstlne.engine.state import (
    Action,
    BonusPicks,
    BonusSolve,
    BonusState,
    Forfeit,
    GameState,
    IllegalAction,
    Phase,
    Result,
)
from rstlne.engine.wheel import WheelSpec


def envelopes(spec: WheelSpec, million: bool) -> tuple[int, ...]:
    """The 24 bonus envelopes, with the Million swap for a Million card holder."""
    if not million:
        return spec.envelopes
    old, new = spec.million_swap
    i = spec.envelopes.index(old)
    return (*spec.envelopes[:i], new, *spec.envelopes[i + 1:])


def qualifier(state: GameState) -> int:
    """The seat with the highest game total. A seeded draw breaks ties."""
    best = max(s.total for s in state.seats)
    tied = [i for i, s in enumerate(state.seats) if s.total == best]
    return tied[wheel.draw(len(tied), state.seed, "tiebreak")]


def start(state: GameState) -> GameState:
    """Spin the bonus wheel, hide the envelope, and reveal the given letters."""
    seat = qualifier(state)
    options = envelopes(state.wheel, state.seats[seat].million)
    b = BonusState(
        seat=seat,
        puzzle=state.bonus_puzzle,
        envelope=options[wheel.draw(len(options), state.seed, "bonus")],
        used=frozenset(state.rules.bonus_letters),
    )
    return replace(
        state,
        round=None,
        bonus=b,
        phase=Phase.BONUS_PICKS,
        seat=seat,
        last=state.last.plus("bonus_started"),
    )


def apply(state: GameState, action: Action) -> GameState:
    b = state.bonus
    if state.phase is Phase.BONUS_PICKS:
        if isinstance(action, Forfeit):
            return replace(state, phase=Phase.BONUS_SOLVE, last=_result(state, action, "forfeit"))
        consonants, vowel = _check(state, action)
        if len(consonants) > state.rules.bonus_consonants:
            state = state.with_seat(b.seat, wild=False)
        return replace(
            state,
            bonus=replace(b, used=b.used | {*consonants, vowel}),
            phase=Phase.BONUS_SOLVE,
            last=_result(state, action, "picks"),
        )

    solved = False
    if isinstance(action, BonusSolve):
        if not isinstance(action.answer, str) or not action.answer.strip():
            raise IllegalAction("malformed_solve", "solve needs an answer")
        solved = solve_matches(b.puzzle.answer, action.answer)
    outcome = "bonus_solved" if solved else "bonus_missed" if isinstance(action, BonusSolve) else "forfeit"
    earned = b.envelope if solved else 0
    result = _result(state, action, outcome, earned=earned).plus("game_over")
    state = state.with_seat(b.seat, total=state.seats[b.seat].total + earned)
    return replace(state, bonus=replace(b, solved=solved), phase=Phase.GAME_OVER, last=result)


def _check(state: GameState, action: BonusPicks) -> tuple[tuple[str, ...], str]:
    b = state.bonus
    need = state.rules.bonus_consonants + int(state.seats[b.seat].wild)
    if isinstance(action.consonants, str) or not isinstance(action.consonants, (list, tuple)):
        _bad(f"consonants must be a list of {need} letters")
    consonants = tuple(_upper(c) for c in action.consonants)
    vowel = _upper(action.vowel)
    if len(consonants) != need:
        _bad(f"pick exactly {need} consonants")
    if any(c not in CONSONANTS for c in consonants):
        _bad(f"{', '.join(consonants)} must all be consonants")
    if vowel not in VOWELS:
        _bad(f"{action.vowel!r} is not a vowel")
    if any(letter in b.used for letter in (*consonants, vowel)):
        _bad(f"{', '.join(state.rules.bonus_letters)} are already revealed")
    if len(set(consonants)) != len(consonants):
        _bad("pick each consonant once")
    return consonants, vowel


def _upper(raw: object) -> str:
    return raw.strip().upper() if isinstance(raw, str) else ""


def _bad(message: str):
    raise IllegalAction("bad_picks", message)


def _result(state: GameState, action: Action, outcome: str, **details) -> Result:
    return Result(state.seat, action, outcome, None, **details)
