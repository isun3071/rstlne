"""A live terminal screen. The board stays put and redraws after every move.

Model-only games redraw smoothly with rich's Live display. With a human seat, the screen is cleared and drawn
again instead, with the human's prompt under it, since a Live display can't take typed input. Thinking stays
hidden then: a model's or the bot's thoughts would show the human its best guess."""

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
        read: Callable[[str], str] | None = None,
        read_timed: Callable[[float], str | None] | None = None,
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
        self.interactive = any(p.describe().get("kind") == "human" for p in players)
        self.read = read or self.console.input
        self.read_timed = read_timed
        self.state: GameState | None = None  # the latest state drawn, for a human's prompt
        self.notes: list[str] = []  # hints and messages for the human, shown under the next frame

    def start(self, state: GameState) -> None:
        self.seed = state.seed
        self.state = state
        self._remember(state)
        if self.interactive:
            self._show(self.render(state))
            return
        self.live = Live(self.render(state), console=self.console, refresh_per_second=8)
        self.live.start()

    # A human seat's prompts

    def note(self, text: str) -> None:
        self.notes.append(text.strip())

    def ask(self, prompt: str) -> str:
        """Redraw the screen with any notes, then read the human's command under it."""
        self._redraw_for_human()
        return self.read(prompt)

    def ask_timed(self, seconds: float) -> str | None:
        from rstlne.players.human_cli import read_with_timeout
        self._redraw_for_human()
        return (self.read_timed or read_with_timeout)(seconds)

    def _redraw_for_human(self) -> None:
        if self.state is not None:
            self._show(self.render(self.state))
        for line in self.notes:
            self.console.print(line, markup=False, highlight=False)
        self.notes.clear()

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
        self.state = state
        self._show(self.render(state))
        self.sleep(self.pause)
        self._remember(state)

    def _show(self, frame: RenderableType) -> None:
        if self.interactive:
            self.console.clear()
            self.console.print(frame)
        elif self.live:
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
        if self.live or self.interactive:
            self._show(self.render(state))
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
        if not self.interactive:
            table.add_column("Thinking", overflow="ellipsis", no_wrap=True, ratio=1)
        for i, player in enumerate(self.players):
            cards = ", ".join(
                name for name, held in (("Wild Card", view.wild_cards[i]), ("Million", view.million_cards[i])) if held
            )
            up = i == state.seat and state.phase is not Phase.GAME_OVER
            cells = ["▶" if up else "", f"Seat {i + 1}", player.label(), money(view.banks[i]), money(view.totals[i]), cards]
            if not self.interactive:
                cells.append(self.thoughts.get(i, ""))
            table.add_row(*cells, style="bold" if up else None)
        return table
