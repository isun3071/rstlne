"""Play a game in the terminal.

    python -m rstlne.cli --seats human,llm:<slug>,bot
"""

from __future__ import annotations

import argparse
import random
import sys
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from rstlne import settings
from rstlne.engine.puzzle import Puzzle
from rstlne.engine.rules import new_game
from rstlne.engine.state import GameState
from rstlne.live import LiveShow
from rstlne.llm.decisions import DecisionClient
from rstlne.llm.openrouter import OpenRouter
from rstlne.players.base import Player
from rstlne.players.bot import versions
from rstlne.players.bot.player import BotPlayer, make_reader
from rstlne.players.decision import DecisionPlayer
from rstlne.players.human_cli import HumanPlayer
from rstlne.players.llm import LLMPlayer
from rstlne.runner import GameLog, play_game
from rstlne.show import Show


def parse_seats(text: str) -> list[tuple[str, str | None]]:
    """`human`, `llm:<slug>`, `decision[:<model>]`, or `bot` seats as (kind, model) pairs."""
    seats: list[tuple[str, str | None]] = []
    for part in (p.strip() for p in text.split(",")):
        if part == "human":
            seats.append(("human", None))
        elif part == "bot":
            seats.append(("bot", None))
        elif part.startswith("llm:"):
            slug = part.removeprefix("llm:").strip()
            if not slug:
                raise ValueError("llm seats need a model slug, like llm:openai/gpt-4o")
            seats.append(("llm", slug))
        elif part == "decision" or part.startswith("decision:"):
            seats.append(("decision", part.removeprefix("decision").removeprefix(":").strip() or None))
        else:
            raise ValueError(f"unknown seat {part!r}. Use human, llm:<slug>, decision, or bot.")
    if len(seats) != 3:
        raise ValueError(f"a game needs three seats, got {len(seats)}")
    return seats


def clients(
    kinds: set[str], client: OpenRouter | None, decisions: DecisionClient | None
) -> tuple[OpenRouter | None, DecisionClient | None]:
    """The API clients these seat kinds need, reading the key from .env. Clients passed in are kept."""
    if kinds & {"llm", "decision"}:
        load_dotenv(settings.ROOT / ".env")
        if client is None:
            client = OpenRouter()
    if decisions is None and "decision" in kinds:
        decisions = DecisionClient()
    return client, decisions


def build_players(
    seats: list[tuple[str, str | None]],
    rules,
    spec,
    config: dict,
    client: OpenRouter | None,
    decisions: DecisionClient | None,
    session_prefix: str,
) -> list[Player]:
    """A player per (kind, model) seat. Each model seat gets its own session, `<prefix>-seat<n>`."""
    temperature = config["llm"].get("temperature")
    effort = config["llm"].get("reasoning_effort")
    decision = config["decision"]
    providers = config.get("providers", {})

    def seat(i: int, kind: str, model: str | None) -> Player:
        session = f"{session_prefix}-seat{i + 1}"
        if kind == "human":
            return HumanPlayer(i, seconds=config["cli"]["bonus_solve_seconds"])
        if kind == "bot":
            version = versions.current(config)
            return BotPlayer(i, rules, spec, make_reader(versions.knobs(version)), version=version)
        if kind == "llm":
            return LLMPlayer(
                i, model, client, rules, spec, temperature, session, reasoning_effort=effort, provider=providers.get(model)
            )
        solver_model = decision["solver_model"]
        solver = LLMPlayer(
            i, solver_model, client, rules, spec, temperature, f"{session}-solver",
            reasoning_effort=effort, provider=providers.get(solver_model),
        )
        model = model or decision["decision_model"]
        threshold = decision.get("thresholds", {}).get(model, decision["solve_threshold"])
        return DecisionPlayer(i, model, decisions, solver, rules, spec, threshold, session)

    return [seat(i, kind, model) for i, (kind, model) in enumerate(seats)]


def pick_puzzles(puzzles: Sequence[Puzzle], rounds: int, seed: int) -> tuple[list[Puzzle], Puzzle]:
    """A seeded draw of main round puzzles, with no repeats, and one bonus puzzle."""
    rng = random.Random(f"puzzles:{seed}")
    main = [p for p in puzzles if not p.bonus]
    bonus = [p for p in puzzles if p.bonus]
    if len(main) < rounds or not bonus:
        raise ValueError(f"need {rounds} main puzzles and a bonus puzzle, got {len(main)} and {len(bonus)}")
    return rng.sample(main, rounds), rng.choice(bonus)


def _arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m rstlne.cli", description="Play Wheel of Fortune in the terminal.")
    parser.add_argument("--seats", required=True, help="three seats: human, llm:<slug>, decision, or bot, comma separated")
    parser.add_argument("--seed", type=int, help="game seed; replaying a seed with the same moves replays the game")
    parser.add_argument("--puzzles", default=str(settings.ROOT / "puzzles" / "dev.json"))
    parser.add_argument("--pause", type=float, help="seconds to pause after each model move")
    parser.add_argument("--show-thinking", action="store_true", help="print each model's raw response")
    parser.add_argument("--show-puzzle", action="store_true", help="print the board, letters, and banks after every move")
    parser.add_argument("--live", action="store_true", help="model-only games: redraw one fixed screen after every move")
    parser.add_argument("--log-dir", default=str(settings.ROOT / "logs"))
    return parser.parse_args(argv)


def main(
    argv: Sequence[str] | None = None,
    client: OpenRouter | None = None,
    decisions: DecisionClient | None = None,
) -> GameState:
    args = _arguments(argv)
    try:
        seats = parse_seats(args.seats)
    except ValueError as err:
        sys.exit(f"--seats: {err}")
    config = settings.load_config()
    rules, spec = settings.load_rules(), settings.load_wheel()
    seed = args.seed if args.seed is not None else random.randrange(1_000_000)
    puzzles, bonus = pick_puzzles(settings.load_puzzles(Path(args.puzzles)), rules.main_rounds, seed)

    path = Path(args.log_dir) / f"{datetime.now():%Y%m%d-%H%M%S}-seed{seed}.jsonl"
    kinds = {kind for kind, _ in seats}
    if args.live and "human" in kinds:
        sys.exit("--live is for model-only games, since a redrawing screen can't take typed moves. "
                 "Drop the human seat, or use --show-puzzle.")
    client, decisions = clients(kinds, client, decisions)
    players = build_players(seats, rules, spec, config, client, decisions, path.stem)
    pause = args.pause if args.pause is not None else config["cli"]["model_pause"]
    show: Show | LiveShow
    if args.live and sys.stdout.isatty():
        show = LiveShow(players, pause, solve_pause=config["cli"]["solve_pause"])
    else:
        if args.live:
            print("--live needs a terminal; showing plain output instead.")
        show = Show(players, pause, args.show_thinking, args.show_puzzle, config["cli"]["solve_pause"])

    state = new_game(seed, rules, spec, puzzles, bonus)
    show.start(state)
    try:
        with GameLog(path, state, players) as log:
            final = play_game(state, players, log, on_result=show.result)
    finally:
        show.stop()
    show.finish(final, path)
    return final


if __name__ == "__main__":
    main()
