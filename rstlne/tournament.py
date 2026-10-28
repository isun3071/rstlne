"""Seeded model-only tournaments with duplicate scoring.

    python -m rstlne.tournament --seats llm:<slug>,llm:<slug>,decision --sets 50 --seed 42
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from collections import Counter, defaultdict
from collections.abc import Callable, Sequence
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass
from itertools import combinations, permutations
from pathlib import Path

from rstlne import settings
from rstlne.cli import build_players, clients, parse_seats
from rstlne.engine.puzzle import Puzzle
from rstlne.engine.rules import new_game
from rstlne.llm.decisions import DecisionClient
from rstlne.llm.openrouter import OpenRouter
from rstlne.narrate import money
from rstlne.runner import GameLog, play_game

SEATS = 3
RESAMPLES = 10_000
PARALLEL = 6  # a whole set of 6 games at once
HEARTBEAT = 120  # seconds between status lines while games run


@dataclass(frozen=True)
class Game:
    set: int
    permutation: int  # which ordering of the set this is
    order: tuple[int, ...]  # the entrant in each seat
    seed: int

    @property
    def name(self) -> str:
        return f"set{self.set:03d}-perm{self.permutation}"


def orderings(mode: str) -> list[tuple[int, ...]]:
    """"all": every ordering of the entrants. "cyclic": the seat rotations only."""
    if mode == "all":
        return list(permutations(range(SEATS)))
    if mode == "cyclic":
        return [tuple((seat - r) % SEATS for seat in range(SEATS)) for r in range(SEATS)]
    raise ValueError(f'set_permutations must be "all" or "cyclic", not {mode!r}')


def set_seed(seed: int, index: int) -> int:
    return random.Random(f"tournament:{seed}:set:{index}").randrange(1_000_000_000)


def schedule(sets: int, seed: int, mode: str = "all") -> list[Game]:
    """Every game in the tournament. A set's games share its seed, so they share spins and puzzles."""
    return [
        Game(s, k, order, set_seed(seed, s))
        for s in range(sets)
        for k, order in enumerate(orderings(mode))
    ]


def deal(pool: Sequence[Puzzle], per_set: int, sets: int, seed: int, label: str) -> list[list[Puzzle]]:
    """Deal `per_set` puzzles to each set without replacement, reshuffling when the pile runs out.
    A set that straddles a reshuffle skips puzzles it already holds; they stay in the pile for later sets."""
    if len(pool) < per_set:
        raise ValueError(f"{label} pool has {len(pool)} puzzles, and each set needs {per_set}")

    def shuffled(cycle: int) -> list[Puzzle]:
        pile = list(pool)
        random.Random(f"tournament:{seed}:{label}:{cycle}").shuffle(pile)
        return pile

    cycle, pile, hands = 0, shuffled(0), []
    for _ in range(sets):
        hand: list[Puzzle] = []
        while len(hand) < per_set:
            i = next((i for i, puzzle in enumerate(pile) if puzzle not in hand), None)
            if i is None:
                cycle += 1
                pile += shuffled(cycle)
                continue
            hand.append(pile.pop(i))
        hands.append(hand)
    return hands


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


def folder_name(entrants: Sequence[str], seed: int, puzzles_path: Path, config: dict) -> str:
    """Covers everything that changes play, so a rerun resumes only an identical tournament."""
    play = {key: config.get(key) for key in ("tournament", "providers", "llm", "decision")}
    key = json.dumps([list(entrants), seed, Path(puzzles_path).name, play], sort_keys=True)
    return f"seed{seed}-{hashlib.sha256(key.encode()).hexdigest()[:8]}"


