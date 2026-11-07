"""Every number the paper cites, in one file: per player stats, set by set comparisons, the bonus test, letters.

    uv run python -m rstlne.analysis.numbers --out paper/numbers.json

It reads the finished games of each lineup in a lineups.toml phase (its default unless --phase names one), so
the numbers are the same every run: intervals resample whole sets with tournament.bootstrap's fixed seed. Two
analyses need the bot's word data and run separately on the server; their saved results are folded in when present:

    uv run python -m rstlne.analysis.letters read <ids> --out logs/analysis/letters-v6.json
    uv run python -m rstlne.analysis.reading_gap <ids> --out logs/analysis/reading-gap-v6.json
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import tomllib
from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median, pstdev

from rstlne import settings, tournament
from rstlne.analysis import common, letters as letters_mod
from rstlne.engine.puzzle import LETTERS

VOWELS = set("AEIOU")
ANALYSIS = settings.ROOT / "logs" / "analysis"
BONUSTEST = settings.ROOT / "logs" / "bonustest"

# The set by set comparisons the paper cites: (label, (lineup, entrant), (lineup, entrant)), the first minus the second.
SOL, TERRA, LUNA, HAIKU = "llm:openai/gpt-6.1-sol", "llm:openai/gpt-6.1-terra", "llm:openai/gpt-6-luna", "llm:anthropic/claude-haiku-5.5"
DEEPSEEK, QWEN = "llm:deepseek/deepseek-v4.1-flash-1017", "llm:qwen/qwen3.8-flash"
LUNA_HYBRID, HAIKU_HYBRID = "hybrid:openai/gpt-6-luna", "hybrid:anthropic/claude-haiku-5.5"
LUNA_DEC, D1 = "decision:openai/gpt-6-luna-decisions", "decision:liquid/d1-ultra"
PAIRS = [
    ("Terra minus Sol", ("2t", TERRA), ("2", SOL)),
    ("Sol minus the Luna hybrid", ("2", SOL), ("3", LUNA_HYBRID)),
    ("Terra minus the Luna hybrid", ("2t", TERRA), ("3", LUNA_HYBRID)),
    ("Luna hybrid minus Luna alone", ("3", LUNA_HYBRID), ("3b", LUNA)),
    ("Haiku hybrid minus Haiku alone", ("3f", HAIKU_HYBRID), ("3d", HAIKU)),
    ("Luna hybrid minus Haiku hybrid", ("3", LUNA_HYBRID), ("3f", HAIKU_HYBRID)),
    ("DeepSeek minus Luna", ("3c", DEEPSEEK), ("3b", LUNA)),
    ("DeepSeek minus Qwen 3.8 Flash", ("3c", DEEPSEEK), ("3r", QWEN)),
    ("Qwen 3.8 Flash minus Luna", ("3r", QWEN), ("3b", LUNA)),
    ("Qwen 3.8 Flash minus Haiku", ("3r", QWEN), ("3d", HAIKU)),
    ("Luna minus Haiku", ("3b", LUNA), ("3d", HAIKU)),
    ("Luna alone minus the Luna Decisions seat", ("3b", LUNA), ("d2", LUNA_DEC)),
    ("Luna Decisions seat minus d1-ultra seat", ("d2", LUNA_DEC), ("d1", D1)),
]


def summary(xs: Sequence[float]) -> dict:
    """Mean, standard deviation, median, and the 10th and 90th percentiles."""
    xs = sorted(xs)
    at = lambda p: xs[min(len(xs) - 1, int(p * len(xs)))] if xs else None  # noqa: E731
    return {"n": len(xs), "mean": _r(mean(xs)) if xs else None, "sd": _r(pstdev(xs)) if len(xs) > 1 else None,
            "median": _r(median(xs)) if xs else None, "p10": _r(at(0.1)), "p90": _r(at(0.9))}


def _r(x, places: int = 4):
    return None if x is None else round(x, places)


def places(totals: Sequence[float]) -> list[list[float]]:
    """Each seat's share of 1st, 2nd and 3rd: tied totals split the places they span evenly."""
    out = []
    for t in totals:
        above, tied = sum(x > t for x in totals), totals.count(t)
        out.append([1 / tied if above <= q < above + tied else 0.0 for q in range(3)])
    return out


