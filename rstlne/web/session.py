"""A game played in the browser: the runner on its own thread, streaming events to the page.

The page only ever gets public views. An answer reaches it once its round is solved or over, and the
seats' thinking only when no human is seated, as on the --live screen. The Narrator turns each move into
the page's events, so a live game and a replayed log (replay.py) draw the same way.
"""

from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable, Sequence
from pathlib import Path

from rstlne.engine.bonus import before_bonus
from rstlne.engine.puzzle import LETTERS, board
from rstlne.engine.rules import public_view
from rstlne.engine.state import Action, BonusSolve, Forfeit, GameState, Phase, PublicView
from rstlne.engine.wheel import Wedge
from rstlne.live import board_rows, missed_money
from rstlne.narrate import describe, money, wedge_text
from rstlne.players.base import Player
from rstlne.players.decision import DecisionPlayer
from rstlne.players.human_cli import parse_command, prompt
from rstlne.players.llm import LLMPlayer
from rstlne.runner import GameLog, play_game

_STOP = object()


class GameStopped(Exception):
    """The page closed the game."""


def wedge_json(wedge: Wedge | None) -> dict | None:
    if wedge is None:
        return None
    return {"number": wedge.number, "kind": str(wedge.kind), "value": wedge.value, "wild": wedge.wild,
            "text": wedge_text(wedge)}


def table_json(view: PublicView, seats: Sequence[str]) -> dict:
    """The public view as the page draws it."""
    return {
        "phase": str(view.phase), "round": view.round_number, "category": view.category,
        "rows": board_rows(view.board), "used": list(view.used_letters),
        "banks": list(view.banks), "totals": list(view.totals),
        "wild": list(view.wild_cards), "million": list(view.million_cards),
        "turn": view.turn, "wedge": wedge_json(view.wedge), "express": view.express,
        "legal": list(view.legal_actions), "bonus_consonants": view.bonus_consonants,
        "wheel": [wedge_json(w) for w in view.wheel], "mystery_flipped": view.mystery_flipped,
        "seats": list(seats),
    }


class Narrator:
    """Turns a game's states into the page's events, for a viewer's seat or, with none, for a spectator."""

    def __init__(self, labels: Sequence[str], kinds: Sequence[str], viewer: int | None):
        self.labels = list(labels)
        self.kinds = list(kinds)
        self.viewer = viewer
        self.moves = 0

    def start(self, state: GameState) -> list[dict]:
        seats = [{"label": label, "kind": kind, "you": i == self.viewer}
                 for i, (label, kind) in enumerate(zip(self.labels, self.kinds))]
        return [{"type": "start", "seed": state.seed, "seats": seats}, *self.banner(state), *self.table(state)]

    def view(self, state: GameState) -> PublicView:
        return public_view(state, self.viewer if self.viewer is not None else state.seat)

    def table(self, state: GameState) -> list[dict]:
        if state.phase is Phase.GAME_OVER:
            return []
        return [{"type": "table", **table_json(self.view(state), self.labels)}]

    def banner(self, state: GameState) -> list[dict]:
        if state.round:
            return [{"type": "round", "round": state.round.number, "starts": state.seat,
                     "category": state.round.puzzle.category}]
        if state.bonus:
            return [{"type": "round", "round": None, "starts": state.seat, "category": state.bonus.puzzle.category}]
        return []

    def move(self, before: GameState, state: GameState, thoughts: Sequence[str] = (), hold: float = 0) -> list[dict]:
        """The events for one applied action: the move, any thinking, a solved board, the next round, the table."""
        result = state.last
        self.moves += 1
        move = {"type": "move", "index": self.moves, "seat": result.seat, "text": describe(result, self.viewer),
                "outcome": result.outcome, "kind": result.action.kind, "events": list(result.events),
                "wedge": wedge_json(result.wedge) if result.action.kind == "spin" else None}
        if result.outcome == "solved" and before.round:
            move["note"] = missed_money(before).strip()
        events = [move]
        if self.viewer is None and thoughts:
            events.append({"type": "thoughts", "seat": result.seat, "lines": [t for t in thoughts if t.strip()]})
        puzzle = before.round.puzzle if before.round else None
        if result.outcome == "solved" and puzzle:
            events.append({"type": "solved", "category": puzzle.category,
                           "rows": board_rows(board(puzzle.answer, LETTERS)), "seconds": hold})
        elif "turn_cap" in result.events and puzzle:
            events.append({"type": "round_over", "text": f"Nobody solved it. The answer was {puzzle.answer}."})
        if "round_over" in result.events and state.phase is not Phase.GAME_OVER:
            events += self.banner(state)
        return events + self.table(state)

    def over(self, state: GameState, usage: Sequence[dict], log: str) -> dict:
        b = state.bonus
        return {
            "type": "over",
            "bonus": None if b is None else {"seat": b.seat, "answer": b.puzzle.answer, "category": b.puzzle.category,
                                             "rows": board_rows(board(b.puzzle.answer, LETTERS)),
                                             "envelope": b.envelope, "envelope_text": money(b.envelope),
                                             "solved": bool(b.solved), "used": sorted(b.used)},
            "before_bonus": before_bonus(state) if b else [s.total for s in state.seats],
            "totals": [s.total for s in state.seats],
            "usage": list(usage),
            "log": log,
        }


