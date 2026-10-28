"""A seat played by a model through OpenRouter tool calls."""

from __future__ import annotations

import json

from wof.engine.state import (
    Action,
    BonusPicks,
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
from wof.engine.wheel import WEDGES, WheelSpec
from wof.llm.openrouter import OpenRouter, Usage, check_temperature
from wof.narrate import describe, money, table
from wof.players.base import CallRecord, InvalidResponse, Player

LETTER = {"type": "string", "description": "One letter."}
ANSWER = {"type": "string", "description": "The full answer, keeping its punctuation."}


def _tool(name: str, description: str, **parameters: dict) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": parameters, "required": list(parameters)},
        },
    }


def tool_specs(rules: Rules, spec: WheelSpec) -> dict[str, dict]:
    """Every tool a model can be offered, keyed by the engine's action kind."""
    return {
        "spin": _tool("spin", "Spin the wheel. On a letter wedge you then call a consonant for its value."),
        "buy_vowel": _tool("buy_vowel", "Buy a vowel (A, E, I, O, or U) from your round bank.", letter=LETTER),
        "solve": _tool("solve", "Solve the puzzle.", answer=ANSWER),
        "call_consonant": _tool("call_consonant", "Call a consonant.", letter=LETTER),
        "call_letter": _tool(
            "call_letter",
            f"Free Play: call any letter. A consonant earns {money(spec.free_play)} per copy, "
            "a vowel is free, and a miss keeps your turn.",
            letter=LETTER,
        ),
        "keep": _tool("keep", f"Keep the Mystery wedge's {money(spec.mystery_face)} per copy."),
        "flip": _tool("flip", f"Give up that money and flip the Mystery wedge: {money(spec.mystery_prize)} or Bankrupt."),
        "pass": _tool("pass", "Pass on the Express and keep playing normally."),
        "play": _tool(
            "play",
            f"Ride the Express: call consonants at {money(spec.express)} each and buy vowels for "
            f"{money(rules.express_vowel_cost)}, with no spinning, until you solve. "
            "Any miss, repeat, or wrong solve is Bankrupt.",
        ),
        "use_wild": _tool(
            "use_wild",
            "true spends the Wild Card on one extra consonant at this wedge's value. false keeps it.",
            use={"type": "boolean"},
        ),
        "bonus_picks": _tool(
            "bonus_picks",
            "Pick your bonus round letters.",
            consonants={"type": "array", "items": LETTER},
            vowel=LETTER,
        ),
        "bonus_solve": _tool("bonus_solve", "Your one bonus solve attempt.", answer=ANSWER),
    }


def to_action(name: str, arguments: str | None, offered: tuple[str, ...]) -> Action:
    """Turn a tool call into an engine action, or raise InvalidResponse."""
    if name not in offered:
        raise InvalidResponse("bad_tool_call", f"{name} is not on offer. Call one of: {', '.join(offered)}.")
    try:
        args = json.loads(arguments) if arguments and arguments.strip() else {}
    except json.JSONDecodeError:
        raise InvalidResponse("bad_tool_call", f"Could not read the arguments {arguments!r} as JSON.") from None
    if not isinstance(args, dict):
        raise InvalidResponse("bad_tool_call", "Tool arguments must be a JSON object.")
    try:
        match name:
            case "spin":
                return Spin()
            case "buy_vowel":
                return BuyVowel(args["letter"])
            case "solve":
                return Solve(args["answer"])
            case "call_consonant":
                return CallConsonant(args["letter"])
            case "call_letter":
                return CallLetter(args["letter"])
            case "use_wild":
                if not isinstance(args["use"], bool):
                    raise InvalidResponse("bad_tool_call", "use must be true or false.")
                return UseWild(args["use"])
            case "bonus_picks":
                if not isinstance(args["consonants"], list):
                    raise InvalidResponse("bad_tool_call", "consonants must be a list of letters.")
                return BonusPicks(tuple(args["consonants"]), args["vowel"])
            case "bonus_solve":
                return BonusSolve(args["answer"])
        return Choose(name)  # keep, flip, pass, or play
    except KeyError as missing:
        raise InvalidResponse("bad_tool_call", f"{name} needs the argument {missing}.") from None


def _rounds(numbers: list[int]) -> str:
    if len(numbers) == 1:
        return f"round {numbers[0]}"
    if numbers == list(range(numbers[0], numbers[-1] + 1)):
        return f"rounds {numbers[0]}{' and ' if len(numbers) == 2 else ' to '}{numbers[-1]}"
    return "rounds " + ", ".join(map(str, numbers[:-1])) + f" and {numbers[-1]}"


def _tops(spec: WheelSpec, rounds: range) -> str:
    groups: list[tuple[int, list[int]]] = []
    for r in rounds:
        top = spec.overlay(r).top
        if groups and groups[-1][0] == top:
            groups[-1][1].append(r)
        else:
            groups.append((top, [r]))
    return ", ".join(f"{money(top)} in {_rounds(numbers)}" for top, numbers in groups)