def set_shares(folder: Path) -> dict[str, dict[int, float]]:
    """Each entrant's mean share of the win in each set, ties split."""
    per: dict[str, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))
    for g in common.games(folder):
        for seat, w in enumerate(g.winners()):
            per[g.names[seat]][g.set].append(w)
    return {n: {s: mean(v) for s, v in sets.items()} for n, sets in per.items()}


def pair_of(a: dict[int, float], b: dict[int, float]) -> dict:
    """The mean of a minus b over the sets both played, with a 95% interval from resampling those sets."""
    diffs = [a[k] - b[k] for k in sorted(a.keys() & b.keys())]
    ci = tournament.bootstrap(diffs, lambda rows: sum(rows) / len(rows)) if diffs else None
    return {"sets": len(diffs), "diff": _r(mean(diffs)) if diffs else None, "ci95": list(ci) if ci else None}


def lineup(folder: Path) -> dict:
    """Every per entrant stat of one lineup, from its finished games."""
    rep = tournament.report(folder)
    E: dict[str, dict] = defaultdict(lambda: defaultdict(list))
    n_games = 0
    for g in common.games(folder):
        n_games += 1
        tot, s = g.summary["totals"], g.summary
        bonus = s.get("bonus") or {}
        usage = s.get("usage_by_seat") or [{}] * 3
        for seat, (name, share) in enumerate(zip(g.names, places(tot))):
            d = E[name]
            d["kind"] = g.kind(seat)
            d["share"].append(share)
            d["place"].append(sum((q + 1) * x for q, x in enumerate(share)))
            won_bonus = bonus.get("seat") == seat and bonus.get("solved")
            d["main"].append(tot[seat] - (bonus["envelope"] if won_bonus else 0))
            d["total"].append(tot[seat])
            d["cost"].append((usage[seat] or {}).get("cost") or 0.0)
            d["output_tokens"].append((usage[seat] or {}).get("completion_tokens") or 0)
            for k in ("rounds_won", "tries", "wrong", "cons", "cons_hit", "vow", "vow_hit", "spins", "bankrupt",
                      "lose_a_turn", "lost_to_bankrupt"):
                d[k].append(0)
        for number, actions in g.rounds().items():
            for a in actions:
                d, kind, res, st = E[g.names[a["seat"]]], a["action"]["kind"], a["result"], a["state"]
                answer, used = st["round"]["puzzle"]["answer"], st["round"]["used"]
                if kind == "spin":
                    d["spins"][-1] += 1
                    if res["outcome"] in ("bankrupt", "flipped_bankrupt"):
                        d["bankrupt"][-1] += 1
                        d["lost_to_bankrupt"][-1] += st["seats"][a["seat"]]["bank"]
                    d["lose_a_turn"][-1] += res["outcome"] == "lose_a_turn"
                elif kind in ("call_consonant", "call_letter", "buy_vowel") and a["action"].get("letter") in LETTERS:
                    letter = a["action"]["letter"]
                    k = "vow" if letter in VOWELS else "cons"
                    c = answer.count(letter)
                    d[k][-1] += 1
                    d[k + "_hit"][-1] += c > 0
                    d[k + "_copies"].append(c)
                    d[k + "_board"].append(common.shown(answer, used))
                elif kind == "solve":
                    d["tries"][-1] += 1
                    shown = common.shown(answer, used)
                    if res["outcome"] == "solved":
                        d["rounds_won"][-1] += 1
                        d["round_money"].append(res.get("earned") or 0)
                        d["round_money_r" + str(number)].append(res.get("earned") or 0)
                        d["shown_right"].append(shown)
                    else:
                        d["wrong"][-1] += 1
                        d["shown_wrong"].append(shown)

    def letter_stats(d, k):
        n = sum(d[k])
        return {"per_game": _r(n / len(d["place"])), "hit_rate": _r(sum(d[k + "_hit"]) / n) if n else None,
                "copies": summary(d[k + "_copies"]), "copies_when_hit": summary([c for c in d[k + "_copies"] if c]),
                "board_when_called": summary(d[k + "_board"])}

    entrants = {}
    for e in rep["entrants"]:
        d = E[e["entrant"]]
        g = len(d["place"])
        per_game = lambda k: _r(sum(d[k]) / g)  # noqa: E731
        tries = sum(d["tries"])
        entrants[e["entrant"]] = {
            "kind": d["kind"], "games": g,
            "win_rate": e["win_rate"], "win_ci95": e["ci95"]["win_rate"], "win_rate_by_seat": e["win_rate_by_seat"],
            "place": summary(d["place"]), "places": [_r(sum(x[q] for x in d["share"]) / g) for q in range(3)],
            "rounds_won_per_game": per_game("rounds_won"), "solve_tries_per_game": per_game("tries"),
            "solve_accuracy": _r(sum(d["rounds_won"]) / tries) if tries else None,
            "solve_accuracy_ci95": e["ci95"]["solve_accuracy"], "wrong_solves_per_game": per_game("wrong"),
            "shown_at_correct_solve": summary(d["shown_right"]), "shown_at_wrong_solve": summary(d["shown_wrong"]),
            "money_per_round_won": summary(d["round_money"]),
            "money_per_round_won_by_round": {r: summary(d["round_money_r" + r]) for r in "1234"},
            "main_winnings": summary(d["main"]), "main_winnings_ci95": e["ci95"]["avg_main_winnings"],
            "total_winnings": summary(d["total"]),
            "consonants": letter_stats(d, "cons"), "vowels": letter_stats(d, "vow"),
            "spins_per_game": per_game("spins"), "bankrupts_per_game": per_game("bankrupt"),
            "lose_a_turn_per_game": per_game("lose_a_turn"), "lost_to_bankrupt_per_game": per_game("lost_to_bankrupt"),
            "bonus_reached": e["bonus_reached"], "bonus_won": e["bonus_won"],
            "invalid_per_game": e["invalid_per_game"], "invalid": e["invalid"],
            "cost": summary(d["cost"]) if any(d["cost"]) else None,
            "output_tokens_per_game": summary(d["output_tokens"]) if any(d["output_tokens"]) else None,
        }
    return {"games": n_games, "sets": rep["sets"], "puzzles": Path(rep["puzzles"]).name if rep["puzzles"] else None,
            "cost": _r(sum(e["cost"] for e in rep["entrants"]), 6), "entrants": entrants,
            "generated_by": rep.get("generated_by"), "pairwise": rep.get("pairwise", [])}


