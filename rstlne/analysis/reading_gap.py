"""Why a player wins the rounds it wins against bots: what the bots lacked on each of those rounds.

For every round the focal seat (an LLM, hybrid, or decision seat) solved:
  - knew it first: a bot or hybrid seat already treated the answer as known (its planner was on) and lost the
    wheel before the focal seat solved; how it lost the wheel is kept
  - otherwise the board the focal seat solved is read with the bot's reader and calibrated:
      - the reader's best answer is wrong
      - right but unsure: below the known-answer threshold
      - sure, but not its turn: the bot would have known it, and the turn was the focal seat's
A board's read needs the bot's word data, so run it where the data is (the server).

    uv run python -m rstlne.analysis.reading_gap 2 3 --version 6
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from collections.abc import Callable, Sequence
from pathlib import Path
from statistics import median

from rstlne.analysis import common
from rstlne.engine.puzzle import normalize
from rstlne.players.bot import calibration, versions

KNEW = "a bot knew it first and lost the wheel"
WRONG = "the bot's reader had another answer"
UNSURE = "right, but the bot wasn't sure"
SURE = "the bot would have known it, but it was the other seat's turn"
CATEGORIES = (WRONG, UNSURE, SURE, KNEW)
FOCAL_KINDS = ("llm", "hybrid", "decision")


def cases(game: common.Game, focal: Callable[[str, str], bool]) -> list[dict]:
    """Each round a focal seat solved: its category when a bot knew it first, else None with the board to read."""
    out = []
    for number, actions in sorted(game.rounds().items()):
        solved = common.solved_by(actions)
        if not solved or not focal(game.names[solved[0]], game.kind(solved[0])):
            continue
        seat, solve = solved
        refuted, knew, how = [], None, None
        for a in actions:
            if a is solve:
                break
            raw = a.get("raw") if isinstance(a.get("raw"), dict) else {}
            if a["action"]["kind"] == "solve" and a["result"]["outcome"] == "wrong_solve" and a["action"].get("answer"):
                try:
                    refuted.append(normalize(a["action"]["answer"]))
                except ValueError:  # a guess no puzzle can hold refutes nothing the reader samples
                    pass
            if knew is None and game.planner_on(a):
                knew = a["seat"]
            if knew is not None and a["seat"] == knew and how is None and a["result"]["outcome"] in (
                    "bankrupt", "lose_a_turn", "missing", "repeated", "wrong_solve", "forfeit", "flipped_bankrupt"):
                how = a["result"]["outcome"]
        rnd = solve["state"]["round"]
        out.append({"round": number, "seat": seat, "name": game.names[seat],
                    "answer": rnd["puzzle"]["answer"], "letters": common.letters_in(rnd["puzzle"]["answer"]),
                    "shown": common.shown(rnd["puzzle"]["answer"], rnd["used"]),
                    "category": KNEW if knew is not None else None, "how": how,
                    "board": None if knew is not None else common.board_of(solve, refuted)})
    return out


LENGTHS = ((0, 18, "17 letters or fewer"), (18, 23, "18 to 22"), (23, 27, "23 to 26"), (27, 99, "27 or more"))


def shares(games: Sequence[common.Game], focal: Callable[[str, str], bool]) -> dict[str, dict]:
    """The focal seats' share of the solved rounds, by round number and by puzzle length."""
    out: dict[str, dict] = {"round": defaultdict(lambda: [0, 0]), "length": defaultdict(lambda: [0, 0])}
    for game in games:
        for number, actions in game.rounds().items():
            solved = common.solved_by(actions)
            if not solved:
                continue
            mine = focal(game.names[solved[0]], game.kind(solved[0]))
            n = common.letters_in(solved[1]["state"]["round"]["puzzle"]["answer"])
            band = next(label for lo, hi, label in LENGTHS if lo <= n < hi)
            for key, value in (("round", number), ("length", band)):
                out[key][value][0] += mine
                out[key][value][1] += 1
    return out


