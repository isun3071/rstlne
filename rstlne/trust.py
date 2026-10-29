"""Trust and steal curves for hybrid seats, measured on real game boards.

    python -m rstlne.calibrate trust --models deepseek/deepseek-v4.1-flash-1017 --logs logs/tournaments/prior-101

Boards come from tournament logs, which hold the true answers. Each sampled board gets the exact hybrid
ask from every model, and the bot's reader reads it. The trust curve is fit on the asks that gave a
fitting answer; the steal curve on every sampled turn, from whether the logged player solved.
"""

from __future__ import annotations

import argparse
import json
import random
from collections.abc import Callable, Sequence
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from statistics import mean, median

import numpy as np

from rstlne import selfplay, settings
from rstlne.engine.puzzle import LETTERS, Puzzle, fits_shown, normalize, solve_matches
from rstlne.engine.state import Rules
from rstlne.engine.wheel import WheelSpec
from rstlne.llm.openrouter import OpenRouter
from rstlne.narrate import line_output
from rstlne.players.bot import versions
from rstlne.players.bot.reader import Reader
from rstlne.players.hybrid import Asked, ask, logistic

TENTHS = 10
ASKS_PER_GAME = 15  # a hybrid seat's asks in a game, for the cost estimate
CONFIDENT = 0.95  # a reader this sure of its best answer is "confident"
TRUST_TERMS = ("a", "b", "c", "d", "g")  # constant, shown, agree, p_reader, reader confidence
STEAL_TERMS = ("a", "b", "c", "d")  # constant, shown, reader confidence, readable
BANDS = ((0, 0.5), (0.5, 0.7), (0.7, 0.85), (0.85, 0.95), (0.95, 1.01))


@dataclass(frozen=True)
class Turn:
    """A logged main round turn where the player could have solved, and what the board held."""
    answer: str
    category: str
    used: str  # letters called, sorted
    refuted: tuple[str, ...]  # answers wrong solves had refuted this round by then
    shown: float  # share of letter squares showing
    solved: int  # 1 if the logged player solved correctly on this turn
    game: str
    model: str  # who the logged player was

    @property
    def board(self) -> tuple[str, str, str, tuple[str, ...]]:
        return (self.answer, self.category, self.used, self.refuted)


def rules_and_spec() -> tuple[Rules, WheelSpec]:
    return settings.load_rules(), settings.load_wheel()


def collect(folders: Sequence[Path]) -> list[Turn]:
    """Every main round turn of finished games where the player had the wheel and could have solved."""
    turns = []
    for folder in folders:
        for path in sorted(Path(folder).glob("set*.jsonl")):
            rows = selfplay._rows(path)
            if not rows or rows[-1].get("type") != "summary":
                continue
            models = [seat.get("model") or seat.get("kind") for seat in rows[0].get("seats", [])]
            refuted: dict[int, set[str]] = {}
            for r in rows[1:]:
                state = r.get("state") or {}
                rnd = state.get("round")
                if r.get("type") != "action" or not rnd:
                    continue
                wrong = refuted.setdefault(rnd["number"], set())
                kind = r["action"]["kind"]
                if state.get("phase") in selfplay._TURN_PHASES and kind in selfplay._TURN_KINDS:
                    answer, used = rnd["puzzle"]["answer"], frozenset(rnd["used"])
                    letters = [c for c in answer if c in LETTERS]
                    turns.append(Turn(
                        answer, rnd["puzzle"]["category"], "".join(sorted(used)), tuple(sorted(wrong)),
                        sum(c in used for c in letters) / len(letters),
                        int(kind == "solve" and r["result"]["outcome"] == "solved"),
                        f"{folder}:{path.stem}", models[r["seat"]] if r["seat"] < len(models) else "?",
                    ))
                if kind == "solve" and r["result"]["outcome"] != "solved":
                    try:
                        wrong.add(normalize(r["action"]["answer"]))
                    except (KeyError, TypeError, ValueError):
                        pass  # an answer no puzzle could hold refutes nothing the hybrid would say
    return turns


def tenth(shown: float) -> int:
    return min(int(shown * TENTHS), TENTHS - 1)