class WebHuman(Player):
    """A seat played from the page. It reads the terminal's commands, so typos and illegal moves reprompt."""

    max_attempts = None

    def __init__(self, seat: int, emit: Callable[[dict], None], seconds: float):
        self.seat = seat
        self.emit = emit
        self.seconds = seconds  # the bonus solve's clock
        self.inbox: queue.Queue = queue.Queue()

    def describe(self) -> dict:
        return {"kind": "human"}

    def label(self) -> str:
        return "You"

    def submit(self, command: str) -> None:
        self.inbox.put(command)

    def stop(self) -> None:
        self.inbox.put(_STOP)

    def _take(self, timeout: float | None = None):
        item = self.inbox.get(timeout=timeout)
        if item is _STOP:
            raise GameStopped
        return item

    def _prompt(self, view: PublicView, error: str | None) -> None:
        self.emit({"type": "prompt", "seat": self.seat, "phase": str(view.phase), "legal": list(view.legal_actions),
                   "hint": prompt(view).removesuffix(": "), "error": error, "bonus_consonants": view.bonus_consonants})

    def decide(self, view: PublicView, error: str | None = None) -> Action:
        if view.phase is Phase.BONUS_SOLVE:
            return self._timed_solve(error)
        self._prompt(view, error)
        while True:
            try:
                return parse_command(str(self._take()), view)
            except ValueError as err:
                self._prompt(view, str(err))

    def _timed_solve(self, error: str | None) -> Action:
        """One answer within the clock. A late or empty answer counts as wrong, as in the terminal."""
        while not self.inbox.empty():  # anything typed before the clock started doesn't count
            self._take()
        self.emit({"type": "prompt", "seat": self.seat, "phase": str(Phase.BONUS_SOLVE), "legal": ["bonus_solve"],
                   "hint": "Type your answer", "error": error, "seconds": self.seconds})
        start = time.monotonic()
        try:
            text = self._take(timeout=self.seconds)
        except queue.Empty:
            return Forfeit()
        if time.monotonic() - start > self.seconds or not str(text).strip():
            return Forfeit()
        return BonusSolve(str(text).strip())


def usage_of(players: Sequence[Player]) -> list[dict]:
    """Each model's calls, tokens, and cost this game."""
    pairs = []
    for p in players:
        if isinstance(p, DecisionPlayer):
            pairs += [(p.model, p.usage), (f"{p.solver.model} (solver)", p.solver.usage)]
        elif isinstance(p, LLMPlayer):
            pairs.append((p.model, p.usage))
    return [{"model": m, "calls": u.calls, "tokens": u.total_tokens, "cached": u.cached_tokens, "cost": u.cost}
            for m, u in pairs]


class WebGame:
    """One game on its own thread. Events go to every subscriber, and a late subscriber gets the history first."""

    def __init__(self, state: GameState, players: Sequence[Player], log_path: Path, *, pause: float,
                 solve_pause: float, sleep: Callable[[float], None] = time.sleep):
        self.state = state
        self.players = players
        self.log_path = Path(log_path)
        self.pause = pause
        self.solve_pause = solve_pause
        self.sleep = sleep
        humans = [i for i, p in enumerate(players) if isinstance(p, WebHuman)]
        self.viewer = humans[0] if humans else None
        labels = ["You" if i == self.viewer else p.label() for i, p in enumerate(players)]
        self.narrator = Narrator(labels, [p.describe().get("kind") for p in players], self.viewer)
        self.history: list[dict] = []
        self.subscribers: list[queue.Queue] = []
        self.lock = threading.Lock()
        self.stopped = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)
        for p in players:
            if isinstance(p, WebHuman):
                p.emit = self.emit

    # Events

    def emit(self, event: dict) -> None:
        with self.lock:
            self.history.append(event)
            for sub in self.subscribers:
                sub.put(event)

    def subscribe(self) -> queue.Queue:
        """A queue of every event so far, then each new one."""
        sub: queue.Queue = queue.Queue()
        with self.lock:
            for event in self.history:
                sub.put(event)
            self.subscribers.append(sub)
        return sub

    def unsubscribe(self, sub: queue.Queue) -> None:
        with self.lock:
            if sub in self.subscribers:
                self.subscribers.remove(sub)

    @staticmethod
    def next_event(sub: queue.Queue, timeout: float) -> dict | None:
        try:
            return sub.get(timeout=timeout)
        except queue.Empty:
            return None

    # The human's commands, and closing the game

    def submit(self, command: str) -> None:
        if self.viewer is not None:
            self.players[self.viewer].submit(command)

    def stop(self) -> None:
        self.stopped.set()
        for p in self.players:
            if isinstance(p, WebHuman):
                p.stop()

    # The game

    def start(self) -> None:
        self.thread.start()

    def _run(self) -> None:
        state = self.state
        for event in self.narrator.start(state):
            self.emit(event)
        self._beat(state)
        try:
            with GameLog(self.log_path, state, self.players) as log:
                final = play_game(state, self.players, log, on_result=self._result)
        except GameStopped:
            return
        except Exception as err:  # a failed API call or a bug: tell the page instead of hanging it
            self.emit({"type": "failed", "text": f"{type(err).__name__}: {err}"})
            return
        self.emit(self.narrator.over(final, usage_of(self.players), str(self.log_path)))

    def _result(self, state: GameState) -> None:
        if self.stopped.is_set():
            raise GameStopped
        before, self.state = self.state, state
        player = self.players[state.last.seat]
        hold = self.solve_pause if self.pause else 0
        for event in self.narrator.move(before, state, player.thoughts(), hold):
            self.emit(event)
            if event["type"] == "solved" and hold:
                self.sleep(hold)
        self._beat(state)

    def _beat(self, state: GameState) -> None:
        """Before a bot or model moves: tell the page who is thinking, and wait a beat so play can be followed."""
        if state.phase is Phase.GAME_OVER or isinstance(self.players[state.seat], WebHuman):
            return
        self.emit({"type": "thinking", "seat": state.seat})
        if self.pause:
            self.sleep(self.pause)
