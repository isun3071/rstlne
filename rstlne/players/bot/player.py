"""The bot seat."""

from __future__ import annotations

from dataclasses import replace

from rstlne.engine.puzzle import LETTERS
from rstlne.engine.state import (
    Action,
    BonusSolve,
    BuyVowel,
    CallConsonant,
    CallLetter,
    Choose,
    Phase,
    PublicView,
    Result,
    Rules,
    Solve,
    Spin,
    UseWild,
)
from rstlne.engine.wheel import Kind, WheelSpec
from rstlne.llm.openrouter import Usage
from rstlne.players.base import CallRecord, Player
from rstlne.players.bot import bonus, calibration, info, lexicon, planner, versions
from rstlne.players.bot.belief import Belief
from rstlne.players.bot.full import FullReader
from rstlne.players.bot.objective import Objective
from rstlne.players.bot.reader import FREQUENCY, FrequencyReader, Reader, board_text
from rstlne.players.bot.steal import Steal
from rstlne.players.bot.value import Situation

_OPPORTUNITIES = ("spin", "buy_vowel", "solve")  # moves made when the seat could have solved


def make_reader(knobs: versions.Knobs) -> Reader:
    """The full reader when the word data is fetched, or letter frequency alone until it is."""
    root = lexicon.data_dir()
    if not lexicon.available(root):
        return FrequencyReader()
    reader = FullReader(lexicon.load(str(root), knobs.vocabulary), knobs)
    reader.fingerprint = lexicon.fingerprint(root, knobs.vocabulary)
    return reader


def share_revealed(board: str) -> float:
    """Letter squares showing over all letter squares."""
    text = board_text(board)
    hidden = text.count("_")
    shown = sum(c in LETTERS for c in text)
    return shown / (shown + hidden) if shown + hidden else 1.0


def guess(belief: Belief, view: PublicView) -> str:
    """The best answer, or with none, the board with the commonest unused letter in every hidden square."""
    if belief.best:
        return belief.best
    unused = [c for c in sorted(FREQUENCY, key=FREQUENCY.get, reverse=True) if c not in view.used_letters]
    return board_text(view.board).replace("_", unused[0] if unused else "E")


