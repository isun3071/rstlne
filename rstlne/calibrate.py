"""Pick each decision model's solve threshold from data.

    python -m rstlne.calibrate --models openai/gpt-6-luna-decisions,typesafe/jev-1.14
"""

from __future__ import annotations

import argparse
import json
import random
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from statistics import mean

from rstlne import settings
from rstlne.cli import clients
from rstlne.engine.puzzle import LETTERS, Puzzle, solve_matches
from rstlne.engine.rules import new_game, public_view
from rstlne.engine.state import PublicView, Solve
from rstlne.llm.decisions import DecisionClient
from rstlne.llm.openrouter import OpenRouter
from rstlne.narrate import line_output
from rstlne.players.base import InvalidResponse
from rstlne.players.decision import SOLVABLE_QUESTION, decision_state
from rstlne.players.llm import LLMPlayer

ORDER = "ETAOINSHRDLCUMWFGYPBVKJXQZ"  # English letter frequency, the order boards fill in
TARGET, MINIMUM = 0.8, 5


@dataclass(frozen=True)
class Board:
    puzzle: Puzzle
    used: frozenset[str]
    shown: float  # share of the puzzle's letter squares showing


def boards(puzzles: Sequence[Puzzle], count: int, seed: int) -> list[Board]:
    """`count` seeded main round puzzles, each stopped at several points from an empty board to a full one."""
    sample = random.Random(f"calibrate:{seed}").sample([p for p in puzzles if not p.bonus], count)
    out = []
    for puzzle in sample:
        letters = [c for c in puzzle.answer if c in LETTERS]
        progression, used = [frozenset()], set()
        for c in ORDER:
            if c in letters:
                used.add(c)
                progression.append(frozenset(used))
        n = len(progression)
        for i in sorted({0, n // 4, n // 2, (3 * n) // 4, n - 2, n - 1}):
            shown = sum(c in progression[i] for c in letters) / len(letters)
            out.append(Board(puzzle, progression[i], round(shown, 3)))
    return out


def calibration_curve(points: Sequence[tuple[float, bool]]) -> list[tuple[float, float, float, int]]:
    """Solver accuracy as a never-decreasing function of P(solvable), fit by pooling adjacent violators.
    Each block is (lowest P, highest P, accuracy, boards)."""
    blocks: list[list] = []  # [correct, boards, lowest P, highest P]
    for p, correct in sorted(points):
        blocks.append([float(correct), 1, p, p])
        while len(blocks) > 1 and blocks[-2][0] / blocks[-2][1] > blocks[-1][0] / blocks[-1][1]:
            right, n, _, high = blocks.pop()
            blocks[-1][0] += right
            blocks[-1][1] += n
            blocks[-1][3] = high
    return [(low, high, right / n, n) for right, n, low, high in blocks]


def choose_threshold(points: Sequence[tuple[float, bool]], target: float = TARGET, minimum: int = MINIMUM) -> float | None:
    """The lowest P(solvable) where the calibration curve reaches `target`, with at least `minimum` boards at or above it."""
    for low, _, accuracy, _ in calibration_curve(points):
        if accuracy >= target:
            above = sum(1 for p, _ in points if p >= low)
            return round(low, 3) if above >= minimum else None
    return None


def calibrate(
    models: Sequence[str],
    puzzles_path: Path,
    count: int,
    seed: int,
    client: OpenRouter | None = None,
    decisions: DecisionClient | None = None,
    out_dir: Path = settings.ROOT / "logs" / "calibration",
    parallel: int = 4,
    target: float = TARGET,
    write: Callable[[str], None] = print,
) -> dict:
    config, rules, spec = settings.load_config(), settings.load_rules(), settings.load_wheel()
    client, decisions = clients({"decision"}, client, decisions)
    solver_model = config["decision"]["solver_model"]
    sample = boards(settings.load_puzzles(puzzles_path), count, seed)
    blank = new_game(seed, rules, spec, [Puzzle("Phrase", "X")] * rules.main_rounds, Puzzle("Thing", "X", bonus=True))

    def view_of(board: Board) -> PublicView:
        return public_view(replace(blank, round=replace(blank.round, puzzle=board.puzzle, used=board.used)), 0)

    def solve(board: Board) -> bool:
        solver = LLMPlayer(0, solver_model, client, rules, spec, config["llm"].get("temperature"),
                           reasoning_effort=config["llm"].get("reasoning_effort"),
                           provider=config.get("providers", {}).get(solver_model))
        try:
            action = solver.decide(replace(view_of(board), legal_actions=("solve",)))
        except InvalidResponse:
            return False
        return isinstance(action, Solve) and isinstance(action.answer, str) and solve_matches(board.puzzle.answer, action.answer)

    def p_solvable(model: str, board: Board) -> float:
        state = decision_state(0, rules, spec, view_of(board))
        return decisions.ask(model=model, state=state, questions={"solvable": SOLVABLE_QUESTION}).answers["solvable"]["noul"]

    write(f"{len(sample)} boards from {count} puzzles; solver {solver_model}")
    with ThreadPoolExecutor(max_workers=parallel) as pool:
        correct = list(pool.map(solve, sample))
        scores = {m: list(pool.map(lambda b, m=m: p_solvable(m, b), sample)) for m in models}

    result = {"boards": len(sample), "solver": solver_model, "target": target, "seed": seed, "models": {}, "config_lines": []}
    for model in models:
        points = list(zip(scores[model], correct))
        threshold = choose_threshold(points, target)
        result["models"][model] = {
            "threshold": threshold,
            "points": [
                {"answer": b.puzzle.answer, "shown": b.shown, "p_solvable": p, "solver_correct": c}
                for b, p, c in zip(sample, scores[model], correct)
            ],
        }
        if threshold is not None:
            result["config_lines"].append(f'"{model}" = {threshold}')
        write(f"\n{model}: threshold {threshold if threshold is not None else 'none reaches the target'}")
        if threshold is not None:
            above = [(c, b.shown) for b, p, c in zip(sample, scores[model], correct) if p >= threshold]
            write(f"  at or above it: {len(above)} boards, solver right {mean(c for c, _ in above):.0%}, "
                  f"board {mean(s for _, s in above):.0%} shown on average")
        write(f"  {'board shown':<14}{'avg P(solvable)':>16}{'solver right':>14}")
        for lo, hi in ((0, 0.25), (0.25, 0.5), (0.5, 0.75), (0.75, 1.0), (1.0, 1.01)):
            group = [(p, c) for b, p, c in zip(sample, scores[model], correct) if lo <= b.shown < hi]
            if group:
                label = "100%" if lo == 1.0 else f"{lo:.0%}-{hi:.0%}"
                write(f"  {label:<14}{mean(p for p, _ in group):>16.2f}{mean(c for _, c in group):>14.0%}")
    write("\nAdd to config.toml under [decision.thresholds]:")
    for line in result["config_lines"] or ["  (no model reached the target)"]:
        write(f"  {line}")

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"calibration-{datetime.now():%Y%m%d-%H%M%S}.json"
    path.write_text(json.dumps(result, indent=2))
    write(f"Saved {path}")
    return result


def main(argv: Sequence[str] | None = None) -> dict:
    line_output()
    parser = argparse.ArgumentParser(prog="python -m rstlne.calibrate", description="Pick decision model solve thresholds from data.")
    parser.add_argument("--models", required=True, help="decision model IDs, comma separated")
    parser.add_argument("--puzzles", default=str(settings.ROOT / "puzzles" / "dev.json"))
    parser.add_argument("--count", type=int, default=20, help="puzzles to sample; each gives 5 or 6 boards")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--target", type=float, default=TARGET, help="solver accuracy the threshold must reach")
    parser.add_argument("--parallel", type=int, default=4)
    args = parser.parse_args(argv)
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    return calibrate(models, Path(args.puzzles), args.count, args.seed, parallel=args.parallel, target=args.target)


if __name__ == "__main__":
    main()
