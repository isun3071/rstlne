"""Puzzle board, reveal logic, and letter counts."""

from __future__ import annotations

from dataclasses import dataclass

VOWELS = frozenset("AEIOU")
CONSONANTS = frozenset("BCDFGHJKLMNPQRSTVWXYZ")
LETTERS = VOWELS | CONSONANTS
PUNCTUATION = frozenset("-'&.,!?:;\"")
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

    @classmethod
    def from_dict(cls, data: dict) -> Puzzle:
        return cls(data["category"], normalize(data["answer"]), bool(data.get("bonus", False)))


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


def solve_matches(answer: str, attempt: str) -> bool:
    """Letters, word breaks, and punctuation must match. Case and extra spaces don't."""
    return _clean(attempt) == answer
