import pytest

from wof.engine.puzzle import (
    Puzzle,
    board,
    count,
    hidden_consonants,
    hidden_vowels,
    normalize,
    solve_matches,
)


def test_normalize_uppercases_and_collapses_spaces():
    assert normalize("  well-known   fact ") == "WELL-KNOWN FACT"


def test_normalize_straightens_curly_quotes():
    assert normalize("don’t stop") == "DON'T STOP"


@pytest.mark.parametrize("bad", ["ROOM 101", "CAFÉ", "A_B", "", "   "])
def test_normalize_rejects_other_characters(bad):
    with pytest.raises(ValueError):
        normalize(bad)


def test_puzzle_from_dict_normalizes_the_answer():
    puzzle = Puzzle.from_dict({"category": "Phrase", "answer": "well-known fact", "bonus": False})
    assert puzzle == Puzzle("Phrase", "WELL-KNOWN FACT", False)


def test_board_spaces_letters_and_marks_word_breaks():
    assert board("WHEEL OF FORTUNE", frozenset()) == "_ _ _ _ _   _ _   _ _ _ _ _ _ _"
    assert board("WHEEL OF FORTUNE", frozenset("EL")) == "_ _ E E L   _ _   _ _ _ _ _ _ E"


def test_board_shows_punctuation_from_the_start():
    assert board("DON'T STOP", frozenset()) == "_ _ _ ' _   _ _ _ _"
    assert board("WELL-KNOWN FACT", frozenset()) == "_ _ _ _ - _ _ _ _ _   _ _ _ _"


def test_count_and_hidden_letters():
    assert count("WHEEL OF FORTUNE", "E") == 3
    assert count("WHEEL OF FORTUNE", "Z") == 0
    assert hidden_consonants("WHEEL OF FORTUNE", frozenset("WHL")) == {"F", "R", "T", "N"}
    assert hidden_vowels("WHEEL OF FORTUNE", frozenset("E")) == {"O", "U"}


@pytest.mark.parametrize(
    "attempt, ok",
    [
        ("WELL-KNOWN FACT", True),
        ("well-known  fact", True),
        ("  Well-Known Fact ", True),
        ("WELL KNOWN FACT", False),
        ("WELLKNOWN FACT", False),
        ("WELL-KNOWN FACTS", False),
    ],
)
def test_solve_requires_letters_word_breaks_and_punctuation(attempt, ok):
    assert solve_matches("WELL-KNOWN FACT", attempt) is ok


def test_solve_requires_apostrophes_and_commas():
    assert solve_matches("DON'T STOP", "don't stop")
    assert solve_matches("DON'T STOP", "don’t stop")
    assert not solve_matches("DON'T STOP", "DONT STOP")
    assert solve_matches("YES, SIR", "yes, sir")
    assert not solve_matches("YES, SIR", "YES SIR")
