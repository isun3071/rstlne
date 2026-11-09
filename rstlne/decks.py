"""Building play decks. The mega deck joins every aired puzzle in the archive with every generated puzzle:

    uv run python -m rstlne.decks mega --out puzzles/mega.json

Each puzzle keeps where it came from: an aired puzzle its airings (season, episode, air date, round), a
generated one the decks it's in. The web page shows that once a round is over. The mega deck holds aired
puzzles, so it stays out of git, like the archive, and it's for play only: no results are scored on it.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from rstlne import settings
from rstlne.engine.puzzle import Puzzle, normalize
from rstlne.puzzlegen import fits_rows

ROUND_4_LETTERS = 18  # an untagged generated main puzzle this short or shorter plays in round 4, where aired ones are shortest


def season_of(year: int, month: int) -> int:
    """The syndicated show's season for an air date: season 1 began in September 1983, and each starts in September."""
    return year - 1982 if month >= 9 else year - 1983


def _air_date(text: str) -> date | None:
    try:
        m, d, y = (int(x) for x in text.split("/"))
    except ValueError:
        return None
    return date(2000 + y if y < 100 else y, m, d)


def _letters(answer: str) -> int:
    return sum(c.isalpha() for c in answer)


def _round_for(answer: str) -> int:
    """A round for an untagged generated main puzzle: short ones to round 4, the rest spread over rounds 1 to 3
    by a hash of the answer, so a rebuild deals them the same way."""
    if _letters(answer) <= ROUND_4_LETTERS:
        return 4
    return int(hashlib.sha256(answer.encode()).hexdigest(), 16) % 3 + 1


def build_mega(archive: Path, generated: Sequence[Path]) -> dict:
    """The mega deck from the aired archive (a CSV with Puzzle, Category, Date, Episode_Number, Round) and
    generated deck files. Toss-ups, empty rows, answers that don't normalize, and answers that don't fit the board are
    left out. An answer in both keeps its aired copy; one in several generated decks lists them all."""
    config = settings.load_config()["puzzlegen"]
    main_rows, bonus_rows = config["rows"], config["bonus_rows"]
    puzzles: dict[tuple[str, bool], dict] = {}

    def fits(answer: str, bonus: bool) -> bool:
        return fits_rows(answer, bonus_rows if bonus else main_rows)

    season_episodes: dict[int, set] = {}  # each season's episodes in the archive (air date, number), from every row, toss-ups too
    with Path(archive).open(newline="") as fh:
        for row in csv.DictReader(fh):
            aired = _air_date(row.get("Date", ""))
            number = row.get("Episode_Number", "").lstrip("#")
            if aired and number.isdigit():
                season_episodes.setdefault(season_of(aired.year, aired.month), set()).add((aired, int(number)))
            mark = (row.get("Round") or "").strip()
            if not row.get("Puzzle") or mark.startswith("T"):  # toss-ups and empty rows
                continue
            bonus = mark == "BR"
            try:
                p = Puzzle.from_dict({"category": row["Category"], "answer": row["Puzzle"], "bonus": bonus,
                                      **({} if bonus else {"round": mark})})
            except (ValueError, KeyError):
                continue
            if not fits(p.answer, bonus):
                continue
            aired = _air_date(row.get("Date", ""))
            airing = {"season": season_of(aired.year, aired.month) if aired else None,
                      "episode": int(row["Episode_Number"].lstrip("#")) if row.get("Episode_Number", "").lstrip("#").isdigit() else None,
                      "date": aired.isoformat() if aired else None, "round": mark}
            key = (p.answer, bonus)
            if key in puzzles:
                airings = puzzles[key]["source"]["airings"]
                if not any(a["episode"] == airing["episode"] and a["round"] == airing["round"] for a in airings):
                    airings.append(airing)  # the archive lists some rows twice
                continue
            entry = {"category": p.category, "answer": p.answer, "bonus": bonus,
                     "source": {"kind": "aired", "airings": [airing]}}
            if not bonus:
                entry["round"] = min(p.round or 4, 4)  # rounds 5 to 7 play as round 4 in a four-round game
            puzzles[key] = entry
    for path in generated:
        data = json.loads(Path(path).read_text())
        if not isinstance(data, dict) or "puzzles" not in data:
            continue
        for raw in data["puzzles"]:
            try:
                answer, bonus = normalize(raw["answer"]), bool(raw.get("bonus", False))
            except (ValueError, KeyError):
                continue
            if not fits(answer, bonus):
                continue
            key = (answer, bonus)
            if key in puzzles:
                if puzzles[key]["source"]["kind"] == "generated" and Path(path).stem not in puzzles[key]["source"]["decks"]:
                    puzzles[key]["source"]["decks"].append(Path(path).stem)
                continue
            entry = {"category": raw["category"], "answer": answer, "bonus": bonus,
                     "source": {"kind": "generated", "decks": [Path(path).stem]}}
            if not bonus:
                tag = raw.get("round")
                entry["round"] = tag if isinstance(tag, int) and 1 <= tag <= 4 else _round_for(answer)
            puzzles[key] = entry
    # The archive numbers episodes across the whole run. Within a season, count them in the order they aired: the
    # COVID seasons' numbers overlap (season 37's last episodes aired in August 2020, numbered past season 38's first).
    order = {(season, number): i for season, eps in season_episodes.items()
             for i, (_, number) in enumerate(sorted(eps), 1)}
    for p in puzzles.values():
        for a in p["source"].get("airings", []):
            if (a["season"], a["episode"]) in order:
                a["season_episode"] = order[(a["season"], a["episode"])]
    out = list(puzzles.values())
    counts = {f"{kind}_{part}": sum(1 for p in out if p["source"]["kind"] == kind and p["bonus"] == (part == "bonus"))
              for kind in ("aired", "generated") for part in ("main", "bonus")}
    return {"name": "mega", "built_from": [str(archive), *(str(p) for p in generated)], "counts": counts, "puzzles": out}


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m rstlne.decks", description="Build play decks.")
    jobs = parser.add_subparsers(dest="job", required=True)
    m = jobs.add_parser("mega", help="every aired puzzle in the archive and every generated puzzle, with their sources")
    m.add_argument("--archive", default=str(settings.ROOT / "puzzles" / "all_recent_puzzles_ktebbe.csv"))
    m.add_argument("--generated", nargs="*", help="generated deck files (default: every one in puzzles/generated/)")
    m.add_argument("--out", default=str(settings.ROOT / "puzzles" / "mega.json"))
    args = parser.parse_args(argv)
    generated = [Path(p) for p in args.generated] if args.generated else sorted((settings.ROOT / "puzzles" / "generated").glob("*.json"))
    deck = build_mega(Path(args.archive), generated)
    Path(args.out).write_text(json.dumps(deck))
    print(f"wrote {args.out}: {len(deck['puzzles'])} puzzles; " + ", ".join(f"{k.replace('_', ' ')} {v:,}" for k, v in deck["counts"].items()))


if __name__ == "__main__":
    main()
