import pytest

from rstlne.engine.puzzle import (
    Puzzle,
    board,
    fits_board,
    fits_shown,
    pattern,
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


@pytest.mark.parametrize(
    "attempt, fits",
    [
        ("A FULL TANK OF GAS", True),
        ("a  full tank of gas", True),
        ("A BULL TANK OF GAS", True),  # wrong, but it fits the board
        ("ANTIQUE ...", False),  # 2 words where the board has 5
        ("A FULL TANKS OF GAS", False),  # a 5 letter word in a 4 letter slot
        ("A FULL BANK OF GAS", False),  # changes a revealed T
        ("A FUNL TANK OF GAS", False),  # puts a used N in a hidden square
    ],
)
def test_fits_board(attempt, fits):
    assert fits_board("A FULL TANK OF GAS", attempt, frozenset("TAN")) is fits


def test_fits_board_checks_punctuation():
    assert fits_board("DON'T STOP", "WON'T STOP", frozenset())
    assert not fits_board("DON'T STOP", "DON-T STOP", frozenset())
    assert not fits_board("DON'T STOP", "DONT STOP", frozenset())
    assert not fits_board("BOWLING & GOLF BALL", "BOWLING AND GOLF BALL", frozenset())


@pytest.mark.parametrize(
    "attempt, fits",
    [
        ("A FULL TANK OF GAS", True),
        ("A BULL TANK OF GAS", True),
        ("A FULL TANKS OF GAS", False),
        ("A FULL BANK OF GAS", False),
        ("A FUNL TANK OF GAS", False),
        ("", False),
    ],
)
def test_fits_shown_checks_against_the_public_board(attempt, fits):
    assert fits_shown("A ____ TAN_ __ _A_", attempt, frozenset("TAN")) is fits


def test_fits_shown_checks_punctuation():
    assert fits_shown("___'T STOP", "WON'T STOP", frozenset("STP"))
    assert not fits_shown("___'T STOP", "DONT STOP", frozenset("STP"))


def test_pattern_is_compact_with_word_lengths():
    assert pattern("A FULL TANK OF GAS", frozenset("TAN")) == "A ____ TAN_ __ _A_ (word lengths 1, 4, 4, 2, 3)"
    assert pattern("DON'T STOP", frozenset("T")) == "___'T _T__ (word lengths 5, 4)"
