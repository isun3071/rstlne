"""Charts of the grid, from the tournament logs: uv run --with matplotlib python figures/make_figures.py figures"""
import json
import glob
import statistics as st
import sys
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from rstlne.tournament import report

OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
T = Path("logs/tournaments")

# Reference palette (light): surface, ink, and one hue per kind of player, validated as a set
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
KIND = {"LLM": "#2a78d6", "bot": "#eb6834", "hybrid": "#1baf7a"}
plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "font.family": "DejaVu Sans", "font.size": 11, "text.color": INK, "axes.labelcolor": INK2,
    "xtick.color": INK2, "ytick.color": INK2, "axes.edgecolor": GRID,
    "axes.spines.top": False, "axes.spines.right": False, "axes.spines.left": False,
})

NAMES = {"openai/gpt-6.1-sol": "Sol", "openai/gpt-6-luna": "Luna", "anthropic/claude-haiku-5.5": "Haiku",
         "deepseek/deepseek-v4.1-flash-1017": "DeepSeek"}


def short(entrant):
    base, _, tag = entrant.partition(" #")
    kind, _, slug = base.partition(":")
    if kind == "hybrid":
        name = f"Hybrid (bot + {NAMES.get(slug, slug)})"
    elif kind == "llm":
        name = NAMES.get(slug, slug)
    else:
        name = "Bot"
    return name + (f" #{tag}" if tag else ""), ("hybrid" if kind == "hybrid" else "LLM" if kind == "llm" else "bot")


def entrants(folder):
    return report(T / folder)["entrants"]


LINEUPS = [  # (label, folder)
    ("1  Sol · DeepSeek · Haiku", "seed707-d7589355"),
    ("2  Sol · bot · bot", "seed707-e250a942"),
    ("3  Hybrid · bot · bot", "seed707-ca968604"),
    ("3b  Luna · bot · bot", "seed707-e71dd1af"),
    ("3d  Haiku · bot · bot", "seed707-4ef950be"),
    ("6a  bot · Luna · Luna", "seed707-6496578d"),
    ("6b  bot · Haiku · Haiku", "seed707-261dfa12"),
]
if (T / "seed707-6fa48eea" / "report.json").exists():
    LINEUPS.insert(5, ("3c  DeepSeek · bot · bot", "seed707-6fa48eea"))
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
    texts = [t for t in fig.findobj(matplotlib.text.Text) if t.get_visible() and t.get_text().strip()]
    ext = [(t.get_text().replace(chr(10), " ")[:40], t.get_window_extent(r)) for t in texts]
    issues = [f"outside: {s!r}" for s, b in ext if b.x0 < box.x0 - 1 or b.y0 < box.y0 - 1 or b.x1 > box.x1 + 1 or b.y1 > box.y1 + 1]
    for i in range(len(ext)):
        for j in range(i + 1, len(ext)):
            a, b = ext[i][1], ext[j][1]
            if a.overlaps(b) and (min(a.x1, b.x1) - max(a.x0, b.x0)) > 2 and (min(a.y1, b.y1) - max(a.y0, b.y0)) > 2:
                issues.append(f"overlap: {ext[i][0]!r} / {ext[j][0]!r}")
    print(name, "OK" if not issues else issues)


# 1. The yardstick: each player alone against two bots
solo = [("seed707-e250a942", "openai/gpt-6.1-sol"), ("seed707-ca968604", "hybrid:openai/gpt-6-luna"),
        ("seed707-e71dd1af", "openai/gpt-6-luna"), ("seed707-4ef950be", "anthropic/claude-haiku-5.5")]
if "seed707-6fa48eea" in REPORTS:
    solo.insert(2, ("seed707-6fa48eea", "deepseek/deepseek-v4.1-flash-1017"))
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
handles = [plt.Rectangle((0, 0), 1, 1, color=KIND[k]) for k in ("LLM", "hybrid")]
ax.legend(handles, ["LLM playing alone", "hybrid: the bot decides, the LLM reads"], loc="lower right", frameon=False, fontsize=9.5)
save(fig, "1-alone-against-two-bots.png", "Alone against two bots",
     "One seat against two identical v4 bots, 60 sets (360 games) each, same puzzles and spins")

# 2. Temperament: how early each player solves, and how often it's right
pts = []
for folder, key in solo + [("seed707-e250a942", "bot #1")]:
    e = next(x for x in REPORTS[folder] if key in x["entrant"])
    name, kind = short(e["entrant"])
    name = "Bot" if kind == "bot" else name
    pts.append((name, kind, e["avg_board_shown"] * 100, e["solve_accuracy"] * 100, e["win_rate"]))
fig, ax = plt.subplots(figsize=(9, 6.2))
fig.subplots_adjust(left=0.1, right=0.96, top=0.84, bottom=0.12)
for name, kind, x, y, w in pts:
    ax.scatter(x, y, s=110, color=KIND[kind], edgecolor=SURFACE, linewidth=2, zorder=3)
    label = f"{name}\n{w:.0%} of games" if kind != "bot" else f"{name}\n(against Sol: {w:.0%})"
    ax.annotate(label, (x, y), textcoords="offset points", xytext=(9, -4), fontsize=10, color=INK, va="center")
