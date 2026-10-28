"""A live terminal screen for model-only games. The board stays put and redraws after every move."""

from __future__ import annotations

import time
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
from rstlne.show import Show

TILES_PER_ROW = 14  # the widest row on the show's board
ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


class LiveShow:
    def __init__(
        self,
        players: Sequence[Player],
        pause: float,
        console: Console | None = None,
        sleep: Callable[[float], None] = time.sleep,
        moves_shown: int = 10,
    ):
        self.players = players
        self.pause = pause
        self.console = console or Console()
        self.sleep = sleep
        self.moves: deque[str] = deque(maxlen=moves_shown)
        self.thoughts: dict[int, str] = {}  # each seat's latest thought
        self.seed: int | None = None
        self.live: Live | None = None

    def start(self, state: GameState) -> None:
        self.seed = state.seed
        self.live = Live(self.render(state), console=self.console, refresh_per_second=8)
        self.live.start()

    def result(self, state: GameState) -> None:
        result = state.last
        self.moves.append(describe(result))
        thoughts = self.players[result.seat].thoughts()
        if thoughts:
            self.thoughts[result.seat] = thoughts[-1].splitlines()[0]
        if self.live:
            self.live.update(self.render(state), refresh=True)
        self.sleep(self.pause)

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

    def render(self, state: GameState) -> RenderableType:
        view = public_view(state, state.seat)
        return Group(
            self._header(state, view),
            self._board(view),
            self._letters(view),
            self._seats(state, view),
            Panel(Text("\n".join(self.moves) or "No moves yet."), title="Moves", title_align="left"),
        )

    def _header(self, state: GameState, view: PublicView) -> Text:
        if state.phase is Phase.GAME_OVER:
            stage = "Game over"
        elif view.round_number:
            stage = f"Round {view.round_number} of {state.rules.main_rounds}"
        else:
            stage = "Bonus round"
        seed = f"  ·  seed {self.seed}" if self.seed is not None else ""
        return Text.assemble(("rstlne", "bold magenta"), f"  ·  {stage}  ·  {view.category}{seed}")

    def _board(self, view: PublicView) -> Panel:
        rows: list[list[str]] = [[]]
        for word in (w.split(" ") for w in view.board.split("   ")):
            if rows[-1] and len(rows[-1]) + 1 + len(word) > TILES_PER_ROW:
                rows.append([])
            rows[-1] += ([" "] if rows[-1] else []) + word
        lines = []
        for row in rows:
            line = Text()
            for c in row:
                if c == " ":
                    line.append("   ")
                elif c == "_":
                    line.append("   ", style="on green")
                elif c.isalpha():
                    line.append(f" {c} ", style="bold black on white")
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
