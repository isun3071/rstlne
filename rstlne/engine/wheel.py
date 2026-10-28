"""Wedge definitions, per round overlays, and seeded spins."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from enum import StrEnum

WEDGES = 24
SLOTS = WEDGES * 3  # each wedge splits into equal thirds so the Million wedge can use them
_NAMED = {"TOP", "BANKRUPT", "FREE_PLAY", "LOSE_A_TURN"}


class Kind(StrEnum):
    CASH = "cash"
    BANKRUPT = "bankrupt"
    LOSE_A_TURN = "lose_a_turn"
    FREE_PLAY = "free_play"
    MYSTERY = "mystery"
    EXPRESS = "express"
    MILLION = "million"  # the Million wedge's center third


@dataclass(frozen=True)
class Wedge:
    number: int  # 1 to 24, clockwise from TOP
    kind: Kind
    value: int = 0  # dollars per correct consonant
    wild: bool = False  # the Wild Card sits on this wedge


@dataclass(frozen=True)
class Overlay:
    from_round: int
    top: int
    wild: int | None = None
    million: int | None = None
    mystery: tuple[int, ...] = ()
    express: int | None = None

    def wedge_numbers(self) -> list[int]:
        return [n for n in (self.wild, self.million, self.express, *self.mystery) if n is not None]


@dataclass(frozen=True)
class WheelSpec:
    base: tuple[int | str, ...]
    free_play: int
    million_center: int
    mystery_face: int
    mystery_prize: int
    express: int
    overlays: tuple[Overlay, ...]
    envelopes: tuple[int, ...]  # all 24 bonus envelopes, expanded from their counts
    million_swap: tuple[int, int]  # (replaced envelope, Million envelope)

    @classmethod
    def from_dict(cls, data: dict) -> WheelSpec:
        base = tuple(data["base"])
        if len(base) != WEDGES:
            raise ValueError(f"the wheel needs {WEDGES} wedges, got {len(base)}")
        for entry in base:
            if not isinstance(entry, int) and entry not in _NAMED:
                raise ValueError(f"unknown wedge {entry!r}")

        overlays = tuple(sorted(
            (
                Overlay(
                    from_round=r["from_round"],
                    top=r["top"],
                    wild=r.get("wild"),
                    million=r.get("million"),
                    mystery=tuple(r.get("mystery", ())),
                    express=r.get("express"),
                )
                for r in data["rounds"]
            ),
            key=lambda o: o.from_round,
        ))
        if not overlays or overlays[0].from_round != 1:
            raise ValueError("the first [[rounds]] block must start at round 1")
        for overlay in overlays:
            if len(overlay.mystery) not in (0, 2):
                raise ValueError("a round with Mystery needs exactly two Mystery wedges")
            numbers = overlay.wedge_numbers()
            if len(set(numbers)) != len(numbers):
                raise ValueError(f"overlays overlap in round {overlay.from_round}")
            for number in numbers:
                if not 1 <= number <= WEDGES or not isinstance(base[number - 1], int):
                    raise ValueError(f"overlay on wedge {number} must sit on a cash wedge")

        envelopes = tuple(e["value"] for e in data["bonus"]["envelopes"] for _ in range(e["count"]))
        if len(envelopes) != WEDGES:
            raise ValueError(f"the bonus wheel needs {WEDGES} envelopes, got {len(envelopes)}")
        swap = data["bonus"]["million_swap"]
        if swap["replace"] not in envelopes:
            raise ValueError(f"no ${swap['replace']:,} envelope for the Million card to replace")

        values = data["values"]
        return cls(
            base=base,
            free_play=values["free_play"],
            million_center=values["million_center"],
            mystery_face=values["mystery_face"],
            mystery_prize=values["mystery_prize"],
            express=values["express"],
            overlays=overlays,
            envelopes=envelopes,
            million_swap=(swap["replace"], swap["with"]),
        )

    def overlay(self, round_number: int) -> Overlay:
        return [o for o in self.overlays if o.from_round <= round_number][-1]


def layout(
    spec: WheelSpec,
    round_number: int,
    *,
    wild: bool = True,
    million: bool = True,
    flipped: int | None = None,
) -> tuple[Wedge, ...]:
    """The wheel's 72 thirds for a round.

    `wild` and `million` say whether those cards still sit on the wheel.
    `flipped` is the Mystery wedge already flipped this round, if any.
    """
    overlay = spec.overlay(round_number)
    slots: list[Wedge] = []
    for number, entry in enumerate(spec.base, start=1):
        face = _face(spec, overlay, number, entry)
        if number == overlay.million and million:
            sliver = Wedge(number, Kind.BANKRUPT)
            slots += [sliver, Wedge(number, Kind.MILLION, spec.million_center), sliver]
            continue
        if number == overlay.wild and wild:
            wedge = replace(face, wild=True)
        elif number in overlay.mystery and flipped is None:
            wedge = Wedge(number, Kind.MYSTERY, spec.mystery_face)
        elif number in overlay.mystery and number != flipped:
            wedge = Wedge(number, Kind.CASH, spec.mystery_face)
        elif number == overlay.express:
            wedge = Wedge(number, Kind.EXPRESS, spec.express)
        else:
            wedge = face
        slots += [wedge] * 3
    return tuple(slots)


def _face(spec: WheelSpec, overlay: Overlay, number: int, entry: int | str) -> Wedge:
    if isinstance(entry, int):
        return Wedge(number, Kind.CASH, entry)
    if entry == "TOP":
        return Wedge(number, Kind.CASH, overlay.top)
    if entry == "FREE_PLAY":
        return Wedge(number, Kind.FREE_PLAY, spec.free_play)
    return Wedge(number, Kind(entry.lower()))


def _index(n: int, text: str) -> int:
    digest = hashlib.blake2b(text.encode(), digest_size=8).digest()
    return int.from_bytes(digest, "big") % n


def draw(n: int, seed: int, *key: object) -> int:
    """A seeded index in range(n). Every chance outcome in the game comes from here."""
    return _index(n, ":".join(str(part) for part in (seed, *key)))


def spin(seed: int, round_number: int, spin_index: int) -> int:
    """The third of the wheel a spin lands on, from 0 to 71."""
    return _index(SLOTS, f"{seed}:spin:{round_number}:{spin_index}")


def mystery_prize_wedge(seed: int, round_number: int, wedges: tuple[int, ...]) -> int:
    """Which Mystery wedge hides the $10,000. The other hides Bankrupt."""
    return wedges[draw(len(wedges), seed, "mystery", round_number)]