def sample(turns: Sequence[Turn], count: int, seed: int) -> list[Turn]:
    """An equal share of `count` from each tenth of the board showing, or all of a tenth that has fewer."""
    rng = random.Random(f"trust:{seed}")
    quota = count // TENTHS
    out = []
    for t in range(TENTHS):
        inside = [turn for turn in turns if tenth(turn.shown) == t]
        out += rng.sample(inside, min(quota, len(inside)))
    return out


# Reading and asking


def _read_one(reader: Reader, board, rules: Rules, spec: WheelSpec) -> dict:
    answer, category, used, refuted = board
    belief = reader.read(selfplay.view_of(Puzzle(category, answer), frozenset(used), rules, spec), frozenset(refuted))
    return {"best": belief.best, "confidence": belief.confidence, "answers": dict(belief.answers)}


def _read_in_worker(board) -> dict:
    w = selfplay._worker
    return _read_one(w["reader"], board, w["rules"], w["spec"])


def read_boards(boards: Sequence, reader: Reader | None, knobs: versions.Knobs, rules: Rules, spec: WheelSpec,
                workers: int) -> dict:
    """The reader's best answer, confidence, and top answers on each distinct board."""
    if reader is None and workers > 1:
        with ProcessPoolExecutor(workers, initializer=selfplay._start_worker,
                                 initargs=(selfplay._make_reader, knobs, rules, spec)) as pool:
            return dict(zip(boards, pool.map(_read_in_worker, boards, chunksize=8)))
    reader = reader or selfplay._make_reader(knobs)
    return {b: _read_one(reader, b, rules, spec) for b in boards}


def ask_boards(model: str, boards: Sequence, client: OpenRouter, config: dict, rules: Rules, spec: WheelSpec,
               parallel: int) -> dict:
    """One hybrid ask per distinct board, with the model's configured temperature, effort, and provider."""
    llm = config.get("llm", {})

    def one(board) -> Asked:
        answer, category, used, refuted = board
        view = selfplay.view_of(Puzzle(category, answer), frozenset(used), rules, spec)
        return ask(client, model, view, frozenset(refuted), temperature=llm.get("temperature"),
                   reasoning_effort=llm.get("reasoning_effort"), provider=config.get("providers", {}).get(model))

    with ThreadPoolExecutor(max_workers=parallel) as pool:
        return dict(zip(boards, pool.map(one, boards)))


def points_for(turns: Sequence[Turn], reads: dict, asks: dict) -> list[dict]:
    """A point per turn: what the model said, whether it was right, and what the reader thought."""
    out = []
    for turn in turns:
        read, asked = reads[turn.board], asks[turn.board]
        said = asked.reply is not None and asked.reply[0]
        given = asked.reply[1] if said else None
        try:
            norm = normalize(given) if given else None
        except ValueError:
            norm = None
        shown_text = "".join("_" if c in LETTERS and c not in turn.used else c for c in turn.answer)
        fits = norm is not None and fits_shown(shown_text, norm, frozenset(turn.used))
        if asked.reply is None:
            status = "failed"
        elif not said:
            status = "not solvable"
        elif not fits:
            status = "doesn't fit"
        elif norm in turn.refuted:
            status = "refuted"
        else:
            status = "used"
        out.append({
            **{k: v for k, v in asdict(turn).items() if k != "refuted"}, "refuted": list(turn.refuted),
            "status": status, "solvable": bool(said), "answer_given": given, "fits": fits,
            "right": bool(given) and solve_matches(turn.answer, given),
            "reader_best": read["best"], "reader_confidence": read["confidence"],
            "reader_right": read["best"] == turn.answer, "agree": norm is not None and norm == read["best"],
            "p_reader": read["answers"].get(norm, 0.0) if norm else 0.0, "readable": int(status == "used"),
            "prompt_tokens": asked.usage.prompt_tokens, "completion_tokens": asked.usage.completion_tokens,
            "cost": asked.usage.cost, "seconds": round(asked.seconds, 2), "attempts": asked.attempts,
        })
    return out


# Fits


