"""Fake OpenRouter responses. Tests never touch the network."""

import copy
import itertools
import json
import re
from types import SimpleNamespace

import httpx2  # the HTTP library under openai 3.x
from openai.types.chat import ChatCompletion

from wof.llm.openrouter import OpenRouter

_ids = itertools.count()
FREQUENCY = "TNSHRDLCMWFGYPBVKJXQZ"


def completion(*calls, content=None, usage=None, message_extra=None, response_extra=None, choices=True):
    """A chat completion whose message makes these (tool name, arguments) calls."""
    message = {"role": "assistant", "content": content}
    if calls:
        message["tool_calls"] = [
            {
                "id": f"call_{next(_ids)}",
                "type": "function",
                "function": {"name": name, "arguments": args if isinstance(args, str) else json.dumps(args)},
            }
            for name, args in calls
        ]
    message.update(message_extra or {})
    return ChatCompletion.model_validate({
        "id": "gen-test",
        "object": "chat.completion",
        "created": 0,
        "model": "test/model",
        "choices": [{"index": 0, "finish_reason": "tool_calls", "message": message}] if choices else [],
        "usage": usage or {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15, "cost": 0.001},
        **(response_extra or {}),
    })


class FakeCompletions:
    def __init__(self, replies):
        self.replies = replies  # a list to pop from, or a function of the request
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(copy.deepcopy(kwargs))
        reply = self.replies(kwargs) if callable(self.replies) else self.replies.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        return reply


class FakeClient:
    def __init__(self, replies):
        self.chat = SimpleNamespace(completions=FakeCompletions(replies))

    @property
    def calls(self):
        return self.chat.completions.calls


def status_error(cls, code):
    request = httpx2.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    return cls("boom", response=httpx2.Response(code, request=request), body=None)


def router(replies, **options):
    return OpenRouter(FakeClient(replies), sleep=lambda seconds: None, **options)


def board_reader(request):
    """A fake model that plays from its prompt alone: it calls letters in frequency
    order, keeps every safe default, and solves once the board is full."""
    offered = [tool["function"]["name"] for tool in request["tools"]]
    text = next(
        m["content"] for m in reversed(request["messages"])
        if isinstance(m.get("content"), str) and "Board: " in m["content"]
    )
    board = re.search(r"^Board: (.*)$", text, re.M).group(1)
    used = re.search(r"^Used letters: (.*)$", text, re.M).group(1).split()
    answer = " ".join(word.replace(" ", "") for word in board.split("   "))
    fresh = [c for c in FREQUENCY if c not in used]

    if "bonus_picks" in offered:
        n = int(re.search(r"Pick (\d+) consonants", text).group(1))
        return completion(("bonus_picks", {"consonants": fresh[:n], "vowel": next(v for v in "AIOU" if v not in used)}))
    if "bonus_solve" in offered:
        return completion(("bonus_solve", {"answer": answer}))
    if "solve" in offered and "_" not in board:
        return completion(("solve", {"answer": answer}))
    moves = [
        ("call_consonant", {"letter": fresh[0] if fresh else "Z"}),
        ("call_letter", {"letter": fresh[0] if fresh else "A"}),
        ("keep", {}),
        ("pass", {}),
        ("use_wild", {"use": False}),
        ("spin", {}),
        ("buy_vowel", {"letter": next((v for v in "EAOIU" if v not in used), "E")}),
    ]
    for name, args in moves:
        if name in offered:
            return completion((name, args))
    return completion(("solve", {"answer": answer}))


class FakeDecisions:
    """Stands in for the Decisions API client. `answer(questions, state)` returns the answers."""

    def __init__(self, answer):
        self.answer = answer
        self.calls = []

    def ask(self, *, model, state, questions, session_id=None):
        from wof.llm.decisions import Decisions
        from wof.llm.openrouter import Usage

        self.calls.append({"model": model, "state": state, "questions": copy.deepcopy(questions), "session_id": session_id})
        usage = Usage(prompt_tokens=100, total_tokens=100, cost=0.0000042, calls=1)
        return Decisions(answers=self.answer(questions, state), usage=usage, provider="TypeSafe", model=model)


def decide_by(p_yes=0.1, picks=None):
    """Answers every Noul with p_yes, and every Choice with its pick or else the first option."""
    def answer(questions, state):
        out = {}
        for name, question in questions.items():
            if question["type"] == "noul":
                out[name] = {"type": "noul", "noul": p_yes(state) if callable(p_yes) else p_yes}
                continue
            options = list(question["criteria"])
            pick = (picks or {}).get(name, options[0])
            rest = (1 - 0.9) / max(len(options) - 1, 1)
            out[name] = {
                "type": "choice",
                "choice": pick,
                "confidence": 0.9,
                "probabilities": {o: 0.9 if o == pick else rest for o in options},
            }
        return out
    return answer


def solvable_when_full(state):
    """P(yes) of 1 once the board in the state has no hidden letters."""
    board = re.search(r"^Board: (.*)$", state, re.M).group(1)
    return 0.0 if "_" in board else 1.0
