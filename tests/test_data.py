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


# Version 5: pairs and triples from full English Wikipedia

WORDS = ["the", "red", "door", "is", "open", "barn"]


def test_ngrams_count_pairs_and_triples_and_break_at_unknown_words():
    counter = data.NgramCounter(WORDS)
    counter.add([["the", "red", "door", "is", "open"], ["the", "red", "zzz", "barn"]])
    unigrams, pairs, triples = counter.result()
    ids = {w: i for i, w in enumerate(WORDS)}
    assert unigrams[ids["red"]] == 2 and unigrams[ids["barn"]] == 1
    assert dict(zip(*pairs)) == {data.pair_key(ids["the"], ids["red"]): 2, data.pair_key(ids["red"], ids["door"]): 1,
                                 data.pair_key(ids["door"], ids["is"]): 1, data.pair_key(ids["is"], ids["open"]): 1}
    assert dict(zip(*triples)) == {data.triple_key(ids["the"], ids["red"], ids["door"]): 1,
                                   data.triple_key(ids["red"], ids["door"], ids["is"]): 1,
                                   data.triple_key(ids["door"], ids["is"], ids["open"]): 1}


def test_a_full_counter_drops_what_it_saw_once_and_keeps_the_rest():
    counter = data.NgramCounter(WORDS, cap=2, chunk=4)
    counter.add([["the", "red", "door"]] * 5 + [["is", "open"], ["open", "barn"]])
    _, pairs, _ = counter.result()
    ids = {w: i for i, w in enumerate(WORDS)}
    kept = dict(zip(*pairs))
    assert kept[data.pair_key(ids["the"], ids["red"])] == 5 and kept[data.pair_key(ids["red"], ids["door"])] == 5
    assert data.pair_key(ids["open"], ids["barn"]) not in kept  # seen once, dropped when the counter filled


def test_counts_from_parts_merge_by_key():
    keys, counts = data.merge_counts([(np.array([1, 5]), np.array([2, 3])), (np.array([5, 9]), np.array([4, 1]))])
    assert keys.tolist() == [1, 5, 9] and counts.tolist() == [2, 7, 1]


def test_pruning_keeps_the_commonest_under_a_budget():
    keys, counts = np.arange(6), np.array([1, 2, 2, 5, 9, 3])
    kept_keys, kept_counts, minimum = data.prune_to(keys, counts, entries=3)
    assert minimum == 3 and kept_keys.tolist() == [3, 4, 5] and kept_counts.tolist() == [5, 9, 3]
    assert data.prune_to(keys, counts, entries=10)[2] == 1  # everything fits


def test_the_dump_index_lists_its_numbered_parts_in_order():
    index = ('<a href="enwiki-latest-pages-articles10.xml-p100p200.bz2">x</a>'
             '<a href="enwiki-latest-pages-articles2.xml-p10p20.bz2">x</a>'
             '<a href="enwiki-latest-pages-articles-multistream2.xml-p10p20.bz2">x</a>'
             '<a href="enwiki-latest-pages-articles2.xml-p10p20.bz2-rss.xml">x</a>')
    assert data.dump_parts(index) == ["enwiki-latest-pages-articles2.xml-p10p20.bz2",
                                      "enwiki-latest-pages-articles10.xml-p100p200.bz2"]


def test_stale_copies_of_a_part_left_in_the_listing_are_skipped():
    index = "".join(f'<a href="enwiki-latest-pages-articles27.xml-p83475910p{end}.bz2">x</a>' for end in (84130778, 84442244, 84388309))
    index += '<a href="enwiki-latest-pages-articles27.xml-p81975910p83475909.bz2">x</a>'
    assert data.dump_parts(index) == ["enwiki-latest-pages-articles27.xml-p81975910p83475909.bz2",
                                      "enwiki-latest-pages-articles27.xml-p83475910p84442244.bz2"]  # the newest reaches furthest


def wiki_part(*texts):
    xml = "".join(f"<page><text xml:space=\"preserve\">{t}</text></page>\n" for t in texts)
    return io.BytesIO(__import__("bz2").compress(xml.encode()))


