"""apply(state, action) -> new state, and legal_actions(state)."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import replace

from rstlne.engine import bonus, wheel
from rstlne.engine.puzzle import (
    LETTERS,
    VOWELS,
    Puzzle,
    board,
    count,
    hidden_consonants,
    hidden_vowels,
    solve_matches,
)
from rstlne.engine.state import (
    Action,
    BuyVowel,
    CallConsonant,
    Forfeit,
    GameState,
    IllegalAction,
    Phase,
    PublicView,
    Result,
    RoundState,
    Rules,
    SeatState,
    Solve,
    Spin,
)
from rstlne.engine.wheel import Kind, Wedge, WheelSpec

SEATS = 3

_FIXED = {
    Phase.CALL_CONSONANT: ("call_consonant",),
    Phase.FREE_PLAY: ("call_letter",),
    Phase.MYSTERY_CHOICE: ("keep", "flip"),
    Phase.EXPRESS_CHOICE: ("pass", "play"),
    Phase.WILD_CHOICE: ("use_wild",),
    Phase.WILD_CONSONANT: ("call_consonant",),
    Phase.BONUS_PICKS: ("bonus_picks",),
    Phase.BONUS_SOLVE: ("bonus_solve",),
}


def new_game(
    seed: int,
    rules: Rules,
    spec: WheelSpec,
    puzzles: Sequence[Puzzle],
    bonus_puzzle: Puzzle | None = None,
) -> GameState:
    puzzles = tuple(puzzles)
    if len(puzzles) < rules.main_rounds:
        raise ValueError(f"{rules.main_rounds} main rounds need {rules.main_rounds} puzzles, got {len(puzzles)}")
    if rules.bonus_round and bonus_puzzle is None:
        raise ValueError("the bonus round needs a bonus puzzle")
    state = GameState(
        seed=seed,
        rules=rules,
        wheel=spec,
        puzzles=puzzles,
        bonus_puzzle=bonus_puzzle,
        seats=(SeatState(),) * SEATS,
        phase=Phase.TURN,
        seat=0,
    )
    return _start_round(state, 1)


def legal_actions(state: GameState) -> tuple[str, ...]:
    """Action kinds the acting seat may take. `forfeit` is the harness's fallback
    after a third invalid response, so views never offer it to a player."""
    if state.phase is Phase.GAME_OVER:
        return ()
    if state.phase is Phase.TURN:
        kinds = _letter_kinds(state, "spin", state.rules.vowel_cost)
    elif state.phase is Phase.EXPRESS:
        kinds = _letter_kinds(state, "call_consonant", state.rules.express_vowel_cost)
    else:
        kinds = _FIXED[state.phase]
    return (*kinds, "forfeit")


def apply(state: GameState, action: Action) -> GameState:
    """Return the state after `action`, or raise IllegalAction. Never mutates `state`."""
    legal = legal_actions(state)
    kind = getattr(action, "kind", None)
    if kind not in legal:
        raise _refusal(state, kind, legal)
    if state.phase in (Phase.BONUS_PICKS, Phase.BONUS_SOLVE):
        return bonus.apply(state, action)
    return _HANDLERS[state.phase](state, action)


def current_wheel(state: GameState) -> tuple[Wedge, ...]:
    """The wheel's 72 thirds as they stand right now."""
    r = state.round
    return wheel.layout(
        state.wheel,
        r.number,
        wild=r.wild_on_wheel,
        million=r.million_on_wheel,
        flipped=r.mystery_flipped,
    )


def public_view(state: GameState, seat: int) -> PublicView:
    legal = tuple(k for k in legal_actions(state) if k != "forfeit") if seat == state.seat else ()
    table = dict(
        seat=seat,
        phase=state.phase,
        banks=tuple(s.bank for s in state.seats),
        totals=tuple(s.total for s in state.seats),
        wild_cards=tuple(s.wild for s in state.seats),
        million_cards=tuple(s.million for s in state.seats),
        turn=state.seat,
        legal_actions=legal,
    )
    if state.bonus is not None:
        b = state.bonus
        return PublicView(
            **table,
            round_number=None,
            category=b.puzzle.category,
            board=board(b.puzzle.answer, b.used),
            used_letters=tuple(sorted(b.used)),
            wedge=None,
            express=False,
            bonus_consonants=state.rules.bonus_consonants + int(state.seats[b.seat].wild),
            envelope=b.envelope if state.phase is Phase.GAME_OVER else None,
        )
    r = state.round
    return PublicView(
        **table,
        round_number=r.number,
        category=r.puzzle.category,
        board=board(r.puzzle.answer, r.used),
        used_letters=tuple(sorted(r.used)),
        wedge=r.wedge,
        express=r.express,
        wheel=current_wheel(state),
        mystery_flipped=r.mystery_flipped,
    )


