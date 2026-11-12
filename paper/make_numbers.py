"""paper/numbers.json -> paper/numbers.tex: one LaTeX macro per number the paper cites.

    uv run python paper/make_numbers.py

The text never types a result; it uses these macros. A number numbers.json doesn't hold yet prints as a red
\\missing{...} placeholder, and the script lists it, so a gap can't slip into the draft unseen.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).parent
SOL, TERRA = "llm:openai/gpt-6.1-sol", "llm:openai/gpt-6.1-terra"
LUNA, HAIKU = "llm:openai/gpt-6-luna", "llm:anthropic/claude-haiku-5.5"
DEEPSEEK, QWEN = "llm:deepseek/deepseek-v4.1-flash-1017", "llm:qwen/qwen3.8-flash"
EMBER = "llm:meta/muse-ember"
NOT_REFUSED = {"solve doesn't fit the board", "repeated letter"}  # logged, but played with their penalty
GUESS = "fits, but wrong"  # the one kind of wrong solve that breaks nothing the board shows
LUNA_H, HAIKU_H = "hybrid:openai/gpt-6-luna", "hybrid:anthropic/claude-haiku-5.5"
LUNA_D, D1, JEV = "decision:openai/gpt-6-luna-decisions", "decision:liquid/d1-ultra", "decision:typesafe/jev-1.14"
HAIKU_W = "@anthropic/claude-haiku-5.5"  # a decision seat whose answers Haiku writes
GEMINI_D = "decision:google/gemini-decision-1"
ALONE = {"Sol": ("2", SOL), "Terra": ("2t", TERRA), "DeepSeek": ("3c", DEEPSEEK), "Qwen": ("3r", QWEN), "Ember": ("3m", EMBER),
         "Luna": ("3b", LUNA), "Haiku": ("3d", HAIKU), "LunaHybrid": ("3", LUNA_H), "HaikuHybrid": ("3f", HAIKU_H),
         "LunaDec": ("d2", LUNA_D), "Done": ("d1", D1), "Jev": ("dj", JEV),
         "LunaDecH": ("d2h", LUNA_D + HAIKU_W), "DoneH": ("d1h", D1 + HAIKU_W), "JevH": ("djh", JEV + HAIKU_W),
         "GemDec": ("dg", GEMINI_D), "GemDecH": ("dgh", GEMINI_D + HAIKU_W)}


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
        # Section 6. A refusal is a reply the engine sent back; a misfit or a repeated letter is played, with its penalty
        invalid = get(e, "invalid")
        if invalid is not None:
            refused = sum(v for k, v in invalid.items() if k not in NOT_REFUSED)
            m[f"{name}Refusals"] = f"{refused:,}"
            m[f"{name}RefusalsPerGame"] = f"{refused / e['games']:.2f}"
        wrong = get(e, "play", "wrong_solves")
        if wrong is not None:
            total = sum(wrong.values())
            broke = total - wrong.get(GUESS, 0)
            m[f"{name}WrongAll"] = str(total)
            m[f"{name}WrongBoard"] = str(broke)
            m[f"{name}WrongBoardShare"] = pct(broke / total, 0) if total else None
    forfeits = [get(e, "play", "forfeits") for L in lineups.values() for e in L["entrants"].values()]
    m["NumForfeits"] = str(sum(f or 0 for f in forfeits)) if any(f is not None for f in forfeits) else None
    for lid, mates in (("6a", "Lunas"), ("6b", "Haikus"), ("6d2", "LunaDecs"), ("6d1", "Dones"), ("6dj", "Jevs"), ("6dg", "GemDecs")):
        m[f"BotVs{mates}"] = pct(get(lineups, lid, "entrants", "bot", "win_rate"))
    # Section 7: letters, judged by the bot's reader on the board before each call, and the reading gap
    models = ("Sol", "Terra", "DeepSeek", "Ember", "Qwen", "Luna", "Haiku")
    gap_kinds = {"Other": "the bot's reader had another answer", "Unsure": "right, but the bot wasn't sure",
                 "Turn": "the bot would have known it, but it was the other seat's turn",
                 "First": "a bot knew it first and lost the wheel"}
    bots = defaultdict(list)
    for name in models:
        lid, key = ALONE[name]
        e = get(lineups, lid, "entrants", key)
        vow = get(e, "vowels", "per_game")
        m[f"{name}Vowels"] = None if vow is None else f"{vow:.1f}"
        c = get(n, "letters", "rows", lid, key, "consonant")
        m[f"{name}ConsHit"] = pct(get(c, "hit"), 0)
        m[f"{name}ConsJudge"] = pct(get(c, "judge"), 0)
        m[f"{name}ConsTop"] = pct(get(c, "top"), 0)
        m[f"{name}ConsBeat"] = pts(c["hit"] - c["judge"], 0) if c else None
        cats = get(n, "reading_gap", "lineups", lid, "players", key, "categories") or {}
        for k, label in gap_kinds.items():
            m[f"{name}Gap{k}"] = pct(get(cats, label, "share"), 0)
        hard = [get(cats, gap_kinds[k], "share") for k in ("Other", "Unsure")]
        m[f"{name}GapHard"] = pct(sum(hard), 0) if None not in hard else None
        bots_here = get(lineups, lid, "bots")  # the lineup's two bots as one player, as the charts draw them
        r = get(bots_here, "rounds_won_per_game")
        m[f"{name}BotRounds"] = None if r is None else f"{r:.2f}"
        bots["money"].append(get(bots_here, "money_per_round_won", "median"))
        bots["shown"].append(get(bots_here, "shown_at_correct_solve", "median"))
        bc = get(n, "letters", "rows", lid, "bot", "consonant")
        bots["hit"].append(get(bc, "hit"))
        bots["judge"].append(get(bc, "judge"))
        bots["top"].append(get(bc, "top"))
    span = lambda xs, f: None if None in xs else f"{f(min(xs))}--{f(max(xs))}"  # noqa: E731
    m["BotRoundMoneyRange"] = span(bots["money"], lambda x: f"\\${x:,.0f}")
    for k in ("shown", "hit", "judge", "top"):
        m[f"Bot{k.capitalize()}Range"] = span(bots[k], lambda x: f"{100 * x:.0f}")
    # Section 9: the bonus test on our deck and on aired puzzles, the memory probe, Blatt's 15. Counts print as the
    # number right; a ...N macro holds the asks when they aren't the whole deck.
    players = {name: key for name, (_, key) in ALONE.items()} | {"Bot": "bot"}
    for prefix, test in (("Bonus", "bonus"), ("AiredBonus", "aired_bonus")):
        rows = {e["entrant"]: e for e in get(n, test, "entrants") or []}
        m[f"{prefix}Puzzles"] = str(max((e["puzzles"] for e in rows.values()), default=0)) if rows else None
        for name, key in players.items():
            e = rows.get(key)
            m[f"{prefix}{name}"] = str(e["solved"]) if e else None
            m[f"{prefix}{name}Shown"] = pct(e.get("shown_after_picks"), 0) if e else None
    boards = {"blank": "Blank", "RSTLNE": "Rstlne"}
    probed = get(n, "memory", "players") or {}
    for name, key in players.items():
        if probed and key not in probed:
            continue  # not in the probe: no macros, so citing one fails loudly
        for board, b in boards.items():
            cell = get(n, "memory", "players", key, board)
            for deck, d in (("aired", "Aired"), ("generated", "Control")):
                k = get(cell, deck)
                m[f"Mem{name}{b}{d}"] = str(k[0]) if k else None
                m[f"Mem{name}{b}{d}N"] = str(k[1]) if k else None
            m[f"Mem{name}{b}Gap"] = pts(get(cell, "gap"), 0)
            ci = get(cell, "ci95")
            m[f"Mem{name}{b}GapCI"] = f"{pts(ci[0], 0)} to {pts(ci[1], 0)}" if ci else None
    for board, b in boards.items():
        cell = get(n, "memory", "models_pooled", board)
        for deck, d in (("aired", "Aired"), ("generated", "Control")):
            k = get(cell, deck)
            m[f"MemPooled{b}{d}"] = f"{k[0]} of {k[1]:,}" if k else None
            m[f"MemPooled{b}{d}Rate"] = pct(k[0] / k[1]) if k else None
        m[f"MemPooled{b}Gap"] = pts(get(cell, "gap"))
        ci = get(cell, "ci95")
        m[f"MemPooled{b}GapCI"] = f"{pts(ci[0])} to {pts(ci[1])}" if ci else None
    m["BlattPuzzles"] = str(get(n, "blatt", "puzzles")) if get(n, "blatt") else None
    m["BlattShownRstlne"] = pct(get(n, "blatt", "shown", "RSTLNE"), 0)
    m["BlattShownContestant"] = pct(get(n, "blatt", "shown", "contestant"), 1)
    for board, b in (("blank", "Blank"), ("RSTLNE", "Rstlne"), ("contestant", "Contestant"), ("own", "Own")):
        ran = get(n, "blatt", "boards", board)
        for name, key in players.items():
            if ran and key not in ran:
                continue  # this player wasn't asked on this board
            k = get(ran, key)
            m[f"Blatt{name}{b}"] = str(k[0]) if k else None
    for name, key in players.items():
        m[f"Blatt{name}OwnShown"] = pct(get(n, "blatt", "own_shown", key), 0)
    # Appendix C: the bot's self-play variants, each minus the two copies of the bot it played
    for variant, (v, label) in {"milk_all": ("milk", "Milk"), "vowel_first": ("vowels", "Vowels")}.items():
        for copy, c in (("v6a", "A"), ("v6b", "B")):
            gap = next((p for p in get(n, "variants", variant, "pairwise") or [] if {p["a"], p["b"]} == {v, copy}), None)
            sign = 1 if gap and gap["a"] == v else -1
            m[f"Variant{label}Vs{c}"] = pts(sign * gap["gap"], 0) if gap else None
            ci = sorted(sign * x for x in gap["ci95"]) if gap and gap.get("ci95") else None
            m[f"Variant{label}Vs{c}CI"] = f"{pts(ci[0], 0)} to {pts(ci[1], 0)}" if ci else None
        m[f"Variant{label}Games"] = f"{get(n, 'variants', variant, 'games'):,}" if get(n, "variants", variant) else None
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
