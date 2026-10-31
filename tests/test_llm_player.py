from dataclasses import replace

import pytest
from fakes import board_reader, completion, router
from helpers import set_seat, solve, spin_to, start, to_round

from rstlne.engine.rules import apply, public_view
from rstlne.engine.state import (
    BonusPicks,
    BonusSolve,
    BuyVowel,
    CallConsonant,
    CallLetter,
    Choose,
    Forfeit,
    Phase,
    Solve,
    Spin,
    UseWild,
)
from rstlne.players.base import InvalidResponse
from rstlne.players.llm import LLMPlayer, rules_prompt, to_action
from rstlne.runner import play_game


@pytest.fixture
def game(rules, wheel_spec):
    return start(rules, wheel_spec)


def player(rules, wheel_spec, replies, seat=0, temperature=0.3):
    client = router(replies)
    return LLMPlayer(seat, "test/model", client, rules, wheel_spec, temperature), client.client


def observe_all(players_or_one, state):
    for p in players_or_one:
        p.observe(public_view(state, p.seat), state.last)


# Tool calls to actions


@pytest.mark.parametrize(
    "name, arguments, action",
    [
        ("spin", "", Spin()),
        ("spin", "{}", Spin()),
        ("buy_vowel", '{"letter": "E"}', BuyVowel("E")),
        ("solve", '{"answer": "WHEEL OF FORTUNE"}', Solve("WHEEL OF FORTUNE")),
        ("call_consonant", '{"letter": "T"}', CallConsonant("T")),
        ("call_letter", '{"letter": "A"}', CallLetter("A")),
        ("keep", "{}", Choose("keep")),
        ("flip", "{}", Choose("flip")),
        ("pass", "{}", Choose("pass")),
        ("play", "{}", Choose("play")),
        ("use_wild", '{"use": true}', UseWild(True)),
        ("bonus_picks", '{"consonants": ["B", "G", "C"], "vowel": "I"}', BonusPicks(("B", "G", "C"), "I")),
        ("bonus_solve", '{"answer": "BIG CITY"}', BonusSolve("BIG CITY")),
    ],
)
def test_tool_calls_become_engine_actions(name, arguments, action):
    assert to_action(name, arguments, offered=(name,)) == action


@pytest.mark.parametrize(
    "name, arguments, offered",
    [
        ("solve", '{"answer": "X"}', ("spin", "buy_vowel")),  # not on offer
        ("buy_vowel", '{"letter": ', ("buy_vowel",)),  # unreadable JSON
        ("buy_vowel", '["E"]', ("buy_vowel",)),  # not an object
        ("buy_vowel", "{}", ("buy_vowel",)),  # missing argument
        ("use_wild", '{"use": "yes"}', ("use_wild",)),  # not a boolean
        ("bonus_picks", '{"consonants": "BGC", "vowel": "I"}', ("bonus_picks",)),  # not a list
    ],
)
def test_bad_tool_calls_are_invalid(name, arguments, offered):
    with pytest.raises(InvalidResponse) as err:
        to_action(name, arguments, offered)
    assert err.value.code == "bad_tool_call"


# Requests


def test_offers_only_legal_tools_and_sends_the_view(rules, wheel_spec, game):
    llm, client = player(rules, wheel_spec, [completion(("spin", {}))])
    assert llm.decide(public_view(game, 0)) == Spin()
    request = client.calls[0]
    assert [t["function"]["name"] for t in request["tools"]] == ["spin", "solve"]
    assert request["temperature"] == 0.3
    system, user = request["messages"]
    assert system["role"] == "system" and "Seat 1" in system["content"]
    assert user["role"] == "user"
    assert "Board: _ _ _ _ _   _ _   _ _ _ _ _ _ _" in user["content"]
    assert "Category: Phrase" in user["content"]


