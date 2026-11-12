"""Charts of the grid, from the tournament logs: uv run --with matplotlib python figures/make_figures.py figures [phase]

The lineups come from lineups.toml: its default phase, or the one named (v6, v4). A lineup a phase doesn't list,
or that has no finished games yet, is left out of every chart."""
import json
import glob
import statistics as st
import sys
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker
import tomllib

from rstlne.analysis.common import LINEUPS as LINEUPS_TOML, lineups
from rstlne.tournament import report

OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
T = Path("logs/tournaments")
PHASE = sys.argv[2] if len(sys.argv) > 2 else tomllib.loads(LINEUPS_TOML.read_text())["default"]
MAP = lineups(PHASE)
F = {k: v["folder"].name for k, v in MAP.items()}  # lineup id -> folder


def have(k):
    """Whether the phase lists lineup `k` and it has finished games."""
    return k in F and bool(report(T / F[k])["entrants"])

# Reference palette (light): surface, ink, and one hue per kind of player, validated as a set
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
KIND = {"LLM": "#2a78d6", "bot": "#eb6834", "hybrid": "#1baf7a",
        "decision": "#8f8e89"}  # a neutral gray for the decision seat: neither an LLM's nor the bot's hue
plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "font.family": "DejaVu Sans", "font.size": 11, "text.color": INK, "axes.labelcolor": INK2,
    "xtick.color": INK2, "ytick.color": INK2, "axes.edgecolor": GRID,
    "axes.spines.top": False, "axes.spines.right": False, "axes.spines.left": False,
})

NAMES = {"openai/gpt-6.1-sol": "Sol", "openai/gpt-6-luna": "Luna", "anthropic/claude-haiku-5.5": "Haiku",
         "deepseek/deepseek-v4.1-flash-1017": "DeepSeek", "openai/gpt-6-luna-decisions": "Luna Decisions",
         "liquid/d1-ultra": "d1-ultra", "typesafe/jev-1.14": "Jev", "google/gemini-decision-1": "Gemini Decision", "google/gemini-4-hydrogen": "Gemini 4 Hydrogen", "openai/gpt-6.1-terra": "Terra", "qwen/qwen3.8-flash": "Qwen 3.8 Flash",
         "meta/muse-ember": "Ember"}


def short(entrant):
    base, _, tag = entrant.partition(" #")
    kind, _, slug = base.partition(":")
    if kind == "hybrid":
        name = f"Hybrid (bot + {NAMES.get(slug, slug)})"
    elif kind == "decision":
        decider, _, writer = slug.partition("@")  # a seat naming its solver: "Luna Dec. + Haiku"
        short_names = {"openai/gpt-6-luna-decisions": "Luna Dec.", "google/gemini-decision-1": "Gemini Dec."}
        name = (f"{short_names.get(decider, NAMES.get(decider, decider))} + {NAMES.get(writer, writer)}" if writer
                else f"{NAMES.get(slug, slug)} seat")
    elif kind == "llm":
        name = NAMES.get(slug, slug)
    else:
        name = "Bot"
    return name + (f" #{tag}" if tag else ""), {"hybrid": "hybrid", "llm": "LLM", "decision": "decision"}.get(kind, "bot")


def entrants(folder):
    return report(T / folder)["entrants"]


LINEUPS = [(f"{k}  {v['label']}", F[k]) for k, v in MAP.items() if have(k)]  # (label, folder)
REPORTS = {folder: entrants(folder) for _, folder in LINEUPS}


def tidy(ax, xlabel=None):
    ax.tick_params(length=0)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    if xlabel:
        ax.set_xlabel(xlabel)


def save(fig, name, title, subtitle):
    from matplotlib.transforms import offset_copy
    top = lambda pts: offset_copy(fig.transFigure, fig=fig, x=0, y=-pts, units="points")  # noqa: E731
    fig.text(0.02, 1, title, ha="left", va="top", fontsize=15, fontweight="bold", color=INK, transform=top(10))
    fig.text(0.02, 1, subtitle, ha="left", va="top", fontsize=10.5, color=INK2, transform=top(32))
    check(fig, name)
    fig.savefig(OUT / name, dpi=200)
    plt.close(fig)


def check(fig, name):
    """Every visible text inside the figure, and no two texts overlapping."""
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    box = fig.bbox
    hidden = set()  # labels of ticks past an axis's limits: matplotlib keeps them "visible" but never draws them
    for ax in fig.axes:
        for axis, (lo, hi) in ((ax.xaxis, sorted(ax.get_xlim())), (ax.yaxis, sorted(ax.get_ylim()))):
            for tick in axis.get_major_ticks() + axis.get_minor_ticks():
                if not lo - 1e-9 <= tick.get_loc() <= hi + 1e-9:
                    hidden.update((id(tick.label1), id(tick.label2)))
    texts = [t for t in fig.findobj(matplotlib.text.Text) if t.get_visible() and t.get_text().strip() and id(t) not in hidden]
    # the text alone: an annotation's own extent also spans its leader line
    ext = [(t.get_text().replace(chr(10), " ")[:40], matplotlib.text.Text.get_window_extent(t, r)) for t in texts]
    issues = [f"outside: {s!r}" for s, b in ext if b.x0 < box.x0 - 1 or b.y0 < box.y0 - 1 or b.x1 > box.x1 + 1 or b.y1 > box.y1 + 1]
    for i in range(len(ext)):
        for j in range(i + 1, len(ext)):
            a, b = ext[i][1], ext[j][1]
            if a.overlaps(b) and (min(a.x1, b.x1) - max(a.x0, b.x0)) > 2 and (min(a.y1, b.y1) - max(a.y0, b.y0)) > 2:
                issues.append(f"overlap: {ext[i][0]!r} / {ext[j][0]!r}")
    print(name, "OK" if not issues else issues)


