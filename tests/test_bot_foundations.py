import json
from dataclasses import replace

import pytest
from helpers import start

from rstlne.engine.rules import public_view
from rstlne.players.bot import versions
from rstlne.players.bot.belief import Belief, LetterStats
from rstlne.players.bot.seed import view_seed
from rstlne.tournament import check_bot_versions, folder_name

DEV = "puzzles/dev.json"


def belief(**changes):
    base = dict(
        letters={"T": LetterStats(p_hit=0.9, count=1.5, entropy=1.2), "Q": LetterStats(p_hit=0.0, count=0.0, entropy=0.0)},
        answers=(("WHEEL OF FORTUNE", 0.6), ("WHEEL OF FORTUNES", 0.1)),
        oov=0.2,
    )
    return Belief(**{**base, **changes})


# Belief


def test_belief_names_its_best_answer_and_confidence():
    b = belief()
    assert b.best == "WHEEL OF FORTUNE" and b.confidence == 0.6
    assert Belief(letters={}, answers=(), oov=1.0).best is None
    assert Belief(letters={}, answers=(), oov=1.0).confidence == 0.0


def test_letters_the_belief_leaves_out_never_hit():
    assert belief().stats("Z") == LetterStats(p_hit=0.0, count=0.0, entropy=0.0)
    assert belief().stats("T").count == 1.5


def test_belief_is_frozen():
    with pytest.raises(AttributeError):
        belief().oov = 0.5


@pytest.mark.parametrize("changes, message", [
    ({"letters": {"t": LetterStats(0.5, 1.0, 1.0)}}, "letter"),
    ({"letters": {"T": LetterStats(1.2, 1.0, 1.0)}}, "p_hit"),
    ({"letters": {"T": LetterStats(0.5, 0.8, 1.0)}}, "count"),
    ({"letters": {"T": LetterStats(0.0, 2.0, 0.0)}}, "count"),
    ({"letters": {"T": LetterStats(0.5, 1.0, -0.1)}}, "entropy"),
    ({"answers": (("A", 0.1), ("B", 0.3))}, "most likely first"),
    ({"answers": (("A", 0.7), ("B", 0.2))}, "sum"),
    ({"oov": -0.1}, "oov"),
])
def test_belief_rejects_impossible_numbers(changes, message):
    with pytest.raises(ValueError, match=message):
        belief(**changes)


# Seeding from the view


def test_the_same_view_gives_the_same_seed_and_a_new_board_a_new_one(rules, wheel_spec):
    state = start(rules, wheel_spec)
    view = public_view(state, 0)
    assert view_seed(view) == view_seed(public_view(state, 0))
    moved = replace(state, round=replace(state.round, used=frozenset("T")))
    assert view_seed(public_view(moved, 0)) != view_seed(view)
    assert view_seed(public_view(state, 1)) != view_seed(view)  # another seat's view


def test_view_seed_is_stable_across_processes(rules, wheel_spec):
    seed = view_seed(public_view(start(rules, wheel_spec), 0))
    assert isinstance(seed, int) and 0 <= seed < 2**64
    assert seed == view_seed(public_view(start(rules, wheel_spec), 0))  # blake2b, not Python's salted hash()


# Versions


def test_config_picks_a_known_version():
    assert versions.current({"bot": {"version": 1}}) == 1
    with pytest.raises(ValueError, match="bot version 99"):
        versions.current({"bot": {"version": 99}})
    with pytest.raises(ValueError, match=r"\[bot\] version"):
        versions.current({})


def test_the_project_config_names_a_known_version():
    from rstlne import settings
    assert versions.current(settings.load_config()) in versions.VERSIONS


def test_v1_plays_the_formula_and_v2_the_win_table():
    v1, v2 = versions.knobs(1), versions.knobs(2)
    assert v1.win_table == () and [left for left, _ in v2.win_table] == [1, 2, 3, 4]
    assert replace(v2, win_table=()) == v1  # the table is their only difference


LATER_KNOBS = {"stealer_gain", "flat_dollars"}  # added after the freeze, off in versions 1 and 2


def knob_hash(version):
    from dataclasses import asdict
    import hashlib
    knobs = {k: v for k, v in asdict(versions.knobs(version)).items() if k not in LATER_KNOBS}
    return hashlib.sha256(json.dumps(knobs, sort_keys=True).encode()).hexdigest()[:12]


def test_frozen_versions_never_change():
    """A frozen version's knobs are fixed. A change belongs in a new version, never in v1 or v2."""
    assert knob_hash(1) == "ee505edb9891" and knob_hash(2) == "4b391d4eb285"


def test_both_versions_are_pinned_to_the_same_word_data():
    assert versions.DATA[1] == versions.DATA[2] == "0640bcd6a420"


class _Reader:
    def __init__(self, lexicon, knobs):
        self.knobs = knobs


@pytest.mark.parametrize("found, ok", [("0640bcd6a420", True), ("abcdef123456", False)])
def test_a_version_refuses_word_data_it_wasnt_frozen_with(monkeypatch, found, ok):
    from rstlne.players.bot import lexicon, player
    monkeypatch.setattr(lexicon, "available", lambda root: True)
    monkeypatch.setattr(lexicon, "load", lambda path, vocabulary: None)
    monkeypatch.setattr(lexicon, "fingerprint", lambda root, vocabulary: found)
    monkeypatch.setattr(player, "FullReader", _Reader)
    assert player.make_reader(versions.knobs(1)).fingerprint == found  # self-play experiments aren't checked
    if ok:
        assert player.make_reader(versions.knobs(1), version=1).fingerprint == found
    else:
        with pytest.raises(ValueError, match="0640bcd6a420"):
            player.make_reader(versions.knobs(1), version=1)


# Tournaments


def test_folder_name_covers_the_bot_version_only_when_a_bot_plays():
    llms = ["llm:a/one", "llm:b/two", "llm:c/three"]
    with_bot = ["bot", "llm:b/two", "llm:c/three"]
    v1, v2 = {"bot": {"version": 1}}, {"bot": {"version": 2}}
    assert folder_name(llms, 42, DEV, v1) == folder_name(llms, 42, DEV, v2) == folder_name(llms, 42, DEV, {})
    assert folder_name(with_bot, 42, DEV, v1) != folder_name(with_bot, 42, DEV, v2)


def write_log(path, seats, finished=True):
    lines = [{"type": "game", "seats": seats}]
    if finished:
        lines.append({"type": "summary"})
    path.write_text("\n".join(json.dumps(line) for line in lines) + "\n")


def test_resuming_refuses_finished_games_from_another_bot_version(tmp_path):
    llm = {"kind": "llm", "model": "a/one"}
    write_log(tmp_path / "set000-perm0.jsonl", [{"kind": "bot", "version": 1}, llm, llm])
    write_log(tmp_path / "set000-perm1.jsonl", [llm, llm, llm])
    write_log(tmp_path / "set000-perm2.jsonl", [{"kind": "bot", "version": 2}, llm, llm], finished=False)  # replayed anyway
    check_bot_versions(tmp_path, 1)
    with pytest.raises(ValueError, match="bot v1.*bot v2"):
        check_bot_versions(tmp_path, 2)
