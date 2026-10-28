"""Configuration 5: a decision model makes every choice, and an LLM writes the solves."""

from __future__ import annotations

from dataclasses import replace

from rstlne.engine.puzzle import CONSONANTS, LETTERS, VOWELS
from rstlne.engine.state import (
    Action,
    BonusPicks,
    BuyVowel,
    CallConsonant,
    CallLetter,
    Choose,
    Phase,
    PublicView,
    Result,
    Rules,
    Spin,
    UseWild,
)
from rstlne.engine.wheel import WheelSpec
from rstlne.llm.decisions import DecisionClient, choice, noul
from rstlne.llm.openrouter import Usage
from rstlne.narrate import money, table
from rstlne.players.base import CallRecord, InvalidResponse, Player
from rstlne.players.llm import LLMPlayer, intro, phase_note, rules_text

SOLVABLE = "Can the puzzle be solved correctly from this board right now?"
SOLVABLE_QUESTION = noul(
    SOLVABLE,
    "The board and category point to one answer that can be written out now.",
    "More letters are needed before the answer is clear.",
)


def decision_state(seat: int, rules: Rules, spec: WheelSpec, view: PublicView, note: str | None = None) -> str:
    """What a decision model sees: the rules summary and the public table."""
    lines = [intro(seat), "", rules_text(rules, spec), "", "The table now", *table(view, seat)]
    for extra in (phase_note(view, rules, spec), note):
        if extra:
            lines.append(extra)
    return "\n".join(lines)


