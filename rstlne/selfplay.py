"""Self-play and tuning for the bot, built to run for hours on a server.

    python -m rstlne.selfplay reads --puzzles puzzles/generated/tuning-101.json --out logs/selfplay/reads --shard 1/1

Every job splits into shards (`--shard i/n`) so several machines can share it, writes compact JSONL,
resumes where it stopped, and prints a status line every 2 minutes with an estimated finish.
No job calls an API: the bot reads boards and plays games on its own.

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
from pathlib import Path

from rstlne import settings
from rstlne.engine.puzzle import LETTERS, Puzzle
from rstlne.engine.rules import new_game, public_view
from rstlne.engine.state import Phase, PublicView, Rules
from rstlne.engine.wheel import WheelSpec
from rstlne.narrate import duration
from rstlne.players.bot import bonus, versions
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


# Knobs


def override(knobs: versions.Knobs, pairs: Sequence[str]) -> versions.Knobs:
    """`name=value` overrides, each value read as its knob's type. An overridden bot is an experiment."""
    types = {f.name: type(getattr(knobs, f.name)) for f in fields(knobs)}
    changes = {}
    for pair in pairs:
        name, _, value = pair.partition("=")
        if name not in types:
            raise ValueError(f"no knob named {name!r}")
        kind = types[name]
        changes[name] = tuple(float(x) for x in value.split(",")) if kind is tuple else kind(value)
    return replace(knobs, **changes)


# Command line


def _make_reader(knobs: versions.Knobs) -> Reader:
    from rstlne.players.bot.player import make_reader

    return make_reader(knobs)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m rstlne.selfplay", description="Bot self-play and tuning.")
    jobs = parser.add_subparsers(dest="job", required=True)
    reads = jobs.add_parser("reads", help="reveal puzzles step by step and record what the reader makes of each board")
    reads.add_argument("--puzzles", required=True, help="a puzzle or batch file")
    reads.add_argument("--out", required=True, help="the folder for reads-shard*.jsonl")
    reads.add_argument("--shard", default="1/1", help="i/n: this machine's share of the puzzles")
    reads.add_argument("--workers", type=int, default=4, help="processes, one per core")
    reads.add_argument("--knob", action="append", default=[], help="name=value, to read with other knobs")
    summary = jobs.add_parser("summary", help="accuracy by confidence across every shard of a reads folder")
    summary.add_argument("folder")
    args = parser.parse_args(argv)

    if args.job == "summary":
        print(json.dumps(summarize_reads(Path(args.folder)), indent=2))
        return
    rules, spec = settings.load_rules(), settings.load_wheel()
    config = settings.load_config()
    knobs = override(versions.knobs(versions.current(config)), args.knob)
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
