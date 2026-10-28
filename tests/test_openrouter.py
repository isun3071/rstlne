import openai
import pytest
from fakes import FakeClient, completion, status_error

from rstlne.llm.openrouter import EmptyResponse, OpenRouter, Usage, check_temperature

TOOLS = [{"type": "function", "function": {"name": "spin", "parameters": {"type": "object", "properties": {}}}}]
MESSAGES = [{"role": "user", "content": "your move"}]


def chat(client, sleeps=None, **options):
    sleeps = [] if sleeps is None else sleeps
    router = OpenRouter(client, sleep=sleeps.append, **options)
    return router.chat(model="test/model", messages=MESSAGES, tools=TOOLS, temperature=0.3)


def test_sends_model_tools_and_temperature_and_requires_one_tool_call():
    client = FakeClient([completion(("spin", {}))])
    reply = chat(client)
    request = client.calls[0]
    assert request["model"] == "test/model"
    assert request["temperature"] == 0.3
    assert request["tools"] == TOOLS
    assert request["tool_choice"] == "required"
    assert request["parallel_tool_calls"] is False
    assert reply.message.tool_calls[0].function.name == "spin"


def test_temperature_is_left_out_when_unset():
    client = FakeClient([completion(("spin", {}))])
    OpenRouter(client).chat(model="test/model", messages=MESSAGES, tools=TOOLS, temperature=None)
    assert "temperature" not in client.calls[0]


def test_usage_per_call_includes_cost():
    usage = {"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150, "cost": 0.0042}
    reply = chat(FakeClient([completion(("spin", {}), usage=usage)]))
    assert reply.usage == Usage(prompt_tokens=120, completion_tokens=30, total_tokens=150, cost=0.0042, calls=1)


def test_usage_records_cache_reads_writes_and_discount():
    usage = {
        "prompt_tokens": 1000, "completion_tokens": 20, "total_tokens": 1020, "cost": 0.0001,
        "prompt_tokens_details": {"cached_tokens": 900, "cache_write_tokens": 64},
    }
    reply = chat(FakeClient([completion(("spin", {}), usage=usage, response_extra={"cache_discount": 0.00008})]))
    assert reply.usage.cached_tokens == 900
    assert reply.usage.cache_write_tokens == 64
    assert reply.usage.cache_discount == pytest.approx(0.00008)


def request_for(model, session_id=None):
    client = FakeClient([completion(("spin", {}))])
    messages = [{"role": "system", "content": "the rules"}, {"role": "user", "content": "your move"}]
    OpenRouter(client).chat(model=model, messages=messages, tools=TOOLS, session_id=session_id)
    assert messages[0] == {"role": "system", "content": "the rules"}  # the caller's history is untouched
    return client.calls[0]


def test_anthropic_requests_ask_for_caching():
    assert request_for("anthropic/claude-haiku-5.5")["extra_body"]["cache_control"] == {"type": "ephemeral"}


def test_qwen_requests_mark_the_system_prompt_for_caching():
    system = request_for("qwen/qwen3.8-flash")["messages"][0]
    assert system == {
        "role": "system",
        "content": [{"type": "text", "text": "the rules", "cache_control": {"type": "ephemeral"}}],
    }


@pytest.mark.parametrize("model", ["openai/gpt-6-luna", "deepseek/deepseek-v4.1-flash-1017", "z-ai/glm-5.3-flash"])
def test_other_models_cache_on_their_own(model):
    request = request_for(model)
    assert "extra_body" not in request
    assert request["messages"][0] == {"role": "system", "content": "the rules"}


def test_session_id_keeps_a_seat_on_one_provider():
    assert request_for("openai/gpt-6-luna", session_id="game-seat2")["extra_body"] == {"session_id": "game-seat2"}


def test_usage_adds_up():
    total = Usage(10, 5, 15, 0.001, 1) + Usage(20, 10, 30, 0.002, 1)
    assert total == Usage(30, 15, 45, pytest.approx(0.003), 2)


def test_retries_rate_limits_with_exponential_backoff():
    sleeps = []
    client = FakeClient([
        status_error(openai.RateLimitError, 429),
        status_error(openai.RateLimitError, 429),
        completion(("spin", {})),
    ])
    chat(client, sleeps)
    assert sleeps == [1.0, 2.0]
    assert len(client.calls) == 3


def test_retries_server_errors_connection_errors_and_empty_replies():
    client = FakeClient([
        status_error(openai.InternalServerError, 502),
        openai.APIConnectionError(request=status_error(openai.InternalServerError, 500).request),
        completion(choices=False),
        completion(("spin", {})),
    ])
    chat(client)
    assert len(client.calls) == 4


def test_gives_up_after_the_last_retry():
    sleeps = []
    client = FakeClient([status_error(openai.RateLimitError, 429)] * 3)
    with pytest.raises(openai.RateLimitError):
        chat(client, sleeps, retries=2)
    assert sleeps == [1.0, 2.0]


def test_empty_replies_raise_once_retries_run_out():
    with pytest.raises(EmptyResponse):
        chat(FakeClient([completion(choices=False)] * 2), retries=1)


def test_does_not_retry_bad_requests():
    sleeps = []
    with pytest.raises(openai.BadRequestError):
        chat(FakeClient([status_error(openai.BadRequestError, 400)]), sleeps)
    assert sleeps == []


def test_backoff_is_capped():
    sleeps = []
    client = FakeClient([status_error(openai.RateLimitError, 429)] * 5 + [completion(("spin", {}))])
    chat(client, sleeps, retries=5, max_delay=4.0)
    assert sleeps == [1.0, 2.0, 4.0, 4.0, 4.0]


@pytest.mark.parametrize("temperature", [0.2, 0.3, 0.4])
def test_temperature_inside_the_range_is_accepted(temperature):
    assert check_temperature(temperature) == temperature


@pytest.mark.parametrize("temperature", [0.0, 0.19, 0.41, 1.0])
def test_temperature_outside_the_range_is_rejected(temperature):
    with pytest.raises(ValueError):
        check_temperature(temperature)


def test_claude_models_get_their_adaptive_thinking_turned_on():
    assert request_for("anthropic/claude-haiku-5.5")["extra_body"]["reasoning"] == {"enabled": True}


def test_one_reasoning_effort_applies_to_every_model():
    for model in ("anthropic/claude-haiku-5.5", "openai/gpt-6-luna", "deepseek/deepseek-v4.1-flash-1017"):
        client = FakeClient([completion(("spin", {}))])
        OpenRouter(client).chat(model=model, messages=MESSAGES, tools=TOOLS, reasoning_effort="low")
        assert client.calls[0]["extra_body"]["reasoning"] == {"effort": "low"}


def test_thinking_claude_models_choose_their_tool_since_forcing_one_turns_thinking_off():
    assert request_for("anthropic/claude-haiku-5.5")["tool_choice"] == "auto"
    assert request_for("openai/gpt-6-luna")["tool_choice"] == "required"
    client = FakeClient([completion(("spin", {}))])
    OpenRouter(client).chat(model="anthropic/claude-haiku-5.5", messages=MESSAGES, tools=TOOLS, reasoning_effort="none")
    assert client.calls[0]["tool_choice"] == "required"
