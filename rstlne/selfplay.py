"""Self-play and tuning for the bot, built to run for hours on a server.

    python -m rstlne.selfplay reads --puzzles puzzles/generated/tuning-101.json --out logs/selfplay/reads --shard 1/1

Every job splits into shards (`--shard i/n`) so several machines can share it, writes compact JSONL,
resumes where it stopped, and prints a status line every 2 minutes with an estimated finish.
No job calls an API: the bot reads boards and plays games on its own.

games: bot-only games with duplicate scoring, between bot variants (a name and knob changes), one compact
line per game: who sat where, final totals, totals after each main round, the bonus, and each seat's solves.

tune-decisions: test each candidate value of each decision knob as a variant against the current bot, with
the eager bot at the table, in duplicate-scored games; adopt a value only if it wins with its 95% interval
clear of zero.

tune-reader: tune the reader's knobs one at a time, scoring each setting by the average log probability
the reader puts on the true answer across every board of the tuning puzzles, then check the tuned knobs
against the untuned ones on held out puzzles.

steal: fit the steal curve, q = 1 / (1 + e^-(a + b * shown + c * confidence)), the chance a player solves
correctly on a turn, from tournament logs: every main round turn where a player could have solved, with
the share of the board showing and the reader's confidence on that board.

reads: reveal each puzzle in English letter frequency order, calling every letter, hit or miss, and
stop once each tenth of the board shows. At each stop, record the reader's best answer, its confidence,
whether it was right, and the probability it gave the true answer. Bonus puzzles are read the way the
bot meets them: R S T L N E and its own picks.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Callable, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, fields, replace
from typing import NamedTuple
from pathlib import Path

import numpy as np

from rstlne import settings
from rstlne.engine.puzzle import LETTERS, Puzzle
from rstlne.engine.rules import new_game, public_view
from rstlne.engine.state import Phase, PublicView, Rules
from rstlne.engine.wheel import WheelSpec
from rstlne.narrate import duration, line_output
from rstlne.players.bot import bonus, calibration, versions
from rstlne.players.bot.reader import Reader

ORDER = "ETAOINSHRDLCUMWFGYPBVKJXQZ"  # English letter frequency
HEARTBEAT = 120  # seconds between status lines
_PLACEHOLDER = Puzzle("Thing", "PLACEHOLDER", bonus=True)


@dataclass(frozen=True)
class Board:
    puzzle: Puzzle
    used: frozenset[str]
    shown: float  # share of the letter squares showing


def stops(puzzle: Puzzle) -> list[tuple[float, frozenset[str]]]:
    """(share shown, letters called) as the board fills: blank, then once each tenth of the board shows."""
    letters = [c for c in puzzle.answer if c in LETTERS]
    out = [(0.0, frozenset())]
    used: set[str] = set()
    for c in ORDER:
        used.add(c)
        shown = sum(x in used for x in letters) / len(letters)
        if shown >= 1:
            break
        if int(shown * 10) > int(out[-1][0] * 10):
            out.append((shown, frozenset(used)))
    return out


def view_of(puzzle: Puzzle, used: frozenset[str], rules: Rules, spec: WheelSpec) -> PublicView:
    """The public view of a main round board with this puzzle and these letters called."""
    state = new_game(1, rules, spec, (puzzle,) * rules.main_rounds, _PLACEHOLDER)
    return public_view(replace(state, round=replace(state.round, used=used)), 0)


def bonus_board(puzzle: Puzzle, reader: Reader, rules: Rules, spec: WheelSpec) -> Board:
    """The board the bot solves a bonus puzzle from: R S T L N E, then its own picks."""
    given = frozenset(rules.bonus_letters)
    view = replace(view_of(puzzle, given, rules, spec), phase=Phase.BONUS_PICKS, round_number=None,
                   bonus_consonants=rules.bonus_consonants)
    picks = bonus.picks(reader.read(view), view, rules)
    used = given | set(picks.consonants) | {picks.vowel}
    letters = [c for c in puzzle.answer if c in LETTERS]
    return Board(puzzle, frozenset(used), sum(c in used for c in letters) / len(letters))


def read_puzzle(puzzle: Puzzle, reader: Reader, rules: Rules, spec: WheelSpec) -> list[dict]:
    """One row per board read."""
    if puzzle.bonus:
        boards = [bonus_board(puzzle, reader, rules, spec)]
    else:
        boards = [Board(puzzle, used, shown) for shown, used in stops(puzzle)]
    rows = []
    for board in boards:
        started = time.monotonic()
        belief = reader.read(view_of(board.puzzle, board.used, rules, spec))
        took = time.monotonic() - started
        answers = dict(belief.answers)
        rows.append({
            "answer": puzzle.answer, "category": puzzle.category, "bonus": puzzle.bonus,
            "shown": round(board.shown, 4), "used": "".join(sorted(board.used)),
            "best": belief.best, "confidence": belief.confidence, "correct": belief.best == puzzle.answer,
            "oov": belief.oov, "p_true": answers.get(puzzle.answer, 0.0), "seconds": round(took, 3),
        })
    return rows


# Shards, workers, and resuming


def shard_of(items: Sequence, i: int, n: int) -> list:
    """The i-th of n shards, by position, so every machine agrees on the split."""
    return [x for k, x in enumerate(items) if k % n == i - 1]


def parse_shard(text: str) -> tuple[int, int]:
    i, n = (int(x) for x in text.split("/"))
    if not 1 <= i <= n:
        raise ValueError(f"shard {text}: i must be 1 to n")
    return i, n


_worker: dict = {}


def _start_worker(make_reader, knobs, rules, spec) -> None:
    _worker.update(reader=make_reader(knobs), rules=rules, spec=spec)


def _read_in_worker(puzzle: Puzzle) -> list[dict]:
    return read_puzzle(puzzle, _worker["reader"], _worker["rules"], _worker["spec"])


def read_all(
    puzzles: Sequence[Puzzle],
    out: Path,
    rules: Rules,
    spec: WheelSpec,
    knobs: versions.Knobs,
    make_reader: Callable[[versions.Knobs], Reader],
    shard: tuple[int, int] = (1, 1),
    workers: int = 1,
    say=print,
    heartbeat: float = HEARTBEAT,
) -> Path:
    """Read every board of this shard's puzzles into reads-shard{i}of{n}.jsonl, skipping puzzles already read."""
    i, n = shard
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"reads-shard{i}of{n}.jsonl"
    done = {(r["answer"], r["bonus"]) for r in _rows(path)}
    mine = [p for p in shard_of(puzzles, i, n) if (p.answer, p.bonus) not in done]
    if done:
        say(f"{len(done)} puzzles already read; reading the other {len(mine)}")
    say(f"Reading {len(mine)} puzzles, shard {i}/{n}, {workers} worker{'s' if workers != 1 else ''}; "
        "a status line every 2 minutes")
    began = last = time.monotonic()
    boards = 0
    if workers > 1:
        pool = ProcessPoolExecutor(workers, initializer=_start_worker, initargs=(make_reader, knobs, rules, spec))
        results = pool.map(_read_in_worker, mine)
    else:
        pool = None
        reader = make_reader(knobs)
        results = (read_puzzle(p, reader, rules, spec) for p in mine)
    try:
        with open(path, "a") as f:
            for k, rows in enumerate(results, 1):
                for row in rows:
                    f.write(json.dumps(row) + "\n")
                f.flush()  # a puzzle's boards land together, so a stop never leaves half a puzzle
                boards += len(rows)
                now = time.monotonic()
                if now - last >= heartbeat:
                    last = now
                    left = (now - began) / k * (len(mine) - k)
                    say(f"  {k} of {len(mine)} puzzles, {boards} boards · {duration(now - began)} elapsed, "
                        f"finish in about {duration(left)}")
    finally:
        if pool:
            pool.shutdown()
    say(f"Read {len(mine)} puzzles ({boards} boards) in {duration(time.monotonic() - began)} into {path}")
    return path


def _rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def summarize_reads(out: Path) -> dict:
    """Every shard's boards together: accuracy overall and by confidence, the reader's average probability
    on the true answer, and how fast it read."""
    rows = [r for path in sorted(out.glob("reads-shard*.jsonl")) for r in _rows(path)]
    bins = []
    for lo in [x / 10 for x in range(10)]:
        inside = [r for r in rows if lo <= r["confidence"] < lo + 0.1 or (lo == 0.9 and r["confidence"] == 1)]
        bins.append({"confidence": f"{lo:.1f}-{lo + 0.1:.1f}", "boards": len(inside),
                     "accuracy": sum(r["correct"] for r in inside) / len(inside) if inside else None})
    return {
        "boards": len(rows),
        "puzzles": len({(r["answer"], r["bonus"]) for r in rows}),
        "accuracy": sum(r["correct"] for r in rows) / len(rows) if rows else None,
        "mean_p_true": sum(r["p_true"] for r in rows) / len(rows) if rows else None,
        "mean_seconds": sum(r["seconds"] for r in rows) / len(rows) if rows else None,
        "by_confidence": bins,
    }