ax.set_xlabel("board showing at a correct solve (%): left solves earlier")
ax.set_ylabel("solves that were right (%)")
ax.set_xlim(40, 80)
ax.set_ylim(65, 100)
ax.set_xticks(range(45, 81, 5))
ax.grid(color=GRID, linewidth=0.8)
ax.set_axisbelow(True)
ax.tick_params(length=0)
ax.text(41, 67, "reckless: early, often wrong", color=INK2, fontsize=9.5)
ax.text(79, 67, "passive: right, but late", color=INK2, fontsize=9.5, ha="right")
ax.text(41, 98.6, "early and right", color=INK2, fontsize=9.5)
handles = [plt.Line2D([], [], marker="o", linestyle="", markersize=9, color=KIND[k]) for k in KIND]
ax.legend(handles, ["LLM alone", "bot", "hybrid"], loc="center right", frameon=False, fontsize=9.5)
save(fig, "2-temperament.png", "Early and right wins",
     "Each player alone against two bots (the bot's point is from its games against Sol); labels give games won")

# 3. Every lineup: share of games won by each seat
fig, ax = plt.subplots(figsize=(11, 0.62 * len(LINEUPS) + 2.6))
fig.subplots_adjust(left=0.24, right=0.98, top=0.83, bottom=0.2)
segments = []
for i, (label, folder) in enumerate(reversed(LINEUPS)):
    left = 0
    for e in sorted(REPORTS[folder], key=lambda x: -x["win_rate"]):
        name, kind = short(e["entrant"])
        width = e["win_rate"] * 100
        ax.barh(i, width - 0.4, left=left + 0.2, height=0.6, color=KIND[kind], zorder=2)
        label = f"{name.split(' #')[0].replace('Hybrid (bot + Luna)', 'Hybrid')} {width:.0f}%"
        t = ax.text(left + width / 2, i, label, ha="center", va="center", fontsize=9,
                    color="#ffffff" if kind != "hybrid" else INK)
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
fig.legend(handles, list(KIND), loc="lower center", ncol=3, frameon=False, fontsize=9.5)
save(fig, "3-every-lineup.png", "Who won each lineup",
     "Share of games won per seat, 60 sets (360 games) per lineup; lineup 1 used the old round 4 rule")


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


groups = [("Sol vs bots", "seed707-e250a942", "openai/gpt-6.1-sol", "LLM"),
          ("Hybrid vs bots", "seed707-ca968604", "hybrid:openai/gpt-6-luna", "hybrid"),
          ("Luna vs bots", "seed707-e71dd1af", "openai/gpt-6-luna", "LLM"),
          ("Haiku vs bots", "seed707-4ef950be", "anthropic/claude-haiku-5.5", "LLM")]
data = [(g, kind, per_round(f, key), per_round(f, "bot")) for g, f, key, kind in groups]
fig, axes = plt.subplots(1, 2, figsize=(12, 4.9))
fig.subplots_adjust(left=0.13, right=0.97, top=0.78, bottom=0.17, wspace=0.55)
for ax, idx, xlabel, fmt in ((axes[0], 0, "rounds won per game", "{:.2f}"),
                             (axes[1], 1, "median bank when it wins a round ($)", "${:,.0f}")):
    for j, (g, kind, star, bot) in enumerate(reversed(data)):
        for off, (val, k) in ((0.18, (star[idx], kind)), (-0.18, (bot[idx], "bot"))):
            ax.barh(j + off, val, height=0.34, color=KIND[k], zorder=2)
            ax.text(val * 1.02, j + off, fmt.format(val), va="center", fontsize=9.5, color=INK)
    ax.set_yticks(range(len(data)), [d[0] for d in reversed(data)])
    ax.set_xlim(0, max(max(d[2][idx], d[3][idx]) for d in data) * 1.25)
    tidy(ax, xlabel)
axes[0].set_title("Rounds won", loc="left", fontsize=11.5, color=INK)
axes[1].set_title("Money per round won", loc="left", fontsize=11.5, color=INK)
handles = [plt.Rectangle((0, 0), 1, 1, color=KIND[k]) for k in KIND]
fig.legend(handles, ["the LLM", "a bot (each)", "the hybrid"], loc="lower center", ncol=3, frameon=False, fontsize=9.5)
save(fig, "4-rounds-and-banks.png", "The bots win fewer rounds, but bigger ones",
     "Same lineups as chart 1: each player alone against two bots")

# 5. Cost per game
cost = [("Luna", 0.37), ("Haiku", 0.52), ("DeepSeek", 1.43), ("Sol (half-price tier)", 1.76),
        ("Gemini 3.8 Flash (half-price, 1-set trial)", 6.9), ("Gemini 4 Argon (half-price, 1-set trial)", 9.6)]
fig, ax = plt.subplots(figsize=(9, 4.6))
fig.subplots_adjust(left=0.38, right=0.95, top=0.8, bottom=0.15)
for i, (name, c) in enumerate(reversed(cost)):
    ax.barh(i, c, height=0.56, color=KIND["LLM"], zorder=2)
    ax.text(c + 0.15, i, f"{c:.1f}¢", va="center", fontsize=10.5, color=INK)
ax.set_yticks(range(len(cost)), [c[0] for c in reversed(cost)])
ax.set_xlim(0, 11.5)
tidy(ax, "cost per game, US cents (one LLM seat)")
save(fig, "5-cost-per-game.png", "Cheap tokens don't make a cheap game",
     "Cost depends on how much a model writes and how much of its prompt is cached, not just its token price")

# 6. The bonus test: each player alone on every bonus puzzle in a deck
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
print("written to", OUT, sorted(p.name for p in OUT.glob("*.png")))