def intro(seat: int) -> str:
    return f"You are Seat {seat + 1} in a three-seat game of Wheel of Fortune. Finish with the highest game total."


def rules_text(rules: Rules, spec: WheelSpec) -> str:
    """The rules summary. Every dollar figure comes from config.toml and wheel.toml."""
    rounds = range(1, rules.main_rounds + 1)
    with_overlay = {
        name: [r for r in rounds if test(spec.overlay(r))]
        for name, test in (
            ("wild", lambda o: o.wild is not None),
            ("million", lambda o: o.million is not None),
            ("mystery", lambda o: bool(o.mystery)),
            ("express", lambda o: o.express is not None),
        )
    }
    cash = [v for v in spec.base if isinstance(v, int)]
    replaced, million = spec.million_swap
    lines = [
        "Turns",
        f"- On your turn, spin and call a consonant, buy a vowel for {money(rules.vowel_cost)}, or solve.",
        "- Each copy of a called consonant earns the wedge's value, and you keep your turn. "
        "A missing letter, or one already called, passes your turn.",
        f"- A vowel costs {money(rules.vowel_cost)} from your round bank even when it misses. A present vowel "
        "keeps your turn; a missing or repeated one passes it. You can't buy once every vowel is showing.",
        f"- A correct solve banks your round money, at least {money(rules.solve_minimum)}, and ends the round. "
        "The other seats lose their round money. A wrong solve passes your turn.",
        "- Type a solve as the puzzle reads, keeping hyphens, apostrophes, and commas. Case and spacing don't matter.",
        "- Once every consonant is showing, you can't spin.",
        f"- A round with no solver ends after {rules.max_turns_per_round} turns, and nobody banks.",
        "",
        "The wheel",
        f"- {WEDGES} wedges, mostly {money(min(cash))} to {money(max(cash))}. The top wedge pays {_tops(spec, rounds)}.",
        "- Bankrupt wipes your round bank and any Wild Card or Million card you hold. Lose a Turn passes your turn.",
        f"- Free Play: call any letter. A consonant earns {money(spec.free_play)} per copy, a vowel is free, "
        "and a miss keeps your turn.",
    ]
    if with_overlay["wild"]:
        lines.append(
            f"- Wild Card ({_rounds(with_overlay['wild'])}): a correct consonant on its wedge claims it, and you keep "
            "it across rounds. After a correct consonant on a plain dollar wedge, you may spend it to call one more "
            "consonant at the same value; a miss passes your turn. Unspent, it gives you an extra consonant in the "
            "bonus round."
        )
    if with_overlay["million"]:
        lines.append(
            f"- Million wedge ({_rounds(with_overlay['million'])}): its outer thirds are Bankrupt and its middle pays "
            f"{money(spec.million_center)} per copy. A correct consonant on the middle claims the Million card, which "
            f"you keep only by solving that round. In the bonus round it swaps the {money(replaced)} envelope for "
            f"{money(million)}."
        )
    if with_overlay["mystery"]:
        lines.append(
            f"- Mystery wedges ({_rounds(with_overlay['mystery'])}): {money(spec.mystery_face)} per copy. After a "
            f"correct consonant, keep that money or flip the wedge. One Mystery wedge hides "
            f"{money(spec.mystery_prize)}, the other Bankrupt. Once one is flipped, the other is a plain "
            f"{money(spec.mystery_face)} wedge."
        )
    if with_overlay["express"]:
        lines.append(
            f"- Express ({_rounds(with_overlay['express'])}): {money(spec.express)} per copy. After a correct "
            f"consonant, pass or play. Playing means calling consonants at {money(spec.express)} each and buying "
            f"vowels for {money(rules.express_vowel_cost)}, with no spinning, until you solve. Any miss, repeat, or "
            "wrong solve is Bankrupt."
        )
    if rules.bonus_round:
        lines += [
            "",
            "Bonus round",
            f"- After round {rules.main_rounds}, the highest game total plays alone. "
            f"{' '.join(rules.bonus_letters)} are shown. Pick {rules.bonus_consonants} consonants and 1 vowel "
            "(one more consonant with a Wild Card), then make one solve attempt for an envelope worth "
            f"{money(min(spec.envelopes))} to {money(max(spec.envelopes))}.",
        ]
    return "\n".join(lines)


def rules_prompt(rules: Rules, spec: WheelSpec, seat: int) -> str:
    """The system prompt for a model that plays by tool calls."""
    return "\n".join([
        intro(seat),
        "",
        rules_text(rules, spec),
        "",
        "Moves",
        "- Every move is a tool call. You are offered only the moves that are legal right now.",
        "- An invalid move comes back with an error. After three invalid tries in a row, you forfeit the move.",
        "- Think briefly if you like, then call exactly one tool.",
    ])