# Phase handlers


def _turn(state: GameState, action: Action) -> GameState:
    match action:
        case Spin():
            return _spin(state)
        case BuyVowel():
            return _buy_vowel(state, action, state.rules.vowel_cost, _pass)
        case Solve():
            return _solve(state, action, _pass)
    return _pass(state, _result(state, action, "forfeit"))


def _spin(state: GameState) -> GameState:
    r = state.round
    wedge = current_wheel(state)[wheel.spin(state.seed, r.number, r.spin_index)]
    state = replace(state, round=replace(r, spin_index=r.spin_index + 1, wedge=wedge))
    if wedge.kind is Kind.BANKRUPT:
        return _bankrupt(state, _result(state, Spin(), "bankrupt"))
    if wedge.kind is Kind.LOSE_A_TURN:
        return _pass(state, _result(state, Spin(), "lose_a_turn"))
    phase = Phase.FREE_PLAY if wedge.kind is Kind.FREE_PLAY else Phase.CALL_CONSONANT
    return replace(state, phase=phase, last=_result(state, Spin(), "landed"))


def _call_consonant(state: GameState, action: Action) -> GameState:
    if isinstance(action, Forfeit):
        return _pass(state, _result(state, action, "forfeit"))
    state, n, repeated = _call(state, _consonant(action.letter))
    if repeated or n == 0:
        return _pass(state, _result(state, action, "repeated" if repeated else "missing"))
    wedge = state.round.wedge
    if wedge.kind is Kind.MYSTERY:
        return replace(
            state,
            phase=Phase.MYSTERY_CHOICE,
            round=replace(state.round, pending=n),
            last=_result(state, action, "correct", count=n),
        )
    earned = wedge.value * n
    result = _result(state, action, "correct", count=n, earned=earned)
    state = _earn(state, earned)
    if wedge.kind is Kind.EXPRESS:
        return replace(state, phase=Phase.EXPRESS_CHOICE, last=result)
    if wedge.kind is Kind.MILLION:
        state = state.with_seat(state.seat, million=True)
        r = replace(state.round, million_on_wheel=False, million_claimed_by=state.seat)
        return replace(state, round=r, phase=Phase.TURN, last=result.plus("million_card"))
    if wedge.wild:
        state = state.with_seat(state.seat, wild=True)
        state = replace(state, round=replace(state.round, wild_on_wheel=False))
        result = result.plus("wild_card")
    return _after_plain_dollar_wedge(state, result)


def _free_play(state: GameState, action: Action) -> GameState:
    if isinstance(action, Forfeit):
        return _pass(state, _result(state, action, "forfeit"))
    letter = _letter(action.letter)
    state, n, repeated = _call(state, letter)
    earned = 0 if letter in VOWELS else state.round.wedge.value * n
    outcome = "repeated" if repeated else "correct" if n else "missing"
    result = _result(state, action, outcome, count=n, earned=earned)
    return replace(_earn(state, earned), phase=Phase.TURN, last=result)


def _mystery_choice(state: GameState, action: Action) -> GameState:
    if isinstance(action, Forfeit):
        state = _keep(state, action)
        return _pass(state, replace(state.last, outcome="forfeit"))
    if action.option == "keep":
        return _keep(state, action)
    r = state.round
    state = replace(state, round=replace(r, pending=0, mystery_flipped=r.wedge.number))
    if r.wedge.number != r.mystery_prize:
        return _bankrupt(state, _result(state, action, "flipped_bankrupt"))
    earned = state.wheel.mystery_prize
    result = _result(state, action, "flipped_prize", earned=earned)
    return replace(_earn(state, earned), phase=Phase.TURN, last=result)


def _keep(state: GameState, action: Action) -> GameState:
    r = state.round
    earned = r.wedge.value * r.pending
    result = _result(state, action, "kept", count=r.pending, earned=earned)
    return replace(_earn(state, earned), round=replace(r, pending=0), phase=Phase.TURN, last=result)


