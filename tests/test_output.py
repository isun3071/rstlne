import io
import sys

import pytest

from rstlne import calibrate, data, puzzlegen, selfplay, tournament


@pytest.mark.parametrize("module", [tournament, calibrate, data, puzzlegen, selfplay])
def test_long_commands_send_each_line_through_a_pipe_at_once(module, monkeypatch):
    piped = io.TextIOWrapper(io.BytesIO())  # what stdout is under `| tee`: block buffered
    monkeypatch.setattr(sys, "stdout", piped)
    with pytest.raises(SystemExit):
        module.main(["--no-such-option"])
    assert piped.line_buffering
