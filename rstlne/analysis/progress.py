"""Win rates so far, with intervals from resampling sets: finished games only, so safe while a lineup plays.

    uv run python -m rstlne.analysis.progress 2 3 3b
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from rstlne.analysis import common
from rstlne.tournament import report


def lines(name: str, folder: Path) -> list[str]:
    r = report(folder)
    if not r.get("entrants"):
        return [f"{name}: no finished games yet"]
    cost = sum(e.get("cost") or 0 for e in r["entrants"])
    out = [f"{name}  on {Path(r['puzzles']).name}  ({r['games']} games in {len(r.get('per_set', []))} sets, ${cost:.2f})"]
    for e in r["entrants"]:
        lo, hi = e["ci95"]["win_rate"]
        out.append(f"  {e['entrant']:42} wins {e['win_rate']:6.1%} ({lo:.0%} to {hi:.0%})  avg total ${e['avg_total']:>9,.0f}"
                   f"  solves right {e['solve_accuracy']:.0%}")
    for p in r["pairwise"]:
        lo, hi = p["ci95"]
        out.append(f"  {p['a']} minus {p['b']}: {p['win_rate_gap'] * 100:+.1f} points ({lo * 100:+.1f} to {hi * 100:+.1f})")
    return out


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m rstlne.analysis.progress", description=__doc__.splitlines()[0])
    parser.add_argument("targets", nargs="+", help="lineup ids from lineups.toml, or tournament folders")
    parser.add_argument("--phase", help="the lineups.toml phase (its default when omitted)")
    args = parser.parse_args(argv)
    for name, folder in common.resolve(args.targets, args.phase):
        print("\n".join(lines(name, folder)) + "\n")


if __name__ == "__main__":
    main()