def trust_rows(points: Sequence[dict]) -> tuple[np.ndarray, np.ndarray, list]:
    used = [p for p in points if p["status"] == "used"]
    x = np.array([[1.0, p["shown"], float(p["agree"]), p["p_reader"], p["reader_confidence"]] for p in used]).reshape(-1, 5)
    return x, np.array([float(p["right"]) for p in used]), [p["answer"] for p in used]


def steal_rows(points: Sequence[dict], readable: bool = True) -> tuple[np.ndarray, np.ndarray, list]:
    x = [[1.0, p["shown"], p["reader_confidence"]] + ([float(p["readable"])] if readable else []) for p in points]
    return np.array(x).reshape(len(points), 4 if readable else 3), np.array([float(p["solved"]) for p in points]), [p["answer"] for p in points]


def fit(x: np.ndarray, y: np.ndarray, groups: Sequence, terms: Sequence[str], resamples: int, seed: int) -> dict | None:
    """Maximum likelihood coefficients, with 95% intervals from resampling whole puzzles. None without both outcomes."""
    if len(y) < len(terms) or y.sum() in (0, len(y)):
        return None
    w, inverse = selfplay._logistic(x, y)
    out = {"coefficients": [float(v) for v in w], "se": dict(zip(terms, (float(v) for v in np.sqrt(np.diag(inverse))))),
           "rows": int(len(y)), "positives": int(y.sum())}
    if resamples:
        by_group: dict = {}
        for k, g in enumerate(groups):
            by_group.setdefault(g, []).append(k)
        keys = list(by_group)
        rng = np.random.default_rng(seed)
        draws = []
        for _ in range(resamples):
            rows = np.concatenate([by_group[keys[i]] for i in rng.integers(0, len(keys), len(keys))])
            draws.append(selfplay._logistic(x[rows], y[rows], start=w)[0])
        draws = np.array(draws)
        out["ci95"] = {t: [float(np.percentile(draws[:, i], 2.5)), float(np.percentile(draws[:, i], 97.5))]
                       for i, t in enumerate(terms)}
    out["config"] = "[" + ", ".join(f"{v:.3f}" for v in w) + "]"
    return out


def predict(coefficients: Sequence[float], row: Sequence[float]) -> float:
    return logistic(float(np.dot(coefficients, row)))


# The report


def _share(values) -> float | None:
    values = list(values)
    return sum(values) / len(values) if values else None


def report(points: Sequence[dict], asks: dict) -> dict:
    by_tenth = []
    for t in range(TENTHS):
        inside = [p for p in points if tenth(p["shown"]) == t]
        if inside:
            used = [p for p in inside if p["status"] == "used"]
            by_tenth.append({"tenth": f"{t * 10}-{t * 10 + 10}%", "boards": len(inside),
                             "said_solvable": _share(p["solvable"] for p in inside),
                             "right_when_used": _share(p["right"] for p in used), "used": len(used)})
    used = [p for p in points if p["status"] == "used"]
    clash = [p for p in used if p["reader_confidence"] >= CONFIDENT and not p["agree"]]
    agreeing = [p for p in used if p["agree"]]
    agree_by_tenth = []
    for t in range(TENTHS):
        inside = [p for p in agreeing if tenth(p["shown"]) == t]
        if inside:
            agree_by_tenth.append({"tenth": f"{t * 10}-{t * 10 + 10}%", "agreeing": len(inside),
                                   "wrong": _share(not p["right"] for p in inside)})
    sure = [p for p in agreeing if p["reader_confidence"] >= CONFIDENT]
    solvable = [p for p in points if p["solvable"]]
    distinct = list(asks.values())
    cost = mean(a.usage.cost for a in distinct) if distinct else 0.0
    return {
        "by_tenth": by_tenth,
        "disagreements": {"boards": len(clash), "model_right": _share(p["right"] for p in clash),
                          "reader_right": _share(p["reader_right"] for p in clash)},
        "agreeing_and_wrong": {"by_tenth": agree_by_tenth,
                               "confident_reader": {"agreeing": len(sure), "wrong": _share(not p["right"] for p in sure)}},
        "misfit_share": _share(p["status"] == "doesn't fit" for p in solvable) or 0,
        "failed_asks": sum(a.reply is None for a in distinct),
        "cost_per_ask": cost, "cost_per_game": cost * ASKS_PER_GAME,
        "seconds_per_ask": mean(a.seconds for a in distinct) if distinct else 0.0,
        "completion_tokens_per_ask": mean(a.usage.completion_tokens for a in distinct) if distinct else 0.0,
    }