def letters_summary(data: dict) -> dict:
    """The letter judgments per lineup and player (copies of one player in a lineup folded together), by kind."""
    agg: dict[tuple, list] = defaultdict(list)
    for row in data["rows"]:
        s = letters_mod.score(row)
        if s:
            agg[(row["lineup"], row["player"].partition(" #")[0], row["kind"])].append(s)
    out: dict = defaultdict(lambda: defaultdict(dict))
    for (lid, player, kind), xs in sorted(agg.items()):
        early = [x for x in xs if x["shown"] < letters_mod.EARLY]
        avg = lambda key, rows=xs: _r(mean(float(r[key]) for r in rows)) if rows else None  # noqa: E731
        out[lid][player][kind] = {"n": len(xs), "judge": avg("p"), "hit": avg("hit"), "top": avg("top"),
                                  "top_early": avg("top", early), "n_early": len(early), "copies": avg("copies"),
                                  "rule_hit": avg("rule_hit"), "rule_copies": avg("rule_copies")}
    return {"judge_version": data.get("judge_version"), "rows": json.loads(json.dumps(out))}


def bonus_report(path: Path | None) -> dict | None:
    if path is None or not Path(path).exists():
        return None
    return {"folder": Path(path).parent.name, **json.loads(Path(path).read_text())}


