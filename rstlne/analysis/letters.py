"""Letter choice: every consonant called and vowel bought, judged by the bot's reader on the board as it stood.

Two steps. `read` judges every board (the bot's word data needed, so on the server) and saves each decision
with the reader's odds for every open letter. `report` scores them per player: how often its letters hit, against
what the reader expected and against calling in English frequency order.

    uv run python -m rstlne.analysis.letters read 2 3 3b --out logs/analysis/letters-v6.json
    uv run python -m rstlne.analysis.letters report logs/analysis/letters-v6.json
"""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from rstlne.analysis import common
from rstlne.engine.puzzle import LETTERS, Puzzle, normalize

VOWELS = set("AEIOU")
CONSONANT_ORDER = "TNSHRDLCMWFGYPBVKJXQZ"  # English text frequency
VOWEL_ORDER = "EAOIU"
TOP = 0.02  # within this much hit chance of the best open letter counts as a top pick
EARLY = 0.4  # boards under this share showing count as early


def decisions(game: common.Game, lineup: str) -> list[dict]:
    """Each letter a seat chose in the main rounds, with the board before it: answer, category, used, refuted."""
    out = []
    for number, actions in sorted(game.rounds().items()):
        refuted: list[str] = []
        for a in actions:
            kind = a["action"]["kind"]
            if kind in ("call_consonant", "buy_vowel", "call_letter") and a["action"].get("letter"):
                rnd = a["state"]["round"]
                letter = a["action"]["letter"]
                out.append({"lineup": lineup, "game": game.path.name, "player": game.names[a["seat"]],
                            "kind": "vowel" if letter in VOWELS else "consonant", "letter": letter,
                            "board": [rnd["puzzle"]["answer"], rnd["puzzle"]["category"], sorted(rnd["used"]), list(refuted)],
                            "count": rnd["puzzle"]["answer"].count(letter)})
            if kind == "solve" and a["result"]["outcome"] == "wrong_solve" and a["action"].get("answer"):
                try:
                    refuted.append(normalize(a["action"]["answer"]))
                except ValueError:
                    pass
    return out


def score(row: dict) -> dict | None:
    """One decision against the judge's odds: its hit chance, the best open letter's, the frequency rule's pick."""
    order = VOWEL_ORDER if row["kind"] == "vowel" else CONSONANT_ORDER
    options = {c: v for c, v in row["judge"].items() if c in order}
    if row["letter"] not in options:
        return None
    p, n = options[row["letter"]]
    best_p = max(v[0] for v in options.values())
    rule = next(c for c in order if c in options)
    answer, _, used, _ = row["board"]
    return {"p": p, "best_p": best_p, "top": p >= best_p - TOP, "hit": row["count"] > 0, "copies": row["count"],
            "rule_hit": rule in answer, "rule_copies": answer.count(rule), "shown": common.shown(answer, used)}


def _read(board) -> dict:
    from rstlne import selfplay
    w = selfplay._worker
    answer, category, used, refuted = board
    view = selfplay.view_of(Puzzle(category, answer), frozenset(used), w["rules"], w["spec"])
    belief = w["reader"].read(view, frozenset(refuted))
    return {c: (belief.stats(c).p_hit, belief.stats(c).count) for c in LETTERS if c not in used}


def read(targets: Sequence[str], out: Path, version: int | None, workers: int, phase: str | None) -> None:
    from rstlne import selfplay, settings, trust
    from rstlne.players.bot import versions
    rows = [r for name, folder in common.resolve(targets, phase) for g in common.games(folder) for r in decisions(g, name)]
    boards = sorted({json.dumps(r["board"]) for r in rows})
    print(f"{len(rows)} letter decisions on {len(boards)} distinct boards", flush=True)
    version = version or versions.current(settings.load_config())
    rules, spec = trust.rules_and_spec()
    reads = {}
    with ProcessPoolExecutor(workers, initializer=selfplay._start_worker,
                             initargs=(selfplay._make_reader, versions.knobs(version), rules, spec)) as pool:
        for k, (b, r) in enumerate(zip(boards, pool.map(_read, [json.loads(b) for b in boards], chunksize=16)), 1):
            reads[b] = r
            if k % 2000 == 0:
                print(f"read {k} of {len(boards)}", flush=True)
    for r in rows:
        r["judge"] = reads[json.dumps(r["board"])]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"judge_version": version, "rows": rows}))
    print(f"saved {out}")


def report(path: Path) -> None:
    data = json.loads(Path(path).read_text())
    agg: dict[tuple, list] = defaultdict(list)
    for r in data["rows"]:
        s = score(r)
        if s:
            agg[(r["player"], r["kind"])].append(s)
            agg[(r["player"], r["kind"], "early" if s["shown"] < EARLY else "late")].append(s)
    mean = lambda xs: sum(xs) / len(xs)  # noqa: E731
    players = sorted({k[0] for k in agg}, key=lambda p: -len(agg.get((p, "consonant"), [])))
    print(f"judged by bot v{data['judge_version']}'s reader")
    for kind in ("consonant", "vowel"):
        print(f"\n{kind.upper()}S")
        print(f"{'player':<34}{'n':>7}{'judge hit':>10}{'hit':>7}{'+/-':>6}{'top pick':>9}{'copies':>8}"
              f"{'rule hit':>9}{'rule cp':>8}{'early top':>10}")
        for pl in players:
            xs = agg.get((pl, kind))
            if not xs or len(xs) < 30:
                continue
            early = agg.get((pl, kind, "early"), [])
            hit, judged = mean([x["hit"] for x in xs]), mean([x["p"] for x in xs])
            print(f"{pl:<34}{len(xs):>7}{judged:>10.1%}{hit:>7.1%}{hit - judged:>+6.0%}{mean([x['top'] for x in xs]):>9.0%}"
                  f"{mean([x['copies'] for x in xs]):>8.2f}{mean([x['rule_hit'] for x in xs]):>9.1%}"
                  f"{mean([x['rule_copies'] for x in xs]):>8.2f}{(mean([x['top'] for x in early]) if early else 0):>10.0%}")


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m rstlne.analysis.letters", description=__doc__.splitlines()[0])
    jobs = parser.add_subparsers(dest="job", required=True)
    r = jobs.add_parser("read", help="judge every letter decision's board with the bot's reader")
    r.add_argument("targets", nargs="+", help="lineup ids from lineups.toml, or tournament folders")
    r.add_argument("--out", required=True)
    r.add_argument("--version", type=int, help="the judging reader's bot version; config.toml's by default")
    r.add_argument("--workers", type=int, default=int(os.environ.get("WORKERS", 4)))
    r.add_argument("--phase", help="the lineups.toml phase (its default when omitted)")
    p = jobs.add_parser("report", help="score the judged decisions per player")
    p.add_argument("path")
    args = parser.parse_args(argv)
    if args.job == "read":
        read(args.targets, Path(args.out), args.version, args.workers, args.phase)
    else:
        report(Path(args.path))


if __name__ == "__main__":
    main()