# Tuning the reader

READER_GRID = {
    "phrase_odds": [0.25, 0.5, 1.0, 2.0, 4.0],
    "name_odds": [0.0125, 0.025, 0.05, 0.1, 0.2],
    "fit_weight": [0.0, 2.0, 4.0, 6.0, 8.0],
    "pair_weight": [0.5, 0.8, 0.95, 0.99],
}
_PAIRED = {"phrase_odds": "phrase_odds_other", "name_odds": "name_odds_other"}  # move together, keeping their ratio


def setting(knobs: versions.Knobs, name: str, value: float) -> dict:
    """The knob changes for one grid value: a paired knob keeps its ratio to its partner."""
    changes = {name: value}
    if name in _PAIRED:
        other = _PAIRED[name]
        changes[other] = round(value * getattr(knobs, other) / getattr(knobs, name), 12)
    return changes


def _score(rows: Sequence[dict], samples: int) -> dict:
    """Average log probability on the true answer, floored at half a sample, with accuracy alongside."""
    floor = 1 / (2 * samples)
    n = len(rows)
    return {
        "boards": n,
        "log_score": float(np.mean([np.log(max(r["p_true"], floor)) for r in rows])) if n else float("-inf"),
        "accuracy": sum(r["correct"] for r in rows) / n if n else 0.0,
        "mean_p_true": float(np.mean([r["p_true"] for r in rows])) if n else 0.0,
    }


def read_rows(puzzles: Sequence[Puzzle], knobs: versions.Knobs, make_reader, rules: Rules, spec: WheelSpec,
              workers: int = 1) -> list[dict]:
    """Every board of `puzzles`, read with these knobs."""
    if workers > 1:
        with ProcessPoolExecutor(workers, initializer=_start_worker, initargs=(make_reader, knobs, rules, spec)) as pool:
            return [row for rows in pool.map(_read_in_worker, puzzles, chunksize=4) for row in rows]
    reader = make_reader(knobs)
    return [row for p in puzzles for row in read_puzzle(p, reader, rules, spec)]


def evaluate(puzzles: Sequence[Puzzle], knobs: versions.Knobs, make_reader, rules: Rules, spec: WheelSpec,
             workers: int = 1) -> dict:
    """Read every board of `puzzles` with these knobs, and score the reading."""
    return _score(read_rows(puzzles, knobs, make_reader, rules, spec, workers), knobs.samples)


# Calibration


def _honesty(pairs: Sequence[tuple[float, bool]], correct) -> dict:
    return {"boards": len(pairs), "error": calibration.error(pairs, correct), "brier": calibration.brier(pairs, correct),
            "mean_stated": float(np.mean([correct(c) for c, _ in pairs])), "accuracy": float(np.mean([r for _, r in pairs]))}


def _bands(pairs: Sequence[tuple[float, bool]], correct, bands: int = 10) -> list[dict]:
    out = []
    for b in range(bands):
        lo, hi = b / bands, (b + 1) / bands
        inside = [(c, r) for c, r in pairs if lo <= c < hi or (b == bands - 1 and c == 1)]
        if inside:
            out.append({"raw": f"{lo:.1f}-{hi:.1f}", "boards": len(inside),
                        "raw_mean": float(np.mean([c for c, _ in inside])),
                        "calibrated_mean": float(np.mean([correct(c) for c, _ in inside])),
                        "actual": float(np.mean([r for _, r in inside]))})
    return out


def calibrate(puzzles: Sequence[Puzzle], held_out: Sequence[Puzzle], out: Path, rules: Rules, spec: WheelSpec,
              knobs: versions.Knobs, make_reader, workers: int = 1, say=print) -> calibration.Points:
    """Fit the confidence curve on the tuning puzzles' main round boards, and report how honest the
    reader's confidence is before and after, on the tuning boards and on held out ones."""
    began = time.monotonic()
    raw = replace(knobs, calibration=())
    say(f"Reading {len(puzzles)} tuning and {len(held_out)} held out puzzles, {workers} worker{'s' if workers != 1 else ''}")
    tuning = [(r["confidence"], r["correct"]) for r in read_rows(puzzles, raw, make_reader, rules, spec, workers) if not r["bonus"]]
    unseen = [(r["confidence"], r["correct"]) for r in read_rows(held_out, raw, make_reader, rules, spec, workers) if not r["bonus"]]
    points = calibration.fit(tuning)
    before, after = calibration.curve(()), calibration.curve(points)
    result = {
        "points": [list(p) for p in points],
        "knob": "calibration=" + ",".join(f"{x:g}:{y:g}" for x, y in points),
        "tuning": {"before": _honesty(tuning, before), "after": _honesty(tuning, after)},
        "held_out": {"before": _honesty(unseen, before), "after": _honesty(unseen, after),
                     "bands": _bands(unseen, after)},
        "reader_knobs": _knob_dict(raw),
        "minutes": round((time.monotonic() - began) / 60, 1),
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "calibration.json").write_text(json.dumps(result, indent=2) + "\n")
    for name, label in (("tuning", "tuning boards"), ("held_out", "held out boards")):
        b, a = result[name]["before"], result[name]["after"]
        say(f"{label}: calibration error {b['error']:.3f} -> {a['error']:.3f}, Brier {b['brier']:.3f} -> {a['brier']:.3f} "
            f"({a['boards']} boards; accuracy {a['accuracy']:.1%}, mean stated {b['mean_stated']:.1%} -> {a['mean_stated']:.1%})")
    for band in result["held_out"]["bands"]:
        say(f"  raw {band['raw']}: {band['boards']:5d} boards, says {band['raw_mean']:.0%} -> {band['calibrated_mean']:.0%}, "
            f"actually right {band['actual']:.0%}")
    say(f"Curve points ({len(points)}), for v1's knobs: {result['knob']}")
    return points


def _knob_dict(knobs: versions.Knobs) -> dict:
    return {f.name: list(v) if isinstance(v := getattr(knobs, f.name), tuple) else v for f in fields(knobs)}


def tune_reader(puzzles: Sequence[Puzzle], held_out: Sequence[Puzzle], out: Path, rules: Rules, spec: WheelSpec,
                knobs: versions.Knobs, make_reader, grid: dict | None = None, passes: int = 2, workers: int = 1,
                say=print) -> versions.Knobs:
    """Coordinate search over the reader's knobs. Every setting's score goes to evaluations.jsonl, so a rerun
    skips what's done; the result, with its check on held out puzzles, goes to reader-tune.json."""
    grid = READER_GRID if grid is None else grid
    out.mkdir(parents=True, exist_ok=True)
    log = out / "evaluations.jsonl"
    done = {json.dumps(r["knobs"], sort_keys=True): r["score"] for r in _rows(log)}
    total = 1 + sum(len(v) for v in grid.values()) * passes
    began = time.monotonic()
    say(f"Tuning {', '.join(grid)} on {len(puzzles)} puzzles, up to {passes} passes, {workers} "
        f"worker{'s' if workers != 1 else ''}; {len(done)} settings already scored")

    def score_of(k: versions.Knobs, label: str) -> dict:
        key = json.dumps(_knob_dict(k), sort_keys=True)
        if key not in done:
            started = time.monotonic()
            done[key] = evaluate(puzzles, k, make_reader, rules, spec, workers)
            with open(log, "a") as f:
                f.write(json.dumps({"knobs": _knob_dict(k), "score": done[key]}) + "\n")
            n = len(done)
            elapsed = time.monotonic() - began
            say(f"  {label}: log score {done[key]['log_score']:.3f}, accuracy {done[key]['accuracy']:.1%} "
                f"· {duration(time.monotonic() - started)} · {n} scored, {duration(elapsed)} elapsed, "
                f"at most about {duration(elapsed / max(n, 1) * max(total - n, 0))} more")
        return done[key]

    current, best = knobs, score_of(knobs, "starting knobs")["log_score"]
    for p in range(1, passes + 1):
        changed = False
        for name, values in grid.items():
            for value in values:
                candidate = replace(current, **setting(current, name, value))
                s = score_of(candidate, f"pass {p}, {name} = {value}")["log_score"]
                if s > best + 1e-12:
                    current, best, changed = candidate, s, True
            say(f"  pass {p}: {name} = {getattr(current, name)}, log score {best:.3f}")
        if not changed:
            break

    untuned_score = score_of(knobs, "starting knobs")
    tuned_score = score_of(current, "tuned knobs")
    say(f"Checking on {len(held_out)} held out puzzles")
    held = {"untuned": evaluate(held_out, knobs, make_reader, rules, spec, workers),
            "tuned": evaluate(held_out, current, make_reader, rules, spec, workers)}
    changes = {k: getattr(current, k) for k in _knob_dict(current) if getattr(current, k) != getattr(knobs, k)}
    result = {"start": _knob_dict(knobs), "best": _knob_dict(current), "changes": changes,
              "tuning": {"untuned": untuned_score, "tuned": tuned_score}, "held_out": held,
              "evaluations": len(done), "minutes": round((time.monotonic() - began) / 60, 1)}
    (out / "reader-tune.json").write_text(json.dumps(result, indent=2) + "\n")
    say(f"Tuned knobs: {changes or 'no change'}")
    say(f"  tuning puzzles: log score {untuned_score['log_score']:.3f} -> {tuned_score['log_score']:.3f}, "
        f"accuracy {untuned_score['accuracy']:.1%} -> {tuned_score['accuracy']:.1%}")
    say(f"  held out puzzles: log score {held['untuned']['log_score']:.3f} -> {held['tuned']['log_score']:.3f}, "
        f"accuracy {held['untuned']['accuracy']:.1%} -> {held['tuned']['accuracy']:.1%}")
    return current


