"""The bot's worths as formulas with the numbers in, for --verbose thinking.

Every number here is recomputed from the situation the decision used, by the same functions, so the totals match
the worths the bot chose by. Nothing here feeds a choice, and nothing runs unless verbose thinking is asked for.
"""

from __future__ import annotations

from dataclasses import replace

from rstlne.engine.puzzle import CONSONANTS
from rstlne.engine.state import Phase, Rules
from rstlne.engine.wheel import Kind, WheelSpec
from rstlne.narrate import wedge_text

INDENT = "  "
PER_LINE = 4  # wedges listed per line in a spin's split
WEDGES = 24


def worth(value: float, win: bool) -> str:
    return f"{value:.1%}" if win else f"${value:,.0f}"


def wedges(n: float, slots: int) -> str:
    """How many wedges n of the wheel's slots make. The bot weighs the wheel in thirds of a wedge, since the
    Million wedge covers a third of one."""
    per = slots / WEDGES
    q = n / per
    if abs(q - round(q)) < 1e-9:
        return f"×{round(q)}"
    if per == 3:  # the Million wedge's third, and the two Bankrupt thirds beside it
        whole, part = divmod(round(n), 3)
        return f"×{whole or ''}{'⅓' if part == 1 else '⅔'}"
    return f"×{q:.2f}"


def _cards(win_value: float, banked: float, win: bool) -> str:
    """A won round worth more than its bank in dollars holds cards' worth too (the Wild Card, the Million)."""
    return " plus the cards it holds" if not win and win_value > banked + 0.5 else ""


def _cost(s, rules: Rules) -> int:
    return rules.express_vowel_cost if s.view.express else rules.vowel_cost


def turn(record: dict, context: dict, rules: Rules) -> list[str]:
    """How the turn's moves got their worths: solve, spin, and buy a vowel, or the known answer's plan."""
    s = context.get("s")
    if s is None:
        return []
    win = s.goal.win_mode
    if context.get("plan") is not None:
        return planned(s, context["plan"], win)
    values = record.get("values") or {}
    lines = []
    if "solve" in values:
        lines += solve(s.solve_parts(), win)
    if "spin" in values:
        lines += spin(s.spin_parts(), len(s.wheel), win)
    if "buy_vowel" in values and s.vowels:
        vowel, _ = s.vowel()
        cost = _cost(s, rules)
        lines.append(f"{INDENT}buy a vowel = its best vowel, {vowel}:")
        lines.append(INDENT + letter_line(f"{vowel} for ${cost}", s.letter_parts(vowel, s.bank - cost, 0), win))
    return lines


def solve(p: dict, win: bool) -> list[str]:
    return [
        f"{INDENT}solve = {p['c']:.0%} sure × {worth(p['win'], win)} (takes the round, banking ${p['banked']:,.0f}"
        f"{_cards(p['win'], p['banked'], win)})"
        f" + {1 - p['c']:.0%} × {worth(p['after_wrong'], win)} (wrong) = {worth(p['total'], win)}",
        f"{INDENT * 2}wrong: the wheel passes. {p['steal']:.0%} an opponent solves first × {worth(p['stolen'], win)}"
        f" + {1 - p['steal']:.0%} it comes back, {p['wrong_c']:.0%} sure, × {worth(p['back'], win)}",
    ]


def spin(groups: list[dict], n: int, win: bool) -> list[str]:
    total = sum(g["n"] * g["value"] for g in groups) / n
    cells = [f"{wedge_text(g['wedge'])} {wedges(g['n'], n)} {worth(g['value'], win)}"
             + (f" (calls {g['letter']})" if g["letter"] else "") for g in groups]
    lines = [f"{INDENT}spin = average over the {WEDGES} wedges = {worth(total, win)}:"]
    for i in range(0, len(cells), PER_LINE):
        lines.append(INDENT * 2 + ", ".join(cells[i:i + PER_LINE]))
    return lines


def letter_line(label: str, p: dict, win: bool) -> str:
    gained = p["money"] * p["count"]
    bank = (f"banks ${p['bank']:,.0f} + {p['count']:.2f} × ${p['money']:,.0f} = ${p['bank'] + gained:,.0f}" if p["money"]
            else f"banks ${p['bank']:,.0f}")
    miss = "keeps the wheel" if p["miss_keeps"] else f"the wheel passes, {p['steal']:.0%} an opponent solves first"
    return (f"{INDENT}{label} = {p['p']:.0%} hit × {worth(p['hit'], win)} ({bank}, then {p['c_hit']:.0%} sure)"
            f" + {1 - p['p']:.0%} miss × {worth(p['miss'], win)} ({miss}, {p['c_miss']:.0%} sure) = {worth(p['total'], win)}")