def _express_choice(state: GameState, action: Action) -> GameState:
    if isinstance(action, Forfeit):
        return _pass(state, _result(state, action, "forfeit"))
    if action.option == "pass":
        return replace(state, phase=Phase.TURN, last=_result(state, action, "passed_express"))
    return replace(
        state,
        phase=Phase.EXPRESS,
        round=replace(state.round, express=True),
        last=_result(state, action, "rode_express"),
    )


def _wild_choice(state: GameState, action: Action) -> GameState:
    if isinstance(action, Forfeit):
        return _pass(state, _result(state, action, "forfeit"))
    if action.use is True:
        state = state.with_seat(state.seat, wild=False)
        return replace(state, phase=Phase.WILD_CONSONANT, last=_result(state, action, "used_wild"))
    if action.use is False:
        return replace(state, phase=Phase.TURN, last=_result(state, action, "declined_wild"))
    raise IllegalAction("not_legal_now", "use_wild takes true or false")


def _wild_consonant(state: GameState, action: Action) -> GameState:
    if isinstance(action, Forfeit):
        return _pass(state, _result(state, action, "forfeit"))
    state, n, repeated = _call(state, _consonant(action.letter))
    if repeated or n == 0:
        return _pass(state, _result(state, action, "repeated" if repeated else "missing"))
    earned = state.round.wedge.value * n
    result = _result(state, action, "correct", count=n, earned=earned)
    return replace(_earn(state, earned), phase=Phase.TURN, last=result)


def _express(state: GameState, action: Action) -> GameState:
    match action:
        case CallConsonant():
            state, n, repeated = _call(state, _consonant(action.letter))
            if repeated or n == 0:
                return _bankrupt(state, _result(state, action, "repeated" if repeated else "missing"))
            earned = state.round.wedge.value * n
            return replace(_earn(state, earned), last=_result(state, action, "correct", count=n, earned=earned))
        case BuyVowel():
            return _buy_vowel(state, action, state.rules.express_vowel_cost, _bankrupt)
        case Solve():
            return _solve(state, action, _bankrupt)
    return _bankrupt(state, _result(state, action, "forfeit"))


_HANDLERS: dict[Phase, Callable[[GameState, Action], GameState]] = {
    Phase.TURN: _turn,
    Phase.CALL_CONSONANT: _call_consonant,
    Phase.FREE_PLAY: _free_play,
    Phase.MYSTERY_CHOICE: _mystery_choice,
    Phase.EXPRESS_CHOICE: _express_choice,
    Phase.WILD_CHOICE: _wild_choice,
    Phase.WILD_CONSONANT: _wild_consonant,
    Phase.EXPRESS: _express,
}


# Shared moves

Miss = Callable[[GameState, Result], GameState]


def _buy_vowel(state: GameState, action: BuyVowel, cost: int, on_miss: Miss) -> GameState:
    letter = _letter(action.letter)
    if letter not in VOWELS:
        raise IllegalAction("consonant_on_vowel_buy", f"{letter} is a consonant. Buy A, E, I, O, or U.")
    state, n, repeated = _call(_earn(state, -cost), letter)
    outcome = "repeated" if repeated else "correct" if n else "missing"
    result = _result(state, action, outcome, count=n, earned=-cost)
    if repeated or n == 0:
        return on_miss(state, result)
    return replace(state, last=result)


def _solve(state: GameState, action: Solve, on_miss: Miss) -> GameState:
    if not isinstance(action.answer, str) or not action.answer.strip():
        raise IllegalAction("malformed_solve", "solve needs an answer")
    if solve_matches(state.round.puzzle.answer, action.answer):
        return _end_round(state, state.seat, _result(state, action, "solved"))
    return on_miss(state, _result(state, action, "wrong_solve"))


def _after_plain_dollar_wedge(state: GameState, result: Result) -> GameState:
    phase = Phase.WILD_CHOICE if state.seats[state.seat].wild else Phase.TURN
    return replace(state, phase=phase, last=result)


def _pass(state: GameState, result: Result) -> GameState:
    r = state.round
    result = result.plus("turn_passed")
    if r.turns >= state.rules.max_turns_per_round:
        return _end_round(state, None, result.plus("turn_cap"))
    return replace(
        state,
        seat=(state.seat + 1) % SEATS,
        phase=Phase.TURN,
        round=replace(r, turns=r.turns + 1, wedge=None, pending=0, express=False),
        last=result,
    )