# The steal curve


_TURN_PHASES = ("turn", "express")
_TURN_KINDS = ("spin", "buy_vowel", "solve")  # what a player does when solving is on offer


def collect_turns(folders: Sequence[Path]) -> list[dict]:
    """Every main round turn in finished games where a player had the wheel and could have solved."""
    turns = []
    for folder in folders:
        for path in sorted(Path(folder).glob("set*.jsonl")):
            rows = _rows(path)
            if not rows or rows[-1].get("type") != "summary":
                continue
            models = [seat.get("model") or seat.get("kind") for seat in rows[0]["seats"]]
            set_index = rows[0].get("tournament", {}).get("set", 0)
            for r in rows[1:]:
                state = r.get("state") or {}
                if r.get("type") != "action" or state.get("phase") not in _TURN_PHASES or not state.get("round"):
                    continue
                if r["action"]["kind"] not in _TURN_KINDS:
                    continue
                puzzle = state["round"]["puzzle"]
                letters = [c for c in puzzle["answer"] if c in LETTERS]
                used = frozenset(state["round"]["used"])
                turns.append({
                    "set": f"{folder}:{set_index}", "game": path.stem, "model": models[r["seat"]],
                    "answer": puzzle["answer"], "category": puzzle["category"], "used": "".join(sorted(used)),
                    "shown": sum(c in used for c in letters) / len(letters), "kind": r["action"]["kind"],
                    "solved": int(r["action"]["kind"] == "solve" and r["result"]["outcome"] == "solved"),
                })
    return turns


def _confidence(board: tuple[str, str, str]) -> float:
    answer, category, used = board
    view = view_of(Puzzle(category, answer), frozenset(used), _worker["rules"], _worker["spec"])
    return _worker["reader"].read(view).confidence


def confidences(boards: Sequence[tuple[str, str, str]], make_reader, knobs, rules, spec, workers: int = 1,
                say=lambda line: None, heartbeat: float = HEARTBEAT) -> dict:
    """The reader's confidence on each distinct board, read once."""
    if workers > 1:
        pool = ProcessPoolExecutor(workers, initializer=_start_worker, initargs=(make_reader, knobs, rules, spec))
        results = pool.map(_confidence, boards, chunksize=16)
    else:
        pool = None
        _start_worker(make_reader, knobs, rules, spec)
        results = map(_confidence, boards)
    out, began, last = {}, time.monotonic(), time.monotonic()
    try:
        for k, (board, c) in enumerate(zip(boards, results), 1):
            out[board] = c
            now = time.monotonic()
            if now - last >= heartbeat:
                last = now
                say(f"  read {k} of {len(boards)} boards · {duration(now - began)} elapsed, "
                    f"finish in about {duration((now - began) / k * (len(boards) - k))}")
    finally:
        if pool:
            pool.shutdown()
    return out


def steal_points(folders: Sequence[Path], reader: Reader, rules: Rules, spec: WheelSpec) -> list[dict]:
    """Turns with the reader's confidence filled in, in this process."""
    turns = collect_turns(folders)
    boards = sorted({(t["answer"], t["category"], t["used"]) for t in turns})
    _worker.update(reader=reader, rules=rules, spec=spec)
    seen = {b: _confidence(b) for b in boards}
    return [{**t, "confidence": seen[(t["answer"], t["category"], t["used"])]} for t in turns]


def _logistic(x: np.ndarray, y: np.ndarray, start: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Maximum likelihood weights by Newton's method, and the inverse Hessian for standard errors."""
    w = np.zeros(x.shape[1]) if start is None else start.copy()
    hessian = np.eye(x.shape[1])
    for _ in range(100):
        p = 1 / (1 + np.exp(-(x @ w)))
        gradient = x.T @ (y - p)
        hessian = (x * (p * (1 - p))[:, None]).T @ x + 1e-9 * np.eye(x.shape[1])
        step = np.linalg.solve(hessian, gradient)
        w += step
        if np.abs(step).max() < 1e-9:
            break
    return w, np.linalg.inv(hessian)


def fit_steal(points: Sequence[dict], resamples: int = 1000, seed: int = 0) -> dict:
    """a, b, c with standard errors, and 95% intervals from resampling whole sets: the games of a set
    share puzzles, so they aren't independent."""
    x = np.array([[1.0, p["shown"], p["confidence"]] for p in points])
    y = np.array([float(p["solved"]) for p in points])
    w, inverse = _logistic(x, y)
    out = {"a": float(w[0]), "b": float(w[1]), "c": float(w[2]),
           "se": dict(zip("abc", (float(v) for v in np.sqrt(np.diag(inverse)))))}
    if resamples:
        groups: dict = {}
        for k, p in enumerate(points):
            groups.setdefault(p.get("set", k), []).append(k)
        keys = list(groups)
        rng = np.random.default_rng(seed)
        draws = []
        for _ in range(resamples):
            rows = np.concatenate([groups[keys[i]] for i in rng.integers(0, len(keys), len(keys))])
            draws.append(_logistic(x[rows], y[rows], start=w)[0])
        draws = np.array(draws)
        out["ci95"] = {name: [float(np.percentile(draws[:, i], 2.5)), float(np.percentile(draws[:, i], 97.5))]
                       for i, name in enumerate("abc")}
    return out


def steal_q(fit: dict, shown: float, confidence: float) -> float:
    return 1 / (1 + np.exp(-(fit["a"] + fit["b"] * shown + fit["c"] * confidence)))


def _spread(values: Sequence[float]) -> dict:
    v = np.array(values) if len(values) else np.zeros(1)
    return {"p25": float(np.percentile(v, 25)), "median": float(np.median(v)), "p75": float(np.percentile(v, 75))}


def steal(folders, out: Path, rules: Rules, spec: WheelSpec, knobs: versions.Knobs, make_reader,
          workers: int = 1, resamples: int = 1000, say=print) -> dict:
    """Fit the steal curve from tournament logs, and save the fit and its data points under `out`."""
    folders = [Path(f) for f in (folders if isinstance(folders, (list, tuple)) else [folders])]
    turns = collect_turns(folders)
    boards = sorted({(t["answer"], t["category"], t["used"]) for t in turns})
    games = len({(t["set"], t["game"]) for t in turns})
    say(f"Fitting the steal curve from {len(turns)} turns in {games} games; reading {len(boards)} distinct boards "
        f"with {workers} worker{'s' if workers != 1 else ''}")
    began = time.monotonic()
    seen = confidences(boards, make_reader, knobs, rules, spec, workers, say)
    points = [{**t, "confidence": seen[(t["answer"], t["category"], t["used"])]} for t in turns]
    fit = fit_steal(points, resamples)
    calibration = []
    for lo, hi in ((0, 0.02), (0.02, 0.05), (0.05, 0.1), (0.1, 0.2), (0.2, 0.4), (0.4, 1.01)):
        inside = [p for p in points if lo <= steal_q(fit, p["shown"], p["confidence"]) < hi]
        if inside:
            calibration.append({"predicted": f"{lo:.0%}-{min(hi, 1):.0%}", "turns": len(inside),
                                "mean_predicted": float(np.mean([steal_q(fit, p["shown"], p["confidence"]) for p in inside])),
                                "observed": sum(p["solved"] for p in inside) / len(inside)})
    attempts = [p for p in points if p["kind"] == "solve"]
    by_model = {}
    for model in sorted({p["model"] for p in points}):
        mine = [p for p in points if p["model"] == model]
        solves = sum(p["solved"] for p in mine)
        entry = {"turns": len(mine), "solves": solves, "a": None, "b": None, "c": None}
        if 0 < solves < len(mine):  # a curve needs both outcomes
            m = fit_steal(mine, resamples=0)
            entry.update(a=m["a"], b=m["b"], c=m["c"])
        by_model[model] = entry
    result = {
        **fit, "points": len(points), "solves": sum(p["solved"] for p in points), "games": games,
        "logs": [str(f) for f in folders], "knobs": {f.name: getattr(knobs, f.name) for f in fields(knobs)},
        "calibration": calibration, "by_model": by_model,
        "solve_attempts": {"count": len(attempts), "shown": _spread([p["shown"] for p in attempts]),
                           "confidence": _spread([p["confidence"] for p in attempts]),
                           "right": sum(p["solved"] for p in attempts)},
    }
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "steal-points.jsonl", "w") as f:
        for p in points:
            f.write(json.dumps(p) + "\n")
    (out / "steal-fit.json").write_text(json.dumps(result, indent=2) + "\n")
    ci = fit.get("ci95", {})
    for name in "abc":
        span = f" [{ci[name][0]:.2f} to {ci[name][1]:.2f}]" if name in ci else ""
        say(f"{name} = {fit[name]:.2f}{span}")
    say(f"steal_prior = ({fit['a']:.2f}, {fit['b']:.2f}, {fit['c']:.2f})  ·  {len(points)} turns, "
        f"{result['solves']} correct solves, in {duration(time.monotonic() - began)}")
    for row in calibration:
        say(f"  predicted {row['predicted']:>8s}: {row['turns']:5d} turns, solved {row['observed']:.1%} "
            f"(curve says {row['mean_predicted']:.1%})")
    s = result["solve_attempts"]
    say(f"  solve attempts: {s['count']}, {s['right']} right; board shown median {s['shown']['median']:.0%} "
        f"(middle half {s['shown']['p25']:.0%}-{s['shown']['p75']:.0%}), confidence median {s['confidence']['median']:.2f}")
    return result


