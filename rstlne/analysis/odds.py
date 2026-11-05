"""The bot's logged odds against what happened, on every bot and hybrid seat.

1. Steal odds: each time a bot or hybrid seat lost the wheel on a spin (Bankrupt, Lose a Turn), did an opponent
   solve before its next move, as often as the steal odds it logged on that move said? Split into milking (its
   planner on) and still reading.
2. Win chances: from round 3, the win chance it logged for the move it chose, against how often it won the game,
   once per seat and round.

    uv run python -m rstlne.analysis.odds 2 3 3b
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from rstlne.analysis import common

BANDS = (0, 0.2, 0.4, 0.6, 0.8, 1.01)


def band(p: float) -> str:
    return next(f"{a:.1f}-{min(b, 1):.1f}" for a, b in zip(BANDS, BANDS[1:]) if a <= p < b)


def steal_cases(game: common.Game) -> list[dict]:
    out = []
    for number, actions in game.rounds().items():
        for i, a in enumerate(actions):
            raw = a.get("raw") if isinstance(a.get("raw"), dict) else {}
            if (game.kind(a["seat"]) not in ("bot", "hybrid") or a["action"]["kind"] != "spin"
                    or a["result"]["outcome"] not in ("bankrupt", "lose_a_turn") or "p_steal" not in raw):
                continue
            stolen = False
            for later in actions[i + 1:]:
                if later["seat"] == a["seat"]:
                    break
                if later["action"]["kind"] == "solve" and later["result"]["outcome"] == "solved":
                    stolen = True
                    break
            out.append({"p": raw["p_steal"], "stolen": stolen, "milking": "planner" in raw, "round": number})
    return out


def win_cases(game: common.Game) -> list[dict]:
    out, seen = [], set()
    shares = game.winners()
    for number, actions in game.rounds().items():
        for a in actions:
            raw = a.get("raw") if isinstance(a.get("raw"), dict) else {}
            key = (number, a["seat"])
            if (game.kind(a["seat"]) in ("bot", "hybrid") and raw.get("win_mode") and raw.get("chose") in (raw.get("values") or {})
                    and key not in seen):
                seen.add(key)
                out.append({"p": raw["values"][raw["chose"]], "won": shares[a["seat"]], "round": number})
    return out


def _show(title: str, cases: Sequence[dict], outcome: str) -> None:
    if not cases:
        return
    print(f"  {title}: {len(cases)} cases, predicted {sum(c['p'] for c in cases) / len(cases):.0%}, "
          f"happened {sum(c[outcome] for c in cases) / len(cases):.0%}")
    for b in sorted({band(c["p"]) for c in cases}):
        inside = [c for c in cases if band(c["p"]) == b]
        print(f"     {b}: {len(inside):5}  predicted {sum(c['p'] for c in inside) / len(inside):5.0%}"
              f"  happened {sum(c[outcome] for c in inside) / len(inside):5.0%}")


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m rstlne.analysis.odds", description=__doc__.splitlines()[0])
    parser.add_argument("targets", nargs="+", help="lineup ids from lineups.toml, or tournament folders")
    parser.add_argument("--phase", help="the lineups.toml phase (its default when omitted)")
    args = parser.parse_args(argv)
    for name, folder in common.resolve(args.targets, args.phase):
        played = list(common.games(folder))
        steals = [c for g in played for c in steal_cases(g)]
        print(name)
        _show("steal odds when a milking bot lost the wheel", [c for c in steals if c["milking"]], "stolen")
        _show("steal odds when a reading bot lost the wheel", [c for c in steals if not c["milking"]], "stolen")
        _show("win chance of the chosen move, from round 3", [c for g in played for c in win_cases(g)], "won")
        print()


if __name__ == "__main__":
    main()
