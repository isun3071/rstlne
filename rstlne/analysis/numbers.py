"""Every number the paper cites, in one file: per player stats, set by set comparisons, the bonus test, letters.

    uv run python -m rstlne.analysis.numbers --out paper/numbers.json

It reads the finished games of each lineup in a lineups.toml phase (its default unless --phase names one), so
the numbers are the same every run: intervals resample whole sets with tournament.bootstrap's fixed seed. Two
analyses need the bot's word data and run separately on the server; their saved results are folded in when present:

    uv run python -m rstlne.analysis.letters read <ids> --out logs/analysis/letters-v6.json
    uv run python -m rstlne.analysis.reading_gap <ids> --out logs/analysis/reading-gap-v6.json

The side tests are folded in the same way from their saved results: the bonus test on aired puzzles (private.json),
the memory probe, Blatt's 15 hardest bonus puzzles, and the bot's self-play variants (see MEMORY, BLATT, VARIANTS).
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
from rstlne.analysis import common, letters as letters_mod, play
from rstlne.engine.puzzle import LETTERS

VOWELS = set("AEIOU")
ANALYSIS = settings.ROOT / "logs" / "analysis"
BONUSTEST = settings.ROOT / "logs" / "bonustest"

# The set by set comparisons the paper cites: (label, (lineup, entrant), (lineup, entrant)), the first minus the second.
SOL, TERRA, LUNA, HAIKU = "llm:openai/gpt-6.1-sol", "llm:openai/gpt-6.1-terra", "llm:openai/gpt-6-luna", "llm:anthropic/claude-haiku-5.5"
DEEPSEEK, QWEN = "llm:deepseek/deepseek-v4.1-flash-1017", "llm:qwen/qwen3.8-flash"
EMBER = "llm:meta/muse-ember"
LUNA_HYBRID, HAIKU_HYBRID = "hybrid:openai/gpt-6-luna", "hybrid:anthropic/claude-haiku-5.5"
TERRA_HYBRID = "hybrid:openai/gpt-6.1-terra"
FULL_TRUST = "+trust_fit"  # the hybrid variant that takes a fitting answer as the answer
LUNA_DEC, D1, JEV = "decision:openai/gpt-6-luna-decisions", "decision:liquid/d1-ultra", "decision:typesafe/jev-1.14"
GEMINI_DEC = "decision:google/gemini-decision-1"
HAIKU_WRITES = "@anthropic/claude-haiku-5.5"
TERRA_WRITES = "@openai/gpt-6.1-terra"  # a strong reader as the solver: can it rescue a weak decider?  # a decision seat whose answers Haiku writes, in place of Luna
PAIRS = [
    ("Terra minus Sol", ("2t", TERRA), ("2", SOL)),
    ("Sol minus the Luna hybrid", ("2", SOL), ("3", LUNA_HYBRID)),
    ("Terra minus the Luna hybrid", ("2t", TERRA), ("3", LUNA_HYBRID)),
    ("Luna hybrid minus Luna alone", ("3", LUNA_HYBRID), ("3b", LUNA)),
    ("Haiku hybrid minus Haiku alone", ("3f", HAIKU_HYBRID), ("3d", HAIKU)),
    ("Luna hybrid minus Haiku hybrid", ("3", LUNA_HYBRID), ("3f", HAIKU_HYBRID)),
    ("Terra hybrid minus Terra alone", ("3t", TERRA_HYBRID), ("2t", TERRA)),
    ("Terra hybrid minus Sol", ("3t", TERRA_HYBRID), ("2", SOL)),
    ("Terra hybrid minus Luna hybrid", ("3t", TERRA_HYBRID), ("3", LUNA_HYBRID)),
    ("Terra full trust minus Terra hybrid", ("3tf", TERRA_HYBRID + FULL_TRUST), ("3t", TERRA_HYBRID)),
    ("Terra full trust minus Terra alone", ("3tf", TERRA_HYBRID + FULL_TRUST), ("2t", TERRA)),
    ("Luna full trust minus Luna hybrid", ("3lf", LUNA_HYBRID + FULL_TRUST), ("3", LUNA_HYBRID)),
    ("Luna full trust minus Luna alone", ("3lf", LUNA_HYBRID + FULL_TRUST), ("3b", LUNA)),
    ("Terra full trust minus Luna full trust", ("3tf", TERRA_HYBRID + FULL_TRUST), ("3lf", LUNA_HYBRID + FULL_TRUST)),
    ("DeepSeek minus Luna", ("3c", DEEPSEEK), ("3b", LUNA)),
    ("DeepSeek minus Qwen 3.8 Flash", ("3c", DEEPSEEK), ("3r", QWEN)),
    ("Qwen 3.8 Flash minus Luna", ("3r", QWEN), ("3b", LUNA)),
    ("Qwen 3.8 Flash minus Haiku", ("3r", QWEN), ("3d", HAIKU)),
    ("DeepSeek minus Ember", ("3c", DEEPSEEK), ("3m", EMBER)),
    ("Ember minus Qwen 3.8 Flash", ("3m", EMBER), ("3r", QWEN)),
    ("Ember minus Luna", ("3m", EMBER), ("3b", LUNA)),
    ("Ember minus Haiku", ("3m", EMBER), ("3d", HAIKU)),
    ("Luna minus Haiku", ("3b", LUNA), ("3d", HAIKU)),
    ("Luna alone minus the Luna Decisions seat", ("3b", LUNA), ("d2", LUNA_DEC)),
    ("Luna Decisions seat minus d1-ultra seat", ("d2", LUNA_DEC), ("d1", D1)),
    ("Luna alone minus the Jev seat", ("3b", LUNA), ("dj", JEV)),
    ("Luna Decisions seat minus Jev seat", ("d2", LUNA_DEC), ("dj", JEV)),
    ("Jev seat minus d1-ultra seat", ("dj", JEV), ("d1", D1)),
    ("Luna Decisions seat with Haiku writing minus with Luna writing", ("d2h", LUNA_DEC + HAIKU_WRITES), ("d2", LUNA_DEC)),
    ("d1-ultra seat with Haiku writing minus with Luna writing", ("d1h", D1 + HAIKU_WRITES), ("d1", D1)),
    ("Jev seat with Haiku writing minus with Luna writing", ("djh", JEV + HAIKU_WRITES), ("dj", JEV)),
    ("Haiku alone minus the Luna Decisions seat with Haiku writing", ("3d", HAIKU), ("d2h", LUNA_DEC + HAIKU_WRITES)),
    ("Haiku alone minus the d1-ultra seat with Haiku writing", ("3d", HAIKU), ("d1h", D1 + HAIKU_WRITES)),
    ("Haiku alone minus the Jev seat with Haiku writing", ("3d", HAIKU), ("djh", JEV + HAIKU_WRITES)),
    ("Luna alone minus the Gemini Decision seat", ("3b", LUNA), ("dg", GEMINI_DEC)),
    ("Luna Decisions seat minus Gemini Decision seat", ("d2", LUNA_DEC), ("dg", GEMINI_DEC)),
    ("Gemini Decision seat with Haiku writing minus with Luna writing", ("dgh", GEMINI_DEC + HAIKU_WRITES), ("dg", GEMINI_DEC)),
    ("Haiku alone minus the Gemini Decision seat with Haiku writing", ("3d", HAIKU), ("dgh", GEMINI_DEC + HAIKU_WRITES)),
    ("Luna Decisions seat with Terra writing minus with Luna writing", ("d2t", LUNA_DEC + TERRA_WRITES), ("d2", LUNA_DEC)),
    ("d1-ultra seat with Terra writing minus with Luna writing", ("d1t", D1 + TERRA_WRITES), ("d1", D1)),
    ("Jev seat with Terra writing minus with Luna writing", ("djt", JEV + TERRA_WRITES), ("dj", JEV)),
    ("Gemini Decision seat with Terra writing minus with Luna writing", ("dgt", GEMINI_DEC + TERRA_WRITES), ("dg", GEMINI_DEC)),
    ("Terra alone minus the Luna Decisions seat with Terra writing", ("2t", TERRA), ("d2t", LUNA_DEC + TERRA_WRITES)),
    ("Terra alone minus the d1-ultra seat with Terra writing", ("2t", TERRA), ("d1t", D1 + TERRA_WRITES)),
    ("Terra alone minus the Jev seat with Terra writing", ("2t", TERRA), ("djt", JEV + TERRA_WRITES)),
    ("Terra alone minus the Gemini Decision seat with Terra writing", ("2t", TERRA), ("dgt", GEMINI_DEC + TERRA_WRITES)),
    ("Gemini Decision seat with Terra writing minus Luna alone", ("dgt", GEMINI_DEC + TERRA_WRITES), ("3b", LUNA)),
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


def pool_seats(E: dict, names: Sequence[str]) -> dict | None:
    """Several seats as one player, every game, round and solve of theirs together: how a lineup's two bots are cited
    ("a bot"), and how the charts draw them."""
    if not names:
        return None
    cat = lambda k: [x for n in names for x in E[n][k]]  # noqa: E731
    games, won, tries = len(cat("rounds_won")), sum(cat("rounds_won")), sum(cat("tries"))
    return {"seats": len(names), "seat_games": games, "rounds_won_per_game": _r(won / games) if games else None,
            "solve_accuracy": _r(won / tries) if tries else None,
            "shown_at_correct_solve": summary(cat("shown_right")), "money_per_round_won": summary(cat("round_money"))}


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
            "bots": pool_seats(E, sorted(n for n in E if n == "bot" or n.startswith("bot #"))),
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


def noise_floor(lineups: dict) -> dict:
    """How far apart two identical bots in one lineup finish: each lineup's bot #1 minus bot #2, in win rate, with its
    interval, and the widest gap. Chance alone moves a seat this much."""
    gaps = []
    for lid, L in lineups.items():
        for p in L.get("pairwise", []):
            if p["a"].startswith("bot #") and p["b"].startswith("bot #"):
                gaps.append({"lineup": lid, "gap": p["win_rate_gap"], "ci95": p["ci95"]})
    return {"pairs": gaps, "largest": max((abs(g["gap"]) for g in gaps if g["gap"] is not None), default=None),
            "median": round(median(abs(g["gap"]) for g in gaps if g["gap"] is not None), 4) if gaps else None}


def lineup_id(name: str) -> str:
    """A lineup's id from the name analyses give it ("lineup 3b" for an id, a folder's name otherwise)."""
    return name.removeprefix("lineup ")


def merge_letters(paths: Sequence[Path], keep: Sequence[str]) -> dict | None:
    """Saved letter judgments from several files, for the lineups in `keep`; a lineup found in more than one file
    comes from the last. Every file must be judged by the same bot version."""
    rows: dict[str, list] = {}
    versions_seen = set()
    for path in paths:
        data = json.loads(Path(path).read_text())
        versions_seen.add(data.get("judge_version"))
        by: dict[str, list] = defaultdict(list)
        for r in data["rows"]:
            if (lid := lineup_id(r["lineup"])) in keep:
                by[lid].append({**r, "lineup": lid})
        rows.update(by)
    if not rows:
        return None
    if len(versions_seen) > 1:
        raise ValueError(f"letter judgments by different bot versions: {sorted(versions_seen)}")
    return {"judge_version": versions_seen.pop(), "rows": [r for lid in keep if lid in rows for r in rows[lid]]}


RSTLNE = set("RSTLNE")
SHARE_BANDS = [("under 30%", 0.0, 0.3), ("30 to 40%", 0.3, 0.4), ("40% or more", 0.4, 1.01)]
ARCHIVE = settings.ROOT / "puzzles" / "all_recent_puzzles_ktebbe.csv"  # the aired archive, git-ignored


def rstlne_share(answer: str) -> float:
    """The share of an answer's letters that R S T L N E fills, as the bonus board starts."""
    letters = [c for c in answer.upper() if c.isalpha()]
    return sum(c in RSTLNE for c in letters) / len(letters) if letters else 0.0


