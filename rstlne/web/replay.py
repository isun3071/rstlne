"""Replaying a logged game for the page: rebuild it from its header and re-apply every logged action.

The engine is deterministic, so the seed, rules, wheel, and puzzles in a log's header plus its actions give
back every state. Each replayed result is checked against the logged one, so a log the current engine no
longer reproduces is refused instead of drawn wrong. The page gets the same events as a live game, seen by a
spectator, with each seat's thinking rebuilt from its logged record.
"""

from __future__ import annotations

import json
from pathlib import Path

from rstlne.engine.puzzle import Puzzle
from rstlne.engine.rules import apply, new_game
from rstlne.engine.state import (
    Action,
    BonusPicks,
    BonusSolve,
    BuyVowel,
    CallConsonant,
    CallLetter,
    Choose,
    Forfeit,
    GameState,
    Rules,
    Solve,
    Spin,
    UseWild,
)
from rstlne.engine.wheel import Overlay, WheelSpec
from rstlne.players.bot.player import explain
from rstlne.players.decision import decision_lines
from rstlne.players.hybrid import ask_line
from rstlne.web.session import Narrator


def label_of(seat: dict) -> str:
    """A seat's name on the page, from its logged description, as its player's label() gives it in play."""
    kind = seat.get("kind")
    if kind == "bot":
        return f"bot v{seat.get('version', '?')}"
    if kind == "hybrid":
        return f"bot v{seat.get('version', '?')} + {seat.get('model')}"
    if kind == "decision":
        return f"{seat.get('model')} + {seat.get('solver')}"
    if kind == "llm":
        return str(seat.get("model"))
    if kind == "human":
        return str(seat.get("name") or "human")
    return str(kind or "seat")


def thoughts_of(seat: dict, raw: dict | None) -> list[str]:
    """A seat's thinking for one move, from the record its player logged."""
    if not isinstance(raw, dict) or not raw:
        return []
    kind = seat.get("kind")
    if kind in ("bot", "hybrid"):
        lines = explain(raw)
        if kind == "hybrid" and raw.get("ask"):
            lines.append(ask_line(str(seat.get("model")), raw["ask"]))
        return lines
    if kind == "decision":
        return decision_lines(raw)
    if kind == "llm":
        return [f"{key}: {raw[key].strip()}" for key in ("reasoning", "content") if isinstance(raw.get(key), str) and raw[key].strip()]
    return []


def action_of(logged: dict) -> Action:
    kind = logged["kind"]
    match kind:
        case "spin":
            return Spin()
        case "call_consonant":
            return CallConsonant(logged["letter"])
        case "call_letter":
            return CallLetter(logged["letter"])
        case "buy_vowel":
            return BuyVowel(logged["letter"])
        case "solve":
            return Solve(logged["answer"])
        case "use_wild":
            return UseWild(bool(logged["use"]))
        case "bonus_picks":
            return BonusPicks(tuple(logged["consonants"]), logged["vowel"])
        case "bonus_solve":
            return BonusSolve(logged["answer"])
        case "forfeit":
            return Forfeit()
    return Choose(logged.get("option", kind))  # keep, flip, pass, play


def game_of(header: dict) -> GameState:
    """The opening state of a logged game."""
    r = header["rules"]
    rules = Rules(**{**r, "bonus_letters": tuple(r["bonus_letters"])})
    w = header["wheel"]
    spec = WheelSpec(
        base=tuple(w["base"]), free_play=w["free_play"], million_center=w["million_center"],
        mystery_face=w["mystery_face"], mystery_prize=w["mystery_prize"], express=w["express"],
        overlays=tuple(Overlay(**{**o, "mystery": tuple(o.get("mystery") or ())}) for o in w["overlays"]),
        envelopes=tuple(w["envelopes"]), million_swap=tuple(w["million_swap"]),
    )
    puzzles = [Puzzle(**p) for p in header["puzzles"]]
    bonus = Puzzle(**header["bonus_puzzle"]) if header.get("bonus_puzzle") else None
    return new_game(header["seed"], rules, spec, puzzles, bonus)


