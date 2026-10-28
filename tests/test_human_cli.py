import pytest

from wof.engine.state import (
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
from wof.players.human_cli import HumanPlayer, parse_command


def view(phase, legal, bonus_consonants=3):
    return PublicView(
        seat=0, phase=phase, round_number=1, category="Phrase", board="_ _ _", used_letters=(),
        banks=(0, 0, 0), totals=(0, 0, 0), wild_cards=(False,) * 3, million_cards=(False,) * 3,
        turn=0, wedge=None, express=phase is Phase.EXPRESS, legal_actions=legal,
        bonus_consonants=bonus_consonants,
    )


TURN = view(Phase.TURN, ("spin", "buy_vowel", "solve"))


@pytest.mark.parametrize(
    "text, current, action",
    [
        ("s", TURN, Spin()),
        ("spin", TURN, Spin()),
        ("v e", TURN, BuyVowel("E")),
        ("solve wheel of fortune", TURN, Solve("wheel of fortune")),
        ("t", view(Phase.CALL_CONSONANT, ("call_consonant",)), CallConsonant("T")),
        ("t", view(Phase.WILD_CONSONANT, ("call_consonant",)), CallConsonant("T")),
        ("a", view(Phase.FREE_PLAY, ("call_letter",)), CallLetter("A")),
        ("keep", view(Phase.MYSTERY_CHOICE, ("keep", "flip")), Choose("keep")),
        ("FLIP", view(Phase.MYSTERY_CHOICE, ("keep", "flip")), Choose("flip")),
        ("pass", view(Phase.EXPRESS_CHOICE, ("pass", "play")), Choose("pass")),
        ("play", view(Phase.EXPRESS_CHOICE, ("pass", "play")), Choose("play")),
        ("wild", view(Phase.WILD_CHOICE, ("use_wild",)), UseWild(True)),
        ("no", view(Phase.WILD_CHOICE, ("use_wild",)), UseWild(False)),
        ("d", view(Phase.EXPRESS, ("call_consonant", "buy_vowel", "solve")), CallConsonant("D")),
        ("v a", view(Phase.EXPRESS, ("call_consonant", "buy_vowel", "solve")), BuyVowel("A")),
        ("b g h i", view(Phase.BONUS_PICKS, ("bonus_picks",)), BonusPicks(("B", "G", "H"), "I")),
        ("BGHI", view(Phase.BONUS_PICKS, ("bonus_picks",)), BonusPicks(("B", "G", "H"), "I")),
    ],
)
def test_short_commands(text, current, action):
    assert parse_command(text, current) == action


@pytest.mark.parametrize(
    "text, current",
    [
        ("", TURN),
        ("x", TURN),
        ("solve", TURN),
        ("v", TURN),
        ("s", view(Phase.TURN, ("buy_vowel", "solve"))),  # spinning is not legal
        ("maybe", view(Phase.MYSTERY_CHOICE, ("keep", "flip"))),
        ("tt", view(Phase.CALL_CONSONANT, ("call_consonant",))),
        ("b g h", view(Phase.BONUS_PICKS, ("bonus_picks",))),  # no vowel
        ("b g a i", view(Phase.BONUS_PICKS, ("bonus_picks",))),  # two vowels
    ],
)
def test_bad_commands_explain_themselves(text, current):
    with pytest.raises(ValueError):
        parse_command(text, current)


def test_typos_reprompt_until_a_command_parses():
    replies = iter(["x", "", "s"])
    written = []
    human = HumanPlayer(0, read=lambda prompt: next(replies), write=written.append)
    assert human.decide(TURN) == Spin()
    assert len([w for w in written if w.startswith("  ")]) == 2


def timed(answer, elapsed):
    times = iter([100.0, 100.0 + elapsed])
    return HumanPlayer(0, write=lambda text: None, read_timed=lambda seconds: answer, clock=lambda: next(times), seconds=10)


def test_bonus_solve_in_time_counts():
    assert timed("big city", 4).decide(view(Phase.BONUS_SOLVE, ("bonus_solve",))) == BonusSolve("big city")


@pytest.mark.parametrize("answer, elapsed", [(None, 10), ("big city", 11), ("", 3)])
def test_late_or_missing_bonus_solve_counts_as_wrong(answer, elapsed):
    assert timed(answer, elapsed).decide(view(Phase.BONUS_SOLVE, ("bonus_solve",))) == Forfeit()
