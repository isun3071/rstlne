"""One value function for every move:

    V(action) = immediate gain + P(keep the wheel) × V(continue)
                + P(lose the wheel) × [(1 − p_steal) × V(continue later) + p_steal × V(stolen)]

V(stolen) is what the bot is left with when an opponent solves: nothing from the round in dollars,
and the stealer's gain counted against the bot's win chance from round 3 on.

V(continue) is a race from the board a move leads to. Each turn the bot holds the wheel, it takes
the round with chance t: its confidence c, or while c is low, the chance any seat solves on its turn
at that board, since holding the wheel lets it reveal more. The opponents get their steal chances
in between, so the bot takes the round with chance t / (t + (1 − t) × p_steal).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import replace

from rstlne.engine.puzzle import CONSONANTS, LETTERS, VOWELS
from rstlne.engine.state import PublicView, Rules
from rstlne.engine.wheel import Kind, Wedge, WheelSpec
from rstlne.players.bot import info
from rstlne.players.bot.belief import Belief
from rstlne.players.bot.objective import ZERO, Objective, Value
from rstlne.players.bot.steal import Odds
from rstlne.players.bot.versions import Knobs


def _identity(c: float) -> float:
    return c


class Situation:
    """The bot's turn: its view, its Belief, what it plays for, and the steal odds."""

    def __init__(
        self,
        view: PublicView,
        belief: Belief,
        goal: Objective,
        odds: Odds,
        rules: Rules,
        spec: WheelSpec,
        knobs: Knobs,
        wheel: Sequence[Wedge] | None = None,
        calibrate: Callable[[float], float] = _identity,
        turn_chance: Callable[[float], float] = _identity,
    ):
        self.view = view
        self.belief = belief
        self.goal = goal
        self.odds = odds
        self.rules = rules
        self.spec = spec
        self.knobs = knobs
        self.wheel = tuple(view.wheel if wheel is None else wheel)
        self.calibrate = calibrate
        self.turn_chance = turn_chance
        me = view.seat
        self.bank = view.banks[me]
        self.wild_held = view.wild_cards[me]
        self.million_held = view.million_cards[me]
        self.c = calibrate(belief.confidence)
        used = set(view.used_letters)
        self.consonants = sorted(CONSONANTS - used)
        self.vowels = sorted(VOWELS - used)
        a, b = odds.seats
        self.stealers = {a: odds.next, b: (1 - odds.next) * odds.after}

    # The race and the two ways a turn ends

    def race(self, c: float) -> float:
        """The chance the bot takes the round from here, holding the wheel at confidence c."""
        t = self.turn_chance(c)
        steal = self.odds.total
        denominator = t + (1 - t) * steal
        return 1.0 if denominator == 0 else t / denominator

    def leaf(self, bank: float, c: float, wild: bool, million: bool) -> Value:
        """V(continue): the bot holds the wheel at this board."""
        win = self.race(c)
        return self.goal.win_round(bank, wild, million) * win + self.stolen(wild) * (1 - win)

    def stolen(self, wild: bool) -> Value:
        return self.goal.lose_round(wild, self.stealers)

    def lose_wheel(self, bank: float, c: float, wild: bool, million: bool) -> Value:
        """The wheel passes: an opponent may steal, or it comes back to the bot at this board."""
        steal = self.odds.total
        return self.stolen(wild) * steal + self.leaf(bank, c, wild, million) * (1 - steal)

    # Turn actions

    def solve(self) -> Value:
        wrong = self.calibrate(info.after_wrong_solve(self.belief))
        return (self.goal.win_round(self.bank, self.wild_held, self.million_held) * self.c
                + self.lose_wheel(self.bank, wrong, self.wild_held, self.million_held) * (1 - self.c))

    def spin(self) -> Value:
        total = ZERO
        for wedge in self.wheel:
            total += self._landing(wedge)
        return total * (1 / len(self.wheel))

    def vowel(self) -> tuple[str, Value]:
        return self._best({v: self.vowel_value(v) for v in self.vowels})

    def vowel_value(self, letter: str) -> Value:
        cost = self.rules.express_vowel_cost if self.view.express else self.rules.vowel_cost
        return self._reveal(letter, self.bank - cost, money=0)

    def choose_turn(self, legal: Sequence[str]) -> str:
        return self.goal.choose(self.turn_options(legal))

    def turn_options(self, legal: Sequence[str]) -> dict[str, Value]:
        options = {}
        if "spin" in legal:
            options["spin"] = self.spin()
        if "buy_vowel" in legal and self.vowels:
            options["buy_vowel"] = self.vowel()[1]
        if "solve" in legal and (self.belief.best or not options):  # no answer, no guess, unless it's the only move
            options["solve"] = self.solve()
        return options

    # Letters

    def call(self, letter: str, value: float, *, claim_wild: bool = False, claim_million: bool = False,
             wild: bool | None = None) -> Value:
        """Call `letter` at `value` per copy: a hit keeps the wheel, a miss passes it."""
        wild = self.wild_held if wild is None else wild
        stats = self.belief.stats(letter)
        after = info.after(self.belief, letter)
        hit = self.leaf(self.bank + value * stats.count, self.calibrate(after.hit), wild or claim_wild,
                        self.million_held or claim_million)
        miss = self.lose_wheel(self.bank, self.calibrate(after.miss), wild, self.million_held)
        return hit * stats.p_hit + miss * (1 - stats.p_hit)

    def consonant(self, wedge: Wedge, *, spend_wild: bool = False) -> tuple[str, Value]:
        """The best consonant for the wedge the bot landed on."""
        if not self.consonants:  # every consonant called: any call is a repeat
            return min(CONSONANTS), self.lose_wheel(self.bank, self.c, self.wild_held, self.million_held)
        options = {c: self._on_wedge(c, wedge, spend_wild) for c in self.consonants}
        return self._best(options)

    def free_play(self) -> tuple[str, Value]:
        """Any letter: a consonant earns per copy, a vowel is free, and a miss keeps the wheel."""
        options = {}
        for letter in sorted(LETTERS - set(self.view.used_letters)):
            money = self.spec.free_play if letter in CONSONANTS else 0
            options[letter] = self._reveal(letter, self.bank, money=money, miss_keeps=True)
        return self._best(options)

    # Special wedges

    def mystery(self, k: int) -> str:
        return self.goal.choose(self._mystery_options(self.bank, k))

    def express(self) -> str:
        """Board the Express only when riding it, final solve included, beats passing."""
        return self.goal.choose({"pass": self.leaf(self.bank, self.c, self.wild_held, self.million_held),
                                 "play": self.ride(self.bank)})

    def ride(self, bank: float) -> Value:
        """Call every safe consonant at the Express value, then solve. A miss or a wrong solve is Bankrupt."""
        safe = self.safe_consonants()
        money = self.spec.express * sum(self.belief.stats(c).count for c in safe)
        calls_hit = 1.0
        for c in safe:
            calls_hit *= self.belief.stats(c).p_hit
        right = self.calibrate(info.solve_chance(self.belief, safe))
        bust = self.lose_wheel(0, self.calibrate(info.after_wrong_solve(self.belief)), False, False)
        solved = self.goal.win_round(bank + money, self.wild_held, self.million_held)
        return (solved * right + bust * (1 - right)) * calls_hit + bust * (1 - calls_hit)

    def express_move(self, legal: Sequence[str]) -> tuple[str, str | None]:
        """While riding: the safe consonant with the most copies, and once none is left, the solve."""
        safe = self.safe_consonants()
        if safe and "call_consonant" in legal:
            return "call_consonant", safe[0]
        return "solve", None

    def safe_consonants(self) -> list[str]:
        safe = [c for c in self.consonants if self.belief.stats(c).p_hit >= self.knobs.safe_hit]
        return sorted(safe, key=lambda c: (-self.belief.stats(c).count, -self.belief.stats(c).p_hit, c))

    def wild(self, wedge: Wedge) -> bool:
        """After a correct consonant on a dollar wedge: spend the Wild Card on one more, or keep it."""
        if not self.consonants:
            return False
        _, spend = self.consonant(replace(wedge, wild=False), spend_wild=True)  # the extra call can't claim a card
        keep = self.leaf(self.bank, self.c, True, self.million_held)
        return self.goal.choose({"keep": keep, "spend": spend}) == "spend"

    # Helpers

    def _landing(self, wedge: Wedge) -> Value:
        match wedge.kind:
            case Kind.BANKRUPT:
                return self.lose_wheel(0, self.c, False, False)
            case Kind.LOSE_A_TURN:
                return self.lose_wheel(self.bank, self.c, self.wild_held, self.million_held)
            case Kind.FREE_PLAY:
                return self.free_play()[1]
        if not self.consonants:
            return self.leaf(self.bank, self.c, self.wild_held, self.million_held)
        return self.consonant(wedge)[1]

    def _on_wedge(self, letter: str, wedge: Wedge, spend_wild: bool) -> Value:
        wild = False if spend_wild else None
        if wedge.kind is Kind.MYSTERY:
            return self._special_hit(letter, lambda bank, n: self.goal.choose_value(self._mystery_options(bank, n)))
        if wedge.kind is Kind.EXPRESS:
            return self._special_hit(letter, lambda bank, n: self.goal.choose_value({
                "pass": self.leaf(bank + wedge.value * n, self.c, self.wild_held, self.million_held),
                "play": self.ride(bank + wedge.value * n),
            }))
        return self.call(letter, wedge.value, claim_wild=wedge.wild, claim_million=wedge.kind is Kind.MILLION, wild=wild)

    def _special_hit(self, letter: str, on_hit: Callable[[float, float], Value]) -> Value:
        stats = self.belief.stats(letter)
        miss = self.lose_wheel(self.bank, self.calibrate(info.after(self.belief, letter).miss),
                               self.wild_held, self.million_held)
        if stats.p_hit == 0:
            return miss
        return on_hit(self.bank, stats.count) * stats.p_hit + miss * (1 - stats.p_hit)

    def _mystery_options(self, bank: float, k: float) -> dict[str, Value]:
        keep = self.leaf(bank + self.spec.mystery_face * k, self.c, self.wild_held, self.million_held)
        prize = self.leaf(bank + self.spec.mystery_prize, self.c, self.wild_held, self.million_held)
        bust = self.lose_wheel(0, self.c, False, False)
        return {"keep": keep, "flip": prize * 0.5 + bust * 0.5}  # either wedge may hide the $10,000

    def _reveal(self, letter: str, bank: float, money: float, miss_keeps: bool = False) -> Value:
        stats = self.belief.stats(letter)
        after = info.after(self.belief, letter)
        hit = self.leaf(bank + money * stats.count, self.calibrate(after.hit), self.wild_held, self.million_held)
        if miss_keeps:
            miss = self.leaf(bank, self.calibrate(after.miss), self.wild_held, self.million_held)
        else:
            miss = self.lose_wheel(bank, self.calibrate(after.miss), self.wild_held, self.million_held)
        return hit * stats.p_hit + miss * (1 - stats.p_hit)

    def _best(self, options: dict[str, Value]) -> tuple[str, Value]:
        best = self.goal.choose(options)
        return best, options[best]
