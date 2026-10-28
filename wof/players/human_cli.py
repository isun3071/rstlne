"""A seat played from the terminal with short commands."""

from __future__ import annotations

import select
import sys
import time
from collections.abc import Callable

from wof.engine.puzzle import VOWELS
from wof.engine.state import (
    Action,
    BonusPicks,
    BonusSolve,
    BuyVowel,
    CallConsonant,
    CallLetter,
    Choose,
    Forfeit,
    Phase,
    PublicView,
    Solve,
    Spin,
    UseWild,
)
from wof.narrate import table
from wof.players.base import Player

_PROMPTS = {
    Phase.CALL_CONSONANT: "Call a consonant: ",
    Phase.WILD_CONSONANT: "Call your extra consonant: ",
    Phase.FREE_PLAY: "Free Play. Call any letter: ",
    Phase.MYSTERY_CHOICE: "keep or flip: ",
    Phase.EXPRESS_CHOICE: "pass or play: ",
    Phase.WILD_CHOICE: "wild to spend the Wild Card, or no: ",
}


def read_with_timeout(seconds: float) -> str | None:
    ready, _, _ = select.select([sys.stdin], [], [], seconds)
    return sys.stdin.readline().rstrip("\n") if ready else None


def prompt(view: PublicView) -> str:
    if view.phase in _PROMPTS:
        return _PROMPTS[view.phase]
    if view.phase is Phase.BONUS_PICKS:
        return f"Pick {view.bonus_consonants} consonants and 1 vowel, like B G H I: "
    options = []
    if view.express and "call_consonant" in view.legal_actions:
        options.append("a consonant")
    if "spin" in view.legal_actions:
        options.append("s to spin")
    if "buy_vowel" in view.legal_actions:
        options.append("v E to buy a vowel")
    options.append("solve <answer>")
    return ", ".join(options) + ": "


def parse_command(text: str, view: PublicView) -> Action:
    """Turn a typed command into an action, or raise ValueError with a hint."""
    words = text.split()
    if not words:
        raise ValueError(_hint(view))
    head = words[0].lower()
    phase = view.phase

    if phase is Phase.BONUS_PICKS:
        letters = [c.upper() for c in "".join(words)]
        vowels = [c for c in letters if c in VOWELS]
        if len(vowels) != 1:
            raise ValueError("Pick exactly one vowel, like B G H I.")
        return BonusPicks(tuple(c for c in letters if c not in VOWELS), vowels[0])
    if phase in (Phase.MYSTERY_CHOICE, Phase.EXPRESS_CHOICE):
        if len(words) == 1 and head in view.legal_actions:
            return Choose(head)
        raise ValueError(f"Type {' or '.join(view.legal_actions)}.")
    if phase is Phase.WILD_CHOICE:
        if head in ("wild", "w", "yes", "y"):
            return UseWild(True)
        if head in ("no", "n", "skip"):
            return UseWild(False)
        raise ValueError("Type wild to spend the Wild Card, or no to keep it.")
    if phase is Phase.FREE_PLAY:
        return CallLetter(_one_letter(words))
    if phase in (Phase.CALL_CONSONANT, Phase.WILD_CONSONANT):
        return CallConsonant(_one_letter(words))

    # A normal turn, or riding the Express
    if head == "solve":
        answer = text.strip()[len(words[0]):].strip()
        if not answer:
            raise ValueError("Type solve followed by your answer.")
        return Solve(answer)
    if head in ("v", "vowel"):
        if len(words) != 2 or len(words[1]) != 1:
            raise ValueError("Type v and a vowel, like v E.")
        return BuyVowel(words[1].upper())
    if head in ("s", "spin") and len(words) == 1:
        if "spin" not in view.legal_actions:
            raise ValueError("You can't spin now. " + _hint(view))
        return Spin()
    if phase is Phase.EXPRESS and len(words) == 1 and len(head) == 1:
        return CallConsonant(head.upper())
    raise ValueError(_hint(view))


def _one_letter(words: list[str]) -> str:
    if len(words) != 1 or len(words[0]) != 1:
        raise ValueError("Type a single letter.")
    return words[0].upper()


def _hint(view: PublicView) -> str:
    return "Try: " + prompt(view).removesuffix(": ")


class HumanPlayer(Player):
    max_attempts = None  # a typo or illegal move just asks again

    def __init__(
        self,
        seat: int,
        *,
        read: Callable[[str], str] = input,
        write: Callable[[str], None] = print,
        read_timed: Callable[[float], str | None] = read_with_timeout,
        clock: Callable[[], float] = time.monotonic,
        seconds: float = 10,
    ):
        self.seat = seat
        self.read = read
        self.write = write
        self.read_timed = read_timed
        self.clock = clock
        self.seconds = seconds

    def describe(self) -> dict:
        return {"kind": "human"}

    def decide(self, view: PublicView, error: str | None = None) -> Action:
        if error:
            self.write(f"  {error}")
        else:
            self.write("\n" + "\n".join(table(view, self.seat)))
        if view.phase is Phase.BONUS_SOLVE:
            return self._timed_solve()
        while True:
            try:
                return parse_command(self.read(prompt(view)), view)
            except ValueError as err:
                self.write(f"  {err}")

    def _timed_solve(self) -> Action:
        self.write(f"You have {self.seconds:g} seconds. Type your answer and press Enter.")
        start = self.clock()
        text = self.read_timed(self.seconds)
        late = self.clock() - start > self.seconds
        if text is None or late:
            self.write("  Time's up.")
            return Forfeit()
        if not text.strip():
            self.write("  No answer.")
            return Forfeit()
        return BonusSolve(text.strip())