def phase_note(view: PublicView, rules: Rules, spec: WheelSpec) -> str | None:
    """One line on what the current prompt is asking for."""
    if view.express:
        return (
            f"You are riding the Express: call consonants at {money(spec.express)} each, buy vowels for "
            f"{money(rules.express_vowel_cost)}, or solve. Any miss, repeat, or wrong solve is Bankrupt."
        )
    return {
        Phase.CALL_CONSONANT: "Call a consonant.",
        Phase.WILD_CONSONANT: "Call your extra consonant.",
        Phase.FREE_PLAY: "Free Play: call any letter.",
        Phase.MYSTERY_CHOICE: (
            f"Keep {money(spec.mystery_face)} per copy, or flip for {money(spec.mystery_prize)} or Bankrupt."
        ),
        Phase.EXPRESS_CHOICE: "Pass to keep playing normally, or play to ride the Express.",
        Phase.WILD_CHOICE: "You hold the Wild Card. Spend it on one extra consonant at this wedge's value?",
        Phase.BONUS_PICKS: (
            f"Pick {view.bonus_consonants} consonants and 1 vowel. "
            f"{' '.join(rules.bonus_letters)} are already shown."
        ),
        Phase.BONUS_SOLVE: "One attempt: solve the bonus puzzle.",
    }.get(view.phase)


def _raw(message) -> dict:
    extra = message.model_extra or {}
    return {
        "content": message.content,
        "reasoning": extra.get("reasoning"),
        "tool_calls": [{"name": c.function.name, "arguments": c.function.arguments} for c in message.tool_calls or []],
    }


class LLMPlayer(Player):
    max_attempts = 3

    def __init__(
        self,
        seat: int,
        model: str,
        client: OpenRouter,
        rules: Rules,
        spec: WheelSpec,
        temperature: float | None = None,  # None keeps the model's own default
        session_id: str | None = None,  # keeps this seat on one provider so its cache stays warm
    ):
        self.seat = seat
        self.model = model
        self.client = client
        self.rules = rules
        self.spec = spec
        self.temperature = None if temperature is None else check_temperature(temperature)
        self.session_id = session_id
        self.tools = tool_specs(rules, spec)
        self.system = rules_prompt(rules, spec, seat)
        self.usage = Usage()
        self.last_call: CallRecord | None = None
        self.messages: list[dict] = []
        self.stage: int | str | None = None  # the round number, or "bonus"; history resets when it changes
        self.open_call: str | None = None  # the tool call still waiting for its result
        self.notes: list[str] = []  # what happened since this seat's last request

    def describe(self) -> dict:
        return {"kind": "llm", "model": self.model, "temperature": self.temperature}

    def observe(self, view: PublicView, result: Result) -> None:
        self.notes.append(describe(result, viewer=self.seat))

    def decide(self, view: PublicView, error: str | None = None) -> Action:
        stage = view.round_number or "bonus"
        if stage != self.stage:
            self.stage = stage
            self.messages = [{"role": "system", "content": self.system}]
            self.open_call = None
        if error is None:
            self._send(self._turn_text(view))
            self.notes = []
        else:
            self._send(f"Error: {error}")

        reply = self.client.chat(
            model=self.model,
            messages=self.messages,
            tools=[self.tools[kind] for kind in view.legal_actions],
            temperature=self.temperature,
            session_id=self.session_id,
        )
        self.usage += reply.usage
        message = reply.message
        self.last_call = CallRecord(raw={**_raw(message), "provider": reply.provider}, usage=reply.usage)

        assistant: dict = {"role": "assistant", "content": message.content}
        extra = message.model_extra or {}
        for key in ("reasoning", "reasoning_details"):  # some providers need reasoning handed back
            if extra.get(key):
                assistant[key] = extra[key]
        calls = message.tool_calls or []
        if calls:
            first = calls[0]
            assistant["tool_calls"] = [{
                "id": first.id,
                "type": "function",
                "function": {"name": first.function.name, "arguments": first.function.arguments},
            }]
            self.open_call = first.id
        self.messages.append(assistant)

        if not calls:
            raise InvalidResponse("bad_tool_call", f"No tool call. Call one of: {', '.join(view.legal_actions)}.")
        return to_action(calls[0].function.name, calls[0].function.arguments, view.legal_actions)

    def _send(self, text: str) -> None:
        """Answer the open tool call if there is one, or else speak as the host."""
        if self.open_call:
            self.messages.append({"role": "tool", "tool_call_id": self.open_call, "content": text})
            self.open_call = None
        else:
            self.messages.append({"role": "user", "content": text})

    def _turn_text(self, view: PublicView) -> str:
        lines = []
        if self.notes:
            lines += ["Since your last move:", *(f"- {note}" for note in self.notes), ""]
        lines += table(view, self.seat)
        note = phase_note(view, self.rules, self.spec)
        if note:
            lines.append(note)
        lines.append(f"Your move. Legal: {', '.join(view.legal_actions)}.")
        return "\n".join(lines)

    def thoughts(self) -> list[str]:
        raw = self.last_call.raw if self.last_call else {}
        return [f"{key}: {raw[key].strip()}" for key in ("reasoning", "content") if raw.get(key)]