def _latest_bonus(puzzles: str | None, seed: int | None) -> Path | None:
    if not puzzles:
        return None
    found = sorted(BONUSTEST.glob(f"{Path(puzzles).stem}-seed{seed}-*/report.json")) if seed is not None else []
    return found[-1] if found else None


def _commit() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=settings.ROOT, capture_output=True,
                              text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def build(phase: str | None = None, toml: Path = common.LINEUPS, *, pairs=PAIRS, bonus: Path | None = None,
          letters: Path | None = None, gap: Path | None = None) -> dict:
    """The whole file: meta, lineups, pairs, and the bonus test, letters and reading gap where they've been run."""
    phase = phase or tomllib.loads(Path(toml).read_text())["default"]
    meta_lineups = common.lineups(phase, toml)
    out_lineups, shares = {}, {}
    for lid, m in meta_lineups.items():
        if not any(True for _ in common.games(m["folder"])):
            continue
        out_lineups[lid] = {"label": m.get("label"), "note": m.get("note"), "folder": m["folder"].name, **lineup(m["folder"])}
        shares[lid] = set_shares(m["folder"])
    out_pairs = []
    for label, (la, ea), (lb, eb) in pairs:
        if la in shares and lb in shares and ea in shares[la] and eb in shares[lb]:
            out_pairs.append({"label": label, "a": [la, ea], "b": [lb, eb], **pair_of(shares[la][ea], shares[lb][eb])})
    seeds = {m.group(1) for v in out_lineups.values() if (m := re.match(r"seed(\d+)-", v["folder"]))}
    seed = int(seeds.pop()) if len(seeds) == 1 else None
    decks = {v["puzzles"] for v in out_lineups.values()}
    deck = decks.pop() if len(decks) == 1 else None
    made_by = {json.dumps(v.get("generated_by"), sort_keys=True) for v in out_lineups.values()}
    letter_data = json.loads(Path(letters).read_text()) if letters and Path(letters).exists() else None
    return {
        "meta": {"phase": phase, "made": datetime.now(timezone.utc).isoformat(timespec="seconds"), "commit": _commit(),
                 "lineups": list(out_lineups), "deck": deck, "seed": seed,
                 "deck_made_by": json.loads(made_by.pop()) if len(made_by) == 1 else None,
                 "resamples": tournament.RESAMPLES, "interval": "95%, percentile bootstrap over whole sets, seed 0"},
        "lineups": out_lineups,
        "pairs": out_pairs,
        "bonus": bonus_report(bonus),
        "letters": letters_summary(letter_data) if letter_data else None,
        "reading_gap": json.loads(Path(gap).read_text()) if gap and Path(gap).exists() else None,
    }


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m rstlne.analysis.numbers", description=__doc__.splitlines()[0])
    parser.add_argument("--out", required=True, help="where to write the JSON")
    parser.add_argument("--phase", help="the lineups.toml phase (its default when omitted)")
    parser.add_argument("--bonus", help="a bonus test report.json; by default the latest on the phase's deck and seed")
    parser.add_argument("--letters", help="saved letter judgments (default logs/analysis/letters-<phase>.json)")
    parser.add_argument("--gap", help="saved reading gap (default logs/analysis/reading-gap-<phase>.json)")
    args = parser.parse_args(argv)
    phase = args.phase or tomllib.loads(common.LINEUPS.read_text())["default"]
    out = build(phase, letters=Path(args.letters) if args.letters else ANALYSIS / f"letters-{phase}.json",
                gap=Path(args.gap) if args.gap else ANALYSIS / f"reading-gap-{phase}.json", bonus=None)
    out["bonus"] = bonus_report(Path(args.bonus) if args.bonus else _latest_bonus(out["meta"]["deck"], out["meta"]["seed"]))
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=1))
    missing = [k for k in ("bonus", "letters", "reading_gap") if out[k] is None]
    print(f"wrote {args.out}: {len(out['lineups'])} lineups, {len(out['pairs'])} pairs"
          + (f"; not yet run: {', '.join(missing)}" if missing else ""))


if __name__ == "__main__":
    main()
