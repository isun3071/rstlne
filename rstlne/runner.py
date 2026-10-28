"""Plays games: asks each seat for moves, applies the three-strike rule, and logs every step."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import fields, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from statistics import mean

from rstlne.engine.rules import apply, public_view
from rstlne.engine import wheel
from rstlne.engine.puzzle import CONSONANTS, LETTERS, fits_board
from rstlne.engine.state import Action, BonusSolve, Forfeit, GameState, IllegalAction, Phase, Result, Solve
from rstlne.llm.openrouter import Usage
from rstlne.players.base import InvalidResponse, Player

# Engine and player error codes, as the invalid response categories in documentation.md name them.
CATEGORIES = {
    "bad_tool_call": "bad tool call",
    "not_legal_now": "bad tool call",
    "not_a_letter": "not a letter",
    "vowel_on_spin": "vowel on a spin",
    "consonant_on_vowel_buy": "consonant on a vowel buy",
    "insufficient_funds": "insufficient funds",
    "malformed_solve": "malformed solve",
    "bad_picks": "bad bonus picks",
    "bad_decision": "bad decision",
}
REPEATED = "repeated letter"
MISFIT = "solve doesn't fit the board"
_FIXED = {"rules", "wheel", "puzzles", "bonus_puzzle"}  # logged once, in the header


def play_game(
    state: GameState,
    players: Sequence[Player],
    log: GameLog | None = None,
    on_result: Callable[[GameState], None] | None = None,
) -> GameState:
    while state.phase is not Phase.GAME_OVER:
        state = play_turn(state, players, log)
        if on_result:
            on_result(state)
    if log:
        log.summary(state)
    return state


def play_turn(state: GameState, players: Sequence[Player], log: GameLog | None = None) -> GameState:
    """Apply the acting seat's next action. After max_attempts invalid tries, it forfeits."""
    player = players[state.seat]
    error = None
    attempts = 0
    while player.max_attempts is None or attempts < player.max_attempts:
        attempts += 1
        try:
            action = player.decide(public_view(state, state.seat), error)
            after = apply(state, action)
        except (IllegalAction, InvalidResponse) as err:
            if log:
                log.invalid(state, player, err)
            error = str(err)
            continue
        if log:
            log.action(state, player, action, after.last)
        break
    else:
        after = apply(state, Forfeit())
        if log:
            log.action(state, None, Forfeit(), after.last)
    for seat, p in enumerate(players):
        p.observe(public_view(after, seat), after.last)
    return after


class GameLog:
    """One JSONL file per game: a header, a line per action or invalid response, and a summary."""

    def __init__(self, path: Path, state: GameState, players: Sequence[Player], header: dict | None = None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = self.path.open("w", buffering=1)  # line buffered: a running game's log is readable
        self.invalid_counts = [Counter() for _ in players]
        self.usage = [Usage() for _ in players]
        self.solves = [[] for _ in players]  # solve_timing of each correct solve, per seat
        self._write(
            type="game",
            started=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            seed=state.seed,
            seats=[p.describe() for p in players],
            rules=jsonable(state.rules),
            wheel=jsonable(state.wheel),
            puzzles=jsonable(state.puzzles),
            bonus_puzzle=jsonable(state.bonus_puzzle),
            **(header or {}),
        )

    def __enter__(self) -> GameLog:
        return self

    def __exit__(self, *exc) -> None:
        self.file.close()

    def action(self, before: GameState, player: Player | None, action: Action, result: Result) -> None:
        call = player.last_call if player else None
        self._add_usage(result.seat, call)
        if result.outcome == "repeated":
            self.invalid_counts[result.seat][REPEATED] += 1
        fits = _fits(before, action)
        if fits is False:
            self.invalid_counts[result.seat][MISFIT] += 1
        timing = _solve_timing(before, action)
        if timing and result.outcome == "solved":
            self.solves[result.seat].append(timing)
        self._write(
            type="action",
            seat=result.seat,
            state=_state(before),
            raw=call.raw if call else None,
            action=jsonable(action),
            result=jsonable(result),
            wedge=jsonable(result.wedge),
            usage=jsonable(call.usage) if call else None,
            **({} if fits is None else {"fits_board": fits}),
            **({} if timing is None else {"solve_timing": timing}),
        )

    def invalid(self, before: GameState, player: Player, error: IllegalAction | InvalidResponse) -> None:
        seat, call = before.seat, player.last_call
        category = CATEGORIES.get(error.code, error.code)
        self.invalid_counts[seat][category] += 1
        self._add_usage(seat, call)
        self._write(
            type="invalid",
            seat=seat,
            category=category,
            message=str(error),
            state=_state(before),
            raw=call.raw if call else None,
            usage=jsonable(call.usage) if call else None,
        )

    def summary(self, state: GameState) -> None:
        self._write(
            type="summary",
            totals=[s.total for s in state.seats],
            bonus=jsonable(state.bonus),
            usage=jsonable(sum(self.usage, Usage())),
            usage_by_seat=jsonable(self.usage),
            invalid=[dict(c) for c in self.invalid_counts],
            solve_timing=[
                {
                    "correct_solves": len(solves),
                    "avg_board_shown": round(mean(s["board_shown"] for s in solves), 3) if solves else None,
                    "money_left": sum(s["money_left"] for s in solves),
                }
                for solves in self.solves
            ],
        )
        self.file.flush()

    def _add_usage(self, seat: int, call) -> None:
        if call is not None:
            self.usage[seat] += call.usage

    def _write(self, **record) -> None:
        self.file.write(json.dumps(record) + "\n")


def _fits(before: GameState, action: Action) -> bool | None:
    """For a solve, whether the attempt fits the board it was made on. None for other moves."""
    if not isinstance(action, (Solve, BonusSolve)) or not isinstance(action.answer, str):
        return None
    stage = before.round or before.bonus
    return fits_board(stage.puzzle.answer, action.answer, stage.used)


def _solve_timing(before: GameState, action: Action) -> dict | None:
    """How early a main round solve came, and the money its unrevealed consonants could still have
    earned: hidden copies times the round's average spin value (Bankrupt and Lose a Turn count as $0)."""
    if not isinstance(action, Solve) or before.round is None:
        return None
    r = before.round
    letters = [c for c in r.puzzle.answer if c in LETTERS]
    hidden = [c for c in letters if c in CONSONANTS and c not in r.used]
    average_spin = mean(w.value for w in wheel.layout(before.wheel, r.number))
    return {
        "board_shown": round(sum(c in r.used for c in letters) / len(letters), 3),
        "hidden_consonants": len(set(hidden)),
        "hidden_copies": len(hidden),
        "money_left": round(len(hidden) * average_spin),
    }


def _state(state: GameState) -> dict:
    return {f.name: jsonable(getattr(state, f.name)) for f in fields(state) if f.name not in _FIXED}


def jsonable(obj):
    """Engine dataclasses, enums, and sets as plain JSON values. Actions carry their kind."""
    if is_dataclass(obj) and not isinstance(obj, type):
        data = {f.name: jsonable(getattr(obj, f.name)) for f in fields(obj)}
        kind = getattr(obj, "kind", None)
        if "kind" not in data and isinstance(kind, str):
            data = {"kind": kind, **data}
        return data
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, (set, frozenset)):
        return sorted(jsonable(x) for x in obj)
    if isinstance(obj, (list, tuple)):
        return [jsonable(x) for x in obj]
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    return obj
