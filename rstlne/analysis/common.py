"""Reading tournament logs: lineups by id, finished games, and the main rounds in them."""

from __future__ import annotations

import json
import tomllib
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from rstlne import settings
from rstlne.engine.puzzle import LETTERS

TOURNAMENTS = settings.ROOT / "logs" / "tournaments"
LINEUPS = settings.ROOT / "lineups.toml"


def lineups(phase: str | None = None, path: Path = LINEUPS) -> dict[str, dict]:
    """The lineups of a phase in lineups.toml (its default phase when none is named): id -> folder, label, note."""
    data = tomllib.loads(Path(path).read_text())
    phase = phase or data["default"]
    if phase not in data:
        raise ValueError(f"lineups.toml has no phase {phase!r}; it has {', '.join(k for k in data if k != 'default')}")
    return {k: {**v, "folder": TOURNAMENTS / v["folder"]} for k, v in data[phase].items()}


def resolve(targets: Sequence[str], phase: str | None = None, path: Path = LINEUPS) -> list[tuple[str, Path]]:
    """(name, folder) for each target: a lineup id from lineups.toml, or a folder path."""
    known = lineups(phase, path) if Path(path).exists() else {}
    out = []
    for t in targets:
        if t in known:
            out.append((f"lineup {t}", known[t]["folder"]))
        elif Path(t).is_dir():
            out.append((Path(t).name, Path(t)))
        else:
            raise ValueError(f"{t!r} is neither a lineup in lineups.toml nor a folder")
    return out


@dataclass
class Game:
    path: Path
    header: dict
    actions: list[dict]  # every action line, bonus round included
    summary: dict
    names: list[str] = field(init=False)  # the entrant in each seat, as the tournament names them

    def __post_init__(self):
        t = self.header["tournament"]
        self.names = [t["names"][e] for e in t["entrants"]]

    @property
    def set(self) -> int:
        return self.header["tournament"]["set"]

    def kind(self, seat: int) -> str:
        return self.header["seats"][seat]["kind"]

    def winners(self) -> list[float]:
        """Each seat's share of the win: tied leaders split it."""
        totals = self.summary["totals"]
        top = max(totals)
        n = totals.count(top)
        return [1 / n if t == top else 0.0 for t in totals]

    @property
    def logs_planner(self) -> bool:
        """Whether this game's bot moves log the known-answer planner (from 2026-11-01, with "answers")."""
        return any(isinstance(a.get("raw"), dict) and "answers" in a["raw"] for a in self.actions)

    def planner_on(self, a: dict) -> bool:
        """Whether a bot or hybrid move was made with the answer treated as known. Older logs don't record the
        planner, so its own test is redone: the move's confidence, calibrated for its version, at the threshold."""
        raw = a.get("raw") if isinstance(a.get("raw"), dict) else {}
        if self.kind(a["seat"]) not in ("bot", "hybrid"):
            return False
        if "planner" in raw:
            return True
        if self.logs_planner or raw.get("version") is None or raw.get("confidence") is None:
            return False
        from rstlne.players.bot import calibration, versions
        knobs = versions.knobs(raw["version"])
        return calibration.curve(knobs.calibration)(raw["confidence"]) >= knobs.known_answer

    def milks(self, a: dict) -> bool:
        """A spin made with the answer treated as known."""
        raw = a.get("raw") if isinstance(a.get("raw"), dict) else {}
        if not self.planner_on(a):
            return False
        return raw.get("planner") == "spin" if "planner" in raw else a["action"]["kind"] == "spin"

    def rounds(self) -> dict[int, list[dict]]:
        """The main rounds' actions, by round number."""
        out: dict[int, list[dict]] = {}
        for a in self.actions:
            state = a.get("state") or {}
            if state.get("round") and not str(state.get("phase", "")).startswith("bonus"):
                out.setdefault(state["round"]["number"], []).append(a)
        return out


def games(folder: Path) -> Iterator[Game]:
    """Every finished game in a tournament folder, in set and ordering order."""
    for path in sorted(Path(folder).glob("set*.jsonl")):
        rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        if len(rows) < 2 or rows[-1].get("type") != "summary":
            continue
        yield Game(path, rows[0], [r for r in rows[1:-1] if r.get("type") == "action"], rows[-1])


def shown(answer: str, used: Sequence[str]) -> float:
    """The share of the puzzle's letter squares showing once `used` letters are called."""
    letters = [c for c in answer if c in LETTERS]
    called = set(used)
    return sum(c in called for c in letters) / len(letters)


def letters_in(answer: str) -> int:
    return sum(c in LETTERS for c in answer)


def solved_by(round_actions: Sequence[dict]) -> tuple[int, dict] | None:
    """The seat that solved the round and its solving action, or None if nobody did."""
    for a in round_actions:
        if a["action"]["kind"] == "solve" and a["result"]["outcome"] == "solved":
            return a["seat"], a
    return None


def board_of(a: dict, refuted: Sequence[str] = ()) -> tuple[str, str, str, tuple[str, ...]]:
    """(answer, category, used letters sorted, refuted answers sorted): the board key the reader and saved asks use."""
    rnd = a["state"]["round"]
    return rnd["puzzle"]["answer"], rnd["puzzle"]["category"], "".join(sorted(rnd["used"])), tuple(sorted(refuted))