def _band(share: float) -> int:
    return next(i for i, (_, lo, hi) in enumerate(SHARE_BANDS) if lo <= share < hi)


def bonus_shares(deck: Path, archive: Path = ARCHIVE) -> dict:
    """How much R S T L N E fills on the deck's bonus boards, against aired bonus puzzles (each airing once), with
    the aired puzzles' split over SHARE_BANDS. Without the archive, the aired side is None."""
    data = json.loads(Path(deck).read_text())
    rows = data["puzzles"] if isinstance(data, dict) else data
    ours = [rstlne_share(p["answer"]) for p in rows if p.get("bonus")]
    out = {"deck": {"puzzles": len(ours), "mean": _r(mean(ours)) if ours else None}, "aired": None}
    if Path(archive).exists():
        import csv
        seen, aired = set(), []
        with Path(archive).open(newline="") as fh:
            for row in csv.DictReader(fh):
                key = (row.get("Puzzle"), row.get("Episode_Number"))
                if (row.get("Round") or "").strip() == "BR" and row.get("Puzzle") and key not in seen:
                    seen.add(key)
                    aired.append(rstlne_share(row["Puzzle"]))
        if aired:
            counts = [sum(_band(s) == i for s in aired) for i in range(len(SHARE_BANDS))]
            out["aired"] = {"puzzles": len(aired), "mean": _r(mean(aired)), "bands": [_r(c / len(aired)) for c in counts]}
    return out


