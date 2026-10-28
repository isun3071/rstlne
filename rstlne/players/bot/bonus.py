"""The bonus round: brute force every legal set of picks, then answer with the best guess."""

from __future__ import annotations

from itertools import combinations

from rstlne.engine.puzzle import CONSONANTS, VOWELS
from rstlne.engine.state import BonusPicks, PublicView, Rules
from rstlne.players.bot import info
from rstlne.players.bot.belief import Belief
from rstlne.players.bot.reader import FREQUENCY, board_text


def picks(belief: Belief, view: PublicView, rules: Rules) -> BonusPicks:
    """The picks with the best chance that the best guess afterwards is right. Ties go to common letters."""
    given = set(rules.bonus_letters) | set(view.used_letters)
    consonants = sorted(CONSONANTS - given)
    vowels = sorted(VOWELS - given)
    best, best_key = None, None
    for chosen in combinations(consonants, view.bonus_consonants):
        common = sum(FREQUENCY[c] for c in chosen)
        for vowel in vowels:
            key = (info.solve_chance(belief, (*chosen, vowel)), common + FREQUENCY[vowel])
            if best_key is None or key > best_key:
                best, best_key = BonusPicks(chosen, vowel), key
    return best


def answer(belief: Belief, view: PublicView) -> str:
    """The best guess, or with no guess at all, the board with E in every hidden square."""
    return belief.best or board_text(view.board).replace("_", "E")
