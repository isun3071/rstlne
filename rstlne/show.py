"""Prints the game line by line as it happens."""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from pathlib import Path

from rstlne.engine.puzzle import Puzzle
from rstlne.engine.rules import public_view
from rstlne.engine.state import GameState, Phase
from rstlne.narrate import describe, money, seat_name, table
from rstlne.players.base import Player
from rstlne.players.decision import DecisionPlayer
from rstlne.players.human_cli import HumanPlayer
from rstlne.players.llm import LLMPlayer


class Show:
    """Prints the game as it happens, pausing after model moves so it reads like the show."""

    def __init__(
        self,
        players: Sequence[Player],
        pause: float,
        thinking: bool,
        show_puzzle: bool = False,
        write: Callable[[str], None] = print,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.players = players
        self.pause = pause
        self.thinking = thinking
        self.show_puzzle = show_puzzle
        self.write = write
        self.sleep = sleep
        humans = [i for i, p in enumerate(players) if isinstance(p, HumanPlayer)]
        self.viewer = humans[0] if len(humans) == 1 else None
        self.names = [self._name(i, p) for i, p in enumerate(players)]
        self.puzzle: Puzzle | None = None

    def _name(self, seat: int, player: Player) -> str:
        return f"Seat {seat + 1} ({'you' if seat == self.viewer else player.label()})"

    def start(self, state: GameState) -> None:
        self.write(f"Wheel of Fortune, seed {state.seed}")
        for name in self.names:
            self.write(f"  {name}")
        self._banner(state)

    def result(self, state: GameState) -> None:
        result = state.last
        player = self.players[result.seat]
        model = not isinstance(player, HumanPlayer)
        if self.thinking:
            for thought in player.thoughts():
                body = thought.strip().replace("\n", "\n    ")
                self.write(f"    [{self.names[result.seat]}] {body}")
        self.write(describe(result, self.viewer))
        if "turn_cap" in result.events and self.puzzle:
            self.write(f"The answer was {self.puzzle.answer}.")
        if "round_over" in result.events and state.phase is not Phase.GAME_OVER:
            self._banner(state)
        if self.show_puzzle and state.phase is not Phase.GAME_OVER:
            view = public_view(state, self.viewer if self.viewer is not None else state.seat)
            for line in table(view, self.viewer):
                self.write(f"    {line}")
        if model:
            self.sleep(self.pause)

    def _banner(self, state: GameState) -> None:
        starter = seat_name(state.seat, self.viewer)
        if state.round:
            self.puzzle = state.round.puzzle
            self.write(f"\n=== Round {state.round.number} === {starter} {'start' if starter == 'You' else 'starts'}.")
        elif state.bonus:
            self.puzzle = state.bonus.puzzle
            self.write(f"\n=== Bonus round === {starter} {'play' if starter == 'You' else 'plays'} for an envelope.")

    def finish(self, state: GameState, log_path: Path) -> None:
        if state.bonus:
            self.write(
                f"The bonus answer was {state.bonus.puzzle.answer}. "
                f"The envelope held {money(state.bonus.envelope)}."
            )
        self.write("\nFinal totals")
        for name, seat in zip(self.names, state.seats):
            self.write(f"  {name}: {money(seat.total)}")
        for player in self.players:
            if isinstance(player, DecisionPlayer):
                self._usage(player.model, player.usage)
                self._usage(f"{player.solver.model} (solver)", player.solver.usage)
            elif isinstance(player, LLMPlayer):
                self._usage(player.model, player.usage)
        self.write(f"Log: {log_path}")

    def _usage(self, label: str, u) -> None:
        self.write(
            f"  {label}: {u.calls} calls, {u.total_tokens:,} tokens "
            f"({u.cached_tokens:,} read from cache), {u.cost:.4f} credits"
        )

    def stop(self) -> None:
        """Nothing to tear down; the live screen needs this."""
