import pickle

import pytest

from rstlne.engine.state import IllegalAction
from rstlne.llm.decisions import DecisionsError
from rstlne.players.base import InvalidResponse


@pytest.mark.parametrize("err, fields", [
    (DecisionsError(403, "Key limit exceeded"), {"status": 403}),
    (InvalidResponse("bad_tool_call", "No tool call."), {"code": "bad_tool_call"}),
    (IllegalAction("vowel_on_spin", "O is a vowel."), {"code": "vowel_on_spin"}),
])
def test_errors_survive_the_trip_back_from_a_game_process(err, fields):
    # A tournament plays each game in a worker process and gets its error back pickled. An error that can't be
    # rebuilt there broke the whole pool ("terminated abruptly") instead of failing one game with its message.
    back = pickle.loads(pickle.dumps(err))
    assert type(back) is type(err) and str(back) == str(err)
    assert all(getattr(back, k) == v for k, v in fields.items())