def _bankrupt(state: GameState, result: Result) -> GameState:
    r = state.round
    claimed = None if r.million_claimed_by == state.seat else r.million_claimed_by
    state = state.with_seat(state.seat, bank=0, wild=False, million=False)
    state = replace(state, round=replace(r, million_claimed_by=claimed))
    return _pass(state, result.plus("bankrupt"))


def _end_round(state: GameState, solver: int | None, result: Result) -> GameState:
    r = state.round
    seats = []
    for i, s in enumerate(state.seats):
        banked = max(s.bank, state.rules.solve_minimum) if i == solver else 0
        if i == solver:
            result = replace(result, earned=banked)
        keeps_million = s.million and not (r.million_claimed_by == i and i != solver)
        seats.append(replace(s, total=s.total + banked, bank=0, million=keeps_million))
    state = replace(state, seats=tuple(seats), last=result.plus("round_over"))
    if r.number < state.rules.main_rounds:
        return _start_round(state, r.number + 1, solver)
    if state.rules.bonus_round:
        return bonus.start(state)
    return replace(state, phase=Phase.GAME_OVER, last=state.last.plus("game_over"))


def _start_round(state: GameState, number: int, last_solver: int | None = None) -> GameState:
    """Rounds 1 to 3 open on seats 1 to 3. From round 4, the last round's solver opens, or a seeded draw
    picks a seat when nobody solved it."""
    if number <= SEATS:
        first = number - 1
    elif last_solver is not None:
        first = last_solver
    else:
        first = wheel.draw(SEATS, state.seed, "starter", number)
    overlay = state.wheel.overlay(number)
    r = RoundState(
        number=number,
        puzzle=state.puzzles[number - 1],
        wild_on_wheel=overlay.wild is not None and not any(s.wild for s in state.seats),
        million_on_wheel=overlay.million is not None and not any(s.million for s in state.seats),
        mystery_prize=wheel.mystery_prize_wedge(state.seed, number, overlay.mystery) if overlay.mystery else None,
    )
    return replace(state, round=r, phase=Phase.TURN, seat=first)


# Small helpers


def _call(state: GameState, letter: str) -> tuple[GameState, int, bool]:
    """Mark `letter` used. Returns the new state, copies revealed, and whether it was a repeat."""
    r = state.round
    repeated = letter in r.used
    n = 0 if repeated else count(r.puzzle.answer, letter)
    return replace(state, round=replace(r, used=r.used | {letter})), n, repeated


def _earn(state: GameState, amount: int) -> GameState:
    return state.with_seat(state.seat, bank=state.seats[state.seat].bank + amount)


def _result(state: GameState, action: Action, outcome: str, **details) -> Result:
    return Result(state.seat, action, outcome, state.round.wedge, **details)


def _letter(raw: object) -> str:
    letter = raw.strip().upper() if isinstance(raw, str) else ""
    if len(letter) != 1 or letter not in LETTERS:
        raise IllegalAction("not_a_letter", f"{raw!r} is not a letter")
    return letter


def _consonant(raw: object) -> str:
    letter = _letter(raw)
    if letter in VOWELS:
        raise IllegalAction("vowel_on_spin", f"{letter} is a vowel. Call a consonant here.")
    return letter


def _letter_kinds(state: GameState, consonant_kind: str, vowel_cost: int) -> tuple[str, ...]:
    r = state.round
    kinds = []
    if hidden_consonants(r.puzzle.answer, r.used):
        kinds.append(consonant_kind)
    if state.seats[state.seat].bank >= vowel_cost and hidden_vowels(r.puzzle.answer, r.used):
        kinds.append("buy_vowel")
    kinds.append("solve")
    return tuple(kinds)


def _refusal(state: GameState, kind: object, legal: tuple[str, ...]) -> IllegalAction:
    if kind == "buy_vowel" and state.phase in (Phase.TURN, Phase.EXPRESS):
        cost = state.rules.vowel_cost if state.phase is Phase.TURN else state.rules.express_vowel_cost
        bank = state.seats[state.seat].bank
        if bank < cost:
            return IllegalAction("insufficient_funds", f"a vowel costs ${cost:,} and the round bank holds ${bank:,}")
    allowed = ", ".join(k for k in legal if k != "forfeit") or "nothing"
    return IllegalAction("not_legal_now", f"{kind} is not legal now. Legal: {allowed}.")