def letters(record: dict, context: dict, rules: Rules, spec: WheelSpec) -> list[str]:
    """The picked letter and the next best, each as its formula."""
    pick, s = record.get("letter_pick"), context.get("s")
    if not pick or s is None:
        return []
    win = s.goal.win_mode
    phase, wedge = s.view.phase, s.view.wedge
    lines = []
    for k, *_ in pick["ranked"]:
        if pick["verb"].startswith("Buys"):
            cost = _cost(s, rules)
            label, parts = f"{k} for ${cost}", s.letter_parts(k, s.bank - cost, 0)
        elif phase is Phase.FREE_PLAY:
            money = spec.free_play if k in CONSONANTS else 0
            label, parts = f"{k} on Free Play", s.letter_parts(k, s.bank, money, miss_keeps=True)
        elif phase in (Phase.CALL_CONSONANT, Phase.WILD_CONSONANT) and wedge and wedge.kind in (Kind.CASH, Kind.MILLION):
            spend = phase is Phase.WILD_CONSONANT
            w = replace(wedge, wild=False) if spend else wedge
            claims = " claiming the Million" if w.kind is Kind.MILLION else " claiming the Wild Card" if w.wild else ""
            label = f"{k} at ${w.value:,}{claims}"
            parts = s.letter_parts(k, s.bank, w.value, claim_wild=w.wild, claim_million=w.kind is Kind.MILLION,
                                   wild=False if spend else None)
        else:
            return [f"{INDENT}(a hit here leads to another choice, a Mystery flip or an Express ride, so its worth"
                    " isn't broken down)"]
        lines.append(INDENT + letter_line(label, parts, win)[len(INDENT):])
    return lines


def planned(s, plan, win: bool) -> list[str]:
    """The known answer's plan: solve now, or spin and call its consonants, most copies first."""
    answer = s.belief.best or ""
    lines = []
    if plan.letters:
        left = ", ".join(f"{k} ×{n}" for k, n in plan.letters)
        lines.append(f"{INDENT}consonants left in {answer}: {left} (it calls the most copies first)")
    else:
        lines.append(f"{INDENT}no consonants left in {answer}: spinning can't earn anything")
    c = plan.confidence[0]
    wild, million = s.wild_held, s.million_held
    won = s.goal.win_round(s.bank, wild, million).main
    wrong = s.lose_wheel(s.bank, 0.0, wild, million).main
    banked = max(s.bank, s.goal.minimum)
    lines.append(f"{INDENT}solve now = {c:.1%} sure × {worth(won, win)} (takes the round, banking"
                 f" ${banked:,.0f}{_cards(won, banked, win)}) + {1 - c:.1%} × {worth(wrong, win)} (wrong)"
                 f" = {worth(plan.options['solve'].main, win)}")
    if "spin" in plan.options:
        n = len(s.wheel)
        risky = sum(g["share"] for g in plan.spin if g["kind"] in (Kind.BANKRUPT, Kind.LOSE_A_TURN))
        lines.append(f"{INDENT}spin again = average over the {WEDGES} wedges = {worth(plan.options['spin'].main, win)}."
                     f" Bankrupt or Lose a Turn, {risky:.0%} of spins, passes the wheel, and then an opponent solves"
                     f" first {s.odds.total:.0%} of the time:")
        cells = []
        for g in plan.spin:
            name = {Kind.BANKRUPT: "Bankrupt", Kind.LOSE_A_TURN: "Lose a Turn", Kind.FREE_PLAY: "Free Play",
                    Kind.MILLION: "Million", Kind.MYSTERY: "Mystery", Kind.EXPRESS: "Express"}.get(g["kind"])
            name = name or f"${g['money']:,.0f}"
            cells.append(f"{name} {wedges(g['share'] * n, n)} {worth(g['value'], win)}")
        for i in range(0, len(cells), PER_LINE):
            lines.append(INDENT * 2 + ", ".join(cells[i:i + PER_LINE]))
        hit = next((g for g in plan.spin if "hit_chance" in g), None)
        if hit and plan.letters:
            k, copies = plan.letters[0]
            lines.append(f"{INDENT * 2}on a letter wedge it calls {k} ({copies} cop{'y' if copies == 1 else 'ies'}),"
                         f" which hits {hit['hit_chance']:.0%}; after a hit it chooses again, and a miss passes the wheel")
    return lines