def bonus_by_share(folder: Path) -> dict:
    """Each bonus test player's solves in each SHARE_BANDS band of R S T L N E fill, as [solved, puzzles]."""
    entrants: dict[str, list[list[int]]] = {}
    for path in sorted(Path(folder).glob("*/puzzle*.jsonl")):
        lines = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        if not lines or lines[-1].get("type") != "summary":
            continue  # unfinished
        name = lines[0]["bonus_test"]["entrant"]
        bonus = lines[-1]["bonus"]
        cell = entrants.setdefault(name, [[0, 0] for _ in SHARE_BANDS])[_band(rstlne_share(bonus["puzzle"]["answer"]))]
        cell[0] += bool(bonus["solved"])
        cell[1] += 1
    return {"bands": [name for name, _, _ in SHARE_BANDS], "entrants": entrants}


def bonus_report(path: Path | None) -> dict | None:
    """The bonus test's report, with R S T L N E's fill on its deck against aired puzzles and each player's solves by it."""
    if path is None or not Path(path).exists():
        return None
    report = json.loads(Path(path).read_text())
    out = {"folder": Path(path).parent.name, **report, "by_rstlne_share": bonus_by_share(Path(path).parent)}
    deck = settings.ROOT / report["puzzles"] if report.get("puzzles") else None
    if deck is not None and deck.exists():
        out["rstlne_share"] = bonus_shares(deck)
    return out


