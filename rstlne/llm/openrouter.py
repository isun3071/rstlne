"""OpenRouter client: retries with exponential backoff, and token usage per call."""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from dataclasses import astuple, dataclass

import openai
from openai import OpenAI
from openai.types.chat import ChatCompletionMessage

BASE_URL = "https://openrouter.ai/api/v1"
CACHE = {"type": "ephemeral"}  # the default 5 minute cache
TIMEOUT = 180  # seconds per request; the slowest real move seen, a Qwen overthink, took 118
TIMEOUT_RETRIES = 1  # a request that timed out once will likely time out again
MIN_TEMPERATURE, MAX_TEMPERATURE = 0.2, 0.4


class EmptyResponse(Exception):
    """OpenRouter answered with no choices, which happens when a provider fails upstream."""


# 429s, 5xx responses, dropped connections, timeouts, and empty answers are worth another try.
_RETRYABLE = (openai.RateLimitError, openai.InternalServerError, openai.APIConnectionError, EmptyResponse)


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost: float = 0.0  # OpenRouter credits
    calls: int = 0
    cached_tokens: int = 0  # prompt tokens read from a provider's cache
    cache_write_tokens: int = 0
    cache_discount: float = 0.0  # credits saved by the cache; Anthropic writes make it negative

    @classmethod
    def of(cls, usage, discount: float | None = None) -> Usage:
        data = usage.model_dump() if usage is not None else {}
        details = data.get("prompt_tokens_details") or {}
        return cls(
            prompt_tokens=data.get("prompt_tokens") or 0,
            completion_tokens=data.get("completion_tokens") or 0,
            total_tokens=data.get("total_tokens") or 0,
            cost=float(data.get("cost") or 0.0),
            calls=1,
            cached_tokens=details.get("cached_tokens") or 0,
            cache_write_tokens=details.get("cache_write_tokens") or 0,
            cache_discount=float(discount or data.get("cache_discount") or 0.0),
        )

    def __add__(self, other: Usage) -> Usage:
        return Usage(*(a + b for a, b in zip(astuple(self), astuple(other))))


@dataclass(frozen=True)
class Reply:
    message: ChatCompletionMessage
    usage: Usage
    provider: str | None = None  # who OpenRouter routed the call to


def check_temperature(temperature: float) -> float:
    if not MIN_TEMPERATURE <= temperature <= MAX_TEMPERATURE:
        raise ValueError(f"temperature {temperature} is outside {MIN_TEMPERATURE} to {MAX_TEMPERATURE}")
    return temperature


class OpenRouter:
    def __init__(
        self,
        client=None,
        *,
        retries: int = 5,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.client = client if client is not None else OpenAI(
            base_url=BASE_URL,
            api_key=os.environ["OPENROUTER_API_KEY"],
            max_retries=0,  # retries happen here, so every one is counted and backed off the same way
            timeout=TIMEOUT,
        )
        self.retries = retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.sleep = sleep

    def chat(
        self,
        *,
        model: str,
        messages: list[dict],
        tools: list[dict],
        temperature: float | None = None,
        session_id: str | None = None,
        reasoning_effort: str | None = None,
    ) -> Reply:
        """One required tool call's worth of completion, retried on transient failures.

        With no temperature, the request leaves it out and the model uses its own default.
        A session_id keeps one seat's calls on one provider, where its cache lives.
        """
        messages, extra = _caching(model, messages)
        if session_id:
            extra["session_id"] = session_id
        reasoning = _reasoning(model, reasoning_effort)
        if reasoning:
            extra["reasoning"] = reasoning
        options = {} if temperature is None else {"temperature": temperature}
        if extra:
            options["extra_body"] = extra
        timeouts = 0
        for attempt in range(self.retries + 1):
            try:
                response = self.client.chat.completions.create(
                    model=model,
                    messages=messages,
                    tools=tools,
                    tool_choice=_tool_choice(model, reasoning),
                    parallel_tool_calls=False,
                    **options,
                )
                if not response.choices:
                    raise EmptyResponse(f"{model} returned no choices")
                extra = response.model_extra or {}
                usage = Usage.of(response.usage, extra.get("cache_discount"))
                return Reply(response.choices[0].message, usage, extra.get("provider"))
            except _RETRYABLE as err:
                if isinstance(err, openai.APITimeoutError):
                    timeouts += 1
                if attempt == self.retries or timeouts > TIMEOUT_RETRIES:
                    raise
                self.sleep(min(self.base_delay * 2**attempt, self.max_delay))
            except openai.APIStatusError as err:
                _note_provider(err)
                raise
        raise AssertionError("unreachable")


def _note_provider(err: openai.APIStatusError) -> None:
    """OpenRouter reports a provider's rejection as "Provider returned error". Add the provider's own words."""
    metadata = (err.body or {}).get("metadata") if isinstance(err.body, dict) else None
    if metadata and metadata.get("raw"):
        err.add_note(f"{metadata.get('provider_name', 'The provider')} said: {metadata['raw']}")


def _reasoning(model: str, effort: str | None) -> dict | None:
    """One effort for every model when set. Otherwise each model's default: Claude models think only
    when asked, so they get thinking turned on with no effort, which runs their adaptive thinking."""
    if effort is not None:
        return {"effort": effort}
    if model.startswith("anthropic/"):
        return {"enabled": True}
    return None


def _tool_choice(model: str, reasoning: dict | None) -> str:
    """Require a tool call, except from thinking models whose providers won't think under a forced call:
    Claude quietly stops thinking, and Qwen's provider rejects the request. Those choose their own tool,
    and a reply without a tool call gets the usual reprompt. Qwen thinks unless told not to."""
    if reasoning is not None and reasoning.get("effort") == "none":
        return "required"
    if model.startswith("qwen/") or (model.startswith("anthropic/") and reasoning is not None):
        return "auto"
    return "required"


def _caching(model: str, messages: list[dict]) -> tuple[list[dict], dict]:
    """Ask for prompt caching where a provider needs asking. OpenAI, DeepSeek, and Z.AI cache
    on their own. Anthropic takes one top level flag that follows the conversation as it grows.
    Qwen needs a marked message, so the system prompt gets one."""
    if model.startswith("anthropic/"):
        return messages, {"cache_control": CACHE}
    first = messages[0] if messages else {}
    if model.startswith("qwen/") and first.get("role") == "system" and isinstance(first.get("content"), str):
        system = {"role": "system", "content": [{"type": "text", "text": first["content"], "cache_control": CACHE}]}
        return [system, *messages[1:]], {}
    return messages, {}
