"""Seeded model-only tournaments with duplicate scoring.

    python -m rstlne.tournament --seats llm:<slug>,llm:<slug>,decision --sets 100 --seed 42
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from collections import Counter
from collections.abc import Callable, Sequence
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass
from pathlib import Path

from rstlne import settings
from rstlne.cli import build_players, clients, parse_seats, pick_puzzles
from rstlne.engine.rules import new_game
from rstlne.llm.decisions import DecisionClient
from rstlne.llm.openrouter import OpenRouter
from rstlne.narrate import money
from rstlne.runner import GameLog, play_game

ROTATIONS = 3


@dataclass(frozen=True)
class Game:
    set: int
    rotation: int
    seed: int

    @property
    def name(self) -> str:
        return f"set{self.set:03d}-rotation{self.rotation}"


def schedule(sets: int, seed: int) -> list[Game]:
    """Every game in the tournament. A set's three rotations share its seed, so they share spins and puzzles."""
    games = []
    for s in range(sets):
        set_seed = random.Random(f"tournament:{seed}:set:{s}").randrange(1_000_000_000)
        games += [Game(s, r, set_seed) for r in range(ROTATIONS)]
    return games


def seating(rotation: int) -> list[int]:
    """The entrant in each seat. Each rotation moves every entrant one seat along."""
    return [(seat - rotation) % ROTATIONS for seat in range(ROTATIONS)]


def split_wins(totals: Sequence[int]) -> list[float]:
    """The highest final total wins. Tied leaders split the win evenly."""
    best = max(totals)
    leaders = [i for i, total in enumerate(totals) if total == best]
    return [1 / len(leaders) if i in leaders else 0.0 for i in range(len(totals))]


def parse_entrants(seats: str | None, models: str | None) -> list[str]:
    """Three model seats from --seats, or from --models as shorthand for llm: seats."""
    if bool(seats) == bool(models):
        raise ValueError("give either --seats or --models")
    text = seats or ",".join(f"llm:{m.strip()}" for m in models.split(","))
    if any(kind == "human" for kind, _ in parse_seats(text)):
        raise ValueError("tournaments are model-only, so drop the human seat")
    return [part.strip() for part in text.split(",")]


def labels(entrants: Sequence[str]) -> list[str]:
    """Entrant names for the report, numbering repeats like `llm:a #2`."""
    counts, seen = Counter(entrants), Counter()
    names = []
    for entrant in entrants:
        seen[entrant] += 1
        names.append(f"{entrant} #{seen[entrant]}" if counts[entrant] > 1 else entrant)
    return names


def run_tournament(
    entrants: Sequence[str],
    sets: int,
    seed: int,
    puzzles_path: Path,
    out_dir: Path,
    parallel: int = 4,
    max_cost: float | None = None,
    client: OpenRouter | None = None,
    decisions: DecisionClient | None = None,
    write: Callable[[str], None] = print,
) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    config, rules, spec = settings.load_config(), settings.load_rules(), settings.load_wheel()
    puzzles = settings.load_puzzles(puzzles_path)
    client, decisions = clients({kind for kind, _ in parse_seats(",".join(entrants))}, client, decisions)
    names = labels(entrants)

    def play(game: Game) -> tuple[list[int], float]:
        order = seating(game.rotation)
        seats = parse_seats(",".join(entrants[e] for e in order))
        players = build_players(seats, rules, spec, config, client, decisions, f"{out_dir.name}-{game.name}")
        main_puzzles, bonus = pick_puzzles(puzzles, rules.main_rounds, game.seed)
        state = new_game(game.seed, rules, spec, main_puzzles, bonus)
        header = {"tournament": {
            "set": game.set, "rotation": game.rotation, "entrants": order, "names": names, "puzzles": str(puzzles_path),
        }}
        path = out_dir / f"{game.name}.jsonl"
        with GameLog(path, state, players, header) as log:
            final = play_game(state, players, log)
        return [s.total for s in final.seats], _cost(path)

    games = schedule(sets, seed)
    todo = [g for g in games if not _finished(out_dir / f"{g.name}.jsonl")]
    spent = sum(_cost(p) for p in out_dir.glob("set*.jsonl") if _finished(p))
    done = len(games) - len(todo)
    write(f"{out_dir}: {done} of {len(games)} games already done, ${spent:.4f} spent")

    stopped = False
    with ThreadPoolExecutor(max_workers=parallel) as pool:
        pending = {}
        while todo or pending:
            while todo and len(pending) < parallel:
                if max_cost is not None and spent >= max_cost:
                    stopped = True
                    break
                game = todo.pop(0)
                pending[pool.submit(play, game)] = game
            if not pending:
                break
            ready, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in ready:
                game = pending.pop(future)
                try:
                    totals, cost = future.result()
                except Exception as err:  # an API failure after retries; a rerun replays the game
                    write(f"{game.name} failed: {err}. Rerun the tournament to replay it.")
                    continue
                spent += cost
                done += 1
                leader = max(range(ROTATIONS), key=lambda seat: totals[seat])
                write(f"[{done}/{len(games)}] {game.name}: {names[seating(game.rotation)[leader]]} won with "
                      f"{money(totals[leader])}  ·  ${spent:.4f} spent")
            if stopped:
                todo = []
    if stopped:
        write(f"Stopped starting games at the ${max_cost} budget. Rerun with a higher --max-cost to finish.")

    result = {**report(out_dir), "stopped_by_budget": stopped}
    (out_dir / "report.json").write_text(json.dumps(result, indent=2))
    for line in table(result):
        write(line)
    return result


