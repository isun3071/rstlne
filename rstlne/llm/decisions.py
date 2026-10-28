"""OpenRouter's Decisions API: typed questions in, probability distributions out."""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx2

from rstlne.llm.openrouter import DeadlineExceeded, Usage, call_with_deadline

DECISIONS_URL = "https://openrouter.ai/api/alpha/decisions"
# Rate limits, server errors, upstream failures, edge timeouts, and overloaded providers.
_RETRY_STATUS = {429, 500, 502, 503, 524, 529}


class DecisionsError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(f"Decisions API {status}: {message}")
        self.status = status


@dataclass(frozen=True)
class Decisions:
    answers: dict[str, dict]  # each question's answer, keyed by question name
    usage: Usage
    provider: str | None = None
    model: str | None = None


def choice(instructions: str, options: dict[str, str]) -> dict:
    """A question that picks one option. `options` maps each option name to its description."""
    return {"type": "choice", "instructions": instructions, "criteria": options}


def noul(instructions: str, yes: str, no: str) -> dict:
    """A yes or no question. The answer is P(yes)."""
    return {"type": "noul", "instructions": instructions, "criteria": {"true": yes, "false": no}}


class DecisionClient:
    def __init__(
        self,
        http: httpx2.Client | None = None,
        *,
        api_key: str | None = None,
        retries: int = 5,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        sleep: Callable[[float], None] = time.sleep,
        deadline: float = 120,  # Decisions calls take well under a second
    ):
        self.http = http if http is not None else httpx2.Client(timeout=60)
        self.api_key = api_key if api_key is not None else os.environ["OPENROUTER_API_KEY"]
        self.retries = retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.sleep = sleep
        self.deadline = deadline

    def ask(self, *, model: str, state: str, questions: dict[str, dict], session_id: str | None = None) -> Decisions:
        """Ask every question in one call, retrying transient failures with exponential backoff."""
        body = {"model": model, "state": state, "questions": questions}
        if session_id:
            body["session_id"] = session_id
        for attempt in range(self.retries + 1):
            last = attempt == self.retries
            try:
                response = call_with_deadline(
                    lambda: self.http.post(DECISIONS_URL, json=body, headers={"Authorization": f"Bearer {self.api_key}"}),
                    self.deadline,
                )
            except (httpx2.TransportError, DeadlineExceeded):
                if last:
                    raise
                self._wait(attempt)
                continue
            if response.status_code in _RETRY_STATUS and not last:
                self._wait(attempt)
                continue
            if response.status_code != 200:
                raise DecisionsError(response.status_code, response.text)
            data = response.json()
            usage = data.get("usage") or {}
            tokens_in, tokens_out = usage.get("input_tokens") or 0, usage.get("output_tokens") or 0
            return Decisions(
                answers=data["answers"],
                usage=Usage(
                    prompt_tokens=tokens_in,
                    completion_tokens=tokens_out,
                    total_tokens=tokens_in + tokens_out,
                    cost=float(usage.get("cost") or 0.0),
                    calls=1,
                ),
                provider=data.get("provider"),
                model=data.get("model"),
            )
        raise AssertionError("unreachable")

    def _wait(self, attempt: int) -> None:
        self.sleep(min(self.base_delay * 2**attempt, self.max_delay))
