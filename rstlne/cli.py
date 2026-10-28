"""Play a game in the terminal.

    python -m rstlne.cli --seats human,llm:<slug>,decision
"""

from __future__ import annotations

import argparse
import random
import sys
import time
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from rstlne import settings
from rstlne.engine.puzzle import Puzzle
from rstlne.engine.rules import new_game, public_view
from rstlne.engine.state import GameState, Phase
from rstlne.llm.decisions import DecisionClient
from rstlne.llm.openrouter import OpenRouter
from rstlne.narrate import describe, money, seat_name, table
from rstlne.players.base import Player
from rstlne.players.decision import DecisionPlayer
from rstlne.players.human_cli import HumanPlayer
from rstlne.players.llm import LLMPlayer
from rstlne.runner import GameLog, play_game


def parse_seats(text: str) -> list[tuple[str, str | None]]:
    """`human`, `llm:<slug>`, or `decision[:<model>]` seats as (kind, model) pairs."""
    seats: list[tuple[str, str | None]] = []
    for part in (p.strip() for p in text.split(",")):
        if part == "human":
            seats.append(("human", None))
        elif part == "bot":
            raise ValueError("the bot isn't built yet. Use human, llm:<slug>, or decision.")
        elif part.startswith("llm:"):
            slug = part.removeprefix("llm:").strip()
            if not slug:
                raise ValueError("llm seats need a model slug, like llm:openai/gpt-4o")
            seats.append(("llm", slug))
        elif part == "decision" or part.startswith("decision:"):
            seats.append(("decision", part.removeprefix("decision").removeprefix(":").strip() or None))
        else:
            raise ValueError(f"unknown seat {part!r}. Use human, llm:<slug>, or decision.")
    if len(seats) != 3:
        raise ValueError(f"a game needs three seats, got {len(seats)}")
    return seats


def pick_puzzles(puzzles: Sequence[Puzzle], rounds: int, seed: int) -> tuple[list[Puzzle], Puzzle]:
    """A seeded draw of main round puzzles, with no repeats, and one bonus puzzle."""
    rng = random.Random(f"puzzles:{seed}")
    main = [p for p in puzzles if not p.bonus]
    bonus = [p for p in puzzles if p.bonus]
    if len(main) < rounds or not bonus:
        raise ValueError(f"need {rounds} main puzzles and a bonus puzzle, got {len(main)} and {len(bonus)}")
    return rng.sample(main, rounds), rng.choice(bonus)