# Bot games

READER_KNOBS = {"samples", "top_answers", "unknown_word", "vocabulary", "slot_candidates", "pair_weight", "phrase_odds",
                "phrase_odds_other", "name_odds", "name_odds_other", "fit_weight", "ing_boost", "same_letter_boost",
                "rhyme_boost", "same_name_boost"}


@dataclass(frozen=True)
class Entrant:
    """A bot variant: a name and knob changes, written name:knob=value+knob=value."""

    name: str
    changes: tuple[str, ...] = ()

    @classmethod
    def parse(cls, text: str) -> Entrant:
        name, _, rest = text.partition(":")
        return cls(name, tuple(x for x in rest.split("+") if x))

    def knobs(self, base: versions.Knobs) -> versions.Knobs:
        reader = {c.partition("=")[0] for c in self.changes} & READER_KNOBS
        if reader:
            raise ValueError(f"{self.name} changes {', '.join(sorted(reader))}: entrants share one reader, "
                             "so they can only change decision knobs")
        return override(base, self.changes)

    def __str__(self) -> str:
        return self.name + (":" + "+".join(self.changes) if self.changes else "")


def _shown(puzzle_answer: str, used) -> float:
    letters = [c for c in puzzle_answer if c in LETTERS]
    return sum(c in used for c in letters) / len(letters)


def play_one(game, entrants: Sequence[Entrant], puzzles: Sequence[Puzzle], bonus_puzzle: Puzzle, reader: Reader,
             rules: Rules, spec: WheelSpec, base: versions.Knobs, gains: bool = False) -> dict:
    """One bot-only game, summed up in one record. With `gains`, it also holds the stealer's gain points."""
    from rstlne.players.bot.player import BotPlayer
    from rstlne.runner import play_turn

    started = time.monotonic()
    seats = [entrants[e] for e in game.order]
    players = [BotPlayer(i, rules, spec, reader, version=1, knobs=e.knobs(base)) for i, e in enumerate(seats)]
    state = new_game(game.seed, rules, spec, puzzles, bonus_puzzle)
    stats = [{"attempts": 0, "right": 0, "shown": [], "bankrupts": 0, "certain_win": False, "certain_loss": False,
              "flat": 0, "llm_like": {}} for _ in seats]
    round_totals, moves, steps, chances = [], 0, [], []
    while state.phase is not Phase.GAME_OVER:
        before = state
        state = play_turn(state, players)
        moves += 1
        r = state.last
        if before.round is None:
            continue
        if gains:
            steps.append(Step(before.round.number, before.phase.value, r.seat, tuple(s.bank for s in before.seats),
                              _hidden(before.round.puzzle.answer, before.round.used), r.action.kind, r.outcome))
            raw = players[r.seat].last_call.raw if players[r.seat].last_call else {}
            if before.phase.value in _TURN_PHASES and r.action.kind in _TURN_KINDS and "confidence" in (raw or {}):
                # a chance to solve: the share showing, the deciding bot's confidence, and whether it solved correctly
                chances.append([round(_shown(before.round.puzzle.answer, before.round.used), 4),
                                round(raw["confidence"], 4), int(r.action.kind == "solve" and r.outcome == "solved")])
        seat = stats[r.seat]
        raw = players[r.seat].last_call.raw if players[r.seat].last_call else {}
        values = {round(v, 9) for v in (raw or {}).get("values", {}).values()}
        if len(values) == 1 and len(raw["values"]) > 1:  # every move scored the same: the bot saw the result settled
            seat["certain_win"] |= values == {1.0}
            seat["certain_loss"] |= values == {0.0}
        seat["flat"] += bool((raw or {}).get("flat"))
        if (raw or {}).get("llm_like"):  # version 4: how LLM-like it finds each opponent, kept as of its last decision
            seat["llm_like"] = raw["llm_like"]
        if r.action.kind == "solve":
            seat["attempts"] += 1
            if r.outcome == "solved":
                seat["right"] += 1
                seat["shown"].append(round(_shown(before.round.puzzle.answer, before.round.used), 4))
        if "bankrupt" in r.events or r.outcome in ("bankrupt", "flipped_bankrupt"):
            seat["bankrupts"] += 1
        if state.round is None or state.round.number != before.round.number:
            round_totals.append([s.total for s in state.seats])
    b = state.bonus
    return {
        "game": game.name, "set": game.set, "permutation": game.permutation, "seed": game.seed,
        "seats": [e.name for e in seats], "entrants": [str(e) for e in seats],
        "totals": [s.total for s in state.seats], "round_totals": round_totals,
        "bonus": None if b is None else {"seat": b.seat, "solved": b.solved, "envelope": b.envelope},
        "moves": moves, "seconds": round(time.monotonic() - started, 2), "seat_stats": stats,
        **({"gains": gain_points(steps), "chances": chances} if gains else {}),
    }


def _play_in_worker(job) -> dict:
    game, entrants, puzzles, bonus_puzzle, base, gains = job
    return play_one(game, entrants, puzzles, bonus_puzzle, _worker["reader"], _worker["rules"], _worker["spec"], base,
                    gains)


def play_games(entrants: Sequence[Entrant], pool: Sequence[Puzzle], sets: int, seed: int, out: Path, rules: Rules,
               spec: WheelSpec, base: versions.Knobs, make_reader, shard: tuple[int, int] = (1, 1), workers: int = 1,
               say=print, heartbeat: float = HEARTBEAT, gains: bool = False) -> Path:
    """Bot-only games with duplicate scoring: each set's six games share its seed and puzzles, one game per
    ordering of the three entrants. Writes games-shard{i}of{n}.jsonl and skips games already played."""
    from rstlne import tournament

    if len(entrants) != 3:
        raise ValueError("a game needs three entrants")
    i, n = shard
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"games-shard{i}of{n}.jsonl"
    done = {r["game"] for r in _rows(path)}
    main_hands = tournament.deal([p for p in pool if not p.bonus], rules.main_rounds, sets, seed, "main")
    bonus_hands = tournament.deal([p for p in pool if p.bonus], 1, sets, seed, "bonus")
    games = shard_of(tournament.schedule(sets, seed, "all"), i, n)
    todo = [g for g in games if g.name not in done]
    if done:
        say(f"{len(games) - len(todo)} games already played; playing the other {len(todo)}")
    names = ", ".join(str(e) for e in entrants)
    say(f"Playing {len(todo)} games ({sets} sets, shard {i}/{n}) between {names}; {workers} "
        f"worker{'s' if workers != 1 else ''}; a status line every 2 minutes")
    jobs = [(g, tuple(entrants), tuple(main_hands[g.set]), bonus_hands[g.set][0], base, gains) for g in todo]
    if workers > 1:
        pool_ = ProcessPoolExecutor(workers, initializer=_start_worker, initargs=(make_reader, base, rules, spec))
        results = pool_.map(_play_in_worker, jobs)
    else:
        pool_ = None
        _start_worker(make_reader, base, rules, spec)
        results = map(_play_in_worker, jobs)
    began = last = time.monotonic()
    wins: dict[str, float] = {e.name: 0.0 for e in entrants}
    try:
        with open(path, "a") as f:
            for k, record in enumerate(results, 1):
                f.write(json.dumps(record) + "\n")
                f.flush()
                for name, w in zip(record["seats"], tournament.split_wins(record["totals"])):
                    wins[name] += w
                now = time.monotonic()
                if now - last >= heartbeat:
                    last = now
                    tally = ", ".join(f"{name} {w:g}" for name, w in wins.items())
                    say(f"  {k} of {len(todo)} games · wins so far: {tally} · {duration(now - began)} elapsed, "
                        f"finish in about {duration((now - began) / k * (len(todo) - k))}")
    finally:
        if pool_:
            pool_.shutdown()
    say(f"Played {len(todo)} games in {duration(time.monotonic() - began)} into {path}")
    return path