def read_log(path: Path) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def replay(path: Path) -> dict:
    """A logged game as the page's events, with what the replay controls need to know about it."""
    rows = read_log(path)
    header = rows[0]
    if header.get("type") not in ("game", "header"):
        raise ValueError(f"{Path(path).name} doesn't start with a game header")
    seats = header["seats"]
    names = (header.get("tournament") or {}).get("names")
    entrants = (header.get("tournament") or {}).get("entrants")
    labels = [names[entrants[i]] if names and entrants else label_of(s) for i, s in enumerate(seats)]
    narrator = Narrator(labels, [s.get("kind") for s in seats], viewer=None, thoughts=True,
                        names=[s.get("name") if s.get("kind") == "human" else None for s in seats])  # the game is over: thinking gives nothing away
    state = game_of(header)
    events = narrator.start(state)
    rounds = [{"round": p["round"] if p.get("round") else i + 1, "category": p["category"], "answer": p["answer"]}
              for i, p in enumerate(header["puzzles"])]
    if header.get("bonus_puzzle"):
        rounds.append({"round": None, "category": header["bonus_puzzle"]["category"], "answer": header["bonus_puzzle"]["answer"]})
    summary = None
    for n, row in enumerate(rows[1:], 2):
        if row.get("type") == "summary":
            summary = row
            continue
        if row.get("type") != "action":
            continue
        before = state
        try:
            state = apply(state, action_of(row["action"]))
        except Exception as err:
            raise ValueError(f"{Path(path).name} doesn't replay: line {n} was refused ({err})") from None
        logged, got = row["result"], state.last
        landed = (logged.get("wedge") or {}).get("number"), (got.wedge.number if got.wedge else None)
        if logged["outcome"] != got.outcome or (row["action"]["kind"] == "spin" and landed[0] != landed[1]):
            raise ValueError(f"{Path(path).name} doesn't replay: line {n} logged {logged['outcome']}"
                             f"{' on wedge ' + str(landed[0]) if landed[0] else ''}, the engine gives {got.outcome}"
                             f"{' on wedge ' + str(landed[1]) if landed[1] else ''}")
        raw = row.get("raw") if isinstance(row.get("raw"), dict) else {}
        skipped = got.outcome == "forfeit" and bool(raw.get("skipped"))
        events += narrator.move(before, state, [] if skipped else thoughts_of(seats[row["seat"]], raw), skipped=skipped)
    if summary is not None:
        usage = [{"model": labels[i], **u} for i, u in enumerate(summary.get("usage_by_seat") or []) if (u or {}).get("calls")]
        usage = [{"model": u["model"], "calls": u.get("calls", 0), "tokens": u.get("total_tokens", 0),
                  "cached": u.get("cached_tokens", 0), "cost": u.get("cost", 0.0)} for u in usage]
        events.append(narrator.over(state, usage, str(path)))
    return {"meta": {"name": Path(path).name, "seed": header["seed"], "started": header.get("started"),
                     "seats": labels, "kinds": [s.get("kind") for s in seats], "moves": narrator.moves,
                     "finished": summary is not None, "rounds": rounds},
            "events": events}


def list_logs(folder: Path, limit: int = 300) -> list[dict]:
    """The game logs in a folder, newest first: who played, the seed, and how it ended, read from each log's
    first and last lines only."""
    out = []
    for path in sorted(Path(folder).glob("*.jsonl"), key=lambda p: p.name, reverse=True)[:limit]:
        try:
            with path.open() as fh:
                first = fh.readline()
                last = first
                for line in fh:
                    if line.strip():
                        last = line
            header, end = json.loads(first), json.loads(last)
        except (OSError, json.JSONDecodeError):
            continue
        if header.get("type") not in ("game", "header") or "seats" not in header:
            continue
        names = (header.get("tournament") or {}).get("names")
        entrants = (header.get("tournament") or {}).get("entrants")
        seats = [names[entrants[i]] if names and entrants else label_of(s) for i, s in enumerate(header["seats"])]
        finished = end.get("type") == "summary"
        out.append({"name": path.name, "started": header.get("started"), "seed": header.get("seed"), "seats": seats,
                    "kinds": [s.get("kind") for s in header["seats"]], "finished": finished,
                    "totals": end.get("totals") if finished else None})
    return out