def steal_effect(steal_fit: dict | None, points: Sequence[dict]) -> dict | None:
    """The fitted steal odds on a typical board, with readable 0 and 1."""
    if not steal_fit or not points:
        return None
    shown, conf = median(p["shown"] for p in points), median(p["reader_confidence"] for p in points)
    w = steal_fit["coefficients"]
    return {"shown": shown, "reader_confidence": conf, "unreadable": predict(w, [1, shown, conf, 0]),
            "readable": predict(w, [1, shown, conf, 1])}


def held_out_check(trust_fit: dict | None, steal_fit: dict | None, points: Sequence[dict]) -> dict:
    """Predicted against actual on other boards, with the curves as fit: nothing is refit here."""
    out: dict = {"boards": len(points), "bands": [], "steal": None}
    if trust_fit:
        x, y, _ = trust_rows(points)
        predicted = [predict(trust_fit["coefficients"], row) for row in x]
        for lo, hi in BANDS:
            inside = [(p, r) for p, r in zip(predicted, y) if lo <= p < hi]
            if inside:
                out["bands"].append({"band": f"{lo:.2f}-{min(hi, 1):.2f}", "asks": len(inside),
                                     "predicted": mean(p for p, _ in inside), "right": mean(r for _, r in inside)})
    if steal_fit and points:
        x, y, _ = steal_rows(points)
        out["steal"] = {"predicted": mean(predict(steal_fit["coefficients"], row) for row in x), "solved": float(y.mean())}
    return out


def _pct(value) -> str:
    return "-" if value is None else f"{value:.0%}"


def measure(
    models: Sequence[str],
    folders: Sequence[Path],
    *,
    client: OpenRouter | None = None,
    reader: Reader | None = None,
    knobs: versions.Knobs | None = None,
    count: int = 2000,
    seed: int = 7,
    held_out: Sequence[Path] | None = None,
    out_dir: Path = settings.ROOT / "logs" / "calibration",
    parallel: int = 8,
    workers: int = 4,
    resamples: int = 1000,
    write: Callable[[str], None] = print,
) -> dict:
    config = settings.load_config()
    rules, spec = rules_and_spec()
    knobs = knobs or versions.knobs(versions.current(config))
    if client is None:
        from rstlne.cli import clients
        client = clients({"hybrid"}, None, None)[0]

    def run(folders: Sequence[Path], label: str) -> tuple[list[Turn], dict, dict]:
        turns = sample(collect(folders), count, seed)
        boards = sorted({t.board for t in turns})
        write(f"{label}: {len(turns)} turns on {len(boards)} distinct boards from {', '.join(str(f) for f in folders)}")
        reads = read_boards(boards, reader, knobs, rules, spec, workers)
        asks = {m: ask_boards(m, boards, client, config, rules, spec, parallel) for m in models}
        return turns, reads, asks

    turns, reads, asks = run(folders, "Fitting")
    checked = run(held_out, "Held out") if held_out else None
    result: dict = {"logs": [str(f) for f in folders], "held_out_logs": [str(f) for f in held_out or []],
                    "count": count, "seed": seed, "models": {}, "config_lines": {"trust": [], "steal": []}}
    for model in models:
        points = points_for(turns, reads, asks[model])
        trust_fit = fit(*trust_rows(points), TRUST_TERMS, resamples, seed)
        steal_fit = fit(*steal_rows(points), STEAL_TERMS, resamples, seed)
        without = fit(*steal_rows(points, readable=False), STEAL_TERMS[:3], 0, seed)
        entry = {"trust": trust_fit, "steal": steal_fit and {**steal_fit, "readable_effect": steal_effect(steal_fit, points),
                                                             "without_readable": without},
                 "report": report(points, asks[model]), "points": points}
        if checked:
            entry["held_out"] = held_out_check(trust_fit, steal_fit, points_for(checked[0], checked[1], checked[2][model]))
        result["models"][model] = entry
        if trust_fit and steal_fit:
            result["config_lines"]["trust"].append(f'"{model}" = {trust_fit["config"]}')
            result["config_lines"]["steal"].append(f'"{model}" = {steal_fit["config"]}')
        _print(model, entry, write)
    write("\nAdd to config.toml:")
    for table in ("trust", "steal"):
        write(f"  [hybrid.{table}]")
        for line in result["config_lines"][table] or ["  (no model had enough data for both curves)"]:
            write(f"  {line}")

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"trust-{datetime.now():%Y%m%d-%H%M%S}.json"
    path.write_text(json.dumps(result, indent=2))
    write(f"Saved {path}")
    return result