def games_summary(out: Path, resamples: int = 2000) -> dict:
    """Every shard's games together: each entrant's win rate with 95% intervals from resampling whole sets,
    by seat, money, bonus, and solving; and the win rate gap between each pair."""
    from statistics import median

    from rstlne import tournament

    games = [g for path in sorted(Path(out).glob("games-shard*.jsonl")) for g in _rows(path)]
    names = sorted({name for g in games for name in g["seats"]})
    per_set: dict[int, dict[str, list[float]]] = {}
    acc = {name: {"games": 0, "wins": 0.0, "seat_games": [0, 0, 0], "seat_wins": [0.0, 0.0, 0.0], "total": 0,
                  "main": 0, "bonus_played": 0, "bonus_won": 0, "attempts": 0, "right": 0, "shown": [], "bankrupts": 0,
                  "certain_win": 0, "certain_win_lost": 0, "certain_loss": 0, "certain_loss_won": 0, "flat": 0,
                  "llm_like": {}}
           for name in names}
    for g in games:
        shares = tournament.split_wins(g["totals"])
        for seat, (name, w) in enumerate(zip(g["seats"], shares)):
            a = acc[name]
            a["games"] += 1
            a["wins"] += w
            a["seat_games"][seat] += 1
            a["seat_wins"][seat] += w
            a["total"] += g["totals"][seat]
            a["main"] += g["round_totals"][-1][seat] if g["round_totals"] else 0
            if g["bonus"] and g["bonus"]["seat"] == seat:
                a["bonus_played"] += 1
                a["bonus_won"] += bool(g["bonus"]["solved"])
            st = g["seat_stats"][seat]
            a["attempts"] += st["attempts"]
            a["right"] += st["right"]
            a["shown"] += st["shown"]
            a["bankrupts"] += st["bankrupts"]
            if st.get("certain_win"):
                a["certain_win"] += 1
                a["certain_win_lost"] += w == 0
            if st.get("certain_loss"):
                a["certain_loss"] += 1
                a["certain_loss_won"] += w > 0
            a["flat"] += st.get("flat", 0)
            for other, w in st.get("llm_like", {}).items():  # keyed by seat number
                a["llm_like"].setdefault(g["seats"][int(other) - 1], []).append(w)
            per_set.setdefault(g["set"], {}).setdefault(name, []).append(w)
    rows = list(per_set.values())

    def rate(name):
        return lambda sample: (sum(sum(r.get(name, [])) for r in sample) / n if (n := sum(len(r.get(name, [])) for r in sample)) else None)

    entrants = []
    for name in names:
        a = acc[name]
        ci = tournament.bootstrap(rows, rate(name), resamples=resamples) if rows else None
        entrants.append({
            "entrant": name, "games": a["games"], "wins": a["wins"], "win_rate": a["wins"] / a["games"],
            "ci95": list(ci) if ci else None,
            "by_seat": [w / g if g else None for w, g in zip(a["seat_wins"], a["seat_games"])],
            "avg_total": a["total"] / a["games"], "avg_main": a["main"] / a["games"],
            "bonus": f"{a['bonus_won']}/{a['bonus_played']}",
            "solve_accuracy": a["right"] / a["attempts"] if a["attempts"] else None,
            "shown_median": median(a["shown"]) if a["shown"] else None,
            "bankrupts_per_game": a["bankrupts"] / a["games"],
            "certain_win": a["certain_win"], "certain_win_lost": a["certain_win_lost"],
            "certain_loss": a["certain_loss"], "certain_loss_won": a["certain_loss_won"],
            "flat_per_game": a["flat"] / a["games"],
            "llm_like": {other: sum(ws) / len(ws) for other, ws in sorted(a["llm_like"].items())},  # average w at game end
        })
    pairwise = []
    for x in range(len(names)):
        for y in range(x + 1, len(names)):
            a, b = names[x], names[y]
            gap = lambda sample, a=a, b=b: (None if (ra := rate(a)(sample)) is None or (rb := rate(b)(sample)) is None else ra - rb)
            ci = tournament.bootstrap(rows, gap, resamples=resamples) if rows else None
            pairwise.append({"a": a, "b": b, "gap": gap(rows), "ci95": list(ci) if ci else None})
    return {"games": len(games), "sets": len(rows), "entrants": entrants, "pairwise": pairwise}


def summary_lines(summary: dict) -> list[str]:
    lines = [f"{summary['games']} games in {summary['sets']} sets"]
    for e in summary["entrants"]:
        ci = f" [{e['ci95'][0]:.0%}-{e['ci95'][1]:.0%}]" if e["ci95"] else ""
        seats = "/".join("-" if x is None else f"{x:.0%}" for x in e["by_seat"])
        acc = "-" if e["solve_accuracy"] is None else f"{e['solve_accuracy']:.0%}"
        shown = "-" if e["shown_median"] is None else f"{e['shown_median']:.0%}"
        lines.append(f"  {e['entrant']:12s} wins {e['win_rate']:.0%}{ci} by seat {seats} · main ${e['avg_main']:,.0f} "
                     f"· bonus {e['bonus']} · solves {acc} right at {shown} shown · {e['bankrupts_per_game']:.2f} Bankrupts a game")
        if e.get("certain_win") or e.get("certain_loss") or e.get("flat_per_game"):
            lines.append(f"  {'':12s} sure it had won in {e['certain_win']} games, lost {e['certain_win_lost']} · "
                         f"sure it had lost in {e['certain_loss']}, won {e['certain_loss_won']} · "
                         f"{e['flat_per_game']:.2f} choices a game went to dollars")
        if e.get("llm_like"):
            found = ", ".join(f"{other} {w:.2f}" for other, w in e["llm_like"].items())
            lines.append(f"  {'':12s} its chance each opponent plays like an LLM, at game end: {found}")
    for p in summary["pairwise"]:
        ci = f" [{p['ci95'][0]:+.0%} to {p['ci95'][1]:+.0%}]" if p["ci95"] else ""
        lines.append(f"  {p['a']} minus {p['b']}: {p['gap']:+.0%}{ci}")
    return lines


# Tuning decisions

DECISION_GRID = {
    "known_answer": [0.9, 0.98],
    "safe_hit": [0.97, 0.995],
    "tie_margin": [0.002, 0.01],
    "wild_bonus_lift": [0.05, 0.2],
    "bonus_solve": [0.3, 0.7],
}
EAGER = "eager_solve=0.65"  # the LLM-like opponent: the median LLM solve attempt came at this confidence


def grid_for(names: str | None) -> dict:
    """The decision grid, or just the named knobs from it, comma separated."""
    if not names:
        return DECISION_GRID
    wanted = [n.strip() for n in names.split(",") if n.strip()]
    unknown = [n for n in wanted if n not in DECISION_GRID]
    if unknown:
        raise ValueError(f"not a tuned decision knob: {', '.join(unknown)}. Tuned: {', '.join(DECISION_GRID)}")
    return {n: DECISION_GRID[n] for n in wanted}


def pick(results: Sequence[dict]):
    """The value that beat the current one by the most, among those whose 95% interval is clear of zero."""
    clear = [r for r in results if r["ci95"] and r["ci95"][0] > 0]
    return max(clear, key=lambda r: r["gap"])["value"] if clear else None


