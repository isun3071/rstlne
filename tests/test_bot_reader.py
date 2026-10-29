from dataclasses import replace
from itertools import product

import pytest
from helpers import start

from rstlne.engine.puzzle import Puzzle
from rstlne.engine.rules import new_game, public_view
from rstlne.players.bot import versions
from rstlne.players.bot.reader import FrequencyReader, WordListReader, board_text

KNOBS = versions.knobs(1)
LEXICON = {"CAT": 50, "COT": 30, "CUT": 20, "DOG": 40, "DIG": 10, "BIG": 25, "HAT": 15}


def view_for(rules, spec, answer, used="", category="Thing"):
    state = new_game(1, rules, spec, (Puzzle(category, answer),) * rules.main_rounds, Puzzle("Place", "BIG CITY", bonus=True))
    state = replace(state, round=replace(state.round, used=frozenset(used)))
    return public_view(state, 0)


def test_board_text_turns_the_spaced_board_into_words():
    assert board_text("W _ _ _ L   O F   _ _ _") == "W___L OF ___"
    assert board_text("W E L L - K N O W N   F A C T") == "WELL-KNOWN FACT"


def test_frequency_reader_spreads_letters_over_hidden_squares(rules, wheel_spec):
    view = view_for(rules, wheel_spec, "CAT DOG", used="T")
    b = FrequencyReader().read(view)
    assert b.answers == () and b.oov == 1.0
    assert b.stats("T").p_hit == 0  # used letters never hit again
    assert b.stats("E").p_hit > b.stats("Q").p_hit > 0
    full = FrequencyReader().read(view_for(rules, wheel_spec, "CAT", used="CAT"))
    assert full.best == "CAT" and full.confidence == 1.0


def exact(lexicon, slots, used):
    """P(answer) by enumerating every pair of slot words that fits."""
    def fits(word, pattern):
        return len(word) == len(pattern) and all(
            (p == "_" and w not in used) or p == w for w, p in zip(word, pattern))
    options = [[(w, f) for w, f in lexicon.items() if fits(w, slot)] for slot in slots]
    weights = {}
    for combo in product(*options):
        p = 1.0
        for _, f in combo:
            p *= f
        weights[" ".join(w for w, _ in combo)] = p
    total = sum(weights.values())
    return {a: w / total for a, w in weights.items()}


def test_sampled_answers_match_exact_enumeration(rules, wheel_spec):
    knobs = replace(KNOBS, samples=20_000, unknown_word=0.0, top_answers=100)
    view = view_for(rules, wheel_spec, "CAT DOG", used="T")
    b = WordListReader(LEXICON, knobs).read(view)
    truth = exact(LEXICON, ["__T", "___"], {"T"})
    assert set(dict(b.answers)) == set(truth)
    for answer, p in b.answers:
        assert p == pytest.approx(truth[answer], abs=0.02)
    assert b.oov == 0.0
    p_c = sum(p for a, p in truth.items() if a.startswith("C"))
    assert b.stats("C").p_hit == pytest.approx(p_c, abs=0.02)


def test_used_letters_never_sit_in_hidden_squares(rules, wheel_spec):
    knobs = replace(KNOBS, unknown_word=0.0)
    b = WordListReader(LEXICON, knobs).read(view_for(rules, wheel_spec, "CAT DOG", used="TO"))
    for answer, _ in b.answers:
        first, second = answer.split(" ")
        assert first[2] == "T" and second[1] == "O"
        assert "O" not in first and "T" not in second
    assert b.stats("O").p_hit == 0 and b.stats("T").p_hit == 0


def test_a_board_no_listed_word_fits_is_all_unknown(rules, wheel_spec):
    b = WordListReader(LEXICON, KNOBS).read(view_for(rules, wheel_spec, "ZEBRA"))
    assert b.answers == () and b.oov == pytest.approx(1.0)
    assert b.stats("E").p_hit > 0


def test_unknown_words_shrink_as_letters_show(rules, wheel_spec):
    reader = WordListReader(LEXICON, replace(KNOBS, samples=4000))
    blank = reader.read(view_for(rules, wheel_spec, "CAT"))
    shown = reader.read(view_for(rules, wheel_spec, "CAT", used="CA"))
    assert 0 < shown.oov < blank.oov
    assert shown.best == "CAT"


def test_the_same_view_reads_the_same_way(rules, wheel_spec):
    reader = WordListReader(LEXICON, KNOBS)
    view = view_for(rules, wheel_spec, "CAT DOG")
    assert reader.read(view) == reader.read(view)


# A suggested answer, mixed in with a share


def test_a_suggested_answer_takes_its_share_of_the_reader_samples(rules, wheel_spec):
    knobs = replace(KNOBS, samples=20_000, unknown_word=0.0)
    reader = WordListReader(LEXICON, knobs)
    view = view_for(rules, wheel_spec, "CAT", used="T")
    alone = reader.read(view)
    mixed = reader.read(view, suggested=("COT", 0.8))
    p_cot = dict(alone.answers)["COT"]
    assert mixed.best == "COT" and mixed.confidence == pytest.approx(0.8 + 0.2 * p_cot)
    assert mixed.stats("O").p_hit == pytest.approx(0.8 + 0.2 * alone.stats("O").p_hit)
    assert mixed.stats("A").p_hit == pytest.approx(0.2 * alone.stats("A").p_hit)
    assert sum(p for _, p in mixed.answers) + mixed.oov == pytest.approx(1.0)


def test_an_answer_the_reader_never_sampled_gets_exactly_its_share(rules, wheel_spec):
    reader = WordListReader(LEXICON, replace(KNOBS, unknown_word=0.0))
    mixed = reader.read(view_for(rules, wheel_spec, "CAT", used="T"), suggested=("CIT", 0.6))
    assert mixed.best == "CIT" and mixed.confidence == pytest.approx(0.6)
    assert mixed.stats("I").p_hit == pytest.approx(0.6) and mixed.stats("I").count == pytest.approx(1.0)


def test_with_every_sampled_answer_refuted_the_suggestion_is_the_only_answer(rules, wheel_spec):
    reader = WordListReader({"CAT": 1}, replace(KNOBS, unknown_word=0.0))
    mixed = reader.read(view_for(rules, wheel_spec, "CUT", used="T"), frozenset({"CAT"}), suggested=("CUT", 0.7))
    assert mixed.answers == (("CUT", pytest.approx(0.7)),) and mixed.oov == pytest.approx(0.3)


def test_no_suggestion_reads_exactly_as_before(rules, wheel_spec):
    reader = WordListReader(LEXICON, KNOBS)
    view = view_for(rules, wheel_spec, "CAT DOG", used="T")
    assert reader.read(view, frozenset(), None) == reader.read(view)
