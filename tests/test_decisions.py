import json

import httpx2
import pytest

from rstlne.llm.decisions import DECISIONS_URL, DecisionClient, DecisionsError, choice, noul
from rstlne.llm.openrouter import Usage

QUESTIONS = {
    "solvable": noul("Can the puzzle be solved correctly from this board right now?", "yes", "no"),
    "action": choice("Which move should you make?", {"spin": "Spin.", "buy_vowel": "Buy a vowel."}),
}
RESPONSE = {
    "id": "dec-1",
    "model": "typesafe/jev-1.14",
    "provider": "TypeSafe",
    "answers": {
        "solvable": {"type": "noul", "noul": 0.31},
        "action": {"type": "choice", "choice": "spin", "confidence": 0.8, "probabilities": {"spin": 0.9, "buy_vowel": 0.1}},
    },
    "usage": {"input_tokens": 1200, "output_tokens": 0, "cost": 0.0000504},
}


def client(replies, **options):
    """A client whose transport returns these status codes or exceptions in order."""
    requests, sleeps = [], []
    replies = list(replies)

    def handle(request):
        requests.append(request)
        reply = replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return httpx2.Response(reply, json=RESPONSE if reply == 200 else {"error": {"code": reply, "message": "nope"}})

    transport = httpx2.Client(transport=httpx2.MockTransport(handle))
    return DecisionClient(transport, api_key="test-key", sleep=sleeps.append, **options), requests, sleeps


def ask(decisions, session_id=None):
    return decisions.ask(model="typesafe/jev-1.14", state="the board", questions=QUESTIONS, session_id=session_id)


def test_question_builders():
    assert noul("Solvable?", "yes", "no") == {"type": "noul", "instructions": "Solvable?", "criteria": {"true": "yes", "false": "no"}}
    assert choice("Which?", {"a": "A."}) == {"type": "choice", "instructions": "Which?", "criteria": {"a": "A."}}


def test_posts_questions_to_the_decisions_endpoint():
    decisions, requests, _ = client([200])
    ask(decisions, session_id="game-seat1")
    request = requests[0]
    assert request.method == "POST" and str(request.url) == DECISIONS_URL
    assert request.headers["Authorization"] == "Bearer test-key"
    assert json.loads(request.content) == {
        "model": "typesafe/jev-1.14",
        "state": "the board",
        "questions": QUESTIONS,
        "session_id": "game-seat1",
    }


def test_no_session_id_leaves_it_out():
    decisions, requests, _ = client([200])
    ask(decisions)
    assert "session_id" not in json.loads(requests[0].content)


def test_reads_answers_usage_and_provider():
    decisions, _, _ = client([200])
    result = ask(decisions)
    assert result.answers == RESPONSE["answers"]
    assert result.provider == "TypeSafe" and result.model == "typesafe/jev-1.14"
    assert result.usage == Usage(prompt_tokens=1200, completion_tokens=0, total_tokens=1200, cost=0.0000504, calls=1)


def test_retries_rate_limits_overloads_and_upstream_failures():
    decisions, requests, sleeps = client([429, 529, 502, 200])
    ask(decisions)
    assert len(requests) == 4 and sleeps == [1.0, 2.0, 4.0]


def test_retries_dropped_connections():
    request = httpx2.Request("POST", DECISIONS_URL)
    decisions, requests, sleeps = client([httpx2.ConnectError("boom", request=request), 200])
    ask(decisions)
    assert len(requests) == 2 and sleeps == [1.0]


def test_gives_up_after_the_last_retry():
    decisions, _, sleeps = client([503, 503], retries=1)
    with pytest.raises(DecisionsError) as err:
        ask(decisions)
    assert err.value.status == 503 and sleeps == [1.0]


def test_bad_requests_are_not_retried():
    decisions, _, sleeps = client([400])
    with pytest.raises(DecisionsError) as err:
        ask(decisions)
    assert err.value.status == 400 and sleeps == []


def test_a_stalled_decisions_call_hits_the_total_deadline():
    import threading

    release = threading.Event()
    calls = []

    def handle(request):
        calls.append(request)
        if len(calls) == 1:
            release.wait(5)
        return httpx2.Response(200, json=RESPONSE)

    decisions = DecisionClient(httpx2.Client(transport=httpx2.MockTransport(handle)), api_key="k", sleep=lambda s: None, deadline=0.2)
    assert ask(decisions).answers == RESPONSE["answers"]
    release.set()
    assert len(calls) == 2
