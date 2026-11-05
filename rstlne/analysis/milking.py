"""Milking: every round a bot or hybrid seat knew the answer and spun on, and what came of it.

A seat milks once its known-answer planner chooses to spin (`planner` in the move's log; for logs from before
2026-11-01, a spin at a calibrated confidence at the version's known-answer threshold). From that move the
round is followed to its end: did the seat solve it, and with how much more in the bank; or who took it, and how
the seat lost the wheel first.

    uv run python -m rstlne.analysis.milking 2 3 3b
"""

from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Sequence
from statistics import mean, median

from rstlne.analysis import common

LOST_WHEEL = {"bankrupt", "lose_a_turn", "missing", "repeated", "wrong_solve", "forfeit", "flipped_bankrupt"}


def milked_rounds(game: common.Game) -> list[dict]:
    """One entry per round and seat where a bot or hybrid seat's planner first chose to spin."""
    out = []
    for number, actions in sorted(game.rounds().items()):
        solved = common.solved_by(actions)
        started: set[int] = set()
        for i, a in enumerate(actions):
            seat = a["seat"]
            if seat in started or not game.milks(a):
                continue
            started.add(seat)
            bank = a["state"]["seats"][seat]["bank"]
            entry = {"round": number, "seat": seat, "name": game.names[seat], "bank_then": bank}
            if solved and solved[0] == seat:
                entry.update(outcome="won", gain=solved[1]["state"]["seats"][seat]["bank"] - bank)
            else:
                lost = next((b["result"]["outcome"] for b in actions[i:] if b["seat"] == seat
                             and b["result"]["outcome"] in LOST_WHEEL), None)
                entry.update(outcome="lost", lost_wheel=lost,
                             taker=game.names[solved[0]] if solved else None,
                             taker_kind=game.kind(solved[0]) if solved else None)
            out.append(entry)
    return out


def summarize(rounds: Sequence[dict]) -> dict:
    won = [r for r in rounds if r["outcome"] == "won"]
    lost = [r for r in rounds if r["outcome"] == "lost"]
    return {"rounds": len(rounds), "won": len(won) / len(rounds) if rounds else None,
            "mean_gain": mean(r["gain"] for r in won) if won else None,
            "median_gain": median(r["gain"] for r in won) if won else None,
            "lost_to": Counter(r["taker_kind"] or "nobody" for r in lost),
            "lost_wheel": Counter(r["lost_wheel"] or "-" for r in lost),
            "bank_when_lost": mean(r["bank_then"] for r in lost) if lost else None}


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m rstlne.analysis.milking", description=__doc__.splitlines()[0])
    parser.add_argument("targets", nargs="+", help="lineup ids from lineups.toml, or tournament folders")
    parser.add_argument("--phase", help="the lineups.toml phase (its default when omitted)")
    args = parser.parse_args(argv)
    for name, folder in common.resolve(args.targets, args.phase):
        rounds = [r for g in common.games(folder) for r in milked_rounds(g)]
        s = summarize(rounds)
        print(name)
        if not rounds:
            print("  no milked rounds\n")
            continue
        print(f"  {s['rounds']} rounds milked; won {s['won']:.0%}, adding ${s['mean_gain']:,.0f} on average "
              f"(median ${s['median_gain']:,.0f})" if s["mean_gain"] is not None else f"  {s['rounds']} rounds milked; none won")
        if s["lost_to"]:
            print(f"  lost to: {dict(s['lost_to'])}; how it lost the wheel: {dict(s['lost_wheel'])}; "
                  f"bank it held when milking began, in rounds it lost: ${s['bank_when_lost']:,.0f}")
        print()


if __name__ == "__main__":
    main()