def run_tournament(
    entrants: Sequence[str],
    sets: int,
    seed: int,
    puzzles_path: Path,
    out_dir: Path,
    parallel: int = PARALLEL,
    max_cost: float | None = None,
    client: OpenRouter | None = None,
    decisions: DecisionClient | None = None,
    mode: str | None = None,
    write: Callable[[str], None] = print,
    heartbeat: float = HEARTBEAT,
) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    config, rules, spec = settings.load_config(), settings.load_rules(), settings.load_wheel()
    mode = mode or config.get("tournament", {}).get("set_permutations", "all")
    pool = settings.load_puzzles(puzzles_path)
    main_hands = deal([p for p in pool if not p.bonus], rules.main_rounds, sets, seed, "main")
    bonus_hands = deal([p for p in pool if p.bonus], 1, sets, seed, "bonus")
    client, decisions = clients({kind for kind, _ in parse_seats(",".join(entrants))}, client, decisions)
    names = labels(entrants)
    progress: dict[str, list] = {}  # running game name -> [round, moves], updated by the game threads

    def play(game: Game) -> tuple[list[int], float]:
        seats = parse_seats(",".join(entrants[e] for e in game.order))
        players = build_players(seats, rules, spec, config, client, decisions, f"{out_dir.name}-{game.name}")
        state = new_game(game.seed, rules, spec, main_hands[game.set], bonus_hands[game.set][0])
        header = {"tournament": {
            "set": game.set, "permutation": game.permutation, "entrants": list(game.order), "names": names,
            "puzzles": str(puzzles_path), "set_permutations": mode,
        }}
        path = out_dir / f"{game.name}.jsonl"
        progress[game.name] = [1, 0]

        def track(now) -> None:
            entry = progress[game.name]
            entry[0] = now.round.number if now.round else "bonus"
            entry[1] += 1

        try:
            with GameLog(path, state, players, header) as log:
                final = play_game(state, players, log, on_result=track)
        finally:
            progress.pop(game.name, None)
        return [s.total for s in final.seats], _cost(path)

    games = schedule(sets, seed, mode)
    todo = [g for g in games if not _finished(out_dir / f"{g.name}.jsonl")]
    spent = sum(_cost(p) for p in out_dir.glob("set*.jsonl") if _finished(p))
    done = len(games) - len(todo)
    write(f"{out_dir}: {sets} sets of {len(orderings(mode))} games; {done} of {len(games)} done, ${spent:.4f} spent")

    stopped = False
    with ThreadPoolExecutor(max_workers=parallel) as pool_:
        pending = {}
        while todo or pending:
            while todo and len(pending) < parallel:
                if max_cost is not None and spent >= max_cost:
                    stopped = True
                    break
                game = todo.pop(0)
                pending[pool_.submit(play, game)] = game
                seating = ", ".join(f"Seat {seat + 1} {names[e]}" for seat, e in enumerate(game.order))
                write(f"started {game.name}: {seating}")
            if not pending:
                break
            ready, _ = wait(pending, timeout=heartbeat, return_when=FIRST_COMPLETED)
            if not ready:
                running = ", ".join(
                    f"{name} {'bonus round' if r == 'bonus' else f'round {r}'} ({moves} moves)"
                    for name, (r, moves) in sorted(list(progress.items()))
                )
                write(f"in progress: {running or 'starting'}  ·  {done} of {len(games)} done  ·  ${spent:.4f} spent")
                continue
            for future in ready:
                game = pending.pop(future)
                try:
                    totals, cost = future.result()
                except Exception as err:  # an API failure after retries; a rerun replays the game
                    write(f"{game.name} failed: {err}. Rerun the tournament to replay it.")
                    continue
                spent += cost
                done += 1
                leader = max(range(SEATS), key=lambda seat: totals[seat])
                write(f"[{done}/{len(games)}] {game.name}: {names[game.order[leader]]} won with "
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


def bootstrap(rows: Sequence, stat: Callable[[list], float | None], resamples: int = RESAMPLES,
              seed: int = 0, level: float = 0.95) -> tuple[float, float] | None:
    """A percentile confidence interval for `stat`, resampling `rows` (one per set) with replacement."""
    rng = random.Random(seed)
    values = sorted(
        v for v in (stat([rows[rng.randrange(len(rows))] for _ in rows]) for _ in range(resamples)) if v is not None
    )
    if not values:
        return None
    tail = (1 - level) / 2
    return (round(values[int(tail * (len(values) - 1))], 4), round(values[int((1 - tail) * (len(values) - 1))], 4))


def report(out_dir: Path) -> dict:
    """Per entrant and per set results from every finished game log in a tournament folder."""
    logs = [p for p in sorted(Path(out_dir).glob("set*.jsonl")) if _finished(p)]
    stats: dict[int, dict] = {}
    per_set: dict[int, dict[int, dict]] = defaultdict(dict)
    set_puzzles: dict[int, list[str]] = {}
    names: list[str] = []
    puzzles = ""
    for path in logs:
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        header, summary = rows[0], rows[-1]
        tournament = header["tournament"]
        names, puzzles = tournament["names"], tournament["puzzles"]
        set_puzzles[tournament["set"]] = [p["answer"] for p in header["puzzles"]] + [header["bonus_puzzle"]["answer"]]
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
            main = total - (bonus["envelope"] if won_bonus else 0)
            attempts = [r for r in solves if r["seat"] == seat]
            solved = sum(r["result"]["outcome"] == "solved" for r in attempts)
            timing = summary["solve_timing"][seat]
            usage = summary["usage_by_seat"][seat]
            s["games"] += 1
            s["wins"] += wins[seat]
            s["seat_games"][seat] += 1
            s["seat_wins"][seat] += wins[seat]
            s["totals"].append(total)
            s["main"].append(main)
            s["bonus_reached"] += bool(bonus) and bonus["seat"] == seat
            s["bonus_won"] += won_bonus
            s["attempts"] += len(attempts)
            s["solved"] += solved
            if timing["correct_solves"]:
                s["shown"] += timing["avg_board_shown"] * timing["correct_solves"]
            s["timed"] += timing["correct_solves"]
            s["money_left"] += timing["money_left"]
            s["invalid"].update(summary["invalid"][seat])
            s["tokens"] += usage["total_tokens"]
            s["cost"] += usage["cost"]
            row = per_set[tournament["set"]].setdefault(entrant, {"games": 0, "wins": 0.0, "total": 0, "main": 0, "attempts": 0, "solved": 0})
            row["games"] += 1
            row["wins"] += wins[seat]
            row["total"] += total
            row["main"] += main
            row["attempts"] += len(attempts)
            row["solved"] += solved

    def ratio(a, b, places=4):
        return round(a / b, places) if b else None

    set_rows = [per_set[s] for s in sorted(per_set)]

    def interval(entrant: int, numerator: str, denominator: str) -> list[float] | None:
        def stat(rows):
            den = sum(r[entrant][denominator] for r in rows if entrant in r)
            return sum(r[entrant][numerator] for r in rows if entrant in r) / den if den else None
        ci = bootstrap(set_rows, stat) if set_rows else None
        return list(ci) if ci else None

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
            "ci95": {
                "win_rate": interval(entrant, "wins", "games"),
                "avg_total": interval(entrant, "total", "games"),
                "avg_main_winnings": interval(entrant, "main", "games"),
                "solve_accuracy": interval(entrant, "solved", "attempts"),
            },
        })

    pairwise = []
    for a, b in combinations(sorted(stats), 2):
        def gap(rows, a=a, b=b):
            ga, gb = sum(r[a]["games"] for r in rows if a in r), sum(r[b]["games"] for r in rows if b in r)
            if not ga or not gb:
                return None
            return sum(r[a]["wins"] for r in rows if a in r) / ga - sum(r[b]["wins"] for r in rows if b in r) / gb
        ci = bootstrap(set_rows, gap) if set_rows else None
        pairwise.append({
            "a": names[a], "b": names[b],
            "win_rate_gap": round(gap(set_rows), 4) if set_rows else None,
            "ci95": list(ci) if ci else None,
        })

    usage = Counter(answer for answers in set_puzzles.values() for answer in answers)
    return {
        "games": len(logs),
        "sets": len(per_set),
        "puzzles": puzzles,
        "dev_run": Path(puzzles).name != "private.json",
        "entrants": entrants,
        "pairwise": pairwise,
        "per_set": [
            {
                "set": s,
                "games": sum(r["games"] for r in per_set[s].values()) // SEATS,
                "entrants": [
                    {"entrant": names[e], "wins": round(r["wins"], 4), "avg_total": round(r["total"] / r["games"], 2)}
                    for e, r in sorted(per_set[s].items())
                ],
            }
            for s in sorted(per_set)
        ],
        "puzzle_usage": dict(sorted(usage.items())),
    }