# 1. The yardstick: each player alone against two bots
solo = [(F[k], key) for k, key in (("2", "openai/gpt-6.1-sol"), ("2t", "openai/gpt-6.1-terra"), ("3", "hybrid:openai/gpt-6-luna"),
                                     ("3f", "hybrid:anthropic/claude-haiku-5.5"), ("3c", "deepseek/deepseek-v4.1-flash-1017"),
                                     ("3r", "qwen/qwen3.8-flash"), ("3m", "meta/muse-ember"), ("3b", "llm:openai/gpt-6-luna"), ("3d", "anthropic/claude-haiku-5.5"),
                                     ("d2", "decision:openai/gpt-6-luna-decisions"), ("d1", "decision:liquid/d1-ultra"),
                                     ("dj", "decision:typesafe/jev-1.14"),
                                     ("d2h", "decision:openai/gpt-6-luna-decisions@"), ("d1h", "decision:liquid/d1-ultra@"),
                                     ("djh", "decision:typesafe/jev-1.14@"), ("dg", "decision:google/gemini-decision-1"),
                                     ("dgh", "decision:google/gemini-decision-1@anthropic"),
                                     ("d2t", "decision:openai/gpt-6-luna-decisions@openai/gpt-6.1-terra"),
                                     ("d1t", "decision:liquid/d1-ultra@openai/gpt-6.1-terra"),
                                     ("djt", "decision:typesafe/jev-1.14@openai/gpt-6.1-terra"),
                                     ("dgt", "decision:google/gemini-decision-1@openai/gpt-6.1-terra"))
        if have(k)]
rows = []
for folder, key in solo:
    e = next(x for x in REPORTS[folder] if key in x["entrant"])
    name, kind = short(e["entrant"])
    rows.append((name, kind, e["win_rate"], e["ci95"]["win_rate"]))
rows.sort(key=lambda r: r[2])
fig, ax = plt.subplots(figsize=(9, 0.62 * len(rows) + 2.2))
fig.subplots_adjust(left=0.27, right=0.95, top=0.8, bottom=0.17)
for i, (name, kind, rate, ci) in enumerate(rows):
    ax.barh(i, rate * 100, height=0.56, color=KIND[kind], zorder=2)
    ax.plot([ci[0] * 100, ci[1] * 100], [i, i], color=INK, linewidth=1.4, zorder=3)
    ax.text(ci[1] * 100 + 1.2, i, f"{rate:.0%}", va="center", fontsize=11, color=INK, fontweight="bold")
ax.axvline(100 / 3, color=INK2, linewidth=1, linestyle=(0, (4, 3)), zorder=1)
ax.text(100 / 3 + 0.6, len(rows) - 0.45, "fair share (33%)", fontsize=9.5, color=INK2, va="bottom")
ax.set_yticks(range(len(rows)), [r[0] for r in rows])
ax.set_xlim(0, 80)
tidy(ax, "games won against two bots, with 95% interval (%)")
handles = [plt.Rectangle((0, 0), 1, 1, color=KIND[k]) for k in ("LLM", "hybrid", "decision")]
ax.legend(handles, ["LLM playing alone", "hybrid: the bot decides, the LLM reads",
                    "decision seat: a decision model decides, an LLM writes its solves"], loc="lower right", frameon=False, fontsize=9.5)
save(fig, "1-alone-against-two-bots.png", "Alone against two bots",
     f"One seat against two identical {PHASE} bots, 60 sets (360 games) each, same puzzles and spins")

# 2. Temperament: how early each player solves, and how often it's right
# From paper/numbers.json, so the chart shows the same medians as the paper's tables: the median board showing at a
# right solve, and the bot as both bots of Sol's lineup pooled
NUMBERS = json.loads(Path("paper/numbers.json").read_text())["lineups"]
LID = {folder: k for k, folder in F.items()}
pts = []
for folder, key in solo:
    if "@" in key:
        continue  # decision seats that name their solver belong to section 8, not this chart of the models
    full = next(n for n in NUMBERS[LID[folder]]["entrants"] if key in n)
    e = NUMBERS[LID[folder]]["entrants"][full]
    name, kind = short(full)
    pts.append((name, kind, e["shown_at_correct_solve"]["median"] * 100, e["solve_accuracy"] * 100, e["win_rate"]))
if have("2"):
    b = NUMBERS["2"]["bots"]
    bot_win = st.mean(e["win_rate"] for n, e in NUMBERS["2"]["entrants"].items() if n.startswith("bot"))
    pts.append(("Bot", "bot", b["shown_at_correct_solve"]["median"] * 100, b["solve_accuracy"] * 100, bot_win))
fig, ax = plt.subplots(figsize=(9, 6.2))
fig.subplots_adjust(left=0.1, right=0.96, top=0.84, bottom=0.12 if PHASE == "v4" else 0.17)
if PHASE == "v4":
    OFFSETS = {"Hybrid (bot + Luna)": (9, 12), "Hybrid (bot + Haiku)": (-9, -22)}  # the two hybrids sit together
else:  # v6: Sol and Terra sit together, and the hybrids beside the bot
    OFFSETS = {"Sol": (-9, 4), "Terra": (-9, -18), "Hybrid (bot + Luna)": (-9, 14), "Hybrid (bot + Haiku)": (-9, -20),
               "Bot": (6, -22), "Haiku": (9, -18), "Qwen 3.8 Flash": (-9, -4), "d1-ultra seat": (0, -24),
               "Ember": (9, 16)}  # four players sit within four points of each other at the top: leader lines
for name, kind, x, y, w in pts:
    ax.scatter(x, y, s=110, color=KIND[kind], edgecolor=SURFACE, linewidth=2, zorder=3)
    label = f"{name}\n{w:.0%} of games" if kind != "bot" else f"{name}\n({w:.0%} vs Sol)"
    dx, dy = OFFSETS.get(name, (9, -4))
    far = abs(dx) > 40  # a label set well away from its point gets a leader line
    ax.annotate(label, (x, y), textcoords="offset points", xytext=(dx, dy), fontsize=10, color=INK, va="center",
                ha="left" if dx > 0 else "right" if dx < 0 else "center",
                arrowprops=dict(arrowstyle="-", color=INK2, linewidth=0.8, shrinkA=2, shrinkB=6) if far else None)
ax.set_xlabel("median board showing at a correct solve (%): left solves earlier")
ax.set_ylabel("solves that were right (%)")
ax.set_xlim(40, 80)
low = 60 if PHASE == "v4" else 50  # v6: the Luna Decisions seat is right 57% of the time
ax.set_ylim(low, 100 if PHASE == "v4" else 103)
if PHASE != "v4":
    ax.set_yticks(range(low, 101, 10))