def _latest_bonus(puzzles: str | None, seed: int | None) -> Path | None:
    if not puzzles:
        return None
    found = sorted(BONUSTEST.glob(f"{Path(puzzles).stem}-seed{seed}-*/report.json")) if seed is not None else []
    return found[-1] if found else None


LOGS = settings.ROOT / "logs"
# The memory probe: one bonus solve per puzzle on a blank board and on R S T L N E alone, aired puzzles against an
# unaired control deck (logs/memory-probe.py, and logs/bot-rstlne-probe.py for the bot).
MEMORY = [LOGS / "memory-probe.jsonl", LOGS / "memory-probe-more.jsonl", LOGS / "bot-rstlne-probe.jsonl"]
# Blatt's 15 hardest solved bonus puzzles: one solve each on four boards (logs/blatt-picks.py, and a bonus test for
# the players' own picks).
BLATT_DECK = settings.ROOT / "puzzles" / "aired-blatt-15.json"
BLATT = {"blank": LOGS / "blatt-memory-blank.jsonl", "RSTLNE": LOGS / "blatt-memory-rstlne.jsonl",
         "contestant": LOGS / "blatt-picks.jsonl"}
# Bot self-play variants, each against two copies of the bot (rstlne.selfplay play).
VARIANTS = {"milk_all": LOGS / "selfplay" / "variant-milk", "vowel_first": LOGS / "selfplay" / "variant-vowels",
            "solve_on_sight": LOGS / "selfplay" / "variant-solve",  # solve_on_sight: eager_solve at the known-answer level
            "vowels_affordable": LOGS / "selfplay" / "variant-afford", "vowel_cover": LOGS / "selfplay" / "variant-cover",
            "never_vowel": LOGS / "selfplay" / "variant-novowel"}
VARIANT_GAMES = 1002  # every variant run: 334 sets in cyclic seating, three games a set


def _who(row: dict) -> str:
    """The player a probe row belongs to: an LLM by its slug, the bot by its version or seat."""
    if "model" in row:
        return "llm:" + row["model"]
    return "bot" if "version" in row else row["seat"]


def _probe_rows(paths: Sequence[Path]) -> list[dict]:
    """Every ask in the files that exist, one per (player, deck, board, puzzle): a later row replaces an earlier one."""
    asks: dict[tuple, dict] = {}
    for path in paths:
        if Path(path).exists():
            for line in Path(path).read_text().splitlines():
                if line.strip():
                    r = json.loads(line)
                    asks[(_who(r), r.get("deck"), r.get("board"), r["puzzle"])] = {**r, "who": _who(r)}
    return list(asks.values())


def probe_tally(paths: Sequence[Path]) -> dict:
    """Right answers per player, deck and board, as [right, asks]."""
    out: dict = {}
    for r in _probe_rows(paths):
        cell = out.setdefault(r["who"], {}).setdefault(r["deck"], {}).setdefault(r["board"], [0, 0])
        cell[0] += bool(r["right"])
        cell[1] += 1
    return out


