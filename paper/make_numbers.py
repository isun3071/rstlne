"""paper/numbers.json -> paper/numbers.tex: one LaTeX macro per number the paper cites.

    uv run python paper/make_numbers.py

The text never types a result; it uses these macros. A number numbers.json doesn't hold yet prints as a red
\\missing{...} placeholder, and the script lists it, so a gap can't slip into the draft unseen.
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).parent
SOL, TERRA = "llm:openai/gpt-6.1-sol", "llm:openai/gpt-6.1-terra"
LUNA, HAIKU = "llm:openai/gpt-6-luna", "llm:anthropic/claude-haiku-5.5"
DEEPSEEK, QWEN = "llm:deepseek/deepseek-v4.1-flash-1017", "llm:qwen/qwen3.8-flash"
EMBER = "llm:meta/muse-ember"
LUNA_H, HAIKU_H = "hybrid:openai/gpt-6-luna", "hybrid:anthropic/claude-haiku-5.5"
LUNA_D, D1 = "decision:openai/gpt-6-luna-decisions", "decision:liquid/d1-ultra"
ALONE = {"Sol": ("2", SOL), "Terra": ("2t", TERRA), "DeepSeek": ("3c", DEEPSEEK), "Qwen": ("3r", QWEN), "Ember": ("3m", EMBER),
         "Luna": ("3b", LUNA), "Haiku": ("3d", HAIKU), "LunaHybrid": ("3", LUNA_H), "HaikuHybrid": ("3f", HAIKU_H),
         "LunaDec": ("d2", LUNA_D), "Done": ("d1", D1)}


def pct(x, places=1):
    return None if x is None else f"{100 * x:.{places}f}\\%"


def pts(x, places=1):
    return None if x is None else f"{'+' if x >= 0 else '$-$'}{abs(100 * x):.{places}f}"


def money(x):
    return None if x is None else f"\\${x:,.0f}"


def get(d, *path):
    for p in path:
        if d is None:
            return None
        d = d[p] if isinstance(d, list) and isinstance(p, int) and p < len(d) else (d.get(p) if isinstance(d, dict) else None)
    return d


def macros(n: dict) -> dict[str, str | None]:
    m: dict[str, str | None] = {}
    lineups = n["lineups"]
    m["NumLineups"] = str(len(lineups))
    m["NumGames"] = f"{sum(L['games'] for L in lineups.values()):,}"
    m["GamesPerLineup"] = str(next(iter(lineups.values()))["games"])
    m["SetsPerLineup"] = str(next(iter(lineups.values()))["sets"])
    m["Seed"] = str(n["meta"]["seed"])
    m["Resamples"] = f"{n['meta']['resamples']:,}"
    m["TotalCost"] = f"\\${sum(L['cost'] for L in lineups.values()):,.2f}"
    m["NoiseMedian"] = pct(get(n, "noise", "median"))
    m["NoiseLargest"] = pct(get(n, "noise", "largest"))
    m["NoisePairs"] = str(len(get(n, "noise", "pairs") or [])) if get(n, "noise") else None
    m["RstlneDeck"] = pct(get(n, "bonus", "rstlne_share", "deck", "mean"), 0)  # R S T L N E's fill on our bonus boards
    m["RstlneAired"] = pct(get(n, "bonus", "rstlne_share", "aired", "mean"), 0)  # and on aired bonus puzzles
    aired = get(n, "bonus", "rstlne_share", "aired", "puzzles")
    m["AiredBonusPuzzles"] = f"{aired:,}" if aired else None
    for name, (lid, key) in ALONE.items():
        e = get(lineups, lid, "entrants", key)
        m[f"{name}Win"] = pct(get(e, "win_rate"))
        ci = get(e, "win_ci95")
        m[f"{name}WinCI"] = f"{100 * ci[0]:.1f}--{100 * ci[1]:.1f}" if ci else None
        m[f"{name}Acc"] = pct(get(e, "solve_accuracy"), 0)
        m[f"{name}Shown"] = pct(get(e, "shown_at_correct_solve", "median"), 0)
        m[f"{name}Rounds"] = f"{get(e, 'rounds_won_per_game'):.2f}" if get(e, "rounds_won_per_game") is not None else None
        m[f"{name}Wrong"] = f"{get(e, 'wrong_solves_per_game'):.2f}" if get(e, "wrong_solves_per_game") is not None else None
        m[f"{name}Place"] = f"{get(e, 'place', 'mean'):.2f}" if get(e, "place", "mean") is not None else None
        m[f"{name}RoundMoney"] = money(get(e, "money_per_round_won", "median"))
        cost = get(e, "cost", "mean")
        m[f"{name}Cost"] = None if cost is None else f"{100 * cost:.1f}\\textcent"
    for lid, mates in (("6a", "Lunas"), ("6b", "Haikus"), ("6d2", "LunaDecs"), ("6d1", "Dones")):
        m[f"BotVs{mates}"] = pct(get(lineups, lid, "entrants", "bot", "win_rate"))
    for p in n["pairs"]:
        words = p["label"].replace("-", " ").split()
        key = "Pair" + "".join("".join(c for c in w if c.isalpha()).capitalize() for w in words)  # TeX macro names are letters only
        m[key] = pts(p["diff"])
        m[key + "CI"] = f"{pts(p['ci95'][0])} to {pts(p['ci95'][1])}" if p.get("ci95") else None
    return m


def main() -> None:
    n = json.loads((HERE / "numbers.json").read_text())
    m = macros(n)
    lines = ["% Made by paper/make_numbers.py from paper/numbers.json. Don't edit by hand.",
             "\\providecommand{\\missing}[1]{\\textcolor{red}{[#1?]}}"]
    missing = []
    for name, value in sorted(m.items()):
        if value is None:
            missing.append(name)
            value = f"\\missing{{{name}}}"
        lines.append(f"\\newcommand{{\\{name}}}{{{value}}}")
    (HERE / "numbers.tex").write_text("\n".join(lines) + "\n")
    print(f"wrote numbers.tex: {len(m)} macros" + (f"; not in numbers.json yet: {', '.join(missing)}" if missing else ""))


if __name__ == "__main__":
    main()