class DecisionPlayer(Player):
    max_attempts = 3

    def __init__(
        self,
        seat: int,
        model: str,
        decisions: DecisionClient,
        solver: LLMPlayer,
        rules: Rules,
        spec: WheelSpec,
        threshold: float,
        session_id: str | None = None,
    ):
        self.seat = seat
        self.model = model
        self.decisions = decisions
        self.solver = solver
        self.rules = rules
        self.spec = spec
        self.threshold = threshold
        self.session_id = session_id
        self.usage = Usage()  # decision calls; the solver tracks its own
        self.solving = False  # the latest move was the solver's, so a retry goes back to it
        self._record: dict = {}
        self._call_usage = Usage()

    def describe(self) -> dict:
        return {"kind": "decision", "model": self.model, "solver": self.solver.model, "threshold": self.threshold}

    def label(self) -> str:
        return f"{self.model} + {self.solver.model}"

    def observe(self, view: PublicView, result: Result) -> None:
        self.solver.observe(view, result)

    def decide(self, view: PublicView, error: str | None = None) -> Action:
        self._record = {"threshold": self.threshold, "solve_check": None, "decisions": [], "solver": None}
        self._call_usage = Usage()
        try:
            if error is not None and self.solving:
                return self._solve(view, error)
            self.solving = False
            return self._choose(view)
        finally:
            self.last_call = CallRecord(raw=self._record, usage=self._call_usage)

    def thoughts(self) -> list[str]:
        lines = []
        for decision in self._record.get("decisions", []):
            parts = []
            for name, picked in decision["chosen"].items():
                answer = decision["answers"].get(name, {})
                if answer.get("type") == "noul":
                    parts.append(f"P(solvable) {picked:.2f}")
                else:
                    parts.append(f"{name} {picked} ({answer.get('probabilities', {}).get(picked, 0):.2f})")
            lines.append(", ".join(parts))
        return lines

    def _choose(self, view: PublicView) -> Action:
        match view.phase:
            case Phase.TURN | Phase.EXPRESS:
                return self._turn(view)
            case Phase.CALL_CONSONANT | Phase.WILD_CONSONANT:
                return CallConsonant(self._pick(view, "consonant", "Which consonant should you call?", self._letters(view, CONSONANTS)))
            case Phase.FREE_PLAY:
                return CallLetter(self._pick(view, "letter", "Free Play: which letter should you call?", self._letters(view, LETTERS)))
            case Phase.MYSTERY_CHOICE:
                return Choose(self._pick(view, "mystery", "Keep the Mystery wedge's money, or flip it?", {
                    "keep": f"Keep {money(self.spec.mystery_face)} per copy.",
                    "flip": f"Give that up and flip: {money(self.spec.mystery_prize)} or Bankrupt.",
                }))
            case Phase.EXPRESS_CHOICE:
                return Choose(self._pick(view, "express", "Pass on the Express, or ride it?", {
                    "pass": "Keep playing normally.",
                    "play": (
                        f"Call consonants at {money(self.spec.express)} each and buy vowels with no spinning "
                        "until you solve. Any miss, repeat, or wrong solve is Bankrupt."
                    ),
                }))
            case Phase.WILD_CHOICE:
                return UseWild(self._pick(view, "wild_card", "Spend the Wild Card now?", {
                    "spend": "Call one extra consonant at this wedge's value. A miss passes your turn.",
                    "keep": "Save it for an extra consonant in the bonus round.",
                }) == "spend")
            case Phase.BONUS_PICKS:
                return self._bonus_picks(view)
        return self._solve(view)  # the bonus solve

    def _turn(self, view: PublicView) -> Action:
        moves = [kind for kind in view.legal_actions if kind != "solve"]
        if not moves:
            return self._solve(view)
        questions = {"solvable": SOLVABLE_QUESTION}
        if len(moves) > 1:
            questions["action"] = choice("Which move should you make?", {kind: self._move_text(kind) for kind in moves})
        if "buy_vowel" in moves:
            questions["vowel"] = choice("If you buy a vowel, which one?", self._letters(view, VOWELS))
        if view.express and "call_consonant" in moves:
            questions["consonant"] = choice("If you call a consonant, which one?", self._letters(view, CONSONANTS))
        chosen = self._ask(view, questions)
        p_yes = chosen["solvable"]
        if not isinstance(p_yes, (int, float)):
            raise InvalidResponse("bad_decision", f"P(yes) should be a number, got {p_yes!r}")
        if p_yes >= self.threshold:
            self._record["solve_check"] = p_yes
            return self._solve(view)
        move = chosen.get("action", moves[0])
        if move == "spin":
            return Spin()
        if move == "buy_vowel":
            return BuyVowel(chosen["vowel"])
        return CallConsonant(chosen["consonant"])

    def _bonus_picks(self, view: PublicView) -> Action:
        base = self.rules.bonus_consonants
        picks: list[str] = []

        def consonant(instructions: str) -> None:
            note = f"Picked so far: {' '.join(picks)}" if picks else None
            picks.append(self._pick(view, "consonant", instructions, self._letters(view, CONSONANTS, picks), note))

        for n in range(1, base + 1):
            consonant(f"Bonus round: pick consonant {n} of {base}.")
        vowel = self._pick(view, "vowel", "Bonus round: pick your vowel.", self._letters(view, VOWELS), f"Picked so far: {' '.join(picks)}")
        for _ in range(view.bonus_consonants - base):
            consonant("Bonus round: your Wild Card buys one more consonant. Pick it.")
        return BonusPicks(tuple(picks), vowel)

    def _solve(self, view: PublicView, error: str | None = None) -> Action:
        self.solving = True
        kind = "bonus_solve" if view.phase is Phase.BONUS_SOLVE else "solve"
        try:
            return self.solver.decide(replace(view, legal_actions=(kind,)), error)
        finally:
            call = self.solver.last_call
            if call is not None:
                self._record["solver"] = call.raw
                self._call_usage += call.usage

    def _pick(self, view: PublicView, name: str, instructions: str, options: dict[str, str], note: str | None = None) -> str:
        return self._ask(view, {name: choice(instructions, options)}, note)[name]

    def _ask(self, view: PublicView, questions: dict[str, dict], note: str | None = None) -> dict:
        """One Decisions call. Logs every distribution, then checks each choice is an offered option."""
        decisions = self.decisions.ask(model=self.model, state=self._state(view, note), questions=questions, session_id=self.session_id)
        self.usage += decisions.usage
        self._call_usage += decisions.usage
        chosen = {}
        for name, question in questions.items():
            answer = decisions.answers.get(name) or {}
            chosen[name] = answer.get("noul") if question["type"] == "noul" else answer.get("choice")
        self._record["decisions"].append({
            "model": decisions.model or self.model,
            "provider": decisions.provider,
            "questions": {
                name: {"type": q["type"], "options": list(q["criteria"]) if q["type"] == "choice" else None}
                for name, q in questions.items()
            },
            "answers": decisions.answers,
            "chosen": chosen,
        })
        for name, question in questions.items():
            if question["type"] == "choice" and chosen[name] not in question["criteria"]:
                raise InvalidResponse("bad_decision", f"{name}: {chosen[name]!r} is not one of the options")
        return chosen

    def _state(self, view: PublicView, note: str | None) -> str:
        return decision_state(self.seat, self.rules, self.spec, view, note)

    def _letters(self, view: PublicView, pool: frozenset[str], also_used: list[str] = ()) -> dict[str, str]:
        """Unused letters from `pool`. If every one is used, the whole pool, since a repeat is legal."""
        unused = sorted(pool - set(view.used_letters) - set(also_used)) or sorted(pool)
        return {letter: f"The letter {letter}." for letter in unused}

    def _move_text(self, kind: str) -> str:
        return {
            "spin": "Spin the wheel, then call a consonant for the wedge's value. Risks Bankrupt and Lose a Turn.",
            "buy_vowel": f"Buy a vowel from your round bank for {money(self.rules.vowel_cost)}.",
            "call_consonant": f"Call a consonant at {money(self.spec.express)}, with no spin. A miss is Bankrupt.",
        }[kind]
