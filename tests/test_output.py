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


@pytest.mark.parametrize("module", ["rstlne.cli", "rstlne.tournament", "rstlne.calibrate", "rstlne.selfplay",
                                    "rstlne.puzzlegen", "rstlne.data", "rstlne.players.bot.player"])
def test_every_entry_point_imports_on_its_own(module):
    import subprocess
    result = subprocess.run([sys.executable, "-c", f"import {module}"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr.splitlines()[-1:]