def tune_decisions(pool: Sequence[Puzzle], out: Path, rules: Rules, spec: WheelSpec, base: versions.Knobs, make_reader,
                   sets: int = 125, seed: int = 404, grid: dict | None = None, workers: int = 1,
                   say=print) -> tuple[str, ...]:
    """One knob at a time: each candidate value plays as `variant` against `current` and `eager` in the same
    games, all comparisons on the same seed. Returns the adopted changes, also saved in tune-decisions.json."""
    grid = DECISION_GRID if grid is None else grid
    out.mkdir(parents=True, exist_ok=True)
    began = time.monotonic()
    changes: list[str] = []
    comparisons = []
    total = sum(len(v) for v in grid.values())
    k = 0
    for knob, values in grid.items():
        results = []
        for value in values:
            k += 1
            current = Entrant("current", tuple(changes))
            variant = Entrant("variant", tuple(c for c in changes if not c.startswith(f"{knob}=")) + (f"{knob}={value}",))
            eager = Entrant("eager", tuple(changes) + (EAGER,))
            folder = out / f"{knob}={value}"
            say(f"Comparison {k} of {total}: {knob} = {value} (now {getattr(current.knobs(base), knob)}) · "
                f"{duration(time.monotonic() - began)} elapsed so far")
            play_games([variant, current, eager], pool, sets, seed, folder, rules, spec, base, make_reader,
                       workers=workers, say=say)
            summary = games_summary(folder)
            gap = next(p for p in summary["pairwise"] if {p["a"], p["b"]} == {"current", "variant"})
            sign = 1 if gap["a"] == "variant" else -1
            ci = sorted(sign * x + 0.0 for x in gap["ci95"]) if gap["ci95"] else None  # + 0.0 turns -0.0 into 0.0
            result = {"knob": knob, "value": value, "gap": sign * gap["gap"] + 0.0, "ci95": ci, "games": summary["games"]}
            results.append(result)
            comparisons.append(result)
            span = f" [{ci[0]:+.1%} to {ci[1]:+.1%}]" if ci else ""
            say(f"  variant minus current: {result['gap']:+.1%}{span} in win rate over {summary['games']} games")
        best = pick(results)
        if best is not None:
            changes = [c for c in changes if not c.startswith(f"{knob}=")] + [f"{knob}={best}"]
            say(f"  {knob}: adopt {best}")
        else:
            say(f"  {knob}: keep {getattr(Entrant('current', tuple(changes)).knobs(base), knob)}")
    result = {"changes": changes, "comparisons": comparisons, "sets": sets, "seed": seed,
              "base": _knob_dict(base), "hours": round((time.monotonic() - began) / 3600, 2)}
    (out / "tune-decisions.json").write_text(json.dumps(result, indent=2) + "\n")
    say(f"Decision tuning done in {duration(time.monotonic() - began)}: {', '.join(changes) or 'no change'}")
    return tuple(changes)


# The win-chance table


def _increasing(means: Sequence[float], weights: Sequence[float]) -> list[float]:
    """Weighted pooling of adjacent violators: the closest never-decreasing sequence."""
    blocks: list[list[float]] = []  # [weighted sum, weight, count of entries]
    for m, w in zip(means, weights):
        blocks.append([m * w, w, 1])
        while len(blocks) > 1 and blocks[-2][0] / blocks[-2][1] > blocks[-1][0] / blocks[-1][1]:
            s, w2, c = blocks.pop()
            blocks[-1][0] += s
            blocks[-1][1] += w2
            blocks[-1][2] += c
    out = []
    for s, w, c in blocks:
        out += [s / w] * int(c)
    return out


def build_win_table(games: Sequence[dict], main_rounds: int, band: int = 1000, cap: int = 30_000,
                    minimum: int = 20) -> tuple:
    """P(finish first after the main rounds | lead over the best opponent, rounds left), from every seat at
    every round boundary of every game. Ties for first are shared. Leads group into bands; bands with fewer
    than `minimum` records are dropped; the chance is made to rise with the lead."""
    from rstlne import tournament

    groups: dict[int, dict[int, list[float]]] = {}
    for g in games:
        rounds = g["round_totals"]
        if len(rounds) != main_rounds:
            continue
        shares = tournament.split_wins(rounds[-1])
        for k in range(main_rounds):
            totals = [0, 0, 0] if k == 0 else rounds[k - 1]
            left = main_rounds - k
            for seat in range(3):
                lead = totals[seat] - max(t for i, t in enumerate(totals) if i != seat)
                b = max(-cap, min(cap, round(lead / band) * band))
                groups.setdefault(left, {}).setdefault(b, []).append(shares[seat])
    table = []
    for left in sorted(groups):
        bands = sorted((b, v) for b, v in groups[left].items() if len(v) >= minimum)
        if not bands:
            continue
        means = _increasing([sum(v) / len(v) for _, v in bands], [len(v) for _, v in bands])
        table.append((left, tuple((float(b), round(m, 4)) for (b, _), m in zip(bands, means))))
    return tuple(table)


def win_table(folders: Sequence[Path], out: Path, main_rounds: int, say=print) -> tuple:
    """Build the win-chance table from games folders and save it as win-table.json, ready for --knob win_table=@."""
    from rstlne.players.bot.objective import win_chance

    games = [g for folder in folders for path in sorted(Path(folder).glob("games-shard*.jsonl")) for g in _rows(path)]
    table = build_win_table(games, main_rounds)
    out.mkdir(parents=True, exist_ok=True)
    result = {"games": len(games), "main_rounds": main_rounds, "knob": [[r, [list(p) for p in pts]] for r, pts in table]}
    (out / "win-table.json").write_text(json.dumps(result, indent=2) + "\n")
    say(f"Win-chance table from {len(games)} games, saved to {out / 'win-table.json'}")
    for left, points in table:
        row = ", ".join(f"{lead:+,.0f} {win_chance(table, left, lead):.0%}" for lead in (-10000, -5000, -2000, 0, 2000, 5000, 10000))
        say(f"  {left} round{'s' if left != 1 else ''} left: {row}")
    return table


# The stealer's gain

GAIN_ROUNDS = (1, 4)  # rounds 1 to 3, and round 4 on, whose wedges are bigger
GAIN_BANDS = (0, 3, 6, 10, 15)  # hidden letter squares where each band starts
GAIN_MIN_POINTS = 200  # a band with fewer merges into its neighbor with fewer hidden squares
GAIN_SOURCE_MIN = 50  # LLM and bot opponents weigh half and half only where each has this many points
GAIN_QUANTILES = tuple((k + 0.5) / 20 for k in range(20))  # the midpoints of the twentieths


class Step(NamedTuple):
    """One move in a main round, as the stealer's gain sees it."""

    round: int
    phase: str
    seat: int
    banks: tuple[int, ...]  # before the move
    hidden: int  # letter squares still hidden before the move
    kind: str
    outcome: str


def _hidden(answer: str, used) -> int:
    return sum(c in LETTERS and c not in used for c in answer)


def log_steps(rows: Sequence[dict]) -> list[Step]:
    """A tournament game log's main round moves."""
    steps = []
    for r in rows:
        state = r.get("state") or {}
        if r.get("type") != "action" or not state.get("round"):
            continue
        rnd = state["round"]
        steps.append(Step(rnd["number"], state["phase"], r["seat"], tuple(s["bank"] for s in state["seats"]),
                          _hidden(rnd["puzzle"]["answer"], set(rnd["used"])), r["action"]["kind"],
                          r["result"]["outcome"]))
    return steps


def gain_points(steps: Sequence[Step]) -> list[tuple[int, int, float]]:
    """(round, hidden squares, gain) for every turn decision of a seat that didn't solve, in each round that ended
    in a correct solve: the gain is the solver's bank when it solved minus its bank at that decision."""
    points = []
    rounds: dict[int, list[Step]] = {}
    for s in steps:
        rounds.setdefault(s.round, []).append(s)
    for number, moves in rounds.items():
        end = next((s for s in moves if s.kind == "solve" and s.outcome == "solved"), None)
        if end is None:
            continue
        solver, final = end.seat, end.banks[end.seat]
        points += [(number, s.hidden, float(final - s.banks[solver]))
                   for s in moves if s.phase == Phase.TURN.value and s.seat != solver]
    return points


def check_fit_puzzles(name: str) -> None:
    """The gain is fit on tuning puzzles only: never grading, dev, or private puzzles."""
    name = Path(name).name
    if name.startswith("grading") or name in ("dev.json", "private.json"):
        raise ValueError(f"{name} is a grading, dev, or private puzzle file; the stealer's gain never fits on those")


def tournament_gain_points(folders: Sequence[Path]) -> list[tuple[int, int, float]]:
    """Gain points from finished tournament games, after checking which puzzles each tournament played."""
    points = []
    for folder in folders:
        report = Path(folder) / "report.json"
        if not report.exists():
            raise ValueError(f"{folder} has no report.json, so it can't say which puzzles it played")
        check_fit_puzzles(json.loads(report.read_text())["puzzles"])
        for path in sorted(Path(folder).glob("set*.jsonl")):
            rows = _rows(path)
            if rows and rows[-1].get("type") == "summary":
                points += gain_points(log_steps(rows))
    return points


def games_gain_points(folders: Sequence[Path]) -> list[tuple[int, int, float]]:
    """Gain points from round-banks folders, after checking which puzzles they played."""
    points = []
    for folder in folders:
        meta = Path(folder) / "round-banks.json"
        if not meta.exists():
            raise ValueError(f"{folder} has no round-banks.json; make it with selfplay round-banks")
        check_fit_puzzles(json.loads(meta.read_text())["puzzles"])
        for path in sorted(Path(folder).glob("games-shard*.jsonl")):
            points += [tuple(p) for g in _rows(path) for p in g.get("gains", [])]
    return points