class BotPlayer(Player):
    max_attempts = 3

    def __init__(self, seat: int, rules: Rules, spec: WheelSpec, reader: Reader, version: int = 1,
                 knobs: versions.Knobs | None = None):
        self.seat = seat
        self.rules = rules
        self.spec = spec
        self.reader = reader
        self.version = version
        self.experiment = knobs is not None and knobs != versions.knobs(version)
        self.knobs = knobs or versions.knobs(version)
        self.steal = Steal(seat, self.knobs)
        self.last_call: CallRecord | None = None
        self._beliefs: dict[tuple, Belief] = {}
        self._before: PublicView | None = None  # the table before the latest action
        self._pending = 0  # copies found on a Mystery wedge, waiting on keep or flip
        self._record: dict = {}

    def describe(self) -> dict:
        info = {"kind": "bot", "version": self.version, "reader": self.reader.name}
        if getattr(self.reader, "fingerprint", None):
            info["data"] = self.reader.fingerprint  # which fetched data the reader read
        return {**info, "experiment": True} if self.experiment else info

    def label(self) -> str:
        return f"bot v{self.version}"

    def observe(self, view: PublicView, result: Result) -> None:
        if result.seat == self.seat and result.outcome == "correct" and result.wedge and result.wedge.kind is Kind.MYSTERY:
            self._pending = result.count
        before = self._before
        if (result.seat != self.seat and before is not None and before.round_number is not None
                and before.phase in (Phase.TURN, Phase.EXPRESS) and result.action.kind in _OPPORTUNITIES):
            belief = self._read(before)
            self.steal.note(result.seat, share_revealed(before.board), belief.confidence, result.outcome == "solved")
        self._before = view

    def decide(self, view: PublicView, error: str | None = None) -> Action:
        belief = self._read(view)
        self._record = {"version": self.version, "confidence": belief.confidence, "best": belief.best,
                        "oov": belief.oov, "p_steal": None, "values": {}}
        try:
            return self._decide(view, belief)
        finally:
            self.last_call = CallRecord(raw=self._record, usage=Usage())

    def thoughts(self) -> list[str]:
        r = self._record
        if not r:
            return []
        values = ", ".join(f"{k} {v:.3f}" for k, v in r["values"].items())
        steal = "" if r["p_steal"] is None else f" · steal odds {r['p_steal']:.2f}"
        return [f"confidence {r['confidence']:.2f} in {r['best'] or 'nothing yet'} · unknown {r['oov']:.2f}{steal}"
                + (f" · {values}" if values else "")]

    def _decide(self, view: PublicView, belief: Belief) -> Action:
        legal = view.legal_actions
        if view.phase is Phase.BONUS_PICKS:
            return bonus.picks(belief, view, self.rules)
        if view.phase is Phase.BONUS_SOLVE:
            return BonusSolve(guess(belief, view))
        s = self._situation(view, belief)
        match view.phase:
            case Phase.TURN:
                if s.c >= self.knobs.known_answer:
                    kind = planner.decide(s, legal)
                else:
                    options = s.turn_options(legal)
                    self._note(options)
                    kind = s.goal.choose(options)
                if kind == "spin":
                    return Spin()
                if kind == "buy_vowel":
                    return BuyVowel(s.vowel()[0])
                return Solve(guess(belief, view))
            case Phase.EXPRESS:
                kind, letter = s.express_move(legal)
                return CallConsonant(letter) if kind == "call_consonant" else Solve(guess(belief, view))
            case Phase.CALL_CONSONANT:
                return CallConsonant(s.consonant(view.wedge)[0])
            case Phase.WILD_CONSONANT:
                return CallConsonant(s.consonant(replace(view.wedge, wild=False), spend_wild=True)[0])
            case Phase.FREE_PLAY:
                return CallLetter(s.free_play()[0])
            case Phase.MYSTERY_CHOICE:
                return Choose(s.mystery(self._pending))
            case Phase.EXPRESS_CHOICE:
                return Choose(s.express())
            case Phase.WILD_CHOICE:
                return UseWild(s.wild(view.wedge))
        raise ValueError(f"the bot has no move for {view.phase}")

    def _situation(self, view: PublicView, belief: Belief) -> Situation:
        share = share_revealed(view.board)
        letters = len(board_text(view.board).replace(" ", ""))
        # The next seat's likely call: the consonant with the most expected squares
        consonants = [c for c in belief.letters if c not in "AEIOU"]
        if consonants:
            top = max(consonants, key=lambda c: (belief.stats(c).p_hit * belief.stats(c).count, c))
            stats, after = belief.stats(top), info.after(belief, top)
            share_after = min(1.0, share + stats.p_hit * stats.count / max(letters, 1))
            confidence_after = stats.p_hit * after.hit + (1 - stats.p_hit) * after.miss
        else:
            share_after, confidence_after = share, belief.confidence
        odds = self.steal.odds(share, belief.confidence, share_after, confidence_after)
        self._record["p_steal"] = odds.total
        goal = Objective(view, self.rules, self.spec, self.knobs)
        prior = self.steal.prior
        return Situation(view, belief, goal, odds, self.rules, self.spec, self.knobs,
                         calibrate=calibration.curve(self.knobs.calibration),
                         turn_chance=lambda c: max(c, prior(share, c)))

    def _note(self, options: dict) -> None:
        self._record["values"] = {k: v.main for k, v in options.items()}

    def _read(self, view: PublicView) -> Belief:
        key = (view.round_number, view.category, view.board, view.used_letters)
        if key not in self._beliefs:
            self._beliefs[key] = self.reader.read(view)
        return self._beliefs[key]
