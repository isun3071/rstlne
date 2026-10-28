import gzip
import io
import json

import numpy as np
import pytest

from rstlne import data


def test_clean_keeps_board_ready_phrases_only():
    assert data.clean("a blessing in disguise") == "A BLESSING IN DISGUISE"
    assert data.clean("don’t count your chickens") == "DON'T COUNT YOUR CHICKENS"
    assert data.clean("Paris, Texas") == "PARIS, TEXAS"
    for bad in ("Apollo 11", "Mercury (planet)", "x", "naïve", "one two three four five six seven eight nine"):
        assert data.clean(bad) is None


def test_wiktionary_entries_keep_multiword_phrases_with_their_part_of_speech():
    lines = [json.dumps(e) for e in (
        {"word": "a blessing in disguise", "pos": "noun", "senses": [{}, {}]},
        {"word": "rain cats and dogs", "pos": "verb", "senses": [{}]},
        {"word": "cat", "pos": "noun", "senses": [{}]},  # one word: wordfreq has those
        {"word": "24/7", "pos": "adv", "senses": [{}]},
    )]
    rows = list(data.wiktionary_phrases(lines))
    assert rows == [("A BLESSING IN DISGUISE", "noun", 2.0), ("RAIN CATS AND DOGS", "verb", 1.0)]


def test_wikidata_results_become_labels_with_their_kind_and_sitelinks():
    body = {"results": {"bindings": [
        {"label": {"value": "Golden Gate Bridge"}, "links": {"value": "120"}},
        {"label": {"value": "Q12345"}, "links": {"value": "50"}},
    ]}}
    assert list(data.wikidata_labels(body, "landmark")) == [("GOLDEN GATE BRIDGE", "landmark", 120.0)]


def test_wikidata_queries_filter_by_sitelinks_without_personal_details():
    query = data.wikidata_query("wdt:P31 wd:Q5", 40)
    assert "wd:Q5" in query and "?s >= 40" in query and 'LANG(?label) = "en"' in query
    assert "@" not in data.AGENT
    animals = data.wikidata_query("wdt:P1843 ?label", 30, label=None)  # common names carry their own label
    assert "rdfs:label" not in animals and "wdt:P1843 ?label" in animals


def test_vectors_keep_the_vocabulary_lowercase_first_and_unit_length():
    text = "4 3\nParis 3 0 4\nparis 1 0 0\ncat 0 0 2\nzebra 1 1 1\n"
    words, matrix = data.read_vectors(io.StringIO(text), {"paris", "cat"})
    assert words == ["paris", "cat"]
    assert matrix.dtype == np.float16 and matrix.shape == (2, 3)
    assert np.allclose(matrix[0], [0.6, 0, 0.8], atol=1e-3) and np.allclose(np.linalg.norm(matrix, axis=1), 1, atol=1e-3)


def test_phrases_round_trip_through_sqlite(tmp_path):
    db = tmp_path / "lexicon.sqlite"
    data.store_phrases(db, "wiktionary", [("RAIN CATS AND DOGS", "verb", 1.0)])
    data.store_phrases(db, "wikidata", [("GOLDEN GATE BRIDGE", "landmark", 120.0)])
    data.store_phrases(db, "wiktionary", [("A BLESSING IN DISGUISE", "noun", 2.0)])  # a refetch replaces its source
    assert sorted(data.load_phrases(db)) == [
        ("A BLESSING IN DISGUISE", "wiktionary", "noun", 2.0), ("GOLDEN GATE BRIDGE", "wikidata", "landmark", 120.0)]


def test_the_manifest_records_every_file_and_enforces_the_cap(tmp_path):
    (tmp_path / "a.bin").write_bytes(b"x" * 10)
    entry = data.record(tmp_path, "cmudict", ["a.bin"], cap=100)
    assert entry["files"]["a.bin"]["bytes"] == 10 and len(entry["files"]["a.bin"]["sha256"]) == 64
    assert json.loads((tmp_path / "manifest.json").read_text())["cmudict"]["license"] == data.SOURCES["cmudict"].license
    with pytest.raises(data.OverBudget):
        data.record(tmp_path, "cmudict", ["a.bin"], cap=5)


def test_gzip_streams_decode_line_by_line():
    raw = gzip.compress(b"one\ntwo\n")
    assert list(data.lines(io.BytesIO(raw), gz=True)) == ["one\n", "two\n"]


def test_wikitext_keeps_prose_and_drops_markup():
    page = [
        '      <text bytes="2693" xml:space="preserve">In [[mathematics]], \'\'\'arithmetic\'\'\' is the study of [[number]]s.',
        "{{Infobox thing",
        "| name = Arithmetic",
        "}}",
        "==Overview==",
        "Most people learn it in [[primary school|school]].&lt;ref&gt;A source&lt;/ref&gt; {{citation needed}}",
        "[[Category:Mathematics]]",
        "* &lt;math&gt;2+3=5&lt;/math&gt;",
        "</text>",
        "    <title>Not text</title>",
    ]
    assert list(data.wikitext_sentences(page)) == [
        ["in", "mathematics", "arithmetic", "is", "the", "study", "of", "numbers"],
        ["most", "people", "learn", "it", "in", "school"],
    ]


def test_tatoeba_lines_become_sentences():
    rows = ["1276\teng\tLet's try something.\n", "1277\teng\tI have to go to sleep. Now!\n"]
    assert list(data.tatoeba_sentences(rows)) == [["let's", "try", "something"], ["i", "have", "to", "go", "to", "sleep"], ["now"]]


def test_pairs_count_neighbors_inside_the_vocabulary_and_drop_rare_ones():
    sentences = [["the", "back", "porch"], ["the", "back", "porch"], ["the", "back", "door"], ["zzz", "porch"]]
    words, pairs = data.count_pairs(sentences, {"the", "back", "porch", "door"}, minimum=2)
    assert pairs == {("the", "back"): 3, ("back", "porch"): 2}
    assert words["porch"] == 3 and "zzz" not in words


def test_pairs_round_trip_through_sqlite(tmp_path):
    db = tmp_path / "pairs.sqlite"
    data.store_pairs(db, "tatoeba", {"back": 3, "porch": 2}, {("back", "porch"): 2})
    data.store_pairs(db, "simplewiki", {"back": 5}, {("back", "porch"): 4})
    assert data.load_pairs(db) == ({"back": 8, "porch": 2}, {("back", "porch"): 6})


def test_status_counts_a_shared_file_once(tmp_path):
    (tmp_path / "pairs.sqlite").write_bytes(b"x" * 10)
    data.record(tmp_path, "tatoeba", ["pairs.sqlite"])
    (tmp_path / "pairs.sqlite").write_bytes(b"x" * 30)
    data.record(tmp_path, "simplewiki", ["pairs.sqlite"])
    lines = []
    data.status(tmp_path, say=lines.append)
    assert lines[-1].startswith("total 0.00 GB") and "30" not in lines[-1]
    assert data.total_bytes(tmp_path) == 30 + (tmp_path / "manifest.json").stat().st_size