ax.set_xticks(range(45, 81, 5))
ax.grid(color=GRID, linewidth=0.8)
ax.set_axisbelow(True)
ax.tick_params(length=0)
ax.text(41, low + 2, "reckless: early, often wrong", color=INK2, fontsize=9.5)
ax.text(79, low + 2, "passive: right, but late", color=INK2, fontsize=9.5, ha="right")
ax.text(41, 98.6 if PHASE == "v4" else 101.6, "early and right", color=INK2, fontsize=9.5)
handles = [plt.Line2D([], [], marker="o", linestyle="", markersize=9, color=KIND[k]) for k in KIND]
if PHASE == "v4":
    ax.legend(handles, ["LLM alone", "bot", "hybrid", "decision seat"], loc="center right", frameon=False, fontsize=9.5)
else:
    fig.legend(handles, ["LLM alone", "bot", "hybrid", "decision seat"], loc="lower center", ncol=4, frameon=False, fontsize=9.5)
save(fig, "2-temperament.png", "Early and right wins",
     "Each player alone against two bots (the bot's point is both bots against Sol); labels give games won")

# 3. Every lineup: share of games won by each seat
fig, ax = plt.subplots(figsize=(11, 0.62 * len(LINEUPS) + 2.6))
fig.subplots_adjust(left=0.26, right=0.98, top=0.83, bottom=0.2)
segments = []
for i, (label, folder) in enumerate(reversed(LINEUPS)):
    left = 0
    for e in sorted(REPORTS[folder], key=lambda x: -x["win_rate"]):
        name, kind = short(e["entrant"])
        width = e["win_rate"] * 100
        ax.barh(i, width - 0.4, left=left + 0.2, height=0.6, color=KIND[kind], zorder=2)
        label = f"{'Hybrid' if kind == 'hybrid' else name.split(' #')[0]} {width:.0f}%"
        t = ax.text(left + width / 2, i, label, ha="center", va="center", fontsize=9,
                    color="#ffffff" if kind in ("LLM", "bot") else INK)
        segments.append((t, left, width))
        left += width
ax.set_yticks(range(len(LINEUPS)), [l for l, _ in reversed(LINEUPS)])
ax.set_xlim(0, 100)
fig.canvas.draw()
for t, left, width in segments:  # a label that doesn't fit its segment comes off; the legend still names the kind
    bb = t.get_window_extent(fig.canvas.get_renderer())
    span = ax.transData.transform((left + width, 0))[0] - ax.transData.transform((left, 0))[0]
    if bb.width > span - 6:
        print("  label dropped:", t.get_text())
        t.remove()
ax.axvline(100 / 3, color=INK2, linewidth=0.8, linestyle=(0, (4, 3)), zorder=3)
ax.axvline(200 / 3, color=INK2, linewidth=0.8, linestyle=(0, (4, 3)), zorder=3)
tidy(ax, "share of games won (%); dashed lines mark equal thirds")
handles = [plt.Rectangle((0, 0), 1, 1, color=KIND[k]) for k in KIND]
fig.legend(handles, ["LLM", "bot", "hybrid", "decision seat"], loc="lower center", ncol=4, frameon=False, fontsize=9.5)
save(fig, "3-every-lineup.png", "Who won each lineup",
     "Share of games won per seat, 60 sets (360 games) per lineup"
     + ("; lineup 1 used the old round 4 rule" if PHASE == "v4" else ", on grading-606b"))


# 4. How they win: rounds won per game and money banked per round won
def per_round(folder, key):
    rounds, banks = [], []
    for p in glob.glob(str(T / folder / "*.jsonl")):
        L = [json.loads(l) for l in open(p)]
        if L[-1].get("type") != "summary":
            continue
        names = [(x.get("model") or x["kind"]) if x["kind"] != "hybrid" else "hybrid:" + x["model"] for x in L[0]["seats"]]
        seats = [i for i, n in enumerate(names) if (key in n) or (key == "bot" and n == "bot")]
        for i in seats:
            won = [l["result"]["earned"] for l in L if l["type"] == "action" and l["seat"] == i
                   and l["result"]["outcome"] == "solved" and l["state"].get("round")]
            rounds.append(len(won))
            banks += won
    return st.mean(rounds), st.median(banks)


groups = [(g, F[k], key, kind) for g, k, key, kind in (
    ("Sol vs bots", "2", "openai/gpt-6.1-sol", "LLM"),
    ("Terra vs bots", "2t", "openai/gpt-6.1-terra", "LLM"),
    ("Hybrid (Luna) vs bots", "3", "hybrid:openai/gpt-6-luna", "hybrid"),
    ("Hybrid (Haiku) vs bots", "3f", "hybrid:anthropic/claude-haiku-5.5", "hybrid"),
    ("DeepSeek vs bots", "3c", "deepseek/deepseek-v4.1-flash-1017", "LLM"),
    ("Qwen 3.8 Flash vs bots", "3r", "qwen/qwen3.8-flash", "LLM"),
    ("Ember vs bots", "3m", "meta/muse-ember", "LLM"),
    ("Luna vs bots", "3b", "openai/gpt-6-luna", "LLM"),
    ("Haiku vs bots", "3d", "anthropic/claude-haiku-5.5", "LLM"),
    ("Luna Decisions seat vs bots", "d2", "openai/gpt-6-luna-decisions", "decision"),
    ("Jev seat vs bots", "dj", "typesafe/jev-1.14", "decision"),
    ("Luna Dec. + Haiku vs bots", "d2h", "luna-decisions", "decision"),
    ("d1-ultra + Haiku vs bots", "d1h", "d1-ultra", "decision"),
    ("Jev + Haiku vs bots", "djh", "jev-1.14", "decision"),
    ("Gemini Decision seat vs bots", "dg", "gemini-decision-1", "decision"),
    ("Gemini Dec. + Haiku vs bots", "dgh", "gemini-decision-1", "decision"),
    ("Luna Dec. + Terra vs bots", "d2t", "luna-decisions", "decision"),
    ("d1-ultra + Terra vs bots", "d1t", "d1-ultra", "decision"),
    ("Jev + Terra vs bots", "djt", "jev-1.14", "decision"),
    ("Gemini Dec. + Terra vs bots", "dgt", "gemini-decision-1", "decision")) if have(k)]
