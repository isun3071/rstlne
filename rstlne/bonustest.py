"""The bonus round alone: every player meets every bonus puzzle in a file, with no wheel and no opponents.

    python -m rstlne.bonustest --players llm:<slug>,llm:<slug>,bot --puzzles puzzles/private.json --seed 707
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import Counter
from collections.abc import Callable, Sequence
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from itertools import combinations
from pathlib import Path

from rstlne import settings
from rstlne.cli import build_players, clients, parse_seat
from rstlne.engine import bonus
from rstlne.engine.puzzle import LETTERS, Puzzle
from rstlne.engine.state import GameState, Phase, Result, Rules, SeatState
from rstlne.engine.wheel import WheelSpec
from rstlne.llm.openrouter import OpenRouter
from rstlne.narrate import line_output
from rstlne.players.base import Player
from rstlne.runner import MISFIT, GameLog, play_game
from rstlne.tournament import _cost, _finished, bootstrap, set_seed

PARALLEL = 10


class Absent(Player):
    """The two empty seats beside the player. They never act."""

    def describe(self) -> dict:
        return {"kind": "absent"}


def bonus_game(seed: int, rules: Rules, spec: WheelSpec, puzzle: Puzzle) -> GameState:
    """A game that opens at the bonus picks, seat 1 playing, holding no cards."""
    state = GameState(
        seed=seed, rules=rules, wheel=spec, puzzles=(), bonus_puzzle=puzzle,
        seats=(SeatState(),) * 3, phase=Phase.TURN, seat=0, last=Result(0, None, "bonus_test"),
    )
    return bonus.start(state, seat=0)


def safe(entrant: str) -> str:
    """An entrant as a folder name."""
    return entrant.replace("/", "_").replace(":", "-")


def folder_name(seed: int, puzzles_path: Path, config: dict) -> str:
    """Covers the settings that change play, but not the players, so a later run can add one."""
    play = {key: config.get(key) for key in ("providers", "llm", "decision", "hybrid")} | {
        "bot_version": config.get("bot", {}).get("version"),
    }
    key = json.dumps([seed, Path(puzzles_path).name, play], sort_keys=True)
    return f"{Path(puzzles_path).stem}-seed{seed}-{hashlib.sha256(key.encode()).hexdigest()[:8]}"


def run_bonus_test(
    entrants: Sequence[str],
    puzzles_path: Path,
    seed: int,
    out_dir: Path,
    parallel: int = PARALLEL,
    max_cost: float | None = None,
    client: OpenRouter | None = None,
    limit: int | None = None,
    write: Callable[[str], None] = print,
) -> dict:
    out_dir = Path(out_dir)
    seats = [parse_seat(e) for e in entrants]
    if any(kind == "human" for kind, _ in seats):
        raise ValueError("a human takes the bonus round in the CLI, not the bonus test")
    config, rules, spec = settings.load_config(), settings.load_rules(), settings.load_wheel()
    puzzles = [p for p in settings.load_puzzles(puzzles_path) if p.bonus][:limit]
    client, decisions = clients({kind for kind, _ in seats}, client, None)

    jobs = [(e, seat, i, p) for e, seat in zip(entrants, seats) for i, p in enumerate(puzzles)]
    path = lambda e, i: out_dir / safe(e) / f"puzzle{i:03d}.jsonl"  # noqa: E731
    todo = [j for j in jobs if not _finished(path(j[0], j[2]))]
    spent = sum(_cost(path(e, i)) for e, _, i, _ in jobs)
    write(f"{out_dir}: {len(puzzles)} bonus puzzles × {len(entrants)} players; "
          f"{len(jobs) - len(todo)} of {len(jobs)} done, ${spent:.4f} spent")

    def play(entrant: str, seat: tuple[str, str | None], i: int, puzzle: Puzzle) -> tuple[bool, float]:
        session = f"{out_dir.name}-{safe(entrant)}-{i:03d}"
        players = [*build_players([seat], rules, spec, config, client, decisions, session), Absent(), Absent()]
        state = bonus_game(set_seed(seed, i), rules, spec, puzzle)
        header = {"bonus_test": {"entrant": entrant, "puzzle": i, "puzzles": str(puzzles_path)}}
        with GameLog(path(entrant, i), state, players, header) as log:
            final = play_game(state, players, log)
        return bool(final.bonus.solved), _cost(path(entrant, i))

    stopped = False
    with ThreadPoolExecutor(max_workers=parallel) as pool:
        pending = {}
        while todo or pending:
            while todo and len(pending) < parallel:
                if max_cost is not None and spent >= max_cost:
                    stopped, todo = True, []
                    break
                job = todo.pop(0)
                pending[pool.submit(play, *job)] = job
            if not pending:
                break
            ready, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in ready:
                entrant, _, i, puzzle = pending.pop(future)
                try:
                    solved, cost = future.result()
                except Exception as err:  # an API failure after retries; a rerun replays the puzzle
                    write(f"{entrant} puzzle {i} failed: {err}. Rerun to replay it.")
                    continue
                spent += cost
                write(f"{entrant} puzzle {i}: {'solved' if solved else 'missed'} {puzzle.answer}  ·  ${spent:.4f} spent")
    if stopped:
        write(f"Stopped starting puzzles at the ${max_cost} budget. Rerun with a higher --max-cost to finish.")

    result = {**report(out_dir, entrants), "stopped_by_budget": stopped}
    (out_dir / "report.json").write_text(json.dumps(result, indent=2))
    for line in table(result):
        write(line)
    return result


def report(out_dir: Path, entrants: Sequence[str]) -> dict:
    """Per player solve rates, picks, and cost, and paired gaps over the puzzles both players finished."""
    results: dict[str, dict[int, bool]] = {}
    rows = []
    puzzles = ""
    for entrant in entrants:
        solved: dict[int, bool] = {}
        consonants, vowels = Counter(), Counter()
        shown, invalid, misfits, cost, tokens = [], 0, 0, 0.0, 0
        for path in sorted((Path(out_dir) / safe(entrant)).glob("puzzle*.jsonl")):
            if not _finished(path):
                continue
            lines = [json.loads(line) for line in path.read_text().splitlines()]
            header, summary = lines[0], lines[-1]
            puzzles = header["bonus_test"]["puzzles"]
            b = summary["bonus"]
            solved[header["bonus_test"]["puzzle"]] = bool(b["solved"])
            for row in lines:
                if row["type"] == "action" and row["action"]["kind"] == "bonus_picks":
                    consonants.update(c.upper() for c in row["action"]["consonants"])
                    vowels[row["action"]["vowel"].upper()] += 1
            letters = [c for c in b["puzzle"]["answer"] if c in LETTERS]
            shown.append(sum(c in b["used"] for c in letters) / len(letters))
            counts = summary["invalid"][0]
            misfits += counts.get(MISFIT, 0)
            invalid += sum(counts.values()) - counts.get(MISFIT, 0)
            cost += summary["usage"]["cost"]
            tokens += summary["usage"]["completion_tokens"]
        n, k = len(solved), sum(solved.values())
        results[entrant] = solved
        rows.append({
            "entrant": entrant,
            "puzzles": n,
            "solved": k,
            "rate": round(k / n, 4) if n else None,
            "ci95": wilson(k, n),
            "shown_after_picks": round(sum(shown) / n, 4) if n else None,
            "consonants": dict(consonants.most_common()),
            "vowels": dict(vowels.most_common()),
            "invalid": invalid,  # refused responses
            "misfits": misfits,  # solves that don't fit the board
            "cost": round(cost, 6),
            "output_tokens_per_puzzle": round(tokens / n) if n else None,
        })

    pairwise = []
    for a, b in combinations(entrants, 2):
        shared = sorted(results[a].keys() & results[b].keys())
        if not shared:
            continue
        pairs = [(results[a][i], results[b][i]) for i in shared]
        gap = lambda rows: sum(x - y for x, y in rows) / len(rows)  # noqa: E731
        pairwise.append({"a": a, "b": b, "puzzles": len(shared), "gap": round(gap(pairs), 4), "ci95": bootstrap(pairs, gap)})
    return {"puzzles": puzzles, "entrants": rows, "pairwise": pairwise}


def wilson(k: int, n: int, z: float = 1.96) -> list[float] | None:
    """The Wilson 95% interval for k successes in n tries."""
    if not n:
        return None
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4)]


def table(result: dict) -> list[str]:
    def pct(x):
        return "-" if x is None else f"{100 * x:.0f}%"

    lines = [f"Bonus test on {result['puzzles']}", f"{'player':<42} {'solved':>9} {'rate [95% CI]':>18} {'shown':>6} "
             f"{'top picks':<16} {'invalid':>7} {'misfit':>6} {'cost':>8}"]
    for e in result["entrants"]:
        ci = e["ci95"] or [None, None]
        picks = " ".join([*list(e["consonants"])[:3], *list(e["vowels"])[:1]])
        lines.append(f"{e['entrant']:<42} {e['solved']:>4}/{e['puzzles']:<4} {pct(e['rate']):>5} [{pct(ci[0])}-{pct(ci[1])}]"
                     f"{'':>2} {pct(e['shown_after_picks']):>6} {picks:<16} {e['invalid']:>7} {e['misfits']:>6} {e['cost']:>8.4f}")
    if result["pairwise"]:
        lines += ["", "Solve rate gaps on the same puzzles, with 95% intervals from resampling puzzles:"]
        for g in result["pairwise"]:
            ci = g["ci95"] or [0, 0]
            lines.append(f"  {g['a']} minus {g['b']}: {100 * g['gap']:+.0f}% [{100 * ci[0]:+.0f}% to {100 * ci[1]:+.0f}%]")
    return lines


def _arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m rstlne.bonustest", description="Every player on every bonus puzzle in a file.")
    parser.add_argument("--players", required=True, help="llm:<slug>, decision[:<model>], bot, or hybrid:<slug>, comma separated")
    parser.add_argument("--puzzles", required=True, help="a puzzle file; its bonus puzzles are the test")
    parser.add_argument("--seed", type=int, default=42, help="seeds each puzzle's envelope")
    parser.add_argument("--parallel", type=int, default=PARALLEL, help="puzzles to play at once")
    parser.add_argument("--max-cost", type=float, help="stop starting new puzzles once spending reaches this many dollars")
    parser.add_argument("--limit", type=int, help="only the first this many bonus puzzles")
    parser.add_argument("--out", help="test folder; the default covers the settings that change play, so a rerun resumes")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None, client: OpenRouter | None = None) -> dict:
    line_output()
    args = _arguments(argv)
    entrants = [p.strip() for p in args.players.split(",")]
    out = Path(args.out) if args.out else (
        settings.ROOT / "logs" / "bonustest" / folder_name(args.seed, Path(args.puzzles), settings.load_config())
    )
    try:
        return run_bonus_test(entrants, Path(args.puzzles), args.seed, out, args.parallel, args.max_cost, client, args.limit)
    except ValueError as err:
        sys.exit(f"--players: {err}")


if __name__ == "__main__":
    main()