def _gap(aired: list[bool], control: list[bool]) -> dict:
    """Aired minus control in share right, with a 95% interval that resamples each deck on its own (they don't pair)."""
    import random
    rate = lambda xs: sum(xs) / len(xs)  # noqa: E731
    rng = random.Random(0)
    draws = sorted(rate(rng.choices(aired, k=len(aired))) - rate(rng.choices(control, k=len(control)))
                   for _ in range(tournament.RESAMPLES))
    return {"aired": [sum(aired), len(aired)], "generated": [sum(control), len(control)],
            "gap": _r(rate(aired) - rate(control)),
            "ci95": [_r(draws[int(0.025 * (len(draws) - 1))]), _r(draws[int(0.975 * (len(draws) - 1))])]}


def memory(paths: Sequence[Path] = MEMORY) -> dict | None:
    """The memory probe: each player's aired minus control gap on each board, and the LLMs pooled."""
    rows = _probe_rows(paths)
    if not rows:
        return None
    by: dict[tuple, list[bool]] = defaultdict(list)
    for r in rows:
        by[(r["who"], r["deck"], r["board"])].append(bool(r["right"]))
        if r["who"].startswith("llm:"):
            by[("models", r["deck"], r["board"])].append(bool(r["right"]))
    players: dict = {}
    for (who, deck, board) in sorted(by):
        if deck == "aired" and by.get((who, "generated", board)):
            players.setdefault(who, {})[board] = _gap(by[(who, "aired", board)], by[(who, "generated", board)])
    pooled = players.pop("models", None)
    tally = probe_tally(paths)
    for who, decks in tally.items():  # decks with no partner (the bot's grading deck) as plain counts
        for deck, boards in decks.items():
            if deck not in ("aired", "generated"):
                for board, cell in boards.items():
                    players.setdefault(who, {}).setdefault(board, {})[deck] = cell
    return {"players": players, "models_pooled": pooled,
            "cost": _r(sum(r.get("cost") or 0 for r in rows), 4)}


def shown_share(answer: str, called) -> float:
    """The share of an answer's letters that the called letters fill."""
    letters = [c for c in answer.upper() if c.isalpha()]
    return sum(c in called for c in letters) / len(letters) if letters else 0.0


def blatt(deck: Path = BLATT_DECK, boards: dict | None = None) -> dict | None:
    """Blatt's 15: each player's solves on every board (a jsonl of single solves, or a bonus test report for the
    players' own picks), each player's board after its own picks, and how much R S T L N E and the contestants'
    picks fill."""
    if not Path(deck).exists():
        return None
    puzzles = json.loads(Path(deck).read_text())["puzzles"]
    out_boards: dict = {}
    own_shown: dict = {}
    costs: dict = {}
    for name, path in (boards or {}).items():
        path = Path(path)
        if not path.exists():
            out_boards[name] = None
        elif path.suffix == ".json":
            report = json.loads(path.read_text())
            out_boards[name] = {e["entrant"]: [e["solved"], e["puzzles"]] for e in report["entrants"]}
            own_shown = {e["entrant"]: e.get("shown_after_picks") for e in report["entrants"]}
            costs[name] = _r(sum(e.get("cost") or 0 for e in report["entrants"]), 4)
        else:
            rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
            tally: dict = {}
            for r in rows:
                cell = tally.setdefault(r["seat"], [0, 0])
                cell[0] += bool(r["right"])
                cell[1] += 1
            out_boards[name] = tally
            costs[name] = _r(sum(r.get("cost") or 0 for r in rows), 4)
    fill = lambda called: _r(mean(shown_share(p["answer"], called(p)) for p in puzzles))  # noqa: E731
    return {"puzzles": len(puzzles), "boards": out_boards, "own_shown": own_shown, "cost": costs,
            "shown": {"RSTLNE": fill(lambda p: RSTLNE), "contestant": fill(lambda p: RSTLNE | set(p["contestant_picks"]))}}


def variants(folders: dict = VARIANTS, full: int = VARIANT_GAMES) -> dict:
    """Each bot self-play variant's games against two copies of the bot, summarized as rstlne.selfplay does.
    A run with fewer than `full` games is still playing, and is left out."""
    from rstlne import selfplay
    out = {}
    for name, folder in folders.items():
        if Path(folder).exists() and (summary := selfplay.games_summary(folder))["games"] >= full:
            out[name] = summary
    return out