def test_system_prompt_takes_values_from_config(rules, wheel_spec):
    prompt = rules_prompt(rules, wheel_spec, seat=0)
    assert "$250" in prompt and "$1,000" in prompt and "$10,000" in prompt
    assert "$2,500 in round 1" in prompt and "$5,000 in round 4" in prompt
    assert "rounds 1 to 3" in prompt
    assert "$1,000,000" in prompt
    assert "$300" in rules_prompt(replace(rules, vowel_cost=300), wheel_spec, seat=0)


def test_reply_without_a_tool_call_is_invalid_and_the_retry_says_why(rules, wheel_spec, game):
    llm, client = player(rules, wheel_spec, [completion(content="I'll spin!"), completion(("spin", {}))])
    view = public_view(game, 0)
    with pytest.raises(InvalidResponse):
        llm.decide(view)
    assert llm.decide(view, error="call one of the tools") == Spin()
    retry = client.calls[1]["messages"]
    assert retry[-2] == {"role": "assistant", "content": "I'll spin!"}
    assert retry[-1]["role"] == "user" and "call one of the tools" in retry[-1]["content"]


def test_illegal_move_goes_back_as_the_tool_result(rules, wheel_spec, game):
    state = spin_to(game, 3)
    llm, client = player(rules, wheel_spec, [completion(("call_consonant", {"letter": "E"})), completion(("call_consonant", {"letter": "T"}))])
    view = public_view(state, 0)
    assert llm.decide(view) == CallConsonant("E")
    assert llm.decide(view, error="E is a vowel. Call a consonant here.") == CallConsonant("T")
    first_call = client.calls[1]["messages"][-2]["tool_calls"][0]
    tool_result = client.calls[1]["messages"][-1]
    assert tool_result == {"role": "tool", "tool_call_id": first_call["id"], "content": "Error: E is a vowel. Call a consonant here."}


def test_only_the_first_tool_call_counts(rules, wheel_spec, game):
    replies = [completion(("spin", {}), ("solve", {"answer": "X"})), completion(("call_consonant", {"letter": "T"}))]
    llm, client = player(rules, wheel_spec, replies)
    assert llm.decide(public_view(game, 0)) == Spin()
    assert [c["name"] for c in llm.last_call.raw["tool_calls"]] == ["spin", "solve"]
    state = spin_to(game, 3)
    observe_all([llm], state)
    llm.decide(public_view(state, 0))
    assistant = client.calls[1]["messages"][2]
    assert len(assistant["tool_calls"]) == 1


def test_own_outcome_and_other_seats_moves_reach_the_next_request(rules, wheel_spec, game):
    llm, client = player(rules, wheel_spec, [completion(("spin", {})), completion(("call_consonant", {"letter": "Z"})), completion(("spin", {}))])
    state = spin_to(game, 3)  # what the model's spin will be
    llm.decide(public_view(game, 0))
    observe_all([llm], state)
    llm.decide(public_view(state, 0))
    landed = client.calls[1]["messages"][-1]
    assert landed["role"] == "tool" and "You spun $600." in landed["content"]

    state = apply(state, CallConsonant("Z"))  # turn passes to seat 1
    observe_all([llm], state)
    state = apply(state, Forfeit())  # seat 2 passes
    observe_all([llm], state)
    state = apply(state, Forfeit())  # seat 3 passes, back to seat 1
    observe_all([llm], state)
    llm.decide(public_view(state, 0))
    recap = client.calls[2]["messages"][-1]
    assert recap["role"] == "tool"
    assert "You called Z: none. Turn passes." in recap["content"]
    assert "Seat 2 used up three tries without a valid move. Turn passes." in recap["content"]


def test_history_resets_each_round(rules, wheel_spec, game):
    llm, client = player(rules, wheel_spec, [completion(("spin", {}))] * 2)
    llm.decide(public_view(game, 0))
    state = solve(game)
    state = to_round(state, 4)  # seat 0 starts round 4
    observe_all([llm], state)
    llm.decide(public_view(state, 0))
    messages = client.calls[1]["messages"]
    assert [m["role"] for m in messages] == ["system", "user"]
    assert "Round 4" in messages[1]["content"]


