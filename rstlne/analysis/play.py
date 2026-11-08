"""How each seat played, in the detail the paper cites: wrong solves by kind, play by stage of the round,
results by puzzle length, the special wedges, model usage, the hybrids' asks, milking, and comebacks.

analysis.numbers folds these into paper/numbers.json; nothing here reads the bot's word data.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Sequence
from pathlib import Path
from statistics import mean, median, pstdev

from rstlne.analysis import common, milking
from rstlne.analysis.reading_gap import LENGTHS
from rstlne.engine.puzzle import LETTERS, fits_board, normalize

VOWELS = set("AEIOU")
STAGES = ((0.0, 0.25, "open"), (0.25, 0.5, "middle"), (0.5, 1.01, "late"))
BANDS = ((0, 2500, "under $2,500"), (2500, 5000, "$2,500–5,000"), (5000, 7500, "$5,000–7,500"),
         (7500, 10000, "$7,500–10,000"), (10000, 15000, "$10,000–15,000"), (15000, float("inf"), "$15,000 or more"))


def stage(shown: float) -> str:
    """The stage of a round by the share of the board showing: open under a quarter, middle under a half, then late."""
    return next(name for lo, hi, name in STAGES if lo <= shown < hi)


def band(amount: float) -> str:
    return next(name for lo, hi, name in BANDS if lo <= amount < hi)


def length_band(letters: int) -> str:
    return next(label for lo, hi, label in LENGTHS if lo <= letters < hi)


def wrong_kind(answer: str, attempt: str, used: frozenset[str], refuted: frozenset[str]) -> str:
    """How a wrong solve went wrong: the board rules it out (by shape, a letter showing, or a called letter in a
    blank), it repeats an answer already ruled wrong this round, or it fits the board and is just wrong."""
    try:
        guess = normalize(attempt)
    except ValueError:
        return "wrong shape"
    if guess in refuted:
        return "already ruled wrong"
    if fits_board(answer, guess, used):
        return "fits, but wrong"
    words, tries = answer.split(" "), guess.split(" ")
    if len(words) != len(tries) or any(len(w) != len(t) for w, t in zip(words, tries)):
        return "wrong shape"
    for w, t in zip(words, tries):
        for c, a in zip(w, t):
            if (c not in LETTERS or c in used) and a != c:
                return "contradicts a shown letter"
    return "called letter in a blank"


def _summary(xs: Sequence[float]) -> dict:
    xs = list(xs)
    return {"n": len(xs), "mean": round(mean(xs), 4) if xs else None, "median": round(median(xs), 4) if xs else None}


def play_stats(folder: Path) -> dict[str, dict]:
    """Per entrant of one lineup, every detail stat below, from its finished games."""
    raw: dict[str, dict] = defaultdict(lambda: {
        "forfeits": 0, "wrong": Counter(),
        "stages": {name: Counter() for _, _, name in STAGES},
        "length": defaultdict(lambda: {"rounds": 0, "won": 0, "shown": []}),
        "specials": {"mystery": Counter(), "express": Counter(), "wild": Counter(), "million": Counter()},
        "prompt": 0, "cached": 0, "output": [], "cost": [], "games": 0,
        "asks": Counter(), "ask_first": [], "milked": [],
    })
    for game in common.games(folder):
        usage = game.summary.get("usage_by_seat") or [{}] * 3
        for seat, name in enumerate(game.names):
            r = raw[name]
            r["games"] += 1
            u = usage[seat] or {}
            r["prompt"] += u.get("prompt_tokens") or 0
            r["cached"] += u.get("cached_tokens") or 0
            r["output"].append(u.get("completion_tokens") or 0)
            r["cost"].append(u.get("cost") or 0.0)
        for number, actions in game.rounds().items():
            solved = common.solved_by(actions)
            if solved:
                answer = solved[1]["state"]["round"]["puzzle"]["answer"]
                lb = length_band(common.letters_in(answer))
                for seat, name in enumerate(game.names):
                    raw[name]["length"][lb]["rounds"] += 1
                won = raw[game.names[solved[0]]]["length"][lb]
                won["won"] += 1
                won["shown"].append(common.shown(answer, solved[1]["state"]["round"]["used"]))
            refuted: set[str] = set()
            first_ask: dict[int, float] = {}
            for a in actions:
                r, kind, res = raw[game.names[a["seat"]]], a["action"]["kind"], a["result"]
                rnd = a["state"]["round"]
                answer, used = rnd["puzzle"]["answer"], frozenset(rnd["used"])
                shown = common.shown(answer, used)
                st = r["stages"][stage(shown)]
                letter = a["action"].get("letter")
                if kind in ("call_consonant", "call_letter") and letter in LETTERS and letter not in VOWELS:
                    st["consonants"] += 1
                    st["hits"] += answer.count(letter) > 0
                    st["copies"] += answer.count(letter)
                elif kind == "buy_vowel":
                    st["vowels"] += 1
                elif kind == "solve":
                    st["solve_tries"] += 1
                    st["solves_right"] += res["outcome"] == "solved"
                    if res["outcome"] == "wrong_solve" and isinstance(a["action"].get("answer"), str):
                        r["wrong"][wrong_kind(answer, a["action"]["answer"], used, frozenset(refuted))] += 1
                        try:
                            refuted.add(normalize(a["action"]["answer"]))
                        except ValueError:
                            pass
                if res["outcome"] == "forfeit":
                    r["forfeits"] += 1
                if kind in ("keep", "flip"):
                    r["specials"]["mystery"][kind] += 1
                    if res["outcome"] in ("flipped_prize", "flipped_bankrupt"):
                        r["specials"]["mystery"][res["outcome"]] += 1
                elif kind in ("pass", "play"):
                    r["specials"]["express"][kind] += 1
                elif kind == "use_wild":
                    r["specials"]["wild"]["used" if a["action"].get("use") else "kept"] += 1
                raw_rec = a.get("raw") if isinstance(a.get("raw"), dict) else {}
                ask = raw_rec.get("ask")
                if isinstance(ask, dict) and ask.get("n") is not None:
                    key = (game.path.name, number, a["seat"], ask["n"])  # one ask, logged on each move it informed
                    if key not in r["asks"]:
                        r["asks"][key] = 1
                        r["asks"][("status", ask.get("status"))] += 1
                        if ask.get("status") == "used" and a["seat"] not in first_ask:
                            first_ask[a["seat"]] = shown
                            r["ask_first"].append(shown)
            _express_rides(game, actions, raw)
        b = game.summary.get("bonus") or {}
        for seat, name in enumerate(game.names):
            if b.get("seat") == seat and b.get("envelope") and b.get("solved") and b.get("envelope") >= 1_000_000:
                raw[name]["specials"]["million"]["won"] += 1
        for m in milking.milked_rounds(game):
            raw[m["name"]]["milked"].append(m)

    out = {}
    for name, r in raw.items():
        stages = {}
        for s, c in r["stages"].items():
            stages[s] = {"consonants": c["consonants"], "hits": c["hits"], "copies": c["copies"], "vowels": c["vowels"],
                         "solve_tries": c["solve_tries"], "solves_right": c["solves_right"],
                         "hit_rate": round(c["hits"] / c["consonants"], 4) if c["consonants"] else None,
                         "copies_per_call": round(c["copies"] / c["consonants"], 4) if c["consonants"] else None,
                         "solve_accuracy": round(c["solves_right"] / c["solve_tries"], 4) if c["solve_tries"] else None}
        costs = r["cost"]
        asks = {k[1]: v for k, v in r["asks"].items() if isinstance(k, tuple) and k[0] == "status"}
        milked = r["milked"]
        out[name] = {
            "forfeits": r["forfeits"],
            "wrong_solves": dict(r["wrong"]), "wrong_solves_total": sum(r["wrong"].values()),
            "stages": stages,
            "by_length": {label: {"rounds": v["rounds"], "won": v["won"],
                                  "share": round(v["won"] / v["rounds"], 4) if v["rounds"] else None,
                                  "median_shown": round(median(v["shown"]), 4) if v["shown"] else None}
                          for label, v in sorted(r["length"].items(), key=lambda kv: [l for _, _, l in LENGTHS].index(kv[0]))},
            "specials": {k: dict(v) for k, v in r["specials"].items()},
            "usage": {"games": r["games"], "prompt_tokens": r["prompt"], "cached_tokens": r["cached"],
                      "cached_share": round(r["cached"] / r["prompt"], 4) if r["prompt"] else None,
                      "output_tokens_per_game": _summary(r["output"]),
                      "cost_cv": round(pstdev(costs) / mean(costs), 4) if costs and mean(costs) > 0 else None},
            "hybrid_asks": None if not asks else {
                "asks": sum(asks.values()), "statuses": asks,
                "fitting_share": round(asks.get("used", 0) / sum(asks.values()), 4),
                "first_fitting_answer_shown": _summary(r["ask_first"])},
            "milking": None if not milked else {
                **{k: v for k, v in milking.summarize(milked).items() if k not in ("lost_to", "lost_wheel")},
                "lost_to": dict(milking.summarize(milked)["lost_to"]),
                "lost_wheel": dict(milking.summarize(milked)["lost_wheel"]),
                "per_game": round(len(milked) / r["games"], 4)},
        }
    return out


def _express_rides(game: common.Game, actions: Sequence[dict], raw: dict) -> None:
    """Each Express ride: boarded with "play", then ended by a right solve (solved) or anything else (bust)."""
    riding: int | None = None
    for a in actions:
        kind, outcome = a["action"]["kind"], a["result"]["outcome"]
        if kind == "play" and outcome == "rode_express":
            riding = a["seat"]
            continue
        if riding is not None and a["seat"] == riding:
            if outcome == "solved":
                raw[game.names[riding]]["specials"]["express"]["ride_solved"] += 1
                riding = None
            elif outcome not in ("correct",) or "bankrupt" in a["result"].get("events", []):
                raw[game.names[riding]]["specials"]["express"]["ride_bust"] += 1
                riding = None
        elif riding is not None and a["seat"] != riding:
            riding = None


def comebacks(folders: Sequence[Path]) -> dict:
    """At the start of rounds 3 and 4: how often the leader held on, by the size of the lead over second place, and
    how often a trailing seat finished first, by how far behind it was; and the same by kind of seat, from round 4.
    Winning counts main-round money, so a tie for the lead at that point counts for neither."""
    held = {n: defaultdict(lambda: [0, 0.0]) for n in (3, 4)}
    back = {n: defaultdict(lambda: [0, 0.0]) for n in (3, 4)}
    kind_held, kind_back = defaultdict(lambda: [0, 0.0]), defaultdict(lambda: [0, 0.0])
    for folder in folders:
        for game in common.games(folder):
            totals = game.summary["totals"]
            b = game.summary.get("bonus") or {}
            main = [t - (b["envelope"] if b.get("solved") and b.get("seat") == i else 0) for i, t in enumerate(totals)]
            top = max(main)
            win = [1 / main.count(top) if m == top else 0.0 for m in main]
            starts: dict[int, list[int]] = {}
            for a in game.actions:
                rnd = (a.get("state") or {}).get("round") or {}
                if rnd.get("number") in (3, 4):
                    starts.setdefault(rnd["number"], [s["total"] for s in a["state"]["seats"]])
            for n, t in starts.items():
                lead = max(t)
                if t.count(lead) > 1:
                    continue
                i = t.index(lead)
                h = held[n][band(lead - sorted(t)[-2])]
                h[0] += 1
                h[1] += win[i]
                if n == 4:
                    kind_held[_kind(game, i)][0] += 1
                    kind_held[_kind(game, i)][1] += win[i]
                for j in range(3):
                    if j != i:
                        c = back[n][band(lead - t[j])]
                        c[0] += 1
                        c[1] += win[j]
                        if n == 4:
                            kind_back[_kind(game, j)][0] += 1
                            kind_back[_kind(game, j)][1] += win[j]
    order = [label for _, _, label in BANDS]
    fmt = lambda d, key: {k: {"games" if key == "held" else "seats": v[0], key: round(v[1] / v[0], 4)}  # noqa: E731
                          for k, v in sorted(d.items(), key=lambda kv: order.index(kv[0]) if kv[0] in order else 0)}
    return {str(n): {"held": fmt(held[n], "held"), "came_back": fmt(back[n], "came_back")} for n in (3, 4)} | {
        "round_4_by_kind": {"held": {k: {"games": v[0], "held": round(v[1] / v[0], 4)} for k, v in kind_held.items()},
                            "came_back": {k: {"seats": v[0], "came_back": round(v[1] / v[0], 4)} for k, v in kind_back.items()}}}


def _kind(game: common.Game, seat: int) -> str:
    """A seat's kind for the comeback table: bot, hybrid, decision, or the model's name."""
    kind = game.kind(seat)
    if kind == "llm":
        return game.names[seat].split(":", 1)[-1].split(" #")[0].split("/")[-1]
    return kind
