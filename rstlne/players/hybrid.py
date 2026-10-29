"""The hybrid seat: the bot plays every move, and a model reads the board for it.

On its own turns, once per new board, the hybrid asks the model whether the board looks solvable and,
if so, for the answer. A fitting answer joins the reader's samples with a share set by the model's
trust curve. The bot decides everything, including when to solve.
"""

from __future__ import annotations

import json
import math
import time

from rstlne.engine.puzzle import compact, fits_shown, normalize
from rstlne.engine.state import Action, Phase, PublicView, Result, Rules
from rstlne.engine.wheel import WheelSpec
from rstlne.llm.openrouter import OpenRouter, Usage, check_temperature
from rstlne.players.base import CallRecord, InvalidResponse
from rstlne.players.bot import versions
from rstlne.players.bot.belief import Belief
from rstlne.players.bot.player import BotPlayer, share_revealed
from rstlne.players.bot.reader import Reader, board_text
from rstlne.players.bot.steal import Steal

SYSTEM = (
    "You read Wheel of Fortune puzzle boards. Each request shows a board with _ for every hidden letter. "
    "Say whether the puzzle looks solvable from the board as it stands and, if it does, give the answer. "
    "An answer is the whole puzzle, every word. It must match the board: the same number of words, the "
    "same word lengths, every revealed letter in place, and the punctuation shown. A hidden square never "
    "holds a used letter, and an answer proven wrong this round is wrong."
)
READ_BOARD = {
    "type": "function",
    "function": {
        "name": "read_board",
        "description": "Say whether the puzzle looks solvable now and, if it does, the answer.",
        "parameters": {
            "type": "object",
            "properties": {
                "solvable": {"type": "boolean", "description": "True if you can tell the answer from the board as it stands."},
                "answer": {"type": "string", "description": "The whole puzzle, every word, with its punctuation. Required when solvable is true."},
            },
            "required": ["solvable"],
        },
    },
}
ATTEMPTS = 3  # the first try and 2 reprompts; after that the ask counts as "not solvable"


def logistic(x: float) -> float:
    return 1 / (1 + math.exp(-x))


class HybridSteal(Steal):
    """The bot's steal odds on the model's own curve, which also knows whether the model can read the board."""

    def __init__(self, me: int, knobs: versions.Knobs, coefficients: tuple[float, float, float, float]):
        super().__init__(me, knobs)
        self.coefficients = coefficients
        self.readable = 0  # 1 when the latest ask this round got a fitting answer

    def prior(self, share: float, confidence: float) -> float:
        a, b, c, d = self.coefficients
        return logistic(a + b * share + c * confidence + d * self.readable)


def read_reply(message) -> tuple[bool, str | None]:
    """(solvable, answer) from a read_board call, or InvalidResponse."""
    calls = message.tool_calls or []
    if not calls:
        raise InvalidResponse("bad_tool_call", "No tool call. Call read_board.")
    call = calls[0].function
    if call.name != "read_board":
        raise InvalidResponse("bad_tool_call", f"{call.name} isn't on offer. Call read_board.")
    try:
        args = json.loads(call.arguments or "{}")
    except json.JSONDecodeError:
        raise InvalidResponse("bad_tool_call", "The arguments aren't valid JSON.") from None
    if not isinstance(args, dict) or not isinstance(args.get("solvable"), bool):
        raise InvalidResponse("bad_tool_call", "solvable must be true or false.")
    if not args["solvable"]:
        return False, None
    answer = args.get("answer")
    if not isinstance(answer, str) or not answer.strip():
        raise InvalidResponse("malformed_solve", "solvable is true, so give the answer: the whole puzzle.")
    return True, answer


def ask_text(view: PublicView, refuted: frozenset[str]) -> str:
    used = " ".join(sorted(view.used_letters)) or "none"
    return "\n".join([
        f"Category: {view.category}",
        f"Board: {view.board}",
        f"Pattern: {compact(view.board)}",
        f"Used letters: {used}",
        f"Proven wrong this round: {'; '.join(sorted(refuted)) or 'none'}",
        "Does the board look solvable right now? Call read_board.",
    ])


def _assistant(message) -> dict:
    """The model's reply as a message to send back, reasoning included, with its first tool call only."""
    entry: dict = {"role": "assistant", "content": message.content}
    extra = message.model_extra or {}
    if extra.get("reasoning_details"):
        entry["reasoning_details"] = extra["reasoning_details"]
    elif extra.get("reasoning"):
        entry["reasoning"] = extra["reasoning"]
    if message.tool_calls:
        first = message.tool_calls[0]
        entry["tool_calls"] = [{"id": first.id, "type": "function",
                                "function": {"name": first.function.name, "arguments": first.function.arguments}}]
    return entry