def test_express_view_says_so(rules, wheel_spec, game):
    state = to_round(game, 3)
    state = apply(apply(spin_to(state, 12), CallConsonant("G")), Choose("play"))
    llm, client = player(rules, wheel_spec, [completion(("call_consonant", {"letter": "D"}))], seat=2)
    llm.decide(public_view(state, 2))
    request = client.calls[0]
    assert "riding the Express" in request["messages"][-1]["content"]
    assert [t["function"]["name"] for t in request["tools"]] == ["call_consonant", "buy_vowel", "solve"]


def test_bonus_picks_prompt_counts_the_wild_card(rules, wheel_spec, game):
    state = set_seat(game, 0, wild=True)
    for _ in range(4):
        state = solve(state)
    llm, client = player(rules, wheel_spec, [completion(("bonus_picks", {"consonants": ["B", "G", "C", "D"], "vowel": "I"}))])
    assert state.phase is Phase.BONUS_PICKS and state.seat == 0
    llm.decide(public_view(state, 0))
    assert "Pick 4 consonants and 1 vowel" in client.calls[0]["messages"][-1]["content"]


def test_reasoning_stays_in_history(rules, wheel_spec, game):
    details = [{"type": "reasoning.text", "text": "Spin first."}]
    reply = completion(("spin", {}), message_extra={"reasoning": "Spin first.", "reasoning_details": details})
    llm, client = player(rules, wheel_spec, [reply, completion(("call_consonant", {"letter": "T"}))])
    llm.decide(public_view(game, 0))
    assert llm.last_call.raw["reasoning"] == "Spin first."
    state = spin_to(game, 3)
    observe_all([llm], state)
    llm.decide(public_view(state, 0))
    assistant = client.calls[1]["messages"][2]
    assert assistant["reasoning_details"] == details
    assert "reasoning" not in assistant  # the detailed blocks are enough, and some providers want them exactly


def test_log_records_which_provider_served_the_call(rules, wheel_spec, game):
    llm, _ = player(rules, wheel_spec, [completion(("spin", {}), response_extra={"provider": "Anthropic"})])
    llm.decide(public_view(game, 0))
    assert llm.last_call.raw["provider"] == "Anthropic"


def test_usage_adds_up_per_player(rules, wheel_spec, game):
    llm, _ = player(rules, wheel_spec, [completion(("spin", {}))])
    llm.decide(public_view(game, 0))
    assert llm.usage.calls == 1 and llm.usage.total_tokens == 15


def test_unset_temperature_uses_the_model_default(rules, wheel_spec, game):
    llm, client = player(rules, wheel_spec, [completion(("spin", {}))], temperature=None)
    llm.decide(public_view(game, 0))
    assert "temperature" not in client.calls[0]
    assert llm.describe() == {"kind": "llm", "model": "test/model", "temperature": None, "reasoning_effort": None, "provider": None}


def test_solve_tools_say_the_answer_must_match_the_board(rules, wheel_spec):
    from rstlne.players.llm import tool_specs

    tools = tool_specs(rules, wheel_spec)
    for name in ("solve", "bonus_solve"):
        description = tools[name]["function"]["description"]
        assert "whole puzzle" in description and "word lengths" in description and "punctuation" in description


def test_board_pattern_reaches_the_model(rules, wheel_spec, game):
    llm, client = player(rules, wheel_spec, [completion(("spin", {}))])
    llm.decide(public_view(game, 0))
    assert "Pattern: _____ __ _______ (word lengths 5, 2, 7)" in client.calls[0]["messages"][-1]["content"]


