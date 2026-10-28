"""Hand-written Beliefs and views for bot tests, so decision parts are tested without a reader."""

from dataclasses import replace

from helpers import start

from rstlne.engine.rules import public_view
from rstlne.players.bot.belief import Belief, LetterStats


def stats(**letters):
    """stats(T=(0.9, 1.5)) -> {"T": LetterStats(0.9, 1.5, 1.0)}."""
    return {k: LetterStats(p, n if p else 0.0, 1.0 if p else 0.0) for k, (p, n) in letters.items()}


def belief(answers=(), oov=None, **letters):
    answers = tuple(answers)
    if oov is None:
        oov = round(1 - sum(p for _, p in answers), 12)
    return Belief(letters=stats(**letters), answers=answers, oov=oov)


SURE = belief([("WHEEL OF FORTUNE", 1.0)], W=(1.0, 1.0), H=(1.0, 1.0), L=(1.0, 1.0), F=(1.0, 1.0),
              R=(1.0, 1.0), T=(1.0, 1.0), N=(1.0, 1.0), E=(1.0, 3.0), O=(1.0, 2.0), U=(1.0, 1.0))
LOST = belief([], oov=1.0, T=(0.5, 1.0), N=(0.4, 1.0), S=(0.3, 1.0), E=(0.6, 1.5), A=(0.5, 1.0))


def view_at(rules, spec, round_number=1, bank=0, totals=(0, 0, 0), seat=0, **seat_changes):
    """Seat `seat`'s turn view in `round_number`, with its bank and the game totals set."""
    from helpers import to_round
    state = to_round(start(rules, spec), round_number)
    state = replace(state, seat=seat)
    for i, total in enumerate(totals):
        state = state.with_seat(i, total=total, bank=0)
    state = state.with_seat(seat, bank=bank, **seat_changes)
    return public_view(state, seat), state
