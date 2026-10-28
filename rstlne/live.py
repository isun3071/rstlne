"""A live terminal screen for model-only games. The board stays put and redraws after every move."""

from __future__ import annotations

import time
import re
from collections import deque
from collections.abc import Callable, Sequence
from pathlib import Path

from rich.align import Align
from rich.console import Console, Group, RenderableType
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from rstlne.engine.puzzle import VOWELS
from rstlne.engine.rules import public_view
from rstlne.engine.state import GameState, Phase, PublicView
from rstlne.narrate import describe, money, wedge_text
from rstlne.players.base import Player
from rstlne.engine.puzzle import Puzzle
from rstlne.show import Show, solved_view

TILES_PER_ROW = 14  # the widest row on the show's board
ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def board_rows(board: str) -> list[list[str]]:
    """Split a spaced board into rows of tiles, breaking only between words. " " is a gap tile."""
    rows: list[list[str]] = [[]]
    for word in (w.split(" ") for w in board.split("   ")):
        if rows[-1] and len(rows[-1]) + 1 + len(word) > TILES_PER_ROW:
            rows.append([])
        rows[-1] += ([" "] if rows[-1] else []) + word
    return rows


class LiveShow:
    def __init__(
        self,
        players: Sequence[Player],
        pause: float,
        console: Console | None = None,
        sleep: Callable[[float], None] = time.sleep,
        moves_shown: int = 10,
        solve_pause: float = 10,
    ):
        self.players = players
        self.pause = pause
        self.console = console or Console()
        self.sleep = sleep
        self.solve_pause = solve_pause  # holds a solved board; --pause 0 skips it
        self.puzzle: Puzzle | None = None  # the puzzle on the board before the latest move
        self.round_number: int | None = None
        self.moves: deque[str] = deque(maxlen=moves_shown)
        self.thoughts: dict[int, str] = {}  # each seat's latest thought
        self.seed: int | None = None
        self.live: Live | None = None

    def start(self, state: GameState) -> None:
        self.seed = state.seed
        self._remember(state)
        self.live = Live(self.render(state), console=self.console, refresh_per_second=8)
        self.live.start()

    def result(self, state: GameState) -> None:
        result = state.last
        self.moves.append(describe(result))
        thoughts = self.players[result.seat].thoughts()
        if thoughts:
            self.thoughts[result.seat] = self.clean(thoughts[-1])
        if result.outcome == "solved" and self.puzzle:
            self._show(self.render(state, solved_view(public_view(state, state.seat), self.round_number, self.puzzle)))
            if self.pause:
                self.sleep(self.solve_pause)
        self._show(self.render(state))
        self.sleep(self.pause)
        self._remember(state)

    def _show(self, frame: RenderableType) -> None:
        if self.live:
            self.live.update(frame, refresh=True)

    def _remember(self, state: GameState) -> None:
        if state.round:
            self.puzzle, self.round_number = state.round.puzzle, state.round.number
        elif state.bonus:
            self.puzzle, self.round_number = state.bonus.puzzle, None

    @staticmethod
    def clean(thought: str) -> str:
        """The first line of a thought, without its "reasoning:" label or markdown emphasis."""
        line = thought.strip().splitlines()[0] if thought.strip() else ""
        line = re.sub(r"^(reasoning|content):\s*", "", line)
        return line.replace("**", "").replace("__", "").strip()

    def stop(self) -> None:
        if self.live:
            self.live.stop()
            self.live = None

    def finish(self, state: GameState, log_path: Path | str) -> None:
        if self.live:
            self.live.update(self.render(state), refresh=True)
        self.stop()
        write = lambda line: self.console.print(line, markup=False, highlight=False)  # noqa: E731
        Show(self.players, 0, False, write=write).finish(state, log_path)

    def render(self, state: GameState, view: PublicView | None = None) -> RenderableType:
        """The screen for `state`. A solved board passes its revealed `view`; game over reveals the last puzzle."""
        solved = view is not None
        if view is None:
            view = public_view(state, state.seat)
            if state.phase is Phase.GAME_OVER and self.puzzle:
                view = solved_view(view, self.round_number, self.puzzle)
        return Group(
            self._header(state, view, solved),
            self._board(view),
            self._letters(view),
            self._seats(state, view),
            Panel(Text("\n".join(self.moves) or "No moves yet."), title="Moves", title_align="left"),
        )

    def _header(self, state: GameState, view: PublicView, solved: bool = False) -> Text:
        if solved:
            stage = f"Round {view.round_number} of {state.rules.main_rounds}  ·  Solved!"
        elif state.phase is Phase.GAME_OVER:
            stage = "Game over"
        elif view.round_number:
            stage = f"Round {view.round_number} of {state.rules.main_rounds}"
        else:
            stage = "Bonus round"
        seed = f"  ·  seed {self.seed}" if self.seed is not None else ""
        return Text.assemble(("rstlne", "bold magenta"), f"  ·  {stage}  ·  {view.category}{seed}")

    def _board(self, view: PublicView) -> Panel:
        lines: list[RenderableType] = []
        for row in board_rows(view.board):
            if lines:
                lines.append(Text(""))  # a blank line keeps rows from merging into columns
            line = Text()
            for c in row:
                if c == " ":
                    line.append("   ")
                elif c == "_":
                    line.append("   ", style="on green")
                elif c.isalpha():
                    line.append(f" {c} ", style="bold black on bright_white")
                else:
                    line.append(f" {c} ", style="bold")
                line.append(" ")
            lines.append(Align.center(line))
        wedge = f"Wedge: {wedge_text(view.wedge)}" if view.wedge else "Wedge: none yet this turn"
        if view.express:
            wedge += "  ·  riding the Express"
        return Panel(Group(*lines, Text(""), Align.center(Text(wedge, style="italic"))), title=view.category)

    def _letters(self, view: PublicView) -> Align:
        letters = Text()
        for c in ALPHABET:
            used = c in view.used_letters
            style = "dim strike" if used else ("bold cyan" if c in VOWELS else "bold")
            letters.append(c, style=style)
            letters.append(" ")
        return Align.center(letters)

    def _seats(self, state: GameState, view: PublicView) -> Table:
        table = Table(expand=True, show_edge=False)
        for column in ("", "Seat", "Player", "Round bank", "Total", "Cards"):
            table.add_column(column, no_wrap=True)
        table.add_column("Thinking", overflow="ellipsis", no_wrap=True, ratio=1)
        for i, player in enumerate(self.players):
            cards = ", ".join(
                name for name, held in (("Wild Card", view.wild_cards[i]), ("Million", view.million_cards[i])) if held
            )
            up = i == state.seat and state.phase is not Phase.GAME_OVER
            table.add_row(
                "▶" if up else "",
                f"Seat {i + 1}",
                player.label(),
                money(view.banks[i]),
                money(view.totals[i]),
                cards,
                self.thoughts.get(i, ""),
                style="bold" if up else None,
            )
        return table