def test_reasoning_effort_reaches_every_request(rules, wheel_spec, game):
    client = router([completion(("spin", {}))])
    llm = LLMPlayer(0, "openai/gpt-6-luna", client, rules, wheel_spec, reasoning_effort="low")
    llm.decide(public_view(game, 0))
    assert client.client.calls[0]["extra_body"]["reasoning"] == {"effort": "low"}
    assert llm.describe()["reasoning_effort"] == "low"


def test_session_id_reaches_every_request(rules, wheel_spec, game):
    client = router([completion(("spin", {}))])
    llm = LLMPlayer(0, "openai/gpt-6-luna", client, rules, wheel_spec, session_id="game-seat1")
    llm.decide(public_view(game, 0))
    assert client.client.calls[0]["extra_body"]["session_id"] == "game-seat1"


def test_temperature_outside_range_is_rejected(rules, wheel_spec):
    with pytest.raises(ValueError):
        player(rules, wheel_spec, [], temperature=0.7)


def test_three_fake_models_finish_a_game(rules, wheel_spec, game):
    client = router(board_reader)
    players = [LLMPlayer(i, f"test/model-{i}", client, rules, wheel_spec, 0.3) for i in range(3)]
    final = play_game(game, players)
    assert final.phase is Phase.GAME_OVER
    assert sum(p.usage.calls for p in players) == len(client.client.calls)


def test_a_pinned_provider_reaches_every_request_and_the_log(rules, wheel_spec, game):
    client = router([completion(("spin", {}))])
    llm = LLMPlayer(0, "deepseek/deepseek-v4.1-flash-1017", client, rules, wheel_spec, provider="deepseek")
    llm.decide(public_view(game, 0))
    assert client.client.calls[0]["extra_body"]["provider"]["order"] == ["deepseek"]
    assert llm.describe()["provider"] == "deepseek"


# Every tool on every request, for the cache


def test_all_tools_offers_the_same_full_list_on_every_request(rules, wheel_spec, game):
    client = router([completion(("spin", {})), completion(("call_consonant", {"letter": "T"}))])
    llm = LLMPlayer(0, "test/model", client, rules, wheel_spec, all_tools=True)
    assert llm.decide(public_view(game, 0)) == Spin()
    assert llm.decide(public_view(spin_to(game, 3), 0)) == CallConsonant("T")
    first, second = ([t["function"]["name"] for t in call["tools"]] for call in client.client.calls)
    assert first == second == list(llm.tools)  # one fixed list, so the cached prefix never changes
    assert "Legal: call_consonant" in client.client.calls[1]["messages"][-1]["content"]
    assert llm.describe()["tools"] == "all"


def test_all_tools_still_refuses_a_move_that_isnt_legal(rules, wheel_spec, game):
    llm = LLMPlayer(0, "test/model", router([completion(("spin", {}))]), rules, wheel_spec, all_tools=True)
    with pytest.raises(InvalidResponse, match="not on offer"):
        llm.decide(public_view(spin_to(game, 3), 0))  # after a spin only a consonant call is legal


def test_legal_tools_stay_the_default(rules, wheel_spec, game):
    llm, client = player(rules, wheel_spec, [completion(("spin", {}))])
    llm.decide(public_view(game, 0))
    assert [t["function"]["name"] for t in client.calls[0]["tools"]] == ["spin", "solve"]
    assert "tools" not in llm.describe()


def test_the_config_picks_the_tool_list(rules, wheel_spec):
    from rstlne import cli, settings
    config = settings.load_config()
    all_tools = {**config, "llm": {**config["llm"], "tools": "all"}}
    seat = cli.build_players([("llm", "a/one"), ("bot", None), ("bot", None)], rules, wheel_spec, all_tools,
                             router([]), None, "g")[0]
    assert seat.all_tools is True
    with pytest.raises(ValueError, match="legal.*all"):
        cli.build_players([("llm", "a/one"), ("bot", None), ("bot", None)], rules, wheel_spec,
                          {**config, "llm": {**config["llm"], "tools": "some"}}, router([]), None, "g")
