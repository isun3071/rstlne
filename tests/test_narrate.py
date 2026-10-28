import pytest
from helpers import start

from rstlne.engine.rules import public_view
from rstlne.engine.state import BonusPicks, BuyVowel, CallConsonant, Choose, Result, Solve, Spin
from rstlne.engine.wheel import Kind, Wedge
from rstlne.narrate import describe, money, table, wedge_text

CASH = Wedge(3, Kind.CASH, 650)


@pytest.mark.parametrize(
    "result, viewer, text",
    [
        (Result(0, Spin(), "landed", CASH), None, "Seat 1 spun $650."),
        (Result(0, CallConsonant("t"), "correct", CASH, count=2, earned=1300), 0, "You called T: 2 Ts, +$1,300."),
        (Result(1, CallConsonant("Z"), "missing", CASH, events=("turn_passed",)), 0, "Seat 2 called Z: none. Turn passes."),
        (
            Result(1, CallConsonant("T"), "repeated", CASH, events=("turn_passed",)),
            None,
            "Seat 2 called T, which was already called. Turn passes.",
        ),
        (
            Result(2, Spin(), "bankrupt", Wedge(14, Kind.BANKRUPT), events=("bankrupt", "turn_passed")),
            None,
            "Seat 3 spun Bankrupt. Turn passes.",
        ),
        (Result(0, BuyVowel("E"), "correct", CASH, count=3, earned=-250), 0, "You bought E: 3 Es."),
        (
            Result(0, Choose("flip"), "flipped_prize", Wedge(5, Kind.MYSTERY, 1000), earned=10000),
            None,
            "Seat 1 flipped the Mystery wedge and found $10,000!",
        ),
        (
            Result(0, Choose("flip"), "flipped_bankrupt", Wedge(5, Kind.MYSTERY, 1000), events=("bankrupt", "turn_passed")),
            None,
            "Seat 1 flipped the Mystery wedge and found Bankrupt. Turn passes.",
        ),
        (
            Result(0, Solve("wheel of fortune"), "solved", CASH, earned=3200, events=("round_over",)),
            None,
            "Seat 1 solved it: WHEEL OF FORTUNE! Banked $3,200.",
        ),
        (
            Result(0, Solve("golden gate park"), "wrong_solve", Wedge(12, Kind.EXPRESS, 1000), events=("bankrupt", "turn_passed")),
            None,
            'Seat 1 tried "GOLDEN GATE PARK". Wrong. Bankrupt! Turn passes.',
        ),
        (
            Result(0, CallConsonant("F"), "correct", Wedge(2, Kind.CASH, 800, wild=True), count=2, earned=1600, events=("wild_card",)),
            None,
            "Seat 1 called F: 2 Fs, +$1,600. Claimed the Wild Card.",
        ),
        (Result(0, BonusPicks(("B", "G", "C"), "I"), "picks"), 0, "You picked B G C and I."),
    ],
)
def test_describe(result, viewer, text):
    assert describe(result, viewer) == text


@pytest.mark.parametrize(
    "wedge, text",
    [
        (Wedge(1, Kind.CASH, 2500), "$2,500"),
        (Wedge(2, Kind.CASH, 800, wild=True), "$800 with the Wild Card"),
        (Wedge(9, Kind.MILLION, 500), "the Million wedge ($500 per copy)"),
        (Wedge(5, Kind.MYSTERY, 1000), "a Mystery wedge ($1,000 per copy)"),
        (Wedge(12, Kind.EXPRESS, 1000), "the Express ($1,000 per copy)"),
        (Wedge(16, Kind.FREE_PLAY, 500), "Free Play"),
    ],
)
def test_wedge_text(wedge, text):
    assert wedge_text(wedge) == text


def test_money():
    assert money(1300) == "$1,300"
    assert money(-250) == "-$250"


def test_table_shows_the_public_view(rules, wheel_spec):
    state = start(rules, wheel_spec).with_seat(0, bank=1200, wild=True).with_seat(2, total=3000)
    lines = table(public_view(state, 0), viewer=0)
    assert lines == [
        "Round 1. Category: Phrase",
        "Board: _ _ _ _ _   _ _   _ _ _ _ _ _ _",
        "Pattern: _____ __ _______ (word lengths 5, 2, 7)",
        "Used letters: none",
        "Round banks: You $1,200 | Seat 2 $0 | Seat 3 $0",
        "Game totals: You $0 | Seat 2 $0 | Seat 3 $3,000",
        "Cards: You hold the Wild Card.",
        "Wheel: the Wild Card on wedge 2; the Million wedge on wedge 9.",
    ]