def _print(model: str, entry: dict, write: Callable[[str], None]) -> None:
    r = entry["report"]
    write(f"\n{model}")
    write(f"  {'board showing':<15}{'boards':>7}{'said solvable':>15}{'right when used':>17}")
    for row in r["by_tenth"]:
        write(f"  {row['tenth']:<15}{row['boards']:>7}{_pct(row['said_solvable']):>15}{_pct(row['right_when_used']):>17}")
    d = r["disagreements"]
    write(f"  reader at {CONFIDENT}+ but the model says another fitting answer: {d['boards']} boards, "
          f"model right {_pct(d['model_right'])}, reader right {_pct(d['reader_right'])}")
    sure = r["agreeing_and_wrong"]["confident_reader"]
    write(f"  agreeing and wrong with the reader at {CONFIDENT}+: {_pct(sure['wrong'])} of {sure['agreeing']}")
    write(f"  answers that don't fit the board: {_pct(r['misfit_share'])}; failed asks: {r['failed_asks']}")
    write(f"  per ask: ${r['cost_per_ask']:.5f}, {r['seconds_per_ask']:.1f} s, {r['completion_tokens_per_ask']:.0f} output tokens; "
          f"about ${r['cost_per_game']:.3f} a game at {ASKS_PER_GAME} asks")
    for name, f in (("trust", entry["trust"]), ("steal", entry["steal"])):
        write(f"  {name} curve: " + (f"{f['config']} from {f['rows']} rows" if f else "not enough data to fit"))
    effect = entry["steal"] and entry["steal"]["readable_effect"]
    if effect:
        write(f"  steal odds on a typical board: {effect['unreadable']:.1%} when the model can't read it, "
              f"{effect['readable']:.1%} when it can")
    check = entry.get("held_out")
    if check:
        for band in check["bands"]:
            write(f"  held out, trust {band['band']}: {band['asks']} asks, predicted {band['predicted']:.0%}, right {band['right']:.0%}")
        if check["steal"]:
            write(f"  held out steal: predicted {check['steal']['predicted']:.1%}, solved {check['steal']['solved']:.1%}")


def main(argv: Sequence[str] | None = None) -> dict:
    line_output()
    parser = argparse.ArgumentParser(prog="python -m rstlne.calibrate trust",
                                     description="Measure hybrid trust and steal curves on real game boards.")
    parser.add_argument("--models", required=True, help="OpenRouter model slugs, comma separated")
    parser.add_argument("--logs", nargs="+", required=True, help="tournament folders played on tuning puzzles")
    parser.add_argument("--held-out", nargs="+", help="tournament folders to check the curves on, never fit on")
    parser.add_argument("--count", type=int, default=2000, help="turns to sample, an equal share per tenth showing")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--parallel", type=int, default=8, help="asks in flight at once")
    parser.add_argument("--workers", type=int, default=4, help="processes reading boards")
    parser.add_argument("--resamples", type=int, default=1000, help="for the 95%% intervals")
    args = parser.parse_args(argv)
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    return measure(models, [Path(f) for f in args.logs], count=args.count, seed=args.seed,
                   held_out=[Path(f) for f in args.held_out] if args.held_out else None,
                   parallel=args.parallel, workers=args.workers, resamples=args.resamples)