def report(out_dir: Path) -> dict:
    """Per entrant results from every finished game log in a tournament folder."""
    logs = [p for p in sorted(Path(out_dir).glob("set*.jsonl")) if _finished(p)]
    stats: dict[int, dict] = {}
    names: list[str] = []
    puzzles = ""
    for path in logs:
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        header, summary = rows[0], rows[-1]
        tournament = header["tournament"]
        names, puzzles = tournament["names"], tournament["puzzles"]
        wins = split_wins(summary["totals"])
        bonus = summary["bonus"]
        solves = [r for r in rows if r["type"] == "action" and r["action"]["kind"] == "solve"]
        for seat, entrant in enumerate(tournament["entrants"]):
            s = stats.setdefault(entrant, {
                "games": 0, "wins": 0.0, "seat_games": [0, 0, 0], "seat_wins": [0.0, 0.0, 0.0],
                "totals": [], "main": [], "bonus_reached": 0, "bonus_won": 0, "attempts": 0, "solved": 0,
                "shown": 0.0, "timed": 0, "money_left": 0, "invalid": Counter(), "tokens": 0, "cost": 0.0,
            })
            total = summary["totals"][seat]
            won_bonus = bool(bonus) and bonus["seat"] == seat and bool(bonus["solved"])
            attempts = [r for r in solves if r["seat"] == seat]
            timing = summary["solve_timing"][seat]
            usage = summary["usage_by_seat"][seat]
            s["games"] += 1
            s["wins"] += wins[seat]
            s["seat_games"][seat] += 1
            s["seat_wins"][seat] += wins[seat]
            s["totals"].append(total)
            s["main"].append(total - (bonus["envelope"] if won_bonus else 0))
            s["bonus_reached"] += bool(bonus) and bonus["seat"] == seat
            s["bonus_won"] += won_bonus
            s["attempts"] += len(attempts)
            s["solved"] += sum(r["result"]["outcome"] == "solved" for r in attempts)
            if timing["correct_solves"]:
                s["shown"] += timing["avg_board_shown"] * timing["correct_solves"]
            s["timed"] += timing["correct_solves"]
            s["money_left"] += timing["money_left"]
            s["invalid"].update(summary["invalid"][seat])
            s["tokens"] += usage["total_tokens"]
            s["cost"] += usage["cost"]

    def ratio(a, b, places=4):
        return round(a / b, places) if b else None

    entrants = []
    for entrant in sorted(stats):
        s = stats[entrant]
        entrants.append({
            "entrant": names[entrant],
            "games": s["games"],
            "wins": round(s["wins"], 4),
            "win_rate": ratio(s["wins"], s["games"]),
            "win_rate_by_seat": [ratio(w, g) for w, g in zip(s["seat_wins"], s["seat_games"])],
            "avg_total": round(sum(s["totals"]) / s["games"], 2),
            "avg_main_winnings": round(sum(s["main"]) / s["games"], 2),
            "bonus_reached": s["bonus_reached"],
            "bonus_won": s["bonus_won"],
            "solve_attempts": s["attempts"],
            "solve_accuracy": ratio(s["solved"], s["attempts"]),
            "avg_board_shown": ratio(s["shown"], s["timed"], 3),
            "money_left_per_solve": ratio(s["money_left"], s["timed"], 0),
            "invalid": dict(s["invalid"]),
            "invalid_per_game": ratio(sum(s["invalid"].values()), s["games"]),
            "tokens": s["tokens"],
            "cost": round(s["cost"], 6),
        })
    return {
        "games": len(logs),
        "puzzles": puzzles,
        "dev_run": Path(puzzles).name != "private.json",
        "entrants": entrants,
    }