def _weighted(sources: Sequence[Sequence[float]]) -> tuple[np.ndarray, np.ndarray]:
    """Values and weights: each source carries an equal share where every one has GAIN_SOURCE_MIN points,
    and every point counts the same where one doesn't, so a handful of points can't set half the spread."""
    present = [s for s in sources if s]
    values = np.array([v for s in present for v in s], dtype=float)
    if all(len(s) >= GAIN_SOURCE_MIN for s in present):
        weights = np.array([1 / (len(present) * len(s)) for s in present for _ in s])
    else:
        weights = np.full(len(values), 1 / len(values))
    order = np.argsort(values, kind="stable")
    return values[order], weights[order]


def _quantile(values: np.ndarray, weights: np.ndarray, q: float) -> float:
    cumulative = np.cumsum(weights)
    return float(values[min(np.searchsorted(cumulative, q - 1e-12), len(values) - 1)])


def fit_stealer_gain(llm: Sequence[tuple], bot: Sequence[tuple]) -> tuple[tuple, list[dict]]:
    """The stealer_gain knob and a report: per group of rounds and band of hidden squares, the 20 gains at the
    midpoints of the twentieths, with LLM and bot opponents weighted half and half where both are present."""
    table, report = [], []
    for g, start in enumerate(GAIN_ROUNDS):
        end = GAIN_ROUNDS[g + 1] if g + 1 < len(GAIN_ROUNDS) else None
        inside = lambda p: p[0] >= start and (end is None or p[0] < end)
        bands = []
        for b, low in enumerate(GAIN_BANDS):
            high = GAIN_BANDS[b + 1] if b + 1 < len(GAIN_BANDS) else None
            fits = lambda p: inside(p) and p[1] >= low and (high is None or p[1] < high)
            bands.append([low, [p[2] for p in llm if fits(p)], [p[2] for p in bot if fits(p)]])
        if not any(lo or bo for _, lo, bo in bands):
            continue
        while len(bands) > 1:
            sparse = next((i for i, (_, lo, bo) in enumerate(bands) if len(lo) + len(bo) < GAIN_MIN_POINTS), None)
            if sparse is None:
                break
            a, b = (sparse - 1, sparse) if sparse > 0 else (0, 1)
            bands[a:b + 1] = [[bands[a][0], bands[a][1] + bands[b][1], bands[a][2] + bands[b][2]]]
        rows = []
        for low, lo, bo in bands:
            values, weights = _weighted([lo, bo])
            gains = tuple(float(round(_quantile(values, weights, q))) for q in GAIN_QUANTILES)
            rows.append((low, gains))
            spread = lambda s: {"points": len(s), "median": float(np.median(s)) if s else None,
                                "p90": float(np.percentile(s, 90)) if s else None}
            report.append({"from_round": start, "from_hidden": low, "llm": spread(lo), "bot": spread(bo),
                           "gains": list(gains)})
        table.append((start, tuple(rows)))
    return tuple(table), report


def stealer_gain(logs: Sequence[Path], games: Sequence[Path], out: Path, say=print) -> tuple:
    """Fit the stealer's gain from LLM tournaments and round-banks self-play, and save it under `out`."""
    llm, bot = tournament_gain_points(logs), games_gain_points(games)
    if not llm and not bot:
        raise ValueError("no gain points: pass tournament folders with --logs, round-banks folders with --games, or both")
    table, report = fit_stealer_gain(llm, bot)
    out.mkdir(parents=True, exist_ok=True)
    (out / "stealer-gain.json").write_text(json.dumps(
        {"knob": table, "report": report, "logs": [str(f) for f in logs], "games": [str(f) for f in games]}, indent=1))
    say(f"Fit the stealer's gain from {len(llm)} LLM-opponent points and {len(bot)} bot-opponent points "
        f"into {out / 'stealer-gain.json'}")
    for r in report:
        side = lambda s: "-" if s["points"] == 0 else f"{s['points']} pts, median ${s['median']:,.0f}, p90 ${s['p90']:,.0f}"
        say(f"  rounds {r['from_round']}+, {r['from_hidden']}+ hidden: LLM {side(r['llm'])} · bot {side(r['bot'])}")
        say("    gains: " + ", ".join(f"${g:,.0f}" for g in r["gains"]))
    return table


def fit_steal_bot(games: Sequence[Path], resamples: int = 1000) -> dict:
    """Version 4's bot solve curve: steal_prior's logistic form, fit on round-banks games' chances to solve."""
    points = []
    for folder in games:
        meta = Path(folder) / "round-banks.json"
        if not meta.exists():
            raise ValueError(f"{folder} has no round-banks.json; make it with selfplay round-banks")
        check_fit_puzzles(json.loads(meta.read_text())["puzzles"])
        for path in sorted(Path(folder).glob("games-shard*.jsonl")):
            for g in _rows(path):
                points += [{"shown": s, "confidence": c, "solved": k, "set": f"{folder}:{g.get('set', 0)}"}
                           for s, c, k in g.get("chances", [])]
    if not points:
        raise ValueError("no chances to solve in these folders; rerun round-banks with this version's code")
    return {**fit_steal(points, resamples), "points": len(points)}


def v4_fit(logs: Sequence[Path], games: Sequence[Path], out: Path, resamples: int = 1000, say=print) -> None:
    """Version 4's three knobs: the stealer's gain from LLM and from bot opponents apart, and the bot solve curve."""
    llm, bot = tournament_gain_points(logs), games_gain_points(games)
    out.mkdir(parents=True, exist_ok=True)
    for name, points in (("llm", llm), ("bot", bot)):
        table, report = fit_stealer_gain(points, []) if name == "llm" else fit_stealer_gain([], points)
        (out / f"stealer-gain-{name}.json").write_text(json.dumps({"knob": table, "report": report}, indent=1))
        say(f"stealer_gain_{name}: {len(points)} points into {out / f'stealer-gain-{name}.json'}")
    fit = fit_steal_bot(games, resamples)
    (out / "steal-bot.json").write_text(json.dumps({"knob": [fit["a"], fit["b"], fit["c"]], "fit": fit}, indent=1))
    say(f"steal_bot: a {fit['a']:.2f}, b {fit['b']:.2f}, c {fit['c']:.2f} from {fit['points']} chances, "
        f"into {out / 'steal-bot.json'}")


def round_banks(puzzles_path: Path, sets: int, seed: int, out: Path, rules: Rules, spec: WheelSpec,
                base: versions.Knobs, make_reader, shard: tuple[int, int] = (1, 1), workers: int = 1,
                say=print) -> Path:
    """Bot games on tuning puzzles that record the stealer's gain points, for `stealer-gain`."""
    check_fit_puzzles(puzzles_path.name)
    out.mkdir(parents=True, exist_ok=True)
    (out / "round-banks.json").write_text(json.dumps({"puzzles": str(puzzles_path)}))
    entrants = [Entrant(name) for name in ("a", "b", "c")]
    return play_games(entrants, settings.load_puzzles(puzzles_path), sets, seed, out, rules, spec, base, make_reader,
                      shard, workers, say=say, gains=True)


# Knobs


def _tuples(value):
    return tuple(_tuples(v) for v in value) if isinstance(value, list) else value


def override(knobs: versions.Knobs, pairs: Sequence[str]) -> versions.Knobs:
    """`name=value` overrides, each value read as its knob's type. An overridden bot is an experiment."""
    types = {f.name: type(getattr(knobs, f.name)) for f in fields(knobs)}
    changes = {}
    for pair in pairs:
        name, _, value = pair.partition("=")
        if name not in types:
            raise ValueError(f"no knob named {name!r}")
        if value.startswith("@"):  # a big knob, like a table, from a file: its "knob" entry
            data = json.loads(Path(value[1:]).read_text())
            changes[name] = _tuples(data["knob"] if isinstance(data, dict) else data)
            continue
        kind = types[name]
        if kind is bool:
            if value.lower() not in ("true", "false", "1", "0"):
                raise ValueError(f"{name} is true or false, not {value!r}")
            changes[name] = value.lower() in ("true", "1")
            continue
        if kind is type(None):  # a knob that is off by default takes a number
            kind = float
        if name == "calibration":  # points as raw:actual pairs
            changes[name] = tuple(tuple(float(v) for v in pair.split(":")) for pair in value.split(","))
        else:
            changes[name] = tuple(float(x) for x in value.split(",")) if kind is tuple else kind(value)
    return replace(knobs, **changes)


# Command line


def _make_reader(knobs: versions.Knobs) -> Reader:
    from rstlne.players.bot.player import make_reader

    return make_reader(knobs)