def _commit() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=settings.ROOT, capture_output=True,
                              text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def build(phase: str | None = None, toml: Path = common.LINEUPS, *, pairs=PAIRS, bonus: Path | None = None,
          letters: Sequence[Path] | None = None, gap: Path | None = None) -> dict:
    """The whole file: meta, lineups, pairs, and the bonus test, letters and reading gap where they've been run."""
    phase = phase or tomllib.loads(Path(toml).read_text())["default"]
    meta_lineups = common.lineups(phase, toml)
    out_lineups, shares = {}, {}
    for lid, m in meta_lineups.items():
        if not any(True for _ in common.games(m["folder"])):
            continue
        out_lineups[lid] = {"label": m.get("label"), "note": m.get("note"), "folder": m["folder"].name, **lineup(m["folder"])}
        for name, detail in play.play_stats(m["folder"]).items():
            if name in out_lineups[lid]["entrants"]:
                out_lineups[lid]["entrants"][name]["play"] = detail
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
    letter_data = merge_letters([Path(f) for f in (letters or []) if Path(f).exists()], out_lineups)
    gap_data = json.loads(Path(gap).read_text()) if gap and Path(gap).exists() else None
    if gap_data:  # only this phase's lineups, by id
        gap_data = {**gap_data, "lineups": {lid: v for k, v in gap_data["lineups"].items()
                                            if (lid := lineup_id(k)) in out_lineups}}
    return {
        "meta": {"phase": phase, "made": datetime.now(timezone.utc).isoformat(timespec="seconds"), "commit": _commit(),
                 "lineups": list(out_lineups), "deck": deck, "seed": seed,
                 "deck_made_by": json.loads(made_by.pop()) if len(made_by) == 1 else None,
                 "resamples": tournament.RESAMPLES, "interval": "95%, percentile bootstrap over whole sets, seed 0"},
        "lineups": out_lineups,
        "pairs": out_pairs,
        "noise": noise_floor(out_lineups),
        "comebacks": play.comebacks([m["folder"] for lid, m in meta_lineups.items() if lid in out_lineups]),
        "bonus": bonus_report(bonus),
        "letters": {**letters_summary(letter_data), "lineups_missing": [k for k in out_lineups if k not in {
            r["lineup"] for r in letter_data["rows"]}]} if letter_data else None,
        "reading_gap": gap_data,
    }


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m rstlne.analysis.numbers", description=__doc__.splitlines()[0])
    parser.add_argument("--out", required=True, help="where to write the JSON")
    parser.add_argument("--phase", help="the lineups.toml phase (its default when omitted)")
    parser.add_argument("--bonus", help="a bonus test report.json; by default the latest on the phase's deck and seed")
    parser.add_argument("--letters", nargs="+", help="saved letter judgments (default every logs/analysis/letters-<phase>*.json)")
    parser.add_argument("--gap", help="saved reading gap (default logs/analysis/reading-gap-<phase>.json)")
    args = parser.parse_args(argv)
    phase = args.phase or tomllib.loads(common.LINEUPS.read_text())["default"]
    letter_files = [Path(f) for f in args.letters] if args.letters else sorted(ANALYSIS.glob(f"letters-{phase}*.json"))
    out = build(phase, letters=letter_files,
                gap=Path(args.gap) if args.gap else ANALYSIS / f"reading-gap-{phase}.json", bonus=None)
    seed = out["meta"]["seed"]
    out["bonus"] = bonus_report(Path(args.bonus) if args.bonus else _latest_bonus(out["meta"]["deck"], seed))
    out["aired_bonus"] = bonus_report(_latest_bonus("puzzles/private.json", seed))
    out["memory"] = memory()
    own = _latest_bonus(str(BLATT_DECK.relative_to(settings.ROOT)), seed)
    out["blatt"] = blatt(BLATT_DECK, {**BLATT, **({"own": own} if own else {})})
    out["variants"] = variants() or None
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=1))
    missing = [k for k in ("bonus", "letters", "reading_gap", "aired_bonus", "memory", "blatt", "variants") if out[k] is None]
    if out["letters"] and out["letters"]["lineups_missing"]:
        missing.append("letters for " + " ".join(out["letters"]["lineups_missing"]))
    print(f"wrote {args.out}: {len(out['lineups'])} lineups, {len(out['pairs'])} pairs"
          + (f"; not yet run: {', '.join(missing)}" if missing else ""))


if __name__ == "__main__":
    main()
