"""The Player interface: decide(view) -> Action."""

from __future__ import annotations

from dataclasses import dataclass

from rstlne.engine.state import Action, PublicView, Result
from rstlne.llm.openrouter import Usage


class InvalidResponse(Exception):
    """A response that never became an action, such as a model reply with no tool call."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class CallRecord:
    """A model call behind the latest decision: its raw output and token usage."""

    raw: dict
    usage: Usage


class Player:
    max_attempts: int | None = 3  # None retries until the action is valid
    last_call: CallRecord | None = None

    def decide(self, view: PublicView, error: str | None = None) -> Action:
        """Pick an action. `error` explains why the previous attempt was refused."""
        raise NotImplementedError

    def observe(self, view: PublicView, result: Result) -> None:
        """Hear about every applied action, including this seat's own."""

    def describe(self) -> dict:
        return {"kind": type(self).__name__}

    def thoughts(self) -> list[str]:
        """What the seat weighed for its latest move, for --show-thinking."""
        return []