class HybridPlayer(BotPlayer):
    def __init__(
        self,
        seat: int,
        model: str,
        client: OpenRouter,
        trust: tuple[float, float, float, float, float],  # a, b, c, d, g of the model's trust curve
        steal: tuple[float, float, float, float],  # a, b, c, d of the model's steal curve
        rules: Rules,
        spec: WheelSpec,
        reader: Reader,
        version: int = 1,
        knobs: versions.Knobs | None = None,
        temperature: float | None = None,  # None keeps the model's own default
        session_id: str | None = None,
        reasoning_effort: str | None = None,
        provider: str | None = None,
    ):
        super().__init__(seat, rules, spec, reader, version, knobs)
        self.model = model
        self.client = client
        self.trust = tuple(trust)
        self.temperature = None if temperature is None else check_temperature(temperature)
        self.session_id = session_id
        self.reasoning_effort = reasoning_effort
        self.provider = provider
        self.steal = HybridSteal(seat, self.knobs, tuple(steal))
        self.usage = Usage()
        self._round: int | None | str = "start"
        self._asks: dict[tuple, dict] = {}  # one ask per board, with what came of it
        self._asked = 0  # asks this round
        self._alone: Belief | None = None  # the reader's own belief on the board being decided
        self._ask: dict | None = None
        self._ask_usage = Usage()

    def describe(self) -> dict:
        return {**super().describe(), "kind": "hybrid", "model": self.model, "temperature": self.temperature,
                "reasoning_effort": self.reasoning_effort, "provider": self.provider}

    def label(self) -> str:
        return f"bot v{self.version} + {self.model}"

    def observe(self, view: PublicView, result: Result) -> None:
        super().observe(view, result)
        self._new_round(view)

    def decide(self, view: PublicView, error: str | None = None) -> Action:
        self._alone, self._ask, self._ask_usage = None, None, Usage()
        try:
            return super().decide(view, error)
        finally:
            self._record["ask"] = self._ask
            self.last_call = CallRecord(raw=self._record, usage=self._ask_usage)

    def thoughts(self) -> list[str]:
        lines = super().thoughts()
        ask = self._ask
        if ask:
            reply = ask["reply"]
            said = f"solvable, {reply['answer']}" if reply["solvable"] else "not solvable"
            trust = f", trust {ask['trust']:.2f}" if ask["trust"] is not None else ""
            again = f" (same board as ask {ask['n']})" if ask["reused"] else ""
            lines.append(f"model: {said} · {ask['status']}{trust}{again}")
        return lines

    # The bot's hooks

    def _belief(self, view: PublicView) -> Belief:
        self._new_round(view)
        alone = self._alone = self._read(view)
        if view.phase is Phase.BONUS_PICKS:
            return alone  # the picks are the reader's
        refuted = self._refuted_in(view)
        key = (view.round_number, view.board, view.used_letters, refuted)
        entry = self._asks.get(key)
        if entry is None:
            entry = self._asks[key] = self._consult(view, alone, refuted)
            self._ask = {**entry["record"], "reused": False}
        else:
            self._ask = {**entry["record"], "reused": True}
        self.steal.readable = int(entry["record"]["status"] == "used")
        return entry["belief"]

    def _steal_belief(self, view: PublicView, belief: Belief) -> Belief:
        return self._alone or belief

    # The ask

    def _new_round(self, view: PublicView) -> None:
        if view.round_number != self._round:
            self._round = view.round_number
            self._asked = 0
            self.steal.readable = 0

    def _consult(self, view: PublicView, alone: Belief, refuted: frozenset[str]) -> dict:
        """Ask the model about this board, check its answer, and mix it in."""
        self._asked += 1
        reply, attempts, seconds, provider = self._send(view, refuted)
        answer, status, trust, belief = None, "failed" if reply is None else "not solvable", None, alone
        if reply and reply[0]:
            try:
                answer = normalize(reply[1])
            except ValueError:
                answer = None
            if answer is None or not fits_shown(board_text(view.board), answer, frozenset(view.used_letters)):
                status = "doesn't fit"
            elif answer in refuted:
                status = "refuted"
            else:
                status = "used"
                trust = self._trust(view, alone, answer)
                belief = self.reader.read(view, refuted, (answer, trust))
        record = {
            "n": self._asked, "model": self.model, "provider": provider,
            "reply": {"solvable": bool(reply and reply[0]), "answer": reply[1] if reply else None},
            "status": status, "trust": trust, "reader_confidence": alone.confidence,
            "merged_confidence": belief.confidence, "attempts": attempts, "seconds": round(seconds, 2),
        }
        return {"record": record, "belief": belief}

    def _trust(self, view: PublicView, alone: Belief, answer: str) -> float:
        a, b, c, d, g = self.trust
        shown = share_revealed(view.board)
        agree = float(alone.best == answer)
        p_reader = dict(alone.answers).get(answer, 0.0)
        return logistic(a + b * shown + c * agree + d * p_reader + g * alone.confidence)

    def _send(self, view: PublicView, refuted: frozenset[str]):
        """Up to ATTEMPTS requests. Returns ((solvable, answer) or None, attempts, seconds, provider)."""
        messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": ask_text(view, refuted)}]
        began, provider = time.monotonic(), None
        for attempt in range(1, ATTEMPTS + 1):
            reply = self.client.chat(
                model=self.model, messages=messages, tools=[READ_BOARD], temperature=self.temperature,
                session_id=self.session_id, reasoning_effort=self.reasoning_effort, provider=self.provider,
            )
            self.usage += reply.usage
            self._ask_usage += reply.usage
            provider = reply.provider
            try:
                return read_reply(reply.message), attempt, time.monotonic() - began, provider
            except InvalidResponse as err:
                messages.append(_assistant(reply.message))
                if reply.message.tool_calls:
                    messages.append({"role": "tool", "tool_call_id": reply.message.tool_calls[0].id, "content": f"Error: {err}"})
                else:
                    messages.append({"role": "user", "content": f"Error: {err}"})
        return None, ATTEMPTS, time.monotonic() - began, provider