def test_the_wikipedia_fetch_counts_every_part_resumes_and_writes_its_files(tmp_path, monkeypatch):
    monkeypatch.setattr(data, "vocabulary", lambda data_dir: set(WORDS))
    parts = {"p1.bz2": wiki_part("The red door is open."), "p2.bz2": wiki_part("The red barn. The red door.")}
    opened = []
    def opener(name):
        opened.append(name)
        return io.BytesIO(parts[name].getvalue())
    files = data.fetch_enwiki(tmp_path, say=lambda line: None, parts=list(parts), opener=opener, workers=1)
    assert set(files) == {"enwiki-words.txt", "enwiki-unigrams.npy", "enwiki-pair-keys.npy", "enwiki-pair-counts.npy",
                          "enwiki-triple-keys.npy", "enwiki-triple-counts.npy", "enwiki-meta.json"}
    grams = data.load_ngrams(tmp_path)
    ids = {w: i for i, w in enumerate(grams["words"])}
    pairs = dict(zip(grams["pair_keys"].tolist(), grams["pair_counts"].tolist()))
    assert pairs[data.pair_key(ids["the"], ids["red"])] == 3 and pairs[data.pair_key(ids["red"], ids["door"])] == 2
    assert not (tmp_path / ".enwiki-parts").exists()  # the per-part counts go once merged
    opened.clear()
    (tmp_path / ".enwiki-parts").mkdir()
    np.savez(tmp_path / ".enwiki-parts" / "p1.bz2.npz", **data.part_counts(data.NgramCounter(sorted(set(WORDS)))))
    data.fetch_enwiki(tmp_path, say=lambda line: None, parts=list(parts), opener=opener, workers=1)
    assert opened == ["p2.bz2"]  # a part already counted isn't read again


def test_version_4_s_fingerprint_leaves_out_wikipedia(tmp_path):
    from rstlne.players.bot import lexicon
    entry = {"files": {"pairs.sqlite": {"sha256": "aa", "bytes": 1}}}
    (tmp_path / "manifest.json").write_text(json.dumps({"tatoeba": entry}))
    before = lexicon.fingerprint(tmp_path, 100)
    (tmp_path / "manifest.json").write_text(json.dumps({"tatoeba": entry, "enwiki": {"files": {"enwiki-words.txt": {"sha256": "bb", "bytes": 1}}}}))
    assert lexicon.fingerprint(tmp_path, 100) == before
    assert lexicon.fingerprint(tmp_path, 100, extra=("enwiki",)) != before


class Dropped(Exception):
    """A dropped connection, holding something that can't cross between processes, as urllib's errors do."""

    def __init__(self):
        super().__init__("connection dropped")
        self.stream = io.BufferedReader(io.BytesIO(b"x"))


def test_a_part_whose_stream_drops_is_read_again(tmp_path, monkeypatch):
    monkeypatch.setattr(data, "vocabulary", lambda data_dir: set(WORDS))
    monkeypatch.setattr(data, "PART_BACKOFF", 0)
    tries = []
    def opener(name):
        tries.append(name)
        if len(tries) == 1:
            raise Dropped()
        return wiki_part("The red door is open.")
    data.fetch_enwiki(tmp_path, say=lambda line: None, parts=["p1.bz2"], opener=opener, workers=1)
    assert tries == ["p1.bz2", "p1.bz2"] and (tmp_path / "enwiki-pair-keys.npy").exists()


def test_a_part_that_keeps_failing_is_named_and_the_merge_waits(tmp_path, monkeypatch):
    monkeypatch.setattr(data, "vocabulary", lambda data_dir: set(WORDS))
    monkeypatch.setattr(data, "PART_BACKOFF", 0)
    def opener(name):
        if name == "bad.bz2":
            raise Dropped()
        return wiki_part("The red door is open.")
    lines = []
    with pytest.raises(RuntimeError, match="bad.bz2"):
        data.fetch_enwiki(tmp_path, say=lines.append, parts=["good.bz2", "bad.bz2"], opener=opener, workers=1)
    assert (tmp_path / ".enwiki-parts" / "good.bz2.npz").exists()  # the rest was counted and kept
    assert not (tmp_path / "enwiki-pair-keys.npy").exists()
    assert any("Dropped: connection dropped" in line for line in lines)


def test_a_failed_part_comes_back_from_a_worker_process_as_plain_text(tmp_path, monkeypatch):
    monkeypatch.setattr(data, "PART_BACKOFF", 0)
    name, error = data._count_part(("bad.bz2", WORDS, tmp_path, _always_drops))
    assert name == "bad.bz2" and error.startswith("Dropped")
    __import__("pickle").dumps((name, error))  # what a worker sends back can cross between processes


def _always_drops(name):
    raise Dropped()
