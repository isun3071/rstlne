"""Load wheel.toml, config.toml, and puzzle files. File I/O lives here so engine/ stays pure."""

import json
import tomllib
from pathlib import Path

from rstlne.engine.puzzle import Puzzle
from rstlne.engine.state import Rules
from rstlne.engine.wheel import WheelSpec

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config.toml"


def read_toml(path: Path) -> dict:
    with open(path, "rb") as f:
        return tomllib.load(f)


def load_config(path: Path = CONFIG) -> dict:
    return read_toml(path)


def load_wheel(path: Path = ROOT / "wheel.toml") -> WheelSpec:
    return WheelSpec.from_dict(read_toml(path))


def load_rules(path: Path = CONFIG) -> Rules:
    return Rules.from_dict(read_toml(path))


def load_puzzles(path: Path) -> list[Puzzle]:
    """A puzzle file: a plain list, or a generated batch with its puzzles under "puzzles"."""
    data = json.loads(Path(path).read_text())
    return [Puzzle.from_dict(p) for p in (data["puzzles"] if isinstance(data, dict) else data)]
