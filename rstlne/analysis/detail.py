"""Per entrant detail: rounds won, the bank at a winning solve, the board showing then, and wrong solves.

    uv run python -m rstlne.analysis.detail 2 3 3b          # lineup ids from lineups.toml, or folders
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path
from statistics import median

from rstlne.analysis import common


def seat_stats(folder: Path) -> dict[str, dict]:
    """For each entrant: games, rounds won, wrong solves, and the median bank and board showing at its correct solves."""
    raw: dict[str, dict] = defaultdict(lambda: {"games": 0, "rounds_won": 0, "wrong_solves": 0, "banks": [], "shown": []})
    for game in common.games(folder):
        for name in set(game.names):
            raw[name]["games"] += game.names.count(name)
        for actions in game.rounds().values():
            for a in actions:
                if a["action"]["kind"] != "solve":
                    continue
                name = game.names[a["seat"]]
                if a["result"]["outcome"] == "solved":
                    rnd = a["state"]["round"]
                    raw[name]["rounds_won"] += 1
                    raw[name]["banks"].append(a["state"]["seats"][a["seat"]]["bank"])
                    raw[name]["shown"].append(common.shown(rnd["puzzle"]["answer"], rnd["used"]))
                elif a["result"]["outcome"] == "wrong_solve":
                    raw[name]["wrong_solves"] += 1
    return {name: {"games": r["games"], "rounds_won": r["rounds_won"], "wrong_solves": r["wrong_solves"],
                   "median_bank": median(r["banks"]) if r["banks"] else None,
                   "median_shown": median(r["shown"]) if r["shown"] else None}
            for name, r in raw.items()}


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m rstlne.analysis.detail", description=__doc__.splitlines()[0])
    parser.add_argument("targets", nargs="+", help="lineup ids from lineups.toml, or tournament folders")
    parser.add_argument("--phase", help="the lineups.toml phase (its default when omitted)")
    args = parser.parse_args(argv)
    for name, folder in common.resolve(args.targets, args.phase):
        print(name)
        for entrant, s in seat_stats(folder).items():
            g = s["games"]
            bank = f"${s['median_bank']:,.0f}" if s["median_bank"] is not None else "-"
            shown = f"{s['median_shown']:.0%}" if s["median_shown"] is not None else "-"
            print(f"  {entrant:34} rounds won a game {s['rounds_won'] / g:.2f}  median bank at a winning solve {bank:>7}"
                  f"  board showing then {shown:>4}  wrong solves a game {s['wrong_solves'] / g:.2f}")
        print()


if __name__ == "__main__":
    main()