def category(answer: str, read: dict, calibrate: Callable[[float], float], known: float) -> str:
    """What the bot's read of the winning board lacked."""
    if read["best"] != answer:
        return WRONG
    return SURE if calibrate(read["confidence"]) >= known else UNSURE


def summarize(found: Sequence[dict], split: dict[str, dict]) -> dict:
    """Per focal player: rounds won, and per category its share, median board showing, and its detail."""
    players = {}
    for who in sorted({c["name"] for c in found}):
        mine = [c for c in found if c["name"] == who]
        counts = Counter(c["category"] for c in mine)
        cats = {}
        for cat in CATEGORIES:
            inside = [c for c in mine if c["category"] == cat]
            if not inside:
                continue
            row = {"share": round(counts[cat] / len(mine), 4), "rounds": len(inside),
                   "median_shown": round(median(c["shown"] for c in inside), 4)}
            if cat == UNSURE:
                row["median_calibrated"] = round(median(c["calibrated"] for c in inside), 4)
            if cat == KNEW:
                row["how"] = dict(Counter(c["how"] or "-" for c in inside))
            cats[cat] = row
        players[who] = {"rounds": len(mine), "categories": cats}
    return {"players": players,
            "by_round": {str(r): v for r, v in sorted(split["round"].items())},
            "by_length": {label: split["length"][label] for _, _, label in LENGTHS if split["length"].get(label, [0, 0])[1]}}


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m rstlne.analysis.reading_gap", description=__doc__.splitlines()[0])
    parser.add_argument("targets", nargs="+", help="lineup ids from lineups.toml, or tournament folders")
    parser.add_argument("--phase", help="the lineups.toml phase (its default when omitted)")
    parser.add_argument("--version", type=int, help="the bot version whose reader reads the boards; config.toml's by default")
    parser.add_argument("--workers", type=int, default=4, help="processes reading boards")
    parser.add_argument("--out", help="also save the results as JSON here, for analysis.numbers")
    args = parser.parse_args(argv)

    from rstlne import settings, trust
    version = args.version or versions.current(settings.load_config())
    knobs = versions.knobs(version)
    calibrate = calibration.curve(knobs.calibration)
    rules, spec = trust.rules_and_spec()
    focal = lambda n, kind: kind in FOCAL_KINDS  # noqa: E731
    saved = {}
    for name, folder in common.resolve(args.targets, args.phase):
        played = list(common.games(folder))
        found = [c for g in played for c in cases(g, focal)]
        boards = sorted({c["board"] for c in found if c["board"]})
        reads = trust.read_boards(boards, None, knobs, rules, spec, args.workers) if boards else {}
        for c in found:
            if c["category"] is None:
                c["category"] = category(c["answer"], reads[c["board"]], calibrate, knobs.known_answer)
                c["calibrated"] = calibrate(reads[c["board"]]["confidence"])
        result = summarize(found, shares(played, focal))
        saved[name] = result
        print(f"{name}: read with bot v{version}'s reader")
        for who, r in result["players"].items():
            print(f"  {who}: {r['rounds']} rounds won")
            for cat, c in r["categories"].items():
                extra = (f", median calibrated confidence {c['median_calibrated']:.2f}" if "median_calibrated" in c
                         else f", lost the wheel by {c['how']}" if "how" in c else "")
                print(f"    {c['share']:4.0%}  {cat} (median {c['median_shown']:.0%} showing{extra})")
        print("  share of solved rounds by round: " + ", ".join(
            f"round {r} {won / n:.0%} of {n}" for r, (won, n) in result["by_round"].items()))
        print("  by puzzle length: " + ", ".join(
            f"{label} {won / n:.0%} of {n}" for label, (won, n) in result["by_length"].items()))
        print()
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps({"version": version, "lineups": saved}, indent=1))
        print(f"saved {args.out}")


if __name__ == "__main__":
    main()
