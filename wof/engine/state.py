"""GameState, RoundState, actions, and the public view players see."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import ClassVar

from wof.engine.puzzle import Puzzle
from wof.engine.wheel import Wedge, WheelSpec


@dataclass(frozen=True)
class Rules:
    main_rounds: int
    bonus_round: bool
    max_turns_per_round: int
    vowel_cost: int
    express_vowel_cost: int
    solve_minimum: int
    bonus_letters: tuple[str, ...]
    bonus_consonants: int

    @classmethod
    def from_dict(cls, config: dict) -> Rules:
        game, rules = config["game"], config["rules"]
        return cls(
            main_rounds=game["main_rounds"],
            bonus_round=game["bonus_round"],
            max_turns_per_round=game["max_turns_per_round"],
            vowel_cost=rules["vowel_cost"],
            express_vowel_cost=rules["express_vowel_cost"],
            solve_minimum=rules["solve_minimum"],
            bonus_letters=tuple(rules["bonus_letters"]),
            bonus_consonants=rules["bonus_consonants"],
        )


class Phase(StrEnum):
    TURN = "turn"  # spin, buy a vowel, or solve
    CALL_CONSONANT = "call_consonant"  # after a spin landed on a letter wedge
    FREE_PLAY = "free_play"  # after a spin landed on Free Play
    MYSTERY_CHOICE = "mystery_choice"  # keep or flip
    EXPRESS_CHOICE = "express_choice"  # pass or play
    WILD_CHOICE = "wild_choice"  # spend the Wild Card or not
    WILD_CONSONANT = "wild_consonant"  # the extra consonant the Wild Card bought
    EXPRESS = "express"  # riding the Express
    BONUS_PICKS = "bonus_picks"
    BONUS_SOLVE = "bonus_solve"
    GAME_OVER = "game_over"


# Actions. `kind` matches the names in legal_actions.


@dataclass(frozen=True)
class Spin:
    kind: ClassVar[str] = "spin"


@dataclass(frozen=True)
class CallConsonant:
    letter: str
    kind: ClassVar[str] = "call_consonant"


@dataclass(frozen=True)
class CallLetter:
    """Any letter, on Free Play."""

    letter: str
    kind: ClassVar[str] = "call_letter"


@dataclass(frozen=True)
class BuyVowel:
    letter: str
    kind: ClassVar[str] = "buy_vowel"


@dataclass(frozen=True)
class Solve:
    answer: str
    kind: ClassVar[str] = "solve"


@dataclass(frozen=True)
class Choose:
    option: str  # keep or flip on Mystery, pass or play on Express

    @property
    def kind(self) -> str:
        return self.option


@dataclass(frozen=True)
class UseWild:
    use: bool
    kind: ClassVar[str] = "use_wild"


@dataclass(frozen=True)
class BonusPicks:
    consonants: tuple[str, ...]
    vowel: str
    kind: ClassVar[str] = "bonus_picks"


@dataclass(frozen=True)
class BonusSolve:
    answer: str
    kind: ClassVar[str] = "bonus_solve"


@dataclass(frozen=True)
class Forfeit:
    """The harness's fallback after a third invalid response."""

    kind: ClassVar[str] = "forfeit"


Action = (
    Spin | CallConsonant | CallLetter | BuyVowel | Solve | Choose | UseWild
    | BonusPicks | BonusSolve | Forfeit
)


class IllegalAction(Exception):
    """The engine refused an action. `code` names its invalid response category."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Result:
    """What the last action did, for the CLI and the game log."""

    seat: int
    action: Action
    outcome: str
    wedge: Wedge | None = None
    count: int = 0  # copies of the called letter
    earned: int = 0  # dollars added to the round bank, or banked by a solve
    events: tuple[str, ...] = ()

    def plus(self, *events: str) -> Result:
        return replace(self, events=self.events + events)


@dataclass(frozen=True)
class SeatState:
    total: int = 0  # game total, banked from solved rounds
    bank: int = 0  # this round's money
    wild: bool = False
    million: bool = False


@dataclass(frozen=True)
class RoundState:
    number: int
    puzzle: Puzzle
    wild_on_wheel: bool
    million_on_wheel: bool
    mystery_prize: int | None  # hidden: the Mystery wedge with the $10,000
    used: frozenset[str] = frozenset()
    spin_index: int = 0
    turns: int = 1
    wedge: Wedge | None = None  # where the current turn's last spin landed
    pending: int = 0  # copies found on a Mystery wedge, waiting on keep or flip
    express: bool = False
    mystery_flipped: int | None = None
    million_claimed_by: int | None = None  # seat that must solve this round to keep the card


@dataclass(frozen=True)
class BonusState:
    seat: int
    puzzle: Puzzle
    envelope: int  # hidden until the game ends
    used: frozenset[str]
    solved: bool | None = None


@dataclass(frozen=True)
class GameState:
    seed: int
    rules: Rules
    wheel: WheelSpec
    puzzles: tuple[Puzzle, ...]
    bonus_puzzle: Puzzle | None
    seats: tuple[SeatState, ...]
    phase: Phase
    seat: int  # who acts now
    round: RoundState | None = None
    bonus: BonusState | None = None
    last: Result | None = None

    def with_seat(self, index: int, **changes) -> GameState:
        seats = list(self.seats)
        seats[index] = replace(seats[index], **changes)
        return replace(self, seats=tuple(seats))


@dataclass(frozen=True)
class PublicView:
    """Everything one seat may see. Never the answer, a Mystery back, or an unopened envelope."""

    seat: int  # whose view this is
    phase: Phase
    round_number: int | None  # None in the bonus round
    category: str
    board: str
    used_letters: tuple[str, ...]
    banks: tuple[int, ...]
    totals: tuple[int, ...]
    wild_cards: tuple[bool, ...]
    million_cards: tuple[bool, ...]
    turn: int  # whose turn it is
    wedge: Wedge | None
    express: bool
    legal_actions: tuple[str, ...]  # empty unless it is this seat's move
    bonus_consonants: int = 0  # consonants the bonus picks need
    envelope: int | None = None  # shown once the game is over