data = [(g, kind, per_round(f, key), per_round(f, "bot")) for g, f, key, kind in groups]
fig, axes = plt.subplots(1, 2, figsize=(12, 0.62 * len(data) + 2.2))
fig.subplots_adjust(left=0.19, right=0.95, top=0.84, bottom=0.12, wspace=0.62)
for ax, idx, xlabel, fmt in ((axes[0], 0, "rounds won per game", "{:.2f}"),
                             (axes[1], 1, "median bank when it wins a round ($)", "${:,.0f}")):
    for j, (g, kind, star, bot) in enumerate(reversed(data)):
        for off, (val, k) in ((0.18, (star[idx], kind)), (-0.18, (bot[idx], "bot"))):
            ax.barh(j + off, val, height=0.34, color=KIND[k], zorder=2)
            ax.text(val * 1.02, j + off, fmt.format(val), va="center", fontsize=9.5, color=INK)
    ax.set_yticks(range(len(data)), [d[0] for d in reversed(data)])
    ax.set_xlim(0, max(max(d[2][idx], d[3][idx]) for d in data) * 1.25)
    ax.xaxis.set_major_locator(matplotlib.ticker.MaxNLocator(4))
    tidy(ax, xlabel)
axes[0].set_title("Rounds won", loc="left", fontsize=11.5, color=INK)
axes[1].set_title("Money per round won", loc="left", fontsize=11.5, color=INK)
handles = [plt.Rectangle((0, 0), 1, 1, color=KIND[k]) for k in KIND]
fig.legend(handles, ["the LLM", "a bot (each)", "the hybrid", "the decision seat"], loc="lower center", ncol=4, frameon=False, fontsize=9.5)
save(fig, "4-rounds-and-banks.png", "The bots win fewer rounds, but bigger ones",
     "Same lineups as chart 1: each player alone against two bots")

# 5. Cost per game
def game_costs(folder):
    """Each finished game's spend, every call included (moves, and replies redone after an invalid one)."""
    out = []
    for p in glob.glob(str(T / folder / "*.jsonl")):
        with open(p) as fh:
            last = fh.readlines()[-1]
        s = json.loads(last)
        if s.get("type") == "summary":
            out.append(s["usage"]["cost"])
    return out


if PHASE == "v4":  # the v4 chart, from the costs measured then (and two 1-set Gemini trials)
    cost = [("Luna", 0.37, None), ("Haiku", 0.52, None), ("DeepSeek", 1.43, None), ("Sol (half-price tier)", 1.76, None),
            ("Gemini 3.8 Flash (half-price, 1-set trial)", 6.9, None), ("Gemini 4 Argon (half-price, 1-set trial)", 9.6, None)]
