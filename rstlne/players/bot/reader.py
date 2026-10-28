"""The reader interface: board and category in, Belief out."""

from __future__ import annotations

from typing import Protocol

from rstlne.engine.state import PublicView
from rstlne.players.bot.belief import Belief


class Reader(Protocol):
    def read(self, view: PublicView) -> Belief: ...