class Show:
    """Prints the game as it happens, pausing after model moves so it reads like the show."""

    def __init__(
        self,
        players: Sequence[Player],
        pause: float,
        thinking: bool,
        show_puzzle: bool = False,
        write: Callable[[str], None] = print,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.players = players
        self.pause = pause
        self.thinking = thinking
        self.show_puzzle = show_puzzle
        self.write = write
        self.sleep = sleep
        humans = [i for i, p in enumerate(players) if isinstance(p, HumanPlayer)]
        self.viewer = humans[0] if len(humans) == 1 else None
        self.names = [self._name(i, p) for i, p in enumerate(players)]
        self.puzzle: Puzzle | None = None

    def _name(self, seat: int, player: Player) -> str:
        if seat == self.viewer:
            return f"Seat {seat + 1} (you)"
        if isinstance(player, DecisionPlayer):
            return f"Seat {seat + 1} ({player.model} + {player.solver.model})"
        return f"Seat {seat + 1} ({player.model if isinstance(player, LLMPlayer) else 'human'})"

    def start(self, state: GameState) -> None:
        self.write(f"Wheel of Fortune, seed {state.seed}")
        for name in self.names:
            self.write(f"  {name}")
        self._banner(state)

    def result(self, state: GameState) -> None:
        result = state.last
        player = self.players[result.seat]
        model = not isinstance(player, HumanPlayer)
        if self.thinking:
            for thought in player.thoughts():
                body = thought.strip().replace("\n", "\n    ")
                self.write(f"    [{self.names[result.seat]}] {body}")
        self.write(describe(result, self.viewer))
        if "turn_cap" in result.events and self.puzzle:
            self.write(f"The answer was {self.puzzle.answer}.")
        if "round_over" in result.events and state.phase is not Phase.GAME_OVER:
            self._banner(state)
        if self.show_puzzle and state.phase is not Phase.GAME_OVER:
            view = public_view(state, self.viewer if self.viewer is not None else state.seat)
            for line in table(view, self.viewer):
                self.write(f"    {line}")
        if model:
            self.sleep(self.pause)

    def _banner(self, state: GameState) -> None:
        starter = seat_name(state.seat, self.viewer)
        if state.round:
            self.puzzle = state.round.puzzle
            self.write(f"\n=== Round {state.round.number} === {starter} {'start' if starter == 'You' else 'starts'}.")
        elif state.bonus:
            self.puzzle = state.bonus.puzzle
            self.write(f"\n=== Bonus round === {starter} {'play' if starter == 'You' else 'plays'} for an envelope.")

    def finish(self, state: GameState, log_path: Path) -> None:
        if state.bonus:
            self.write(
                f"The bonus answer was {state.bonus.puzzle.answer}. "
                f"The envelope held {money(state.bonus.envelope)}."
            )
        self.write("\nFinal totals")
        for name, seat in zip(self.names, state.seats):
            self.write(f"  {name}: {money(seat.total)}")
        for player in self.players:
            if isinstance(player, DecisionPlayer):
                self._usage(player.model, player.usage)
                self._usage(f"{player.solver.model} (solver)", player.solver.usage)
            elif isinstance(player, LLMPlayer):
                self._usage(player.model, player.usage)
        self.write(f"Log: {log_path}")

    def _usage(self, label: str, u) -> None:
        self.write(
            f"  {label}: {u.calls} calls, {u.total_tokens:,} tokens "
            f"({u.cached_tokens:,} read from cache), {u.cost:.4f} credits"
        )


def _arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m rstlne.cli", description="Play Wheel of Fortune in the terminal.")
    parser.add_argument("--seats", required=True, help="three seats: human, llm:<slug>, or decision, comma separated")
    parser.add_argument("--seed", type=int, help="game seed; replaying a seed with the same moves replays the game")
    parser.add_argument("--puzzles", default=str(settings.ROOT / "puzzles" / "dev.json"))
    parser.add_argument("--pause", type=float, help="seconds to pause after each model move")
    parser.add_argument("--show-thinking", action="store_true", help="print each model's raw response")
    parser.add_argument("--show-puzzle", action="store_true", help="print the board, letters, and banks after every move")
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
    if kinds & {"llm", "decision"}:
        load_dotenv(settings.ROOT / ".env")
    if client is None and kinds & {"llm", "decision"}:
        client = OpenRouter()
    if decisions is None and "decision" in kinds:
        decisions = DecisionClient()

    temperature = config["llm"].get("temperature")
    decision = config["decision"]

    def seat(i: int, kind: str, model: str | None) -> Player:
        session = f"{path.stem}-seat{i + 1}"
        if kind == "human":
            return HumanPlayer(i, seconds=config["cli"]["bonus_solve_seconds"])
        if kind == "llm":
            return LLMPlayer(i, model, client, rules, spec, temperature, session)
        solver = LLMPlayer(i, decision["solver_model"], client, rules, spec, temperature, f"{session}-solver")
        return DecisionPlayer(
            i, model or decision["decision_model"], decisions, solver, rules, spec, decision["solve_threshold"], session
        )

    players = [seat(i, kind, model) for i, (kind, model) in enumerate(seats)]
    pause = args.pause if args.pause is not None else config["cli"]["model_pause"]
    show = Show(players, pause, args.show_thinking, args.show_puzzle)

    state = new_game(seed, rules, spec, puzzles, bonus)
    show.start(state)
    with GameLog(path, state, players) as log:
        final = play_game(state, players, log, on_result=show.result)
    show.finish(final, path)
    return final


if __name__ == "__main__":
    main()