def main(argv: Sequence[str] | None = None) -> None:
    line_output()
    parser = argparse.ArgumentParser(prog="python -m rstlne.selfplay", description="Bot self-play and tuning.")
    jobs = parser.add_subparsers(dest="job", required=True)
    reads = jobs.add_parser("reads", help="reveal puzzles step by step and record what the reader makes of each board")
    reads.add_argument("--puzzles", required=True, help="a puzzle or batch file")
    reads.add_argument("--out", required=True, help="the folder for reads-shard*.jsonl")
    reads.add_argument("--shard", default="1/1", help="i/n: this machine's share of the puzzles")
    reads.add_argument("--workers", type=int, default=4, help="processes, one per core")
    reads.add_argument("--knob", action="append", default=[], help="name=value, to read with other knobs")
    tune = jobs.add_parser("tune-reader", help="tune the reader's knobs on board reads, then check them on held out puzzles")
    tune.add_argument("--puzzles", required=True, help="the tuning batch")
    tune.add_argument("--held-out", required=True, help="the grading batch, never tuned on")
    tune.add_argument("--out", required=True, help="the folder for evaluations.jsonl and reader-tune.json")
    tune.add_argument("--workers", type=int, default=4, help="processes, one per core")
    tune.add_argument("--passes", type=int, default=2)
    tune.add_argument("--knob", action="append", default=[], help="name=value, to start from other knobs")
    games = jobs.add_parser("games", help="bot-only games between bot variants, with duplicate scoring")
    games.add_argument("--entrant", action="append", required=True,
                       help="three of them: name or name:knob=value+knob=value, like eager:eager_solve=0.65")
    games.add_argument("--puzzles", required=True, help="a puzzle or batch file")
    games.add_argument("--sets", type=int, required=True, help="each set is 6 games, one per seat ordering")
    games.add_argument("--seed", type=int, required=True)
    games.add_argument("--out", required=True, help="the folder for games-shard*.jsonl")
    games.add_argument("--shard", default="1/1", help="i/n: this machine's share of the games")
    games.add_argument("--workers", type=int, default=4, help="processes, one per core")
    games.add_argument("--knob", action="append", default=[], help="name=value, for every entrant's starting knobs")
    td = jobs.add_parser("tune-decisions", help="test decision knob values against the current bot in bot games")
    td.add_argument("--puzzles", required=True, help="the tuning batch")
    td.add_argument("--out", required=True, help="the folder for each comparison and tune-decisions.json")
    td.add_argument("--sets", type=int, default=125, help="sets per comparison, 6 games each")
    td.add_argument("--seed", type=int, default=404)
    td.add_argument("--workers", type=int, default=4, help="processes, one per core")
    td.add_argument("--knob", action="append", default=[], help="name=value or name=@file, for the starting knobs")
    td.add_argument("--knobs", help="only these decision knobs, comma separated; all of them by default")
    wt = jobs.add_parser("win-table", help="P(finish first | lead, rounds left) from bot games")
    wt.add_argument("--games", nargs="+", required=True, help="games folders")
    wt.add_argument("--out", required=True, help="the folder for win-table.json")
    gsum = jobs.add_parser("games-summary", help="win rates with intervals across every shard of a games folder")
    gsum.add_argument("folder")
    cal = jobs.add_parser("calibrate", help="fit the confidence curve on tuning reads, then check it on held out ones")
    cal.add_argument("--puzzles", required=True, help="the tuning batch")
    cal.add_argument("--held-out", required=True, help="the grading batch, never fit on")
    cal.add_argument("--out", required=True, help="the folder for calibration.json")
    cal.add_argument("--workers", type=int, default=4, help="processes, one per core")
    cal.add_argument("--knob", action="append", default=[], help="name=value, to read with other knobs")
    fit = jobs.add_parser("steal", help="fit the steal curve from tournament logs")
    fit.add_argument("--logs", nargs="+", required=True, help="tournament folders")
    fit.add_argument("--out", required=True, help="the folder for steal-fit.json and steal-points.jsonl")
    fit.add_argument("--workers", type=int, default=4, help="processes, one per core")
    fit.add_argument("--resamples", type=int, default=1000, help="for the 95%% intervals")
    fit.add_argument("--knob", action="append", default=[], help="name=value, to read with other knobs")
    rb = jobs.add_parser("round-banks", help="bot games on tuning puzzles that record the stealer's gain points")
    rb.add_argument("--puzzles", required=True, help="the tuning batch; grading, dev, and private files are refused")
    rb.add_argument("--sets", type=int, required=True, help="each set is 6 games, one per seat ordering")
    rb.add_argument("--seed", type=int, required=True)
    rb.add_argument("--out", required=True, help="the folder for games-shard*.jsonl and round-banks.json")
    rb.add_argument("--shard", default="1/1", help="i/n: this machine's share of the games")
    rb.add_argument("--workers", type=int, default=4, help="processes, one per core")
    v4 = jobs.add_parser("v4-fit", help="version 4's knobs: the stealer's gain by opponent kind, and the bot solve curve")
    v4.add_argument("--logs", nargs="+", required=True, help="tournament folders: LLM opponents")
    v4.add_argument("--games", nargs="+", required=True, help="round-banks folders: bot opponents, with chances to solve")
    v4.add_argument("--out", required=True, help="the folder for the three knob files")
    v4.add_argument("--resamples", type=int, default=1000, help="for the steal curve's 95%% intervals")
    sg = jobs.add_parser("stealer-gain", help="fit what an opponent adds to its bank before it solves")
    sg.add_argument("--logs", nargs="*", default=[], help="tournament folders: LLM opponents")
    sg.add_argument("--games", nargs="*", default=[], help="round-banks folders: bot opponents")
    sg.add_argument("--out", required=True, help="the folder for stealer-gain.json")
    summary = jobs.add_parser("summary", help="accuracy by confidence across every shard of a reads folder")
    summary.add_argument("folder")
    args = parser.parse_args(argv)

    if args.job == "summary":
        print(json.dumps(summarize_reads(Path(args.folder)), indent=2))
        return
    if args.job == "win-table":
        win_table([Path(f) for f in args.games], Path(args.out), settings.load_rules().main_rounds, say=print)
        return
    if args.job == "v4-fit":
        try:
            v4_fit([Path(f) for f in args.logs], [Path(f) for f in args.games], Path(args.out), args.resamples, say=print)
        except ValueError as err:
            sys.exit(str(err))
        return
    if args.job == "stealer-gain":
        try:
            stealer_gain([Path(f) for f in args.logs], [Path(f) for f in args.games], Path(args.out), say=print)
        except ValueError as err:
            sys.exit(str(err))
        return
    if args.job == "games-summary":
        for line in summary_lines(games_summary(Path(args.folder))):
            print(line)
        return
    rules, spec = settings.load_rules(), settings.load_wheel()
    config = settings.load_config()
    knobs = override(versions.knobs(versions.current(config)), getattr(args, "knob", []))
    if args.job == "tune-decisions":
        try:
            grid = grid_for(args.knobs)
        except ValueError as err:
            sys.exit(str(err))
        tune_decisions(settings.load_puzzles(Path(args.puzzles)), Path(args.out), rules, spec, knobs, _make_reader,
                       args.sets, args.seed, grid=grid, workers=args.workers, say=print)
        return
    if args.job == "games":
        try:
            shard_spec = parse_shard(args.shard)
            entrants = [Entrant.parse(t) for t in args.entrant]
            for e in entrants:
                e.knobs(knobs)
        except ValueError as err:
            sys.exit(str(err))
        path = play_games(entrants, settings.load_puzzles(Path(args.puzzles)), args.sets, args.seed, Path(args.out),
                          rules, spec, knobs, _make_reader, shard_spec, args.workers, say=print)
        for line in summary_lines(games_summary(path.parent)):
            print(line)
        return
    if args.job == "round-banks":
        try:
            path = round_banks(Path(args.puzzles), args.sets, args.seed, Path(args.out), rules, spec, knobs,
                               _make_reader, parse_shard(args.shard), args.workers, say=print)
        except ValueError as err:
            sys.exit(str(err))
        print(f"{sum(len(g.get('gains', [])) for g in _rows(path))} gain points in {path}")
        return
    if args.job == "calibrate":
        calibrate(settings.load_puzzles(Path(args.puzzles)), settings.load_puzzles(Path(args.held_out)), Path(args.out),
                  rules, spec, knobs, _make_reader, args.workers, say=print)
        return
    if args.job == "tune-reader":
        tune_reader(settings.load_puzzles(Path(args.puzzles)), settings.load_puzzles(Path(args.held_out)), Path(args.out),
                    rules, spec, knobs, _make_reader, passes=args.passes, workers=args.workers, say=print)
        return
    if args.job == "steal":
        steal([Path(f) for f in args.logs], Path(args.out), rules, spec, knobs, _make_reader, args.workers,
              args.resamples, say=print)
        return
    try:
        shard_spec = parse_shard(args.shard)
    except ValueError as err:
        sys.exit(str(err))
    path = read_all(settings.load_puzzles(Path(args.puzzles)), Path(args.out), rules, spec, knobs, _make_reader,
                    shard_spec, args.workers, say=lambda line: print(line, flush=True))
    summary = summarize_reads(path.parent)
    print(f"All shards so far: {summary['boards']} boards from {summary['puzzles']} puzzles, "
          f"accuracy {summary['accuracy']:.0%}, mean probability on the true answer {summary['mean_p_true']:.2f}")


if __name__ == "__main__":
    main()
