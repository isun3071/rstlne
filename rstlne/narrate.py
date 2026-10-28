"""Plain-English text for the table, wedges, and results, shared by the CLI and the model prompts."""

from __future__ import annotations

from rstlne.engine.state import BonusPicks, BuyVowel, CallConsonant, CallLetter, PublicView, Result, Spin
from rstlne.engine.wheel import Kind, Wedge

_EVENTS = {
    "wild_card": "Claimed the Wild Card.",
    "million_card": "Claimed the Million card.",
    "turn_passed": "Turn passes.",
    "turn_cap": "The round hit its turn limit with no solver.",
}


def money(amount: int) -> str:
    return f"-${-amount:,}" if amount < 0 else f"${amount:,}"


def seat_name(seat: int, viewer: int | None = None) -> str:
    return "You" if seat == viewer else f"Seat {seat + 1}"


def wedge_text(wedge: Wedge) -> str:
    match wedge.kind:
        case Kind.CASH:
            return money(wedge.value) + (" with the Wild Card" if wedge.wild else "")
        case Kind.MILLION:
            return f"the Million wedge ({money(wedge.value)} per copy)"
        case Kind.MYSTERY:
            return f"a Mystery wedge ({money(wedge.value)} per copy)"
        case Kind.EXPRESS:
            return f"the Express ({money(wedge.value)} per copy)"
        case Kind.FREE_PLAY:
            return "Free Play"
        case Kind.BANKRUPT:
            return "Bankrupt"
    return "Lose a Turn"


def table(view: PublicView, viewer: int | None = None) -> list[str]:
    names = [seat_name(i, viewer) for i in range(len(view.banks))]
    heading = f"Round {view.round_number}" if view.round_number else "Bonus round"
    lines = [
        f"{heading}. Category: {view.category}",
        f"Board: {view.board}",
        f"Used letters: {' '.join(view.used_letters) or 'none'}",
        "Round banks: " + " | ".join(f"{n} {money(b)}" for n, b in zip(names, view.banks)),
        "Game totals: " + " | ".join(f"{n} {money(t)}" for n, t in zip(names, view.totals)),
    ]
    cards = [
        f"{n} {'hold' if n == 'You' else 'holds'} the {card}"
        for n, wild, million in zip(names, view.wild_cards, view.million_cards)
        for card, held in (("Wild Card", wild), ("Million card", million))
        if held
    ]
    if cards:
        lines.append("Cards: " + "; ".join(cards) + ".")
    if view.wedge is not None:
        lines.append(f"Wedge: {wedge_text(view.wedge)}")
    return lines


def describe(result: Result, viewer: int | None = None) -> str:
    """One line for what an action did, like "Seat 2 called N: 2 Ns, +$1,600."."""
    extras = []
    if "bankrupt" in result.events and result.outcome not in ("bankrupt", "flipped_bankrupt"):
        extras.append("Bankrupt!")  # an Express bust
    extras += [_EVENTS[e] for e in result.events if e in _EVENTS]
    return " ".join([_outcome(seat_name(result.seat, viewer), result), *extras])


def _outcome(who: str, result: Result) -> str:
    a, o = result.action, result.outcome
    if isinstance(a, Spin):
        return f"{who} spun {wedge_text(result.wedge)}."
    if isinstance(a, (CallConsonant, CallLetter, BuyVowel)) and o in ("correct", "missing", "repeated"):
        verb = "bought" if isinstance(a, BuyVowel) else "called"
        letter = str(a.letter).strip().upper()
        if o == "repeated":
            return f"{who} {verb} {letter}, which was already called."
        if o == "missing":
            return f"{who} {verb} {letter}: none."
        found = f"{result.count} {letter}" + ("s" if result.count > 1 else "")
        gain = f", +{money(result.earned)}" if result.earned > 0 else ""
        return f"{who} {verb} {letter}: {found}{gain}."
    answer = str(getattr(a, "answer", "")).strip().upper()
    match o:
        case "kept":
            return f"{who} kept the {money(result.earned)}."
        case "flipped_prize":
            return f"{who} flipped the Mystery wedge and found {money(result.earned)}!"
        case "flipped_bankrupt":
            return f"{who} flipped the Mystery wedge and found Bankrupt."
        case "passed_express":
            return f"{who} passed on the Express."
        case "rode_express":
            return f"{who} is riding the Express!"
        case "used_wild":
            return f"{who} spent the Wild Card on an extra consonant."
        case "declined_wild":
            return f"{who} kept the Wild Card for later."
        case "solved":
            return f"{who} solved it: {answer}! Banked {money(result.earned)}."
        case "wrong_solve":
            return f'{who} tried "{answer}". Wrong.'
        case "forfeit":
            return f"{who} used up three tries without a valid move."
        case "picks" if isinstance(a, BonusPicks):
            consonants = " ".join(str(c).strip().upper() for c in a.consonants)
            return f"{who} picked {consonants} and {str(a.vowel).strip().upper()}."
        case "bonus_solved":
            return f"{who} solved the bonus puzzle: {answer}! The envelope held {money(result.earned)}."
        case "bonus_missed":
            return f'{who} guessed "{answer}". Not it.'
    return f"{who}: {o}."
