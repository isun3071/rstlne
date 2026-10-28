"""The full reader on the real word data. Slow: run with `uv run pytest -m slow` once `python -m rstlne.data fetch` has run.
The boards here are not in dev.json, and nothing is tuned on them."""

import time

import pytest
from test_bot_reader import view_for

from rstlne import settings
from rstlne.engine.puzzle import Puzzle
from rstlne.engine.rules import new_game
from rstlne.engine.state import Phase
from rstlne.players.bot import lexicon, versions
from rstlne.players.bot.full import FullReader
from rstlne.players.bot.player import BotPlayer, make_reader
from rstlne.runner import play_game

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not lexicon.available(), reason="run python -m rstlne.data fetch first"),
]


@pytest.fixture(scope="module")
def reader():
    knobs = versions.knobs(1)
    return FullReader(lexicon.load(str(lexicon.data_dir()), knobs.vocabulary), knobs)


@pytest.mark.parametrize("answer, used, category", [
    ("STATUE OF LIBERTY", "ST", "Landmark"),
    ("PEANUT BUTTER AND JELLY", "TN", "Food & Drink"),
    ("THE EIFFEL TOWER", "E", "Landmark"),
    ("BRUSHING MY TEETH", "RSTN", "What Are You Doing?"),
])
def test_well_known_answers_read_from_a_few_letters(reader, rules, wheel_spec, answer, used, category):
    started = time.monotonic()
    belief = reader.read(view_for(rules, wheel_spec, answer, used=used, category=category))
    assert time.monotonic() - started < 2.0
    assert belief.best == answer


def test_the_bot_seat_reads_with_the_full_reader_and_names_its_data():
    bot = BotPlayer(0, settings.load_rules(), settings.load_wheel(), make_reader(versions.knobs(1)))
    assert bot.describe()["reader"] == "full" and len(bot.describe()["data"]) == 12


def test_three_full_reader_bots_finish_a_game(rules, wheel_spec):
    puzzles = (Puzzle("Landmark", "STATUE OF LIBERTY"), Puzzle("Food & Drink", "PEANUT BUTTER AND JELLY"),
               Puzzle("Place", "THE EIFFEL TOWER"), Puzzle("Living Thing", "A BALD EAGLE"))
    state = new_game(11, rules, wheel_spec, puzzles, Puzzle("Thing", "HOT COCOA", bonus=True))
    reader = make_reader(versions.knobs(1))
    final = play_game(state, [BotPlayer(i, rules, wheel_spec, reader) for i in range(3)])
    assert final.phase is Phase.GAME_OVER