def table(result: dict) -> list[str]:
    def pct(x):
        return "-" if x is None else f"{x:.0%}"

    lines = [
        "",
        f"{result['games']} games" + ("  ·  development run on dev.json, not a scored result" if result["dev_run"] else ""),
        f"{'entrant':<36}{'wins':>7}{'win%':>6}{'by seat':>16}{'avg total':>12}{'main':>10}{'bonus':>7}"
        f"{'solve%':>8}{'shown':>7}{'left/solve':>11}{'invalid/g':>10}{'cost':>9}",
    ]
    for e in result["entrants"]:
        seats = "/".join(pct(x) for x in e["win_rate_by_seat"])
        lines.append(
            f"{e['entrant'][:35]:<36}{e['wins']:>7.1f}{pct(e['win_rate']):>6}{seats:>16}"
            f"{money(round(e['avg_total'])):>12}{money(round(e['avg_main_winnings'])):>10}"
            f"{e['bonus_won']:>3}/{e['bonus_reached']:<3}{pct(e['solve_accuracy']):>8}{pct(e['avg_board_shown']):>7}"
            f"{money(round(e['money_left_per_solve'] or 0)):>11}{(e['invalid_per_game'] or 0):>10.2f}{e['cost']:>9.4f}"
        )
    return lines


def _finished(path: Path) -> bool:
    if not path.exists():
        return False
    lines = path.read_text().splitlines()
    return bool(lines) and json.loads(lines[-1]).get("type") == "summary"


def _cost(path: Path) -> float:
    return json.loads(path.read_text().splitlines()[-1])["usage"]["cost"] if _finished(path) else 0.0


def _arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m rstlne.tournament", description="Run a seeded model-only tournament.")
    parser.add_argument("--seats", help="three model seats: llm:<slug> or decision[:<model>], comma separated")
    parser.add_argument("--models", help="three OpenRouter slugs, short for llm:<slug> seats")
    parser.add_argument("--sets", type=int, required=True, help="puzzle sets to play; each is 3 games with the seats rotated")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--puzzles", default=str(settings.ROOT / "puzzles" / "dev.json"))
    parser.add_argument("--parallel", type=int, default=4, help="games to play at once")
    parser.add_argument("--max-cost", type=float, help="stop starting new games once spending reaches this many dollars")
    parser.add_argument("--out", help="tournament folder; the default depends on the entrants, seed, and puzzles, so a rerun resumes")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None, client: OpenRouter | None = None, decisions: DecisionClient | None = None) -> dict:
    args = _arguments(argv)
    try:
        entrants = parse_entrants(args.seats, args.models)
    except ValueError as err:
        sys.exit(f"--seats: {err}")
    key = hashlib.sha256(json.dumps([entrants, args.seed, Path(args.puzzles).name]).encode()).hexdigest()[:8]
    out = Path(args.out) if args.out else settings.ROOT / "logs" / "tournaments" / f"seed{args.seed}-{key}"
    return run_tournament(
        entrants, args.sets, args.seed, Path(args.puzzles), out, args.parallel, args.max_cost, client, decisions,
    )


if __name__ == "__main__":
    main()