def table(result: dict) -> list[str]:
    def pct(x):
        return "-" if x is None else f"{x:.0%}"

    def span(ci):
        return "" if not ci else f" [{pct(ci[0])}-{pct(ci[1])}]"

    lines = [
        "",
        f"{result['games']} games in {result['sets']} sets"
        + ("  ·  development run on dev.json, not a scored result" if result["dev_run"] else ""),
        f"{'entrant':<40}{'wins':>7}{'win% [95% CI]':>18}{'by seat':>16}{'avg total':>12}{'main':>10}{'bonus':>9}"
        f"{'solve%':>8}{'shown':>7}{'left/solve':>11}{'invalid/g':>10}{'cost':>9}",
    ]
    for e in result["entrants"]:
        seats = "/".join(pct(x) for x in e["win_rate_by_seat"])
        lines.append(
            f"{e['entrant'][:39]:<40}{e['wins']:>7.1f}{pct(e['win_rate']) + span(e['ci95']['win_rate']):>18}{seats:>16}"
            f"{money(round(e['avg_total'])):>12}{money(round(e['avg_main_winnings'])):>10}"
            f"{str(e['bonus_won']) + '/' + str(e['bonus_reached']):>9}{pct(e['solve_accuracy']):>8}{pct(e['avg_board_shown']):>7}"
            f"{money(round(e['money_left_per_solve'] or 0)):>11}{(e['invalid_per_game'] or 0):>10.2f}{e['cost']:>9.4f}"
        )
    if result["pairwise"]:
        lines.append("")
        lines.append("Win rate gaps, with 95% intervals from resampling sets:")
        for p in result["pairwise"]:
            gap = p["win_rate_gap"]
            ci = p["ci95"]
            gap_text = "-" if gap is None else f"{gap:+.0%}"
            ci_text = "" if not ci else f" [{ci[0]:+.0%} to {ci[1]:+.0%}]"
            lines.append(f"  {p['a']} minus {p['b']}: {gap_text}{ci_text}")
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
    parser.add_argument("--sets", type=int, required=True,
                        help="puzzle sets to play; each is 6 games, or 3 with set_permutations = \"cyclic\". --sets 1 is a trial run")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--puzzles", default=str(settings.ROOT / "puzzles" / "dev.json"))
    parser.add_argument("--parallel", type=int, default=PARALLEL, help="games to play at once")
    parser.add_argument("--max-cost", type=float, help="stop starting new games once spending reaches this many dollars")
    parser.add_argument("--out", help="tournament folder; the default covers everything that changes play, so a rerun resumes")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None, client: OpenRouter | None = None, decisions: DecisionClient | None = None) -> dict:
    args = _arguments(argv)
    try:
        entrants = parse_entrants(args.seats, args.models)
    except ValueError as err:
        sys.exit(f"--seats: {err}")
    out = Path(args.out) if args.out else (
        settings.ROOT / "logs" / "tournaments" / folder_name(entrants, args.seed, Path(args.puzzles), settings.load_config())
    )
    return run_tournament(
        entrants, args.sets, args.seed, Path(args.puzzles), out, args.parallel, args.max_cost, client, decisions,
    )


if __name__ == "__main__":
    main()