else:  # one LLM seat against two bots; output price per million tokens as billed (Sol and Terra on OpenAI's half-price flex tier)
    priced = (("Sol, $5 out (flex)", "2"), ("Terra, $2.50 out (flex)", "2t"), ("DeepSeek, $0.60 out", "3c"),
              ("Qwen 3.8 Flash, $0.47 out", "3r"), ("Ember, $0.50 out", "3m"), ("Luna, $0.50 out", "3b"), ("Haiku, $0.50 out", "3d"))
    cost = []
    for name, k in priced:
        if have(k):
            g = sorted(game_costs(F[k]))
            cost.append((name, st.mean(g) * 100, (g[len(g) // 10] * 100, g[len(g) * 9 // 10] * 100)))
    cost.sort(key=lambda c: c[1])
fig, ax = plt.subplots(figsize=(9, 4.6) if PHASE == "v4" else (9, 0.62 * len(cost) + 2.2))
fig.subplots_adjust(left=0.38, right=0.95, top=0.8, bottom=0.15 if PHASE == "v4" else 0.17)
for i, (name, c, spread) in enumerate(reversed(cost)):
    ax.barh(i, c, height=0.56, color=KIND["LLM"], zorder=2)
    if spread:
        ax.plot(spread, [i, i], color=INK, linewidth=1.4, zorder=3)
    ax.text((spread[1] if spread else c) + 0.15, i, f"{c:.1f}¢", va="center", fontsize=10.5, color=INK)
ax.set_yticks(range(len(cost)), [c[0] for c in reversed(cost)])
ax.set_xlim(0, 11.5 if PHASE == "v4" else max(s[1] if s else c for _, c, s in cost) * 1.25)
tidy(ax, "cost per game, US cents (one LLM seat)" + ("" if PHASE == "v4" else "; line: 10th to 90th percentile game"))
save(fig, "5-cost-per-game.png", "Cheap tokens don't make a cheap game",
     "Cost depends on how much a model writes and how much of its prompt is cached, not just its token price")

# 6. The bonus test: each player alone on every bonus puzzle in a deck
if PHASE == "v4":  # the v4 chart, from the bonus tests run then on three decks
    bonus = {"Sol": (99, 99, 98), "DeepSeek": (90, 95, 89), "Haiku": (53, 67, 57), "Bot": (67, 88, 86)}
    decks = ["aired (show puzzles)", "grid deck", "harder generated (v7)"]
    shades = ["#86b6ef", "#2a78d6", "#104281"]
    fig, ax = plt.subplots(figsize=(11, 5.2))
    fig.subplots_adjust(left=0.11, right=0.97, top=0.8, bottom=0.22)
    players = list(bonus)
    for d in range(3):
        for i, p in enumerate(players):
            v = bonus[p][d]
            ax.barh(i * 1.0 + (1 - d) * 0.26, v, height=0.24, color=shades[d], zorder=2)
            ax.text(v + 0.8, i + (1 - d) * 0.26, f"{v}%", va="center", fontsize=9, color=INK)
    ax.axvline(38, color=INK2, linewidth=1, linestyle=(0, (4, 3)))
    ax.set_yticks(range(len(players)), players)
    ax.invert_yaxis()
    ax.set_xlim(0, 108)
    ax.set_xticks(range(0, 101, 20))
    tidy(ax, "bonus puzzles solved (%)")
    handles = [plt.Rectangle((0, 0), 1, 1, color=s) for s in shades] + [plt.Line2D([], [], color=INK2, linestyle=(0, (4, 3)))]
    fig.legend(handles, decks + ["contestants, 10 s clock (~38%)"], loc="lower center", ncol=4, frameon=False, fontsize=9.5)
    save(fig, "6-bonus-test.png", "The bonus round, alone",
         "Each player on 100 bonus puzzles per deck, one solve each, no clock for the models")
else:  # v6: the bonus test on grading-606b's 100 bonus puzzles, seed 707
    test = json.loads(sorted(Path("logs/bonustest").glob("grading-606b-seed707-*/report.json"))[-1].read_text())
    rows = []
    for e in test["entrants"]:
        name, kind = short(e["entrant"])
        rows.append((name, kind, e["rate"], e["ci95"], e["solved"], e["puzzles"]))
    rows.sort(key=lambda r: r[2])
    fig, ax = plt.subplots(figsize=(9, 0.62 * len(rows) + 2.2))
    fig.subplots_adjust(left=0.27, right=0.95, top=0.8, bottom=0.17)
    for i, (name, kind, rate, ci, k, n) in enumerate(rows):
        ax.barh(i, rate * 100, height=0.56, color=KIND[kind], zorder=2)
        ax.plot([ci[0] * 100, ci[1] * 100], [i, i], color=INK, linewidth=1.4, zorder=3)
        ax.text(ci[1] * 100 + 1.2, i, f"{rate:.0%}" + ("" if n == 100 else f" ({k} of {n})"),
                va="center", fontsize=11, color=INK, fontweight="bold")
    ax.axvline(38, color=INK2, linewidth=1, linestyle=(0, (4, 3)), zorder=1)
    ax.text(38.6, len(rows) - 0.45, "contestants on the show, 10 s clock (~38%)", fontsize=9.5, color=INK2, va="bottom")
    ax.set_yticks(range(len(rows)), [r[0] for r in rows])
    ax.set_xlim(0, 118)
    ax.set_xticks(range(0, 101, 20))
    tidy(ax, "bonus puzzles solved, with 95% interval (%)")
    handles = [plt.Rectangle((0, 0), 1, 1, color=KIND[k]) for k in ("LLM", "hybrid", "decision", "bot")]
    fig.legend(handles, ["LLM", "hybrid: the bot picks, the LLM reads", "decision seat", "bot"],
               loc="lower center", ncol=4, frameon=False, fontsize=9.5)
    save(fig, "6-bonus-test.png", "The bonus round, alone",
         "Each player on grading-606b's 100 bonus puzzles: RSTLNE, its own picks, one solve, no clock for the models")
# 7. Finishing places: 1st, 2nd, 3rd, and the average place (2.00 is par)
def places_of(folder, pick):
    """Each matching seat's places in a lineup; ties share the average place."""
    out = []
    for p in glob.glob(str(T / folder / "*.jsonl")):
        L = [json.loads(l) for l in open(p)]
        if L[-1].get("type") != "summary":
            continue
        tot = L[-1]["totals"]
        for i, seat in enumerate(L[0]["seats"]):
            if pick(seat):
                above, tied = sum(x > tot[i] for x in tot), sum(x == tot[i] for x in tot)
                out.append(above + 1 + (tied - 1) / 2)
    return out


rows7 = [(name, k, pick, kind) for name, k, pick, kind in (
         ("Sol", "2", lambda s: s.get("model") == "openai/gpt-6.1-sol", "LLM"),
         ("Terra", "2t", lambda s: s.get("model") == "openai/gpt-6.1-terra", "LLM"),
         ("Hybrid (bot + Luna)", "3", lambda s: s["kind"] == "hybrid", "hybrid"),
         ("Hybrid (bot + Haiku)", "3f", lambda s: s["kind"] == "hybrid", "hybrid"),
         ("DeepSeek", "3c", lambda s: s.get("model") == "deepseek/deepseek-v4.1-flash-1017", "LLM"),
         ("Qwen 3.8 Flash", "3r", lambda s: s.get("model") == "qwen/qwen3.8-flash", "LLM"),
         ("Ember", "3m", lambda s: s.get("model") == "meta/muse-ember", "LLM"),
         ("Luna", "3b", lambda s: s.get("model") == "openai/gpt-6-luna" and s["kind"] == "llm", "LLM"),
         ("Haiku", "3d", lambda s: s.get("model") == "anthropic/claude-haiku-5.5", "LLM"),
         ("Luna Decisions seat", "d2", lambda s: s["kind"] == "decision", "decision"),
         ("d1-ultra seat", "d1", lambda s: s["kind"] == "decision", "decision"),
         ("Jev seat", "dj", lambda s: s["kind"] == "decision", "decision"),
         ("Luna Dec. + Haiku", "d2h", lambda s: s["kind"] == "decision", "decision"),
         ("d1-ultra + Haiku", "d1h", lambda s: s["kind"] == "decision", "decision"),
         ("Jev + Haiku", "djh", lambda s: s["kind"] == "decision", "decision"),
         ("Gemini Decision seat", "dg", lambda s: s["kind"] == "decision", "decision"),
         ("Gemini Dec. + Haiku", "dgh", lambda s: s["kind"] == "decision", "decision"),
         ("Luna Dec. + Terra", "d2t", lambda s: s["kind"] == "decision", "decision"),
         ("d1-ultra + Terra", "d1t", lambda s: s["kind"] == "decision", "decision"),
         ("Jev + Terra", "djt", lambda s: s["kind"] == "decision", "decision"),
         ("Gemini Dec. + Terra", "dgt", lambda s: s["kind"] == "decision", "decision"),
         ("Bot, against two Lunas", "6a", lambda s: s["kind"] == "bot", "bot"),
         ("Bot, against two Haikus", "6b", lambda s: s["kind"] == "bot", "bot"),
         ("Bot, against two d1-ultras", "6d1", lambda s: s["kind"] == "bot", "bot"),
         ("Bot, against two Luna Dec.", "6d2", lambda s: s["kind"] == "bot", "bot"),
         ("Bot, against two Jevs", "6dj", lambda s: s["kind"] == "bot", "bot"),
         ("Bot, against two Gemini Dec.", "6dg", lambda s: s["kind"] == "bot", "bot")) if have(k)]
rows7 = [(name, F[k], pick, kind) for name, k, pick, kind in rows7]  # (name, folder, pick, kind) from here on
RAMP = ["#104281", "#2a78d6", "#86b6ef"]  # 1st, 2nd, 3rd: one hue, darkest first
fig, ax = plt.subplots(figsize=(11, 0.6 * len(rows7) + 2.6))
fig.subplots_adjust(left=0.24, right=0.86, top=0.82, bottom=0.17)
for i, (name, folder, pick, kind) in enumerate(reversed(rows7)):
    pl = places_of(folder, pick)
    shares = [sum(1 if x == r else 0.5 if abs(x - r) == 0.5 else 0 for x in pl) / len(pl) * 100 for r in (1, 2, 3)]
    left = 0
    for r, (share, colour) in enumerate(zip(shares, RAMP)):
        ax.barh(i, share - 0.4, left=left + 0.2, height=0.6, color=colour, zorder=2)
        if share >= 8:
            ax.text(left + share / 2, i, f"{share:.0f}%", ha="center", va="center", fontsize=9,
                    color="#ffffff" if r < 2 else INK)
        left += share
    ax.text(102, i, f"{st.mean(pl):.2f}", va="center", fontsize=10.5, color=INK, fontweight="bold")
ax.text(102, len(rows7) - 0.35, "average\nplace", fontsize=9, color=INK2, va="bottom")
ax.set_yticks(range(len(rows7)), [r[0] for r in reversed(rows7)])
ax.set_xlim(0, 100)
ax.axhline(1.5, color=GRID, linewidth=1)
tidy(ax, "share of games finished in each place (%); an average place of 2.00 is par")
handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in RAMP]
fig.legend(handles, ["1st", "2nd", "3rd"], loc="lower center", ncol=3, frameon=False, fontsize=9.5)
save(fig, "7-finishing-places.png", "Where each player finishes",
     "Each player alone against two bots, then the bot against two copies of a model; ties share places")

# 8-11. Money spread, gaps between places, leads and comebacks, risk
def games_of(folder, pick):
    """Per matching seat and game: main-round money, all three seats' main money, money after round 3, and counts."""
    out = []
    for p in glob.glob(str(T / folder / "*.jsonl")):
        L = [json.loads(l) for l in open(p)]
        if L[-1].get("type") != "summary":
            continue
        b, tot = L[-1]["bonus"], L[-1]["totals"]
        main = [t - (b["envelope"] if b and b["solved"] and b["seat"] == i else 0) for i, t in enumerate(tot)]
        after3, bankrupts, wrong, turns, r4 = [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], None
        for l in L:
            if l["type"] != "action" or not l["state"].get("round"):
                continue
            res, seat, rnd = l["result"], l["seat"], l["state"]["round"]["number"]
            if l["state"]["phase"] == "turn":
                turns[seat] += 1
            if res["outcome"] == "solved":
                if rnd <= 3:
                    after3[seat] += res["earned"]
                if rnd == 4:
                    r4 = seat
            if res["outcome"] == "wrong_solve":
                wrong[seat] += 1
            if res["outcome"] == "bankrupt" or "bankrupt" in res.get("events", []):
                bankrupts[seat] += 1
        for i, seat in enumerate(L[0]["seats"]):
            if pick(seat):
                out.append({"main": main[i], "all": main, "after3": after3, "seat": i, "bankrupts": bankrupts[i],
                            "wrong": wrong[i], "turn_share": turns[i] / max(sum(turns), 1), "r4": r4 == i})
    return out


players = rows7
G = {name: games_of(folder, pick) for name, folder, pick, kind in players}

fig, ax = plt.subplots(figsize=(11, 0.62 * len(players) + 2.4))
fig.subplots_adjust(left=0.24, right=0.97, top=0.82, bottom=0.17)
for i, (name, folder, pick, kind) in enumerate(reversed(players)):
    m = sorted(g["main"] / 1000 for g in G[name])
    q = lambda f: m[min(int(f * len(m)), len(m) - 1)]  # noqa: E731
    ax.plot([q(0.1), q(0.9)], [i, i], color=INK2, linewidth=1.4, zorder=2)
    ax.barh(i, q(0.75) - q(0.25), left=q(0.25), height=0.46, color=KIND[kind], zorder=3)
    ax.plot([q(0.5)] * 2, [i - 0.23, i + 0.23], color=SURFACE, linewidth=2.2, zorder=4)
    ax.scatter([m[-1]], [i], marker="D", s=30, color=INK, zorder=4)
    ax.text(m[-1] + 0.6, i, f"max ${m[-1]:.1f}k", va="center", fontsize=9, color=INK2)
    ax.text(q(0.25) - 0.4, i + 0.34, f"median ${q(0.5):.1f}k", ha="left", fontsize=8.5, color=INK, va="bottom")
ax.set_yticks(range(len(players)), [p[0] for p in reversed(players)])
ax.set_xlim(0, max(max(g["main"] for g in G[n]) for n in G) / 1000 * 1.18)
tidy(ax, "main-round money per game ($ thousands)")
handles = [plt.Rectangle((0, 0), 1, 1, color=KIND["LLM"]), plt.Line2D([], [], color=INK2, linewidth=1.4),
           plt.Line2D([], [], marker="D", linestyle="", color=INK, markersize=5)]
fig.legend(handles, ["middle half of games (white tick: median)", "10th to 90th percentile", "best game"],
           loc="lower center", ncol=3, frameon=False, fontsize=9.5)
save(fig, "8-money-spread.png", "How much each player banks, game to game",
     "Main-round money (before the bonus), each player alone against two bots, then the bot against two copies")

lineup_gaps = []
for label, folder in LINEUPS:
    rows = games_of(folder, lambda seat: True)
    by_game = {}
    for g in rows:
        by_game.setdefault(tuple(g["all"]), g["all"])
    gaps = []
    for allm in by_game.values():
        a, b2, c = sorted(allm, reverse=True)
        gaps.append((a - b2, b2 - c))
    lineup_gaps.append((label, st.median(x for x, _ in gaps) / 1000, st.median(y for _, y in gaps) / 1000,
                        sum(x < 1000 for x, _ in gaps) / len(gaps)))
fig, ax = plt.subplots(figsize=(11, 0.62 * len(lineup_gaps) + 2.4))
fig.subplots_adjust(left=0.26, right=0.95, top=0.82, bottom=0.17)
for i, (label, g12, g23, close) in enumerate(reversed(lineup_gaps)):
    ax.barh(i + 0.17, g12, height=0.32, color=RAMP[0], zorder=2)
    ax.barh(i - 0.17, g23, height=0.32, color=RAMP[2], zorder=2)
    ax.text(g12 + 0.15, i + 0.17, f"${g12:.1f}k", va="center", fontsize=9, color=INK)
    ax.text(g23 + 0.15, i - 0.17, f"${g23:.1f}k", va="center", fontsize=9, color=INK)
ax.set_yticks(range(len(lineup_gaps)), [l[0] for l in reversed(lineup_gaps)])
top = max(max(l[1], l[2]) for l in lineup_gaps) * 1.2
ax.set_xlim(0, top)
ax.set_xticks(range(0, int(top) + 1, 2))
tidy(ax, "median gap in main-round money ($ thousands)")
handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in (RAMP[0], RAMP[2])]
fig.legend(handles, ["1st minus 2nd", "2nd minus 3rd"], loc="lower center", ncol=2, frameon=False, fontsize=9.5)
save(fig, "9-gaps-between-places.png", "How far apart the places finish",
     "Median gap in main-round money between neighbouring places, per lineup")

fig, ax = plt.subplots(figsize=(10.5, 0.62 * len(players) + 2.4))
fig.subplots_adjust(left=0.24, right=0.95, top=0.82, bottom=0.17)
for i, (name, folder, pick, kind) in enumerate(reversed(players)):
    led = [g for g in G[name] if g["after3"][g["seat"]] > max(v for j, v in enumerate(g["after3"]) if j != g["seat"])]
    trail = [g for g in G[name] if g["after3"][g["seat"]] < max(v for j, v in enumerate(g["after3"]) if j != g["seat"])]
    won = lambda g: g["main"] > max(v for j, v in enumerate(g["all"]) if j != g["seat"])  # noqa: E731
    held = 100 * sum(map(won, led)) / max(len(led), 1)
    came = 100 * sum(map(won, trail)) / max(len(trail), 1)
    ax.plot([came, held], [i, i], color=GRID, linewidth=2, zorder=1)
    ax.scatter([held], [i], s=80, color=RAMP[0], edgecolor=SURFACE, linewidth=1.5, zorder=3)
    ax.scatter([came], [i], s=80, color=RAMP[2], edgecolor=SURFACE, linewidth=1.5, zorder=3)
    ax.text(held + 2, i, f"{held:.0f}% (led {100 * len(led) / len(G[name]):.0f}% of games)", va="center", fontsize=9, color=INK)
    ax.text(came - 2, i, f"{came:.0f}%", va="center", ha="right", fontsize=9, color=INK)
ax.set_yticks(range(len(players)), [p[0] for p in reversed(players)])
ax.set_xlim(-8, 130)
ax.set_xticks(range(0, 101, 20))
tidy(ax, "share of games won (%)")
handles = [plt.Line2D([], [], marker="o", linestyle="", color=c, markersize=8) for c in (RAMP[0], RAMP[2])]
fig.legend(handles, ["led after round 3, and won", "trailed after round 3, and came back"], loc="lower center", ncol=2, frameon=False, fontsize=9.5)
save(fig, "10-leads-and-comebacks.png", "Holding a lead, and coming back",
     "Standings after round 3, then who finished first in main-round money")

fig, axes = plt.subplots(1, 2, figsize=(12, 0.55 * len(players) + 2.6))
fig.subplots_adjust(left=0.2, right=0.96, top=0.8, bottom=0.12, wspace=0.6)
for ax, key, title in ((axes[0], "bankrupts", "Bankrupts per game"), (axes[1], "wrong", "Wrong solves per game")):
    for i, (name, folder, pick, kind) in enumerate(reversed(players)):
        v = st.mean(g[key] for g in G[name])
        ax.barh(i, v, height=0.56, color=KIND[kind], zorder=2)
        ax.text(v + 0.02, i, f"{v:.2f}", va="center", fontsize=9, color=INK)
    ax.set_yticks(range(len(players)), [p[0] for p in reversed(players)])
    ax.set_xlim(0, max(st.mean(g[key] for g in G[n]) for n in G) * 1.3)
    ax.set_title(title, loc="left", fontsize=11.5, color=INK)
    tidy(ax)
save(fig, "11-risk.png", "Two ways to give a round away",
     "Bankrupts come from spinning; wrong solves from guessing. Same players as charts 7 and 8")


# 12. Puzzle length: whether a long puzzle changes who wins the round
BANDS = [(16, 17), (18, 19), (20, 22), (23, 26), (27, 99)]
band_names = ["16–17", "18–19", "20–22", "23–26", "27+"]


def solved_rounds(folder, pick):
    """Every solved main round in a lineup: its set, letters, the share showing, and whether the picked seat solved it."""
    out = []
    for p in glob.glob(str(T / folder / "*.jsonl")):
        L = [json.loads(l) for l in open(p)]
        if L[-1].get("type") != "summary":
            continue
        me = next(i for i, seat in enumerate(L[0]["seats"]) if pick(seat))
        number = int(Path(p).name[3:6])
        for l in L:
            if l["type"] == "action" and l["result"]["outcome"] == "solved" and l["state"].get("round"):
                r = l["state"]["round"]
                letters = [c for c in r["puzzle"]["answer"] if c.isalpha()]
                out.append({"set": number, "letters": len(letters), "mine": l["seat"] == me,
                            "shown": sum(c in r["used"] for c in letters) / len(letters)})
    return out


def long_minus_short(rows):
    share = lambda rs: sum(r["mine"] for r in rs) / len(rs)  # noqa: E731
    return share([r for r in rows if r["letters"] >= 27]) - share([r for r in rows if r["letters"] <= 19])


def by_set(rows):
    sets = {}
    for r in rows:
        sets.setdefault(r["set"], []).append(r)
    return sets


import random  # noqa: E402
rng = random.Random(12)
solo12 = [r for r in rows7 if not r[0].startswith("Bot")]
R = {name: solved_rounds(folder, pick) for name, folder, pick, kind in solo12}
gaps12 = []
for name, folder, pick, kind in solo12:
    sets = by_set(R[name])
    keys = sorted(sets)
    boots = sorted(long_minus_short([r for k in rng.choices(keys, k=len(keys)) for r in sets[k]]) for _ in range(2000))
    gaps12.append((name, kind, long_minus_short(R[name]), boots[50], boots[1949]))
llm_names = [name for name, _, _, kind in solo12 if kind == "LLM"]
fig, axes = plt.subplots(1, 2, figsize=(13, 5.6), gridspec_kw={"width_ratios": [1, 1.25]})
fig.subplots_adjust(left=0.07, right=0.97, top=0.78, bottom=0.2, wspace=0.55)
ax = axes[0]
for label, rows, colour in (("bots", [r for rs in R.values() for r in rs if not r["mine"]], KIND["bot"]),
                            ("LLMs alone", [r for n in llm_names for r in R[n] if r["mine"]], KIND["LLM"])):
    ys = [100 * st.median([r["shown"] for r in rows if lo <= r["letters"] <= hi]) for lo, hi in BANDS]
    ax.plot(range(len(BANDS)), ys, color=colour, linewidth=2, marker="o", markersize=8, zorder=3)
    ax.text(len(BANDS) - 1 + 0.15, ys[-1], label, va="center", fontsize=10, color=INK)
ax.set_xticks(range(len(BANDS)), band_names)
ax.set_xlim(-0.3, len(BANDS) + 0.6)
ax.set_ylim(40, 75)
ax.set_yticks(range(40, 76, 5))
ax.set_xlabel("letters in the puzzle")
ax.set_ylabel("board showing at a correct solve (median, %)")
ax.grid(axis="y", color=GRID, linewidth=0.8)
ax.set_axisbelow(True)
ax.tick_params(length=0)
ax.set_title("How much board each needs", loc="left", fontsize=11.5, color=INK)
ax = axes[1]
for i, (name, kind, g, lo, hi) in enumerate(reversed(gaps12)):
    ax.plot([lo * 100, hi * 100], [i, i], color=INK2, linewidth=1.4, zorder=2)
    ax.scatter([g * 100], [i], s=70, color=KIND[kind], edgecolor=SURFACE, linewidth=1.5, zorder=3)
    ax.text(hi * 100 + 1, i, f"{g * 100:+.0f}", va="center", fontsize=9.5, color=INK)
ax.axvline(0, color=INK2, linewidth=1, linestyle=(0, (4, 3)))
ax.set_yticks(range(len(gaps12)), [g[0] for g in reversed(gaps12)])
ax.set_xlim(-12, 32)
ax.set_xticks(range(-10, 31, 10))
tidy(ax, "rounds won on 27+ letters minus on 16–19 (points, 95%)")
ax.set_title("Each player against two bots", loc="left", fontsize=11.5, color=INK)
handles = [plt.Line2D([], [], marker="o", linestyle="", color=KIND[k], markersize=8) for k in KIND]
fig.legend(handles, ["LLM", "bot", "hybrid", "decision seat"], loc="lower center", ncol=4, frameon=False, fontsize=9.5)
save(fig, "12-puzzle-length.png", "Puzzle length doesn't change who wins a round",
     "Every main round solved in the lineups against two bots; every interval includes zero")
# 13. The reading gap: what the bots lacked on each round a model won
GAP = json.loads(Path("paper/numbers.json").read_text())["reading_gap"]["lineups"]
CATS = [("the bot's reader had another answer", "out-read the bot: its reader had another answer"),
        ("right, but the bot wasn't sure", "the bot's reader was right, but unsure"),
        ("the bot would have known it, but it was the other seat's turn", "the bot would have known it, but it was the model's turn"),
        ("a bot knew it first and lost the wheel", "a bot knew it first, then lost the wheel")]
GAP_RAMP = ["#0b3a73", "#2a78d6", "#7fb0ec", "#c6dcf7"]  # one hue: darkest is the model reading ahead of the bot
gap_rows = []
for k, key in (("2", "llm:openai/gpt-6.1-sol"), ("2t", "llm:openai/gpt-6.1-terra"), ("3c", "llm:deepseek/deepseek-v4.1-flash-1017"),
               ("3b", "llm:openai/gpt-6-luna"), ("3m", "llm:meta/muse-ember"), ("3r", "llm:qwen/qwen3.8-flash"),
               ("3d", "llm:anthropic/claude-haiku-5.5")):
    player = GAP.get(k, {}).get("players", {}).get(key)
    if player:
        gap_rows.append((short(key)[0], player["rounds"], [player["categories"][c]["share"] * 100 for c, _ in CATS]))
fig, ax = plt.subplots(figsize=(11, 0.62 * len(gap_rows) + 2.9))
fig.subplots_adjust(left=0.25, right=0.97, top=0.82, bottom=0.25)
for i, (name, n, shares) in enumerate(reversed(gap_rows)):
    left = 0
    for j, (share, colour) in enumerate(zip(shares, GAP_RAMP)):
        ax.barh(i, share - 0.4, left=left + 0.2, height=0.6, color=colour, zorder=2)
        if share >= 7:
            ax.text(left + share / 2, i, f"{share:.0f}%", ha="center", va="center", fontsize=9,
                    color="#ffffff" if j < 2 else INK)
        left += share
ax.set_yticks(range(len(gap_rows)), [f"{name} ({n} rounds)" for name, n, _ in reversed(gap_rows)])
ax.set_xlim(0, 100)
tidy(ax, "share of the rounds the model won (%)")
handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in GAP_RAMP]
fig.legend(handles, [label for _, label in CATS], loc="lower center", ncol=2, frameon=False, fontsize=9.5)
save(fig, "13-reading-gap.png", "Where the models' rounds come from",
     "Each round a model won against two bots, read by the bot's reader on the board the model solved")

print("\nPuzzle length (rounds won on 27+ letters minus 16–19):")
for name, kind, g, lo, hi in gaps12:
    print(f"  {name:26} {g * 100:+5.1f} [{lo * 100:+.1f}, {hi * 100:+.1f}]")

print("\nExtra stats (main-round money):")
for name, folder, pick, kind in players:
    gs = G[name]
    margins = [abs(g["main"] - max(v for j, v in enumerate(g["all"]) if j != g["seat"])) for g in gs]
    print(f"  {name:26} close games (within $1,000 of the leader or runner-up) {sum(m < 1000 for m in margins) / len(gs):4.0%}"
          f" | share of turns {100 * st.mean(g['turn_share'] for g in gs):4.1f}% | won round 4 {100 * st.mean(g['r4'] for g in gs):4.0f}%")
for label, g12, g23, close in lineup_gaps:
    print(f"  {label:30} median 1st-2nd ${g12:.1f}k, 2nd-3rd ${g23:.1f}k, games won by under $1,000: {close:.0%}")

print("written to", OUT, sorted(p.name for p in OUT.glob("*.png")))
