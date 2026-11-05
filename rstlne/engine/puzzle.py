"""Puzzle board, reveal logic, and letter counts."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

VOWELS = frozenset("AEIOU")
CONSONANTS = frozenset("BCDFGHJKLMNPQRSTVWXYZ")
LETTERS = VOWELS | CONSONANTS
PUNCTUATION = frozenset("-'&.,!?:;\"")
_AIRED_ROUND = re.compile(r"R(\d+)[*^]*|BR")  # the aired archive's round marks
_QUOTES = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"'})


def _clean(text: str) -> str:
    return " ".join(text.translate(_QUOTES).upper().split())


def normalize(text: str) -> str:
    """Uppercase letters, single spaces, and basic punctuation, or ValueError."""
    answer = _clean(text)
    if not answer:
        raise ValueError("empty answer")
    bad = set(answer) - LETTERS - PUNCTUATION - {" "}
    if bad:
        raise ValueError(f"unsupported characters {''.join(sorted(bad))!r} in {text!r}")
    return answer


@dataclass(frozen=True)
class Puzzle:
    category: str
    answer: str  # normalized
    bonus: bool = False
    round: int | None = None  # the main round a deck reserves it for; None deals it to any round

    @classmethod
    def from_dict(cls, data: dict) -> Puzzle:
        tag = data.get("round")
        aired = _AIRED_ROUND.fullmatch(tag) if isinstance(tag, str) else None
        if aired:  # the archive's mark for the round an aired puzzle aired in: R2^ is round 2, BR the bonus round
            tag = int(aired.group(1)) if aired.group(1) else None
        if tag is not None and (isinstance(tag, bool) or not isinstance(tag, int) or tag < 1):
            raise ValueError(f"a puzzle's round must be a whole number from 1, not {tag!r}")
        return cls(data["category"], normalize(data["answer"]), bool(data.get("bonus", False)), tag)


def round_pools(main: Sequence[Puzzle], rounds: int) -> list[list[Puzzle]] | None:
    """A deck's main puzzles grouped by round tag, for rounds 1 to `rounds`; None when none is tagged.
    A deck tags all its main puzzles or none, and every round played needs at least one."""
    tagged = [p for p in main if p.round is not None]
    if not tagged:
        return None
    if len(tagged) < len(main):
        raise ValueError(f"{len(tagged)} main puzzles have a round tag and {len(main) - len(tagged)} don't: "
                         "a deck tags all or none")
    pools = [[p for p in main if p.round == r] for r in range(1, rounds + 1)]
    empty = [r for r, pool in enumerate(pools, 1) if not pool]
    if empty:
        raise ValueError(f"the deck tags no puzzle for round {', '.join(map(str, empty))}, and a game plays {rounds}")
    return pools


def board(answer: str, revealed: frozenset[str]) -> str:
    """Spaced board: `_ _ E _ L   _ _ _`. Punctuation shows from the start."""
    return "   ".join(
        " ".join("_" if c in LETTERS and c not in revealed else c for c in word)
        for word in answer.split(" ")
    )


def count(answer: str, letter: str) -> int:
    return answer.count(letter)


def hidden_consonants(answer: str, revealed: frozenset[str]) -> frozenset[str]:
    return frozenset(c for c in answer if c in CONSONANTS) - revealed


def hidden_vowels(answer: str, revealed: frozenset[str]) -> frozenset[str]:
    return frozenset(c for c in answer if c in VOWELS) - revealed


def compact(spaced: str) -> str:
    """A spaced board as one compact pattern with word lengths: `A ____ TAN_ (word lengths 1, 4, 4)`."""
    words = ["".join(word.split(" ")) for word in spaced.split("   ")]
    return f"{' '.join(words)} (word lengths {', '.join(str(len(w)) for w in words)})"


def pattern(answer: str, revealed: frozenset[str]) -> str:
    return compact(board(answer, revealed))


def fits_shown(shown: str, attempt: str, used: frozenset[str]) -> bool:
    """Whether an attempt could be the answer to the board players see: `shown` is its words with `_`
    in every hidden square, like `WH__L _F`. Revealed letters and punctuation must match, and hidden
    squares take only unused letters."""
    guess, words = _clean(attempt).split(" "), shown.split(" ")
    if len(guess) != len(words):
        return False
    for g, word in zip(guess, words):
        if len(g) != len(word):
            return False
        for a, c in zip(g, word):
            if (c != "_" and a != c) or (c == "_" and (a not in LETTERS or a in used)):
                return False
    return True


def fits_board(answer: str, attempt: str, used: frozenset[str]) -> bool:
    """Whether an attempt could be the answer given the board: the same words and word lengths,
    every revealed letter and punctuation mark in place, and only unused letters in hidden squares."""
    guess, words = _clean(attempt).split(" "), answer.split(" ")
    if len(guess) != len(words):
        return False
    for g, word in zip(guess, words):
        if len(g) != len(word):
            return False
        for a, c in zip(g, word):
            shown = c not in LETTERS or c in used
            if (shown and a != c) or (not shown and (a not in LETTERS or a in used)):
                return False
    return True


def solve_matches(answer: str, attempt: str) -> bool:
    """Letters, word breaks, and punctuation must match. Case and extra spaces don't."""
    return _clean(attempt) == answer
