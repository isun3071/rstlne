import math
from dataclasses import replace

import numpy as np
import pytest
from test_bot_reader import view_for

from rstlne.players.bot import versions
from rstlne.players.bot.full import FullReader, category_kinds
from rstlne.players.bot.lexicon import Lexicon, rhyme_key, tokens

KNOBS = replace(versions.knobs(1), samples=600, unknown_word=0.0, top_answers=200)


def reader(words, phrases=(), pairs=None, counts=None, rhymes=None, knobs=KNOBS):
    return FullReader(Lexicon.build(words, phrases, pairs, counts, rhymes), knobs)


def test_tokens_split_words_from_their_separators():
    assert tokens("WELL-KNOWN FACT") == (("WELL", "KNOWN", "FACT"), ("-", " "))
    assert tokens("PARIS, TEXAS") == (("PARIS,", "TEXAS"), (" ",))


def test_pair_counts_look_up_every_pair_at_once():
    lex = Lexicon.build({"back": 1e-4, "porch": 1e-5, "door": 1e-5}, pairs={("back", "porch"): 7}, counts={"back": 20})
    ids = lambda *w: np.array([lex.pair_ids.get(x.upper(), -1) for x in w])
    assert lex.pair_count(ids("BACK", "DOOR"), ids("PORCH", "DOOR", "ZEBRA")).tolist() == [[7, 0, 0], [0, 0, 0]]


def test_rhyme_keys_start_at_the_last_stressed_vowel():
    assert rhyme_key(["K", "AE1", "T"]) == "AE1 T"
    assert rhyme_key(["B", "AE1", "N", "AH0", "N", "AH0"]) == "AE1 N AH0 N AH0"


def test_categories_name_the_kinds_of_phrase_that_fit():
    assert "dish" in category_kinds("Food & Drink") and "person" in category_kinds("Person")
    assert "landmark" in category_kinds("Landmark") and "proverb" in category_kinds("Phrase")


def exact(r, words, kinds, category, used=frozenset()):
    """Every path through the chain, weighted as the reader defines it, summed per answer."""
    knobs, lex = r.knobs, r.lexicon
    def fits(w, p):
        return len(w) == len(p) and all((c == "_" and x not in used) or c == x for x, c in zip(w, p))
    def link(a, b):
        ca = lex.word_counts[lex.pair_ids[a]] if a in lex.pair_ids else 0
        if not ca:
            return 1.0
        cab = lex.pair_count(np.array([lex.pair_ids[a]]), np.array([lex.pair_ids.get(b, -1)]))[0, 0]
        seen = lex.distinct[lex.pair_ids[a]]
        witten_bell = (cab / lex.freq(b) + seen) / (ca + seen)  # P(b | a) / P(b)
        return (1 - knobs.pair_weight) + knobs.pair_weight * witten_bell
    phrases = [(p, start) for start in range(len(words)) for length in range(1, len(words) - start + 1)
               for p in lex.phrases((tuple(len(w) for w in words[start:start + length]), tuple(" " for _ in range(length - 1))))
               if all(fits(x, w) for x, w in zip(p.words, words[start:start + length]))]
    totals = {}
    def walk(i, prev, weight, chosen):
        if i == len(words):
            text = " ".join(chosen)
            totals[text] = totals.get(text, 0) + weight
            return
        for w in lex.by_length.get(len(words[i]), ()):
            if fits(w, words[i]):
                walk(i + 1, w, weight * lex.freq(w) * (link(prev, w) if prev else 1.0), chosen + [w])
        for p, start in phrases:
            if start == i:
                walk(i + len(p.words), None, weight * r.match_weight(p, kinds), chosen + list(p.words))
    walk(0, None, 1.0, [])
    total = sum(totals.values())
    return {a: w / total for a, w in totals.items()}


def test_sampled_answers_match_every_path_through_the_chain(rules, wheel_spec):
    words = {"back": 3e-4, "pack": 2e-4, "porch": 2e-5, "perch": 3e-5, "torch": 2e-5}
    phrases = [("back porch", "noun", 1.0), ("pack torch", "verb", 1.0)]
    pairs, counts = {("back", "porch"): 30, ("pack", "perch"): 5}, {"back": 100, "pack": 50}
    r = reader(words, phrases, pairs, counts, knobs=replace(KNOBS, samples=30_000))
    b = r.read(view_for(rules, wheel_spec, "BACK PORCH", category="Thing"))
    truth = exact(r, ["____", "_____"], category_kinds("Thing"), "THING")
    sampled = dict(b.answers)
    assert set(sampled) <= set(truth)
    for answer, p in truth.items():  # answers too rare to sample come out near zero either way
        assert sampled.get(answer, 0.0) == pytest.approx(p, abs=0.015)


def test_a_known_phrase_reads_off_a_blank_board(rules, wheel_spec):
    words = {"a": 3e-2, "i": 1e-2, "blessing": 1e-5, "blistery": 1e-6, "in": 1e-2, "on": 1e-2, "disguise": 5e-6, "displace": 5e-6}
    r = reader(words, [("blessing in disguise", "noun", 3.0)])
    b = r.read(view_for(rules, wheel_spec, "A BLESSING IN DISGUISE", category="Phrase"))
    assert b.best == "A BLESSING IN DISGUISE"
    assert b.confidence == pytest.approx(0.75 * 0.5, abs=0.06)  # A over I, times the phrase's half of the run


def test_placeholders_in_headwords_fill_in(rules, wheel_spec):
    words = {"count": 1e-4, "mount": 1e-4, "your": 1e-3, "chickens": 1e-6, "kitchens": 1e-6}
    r = reader(words, [("count one's chickens", "proverb", 2.0)])
    b = r.read(view_for(rules, wheel_spec, "COUNT YOUR CHICKENS", used="OU", category="Phrase"))
    assert b.best == "COUNT YOUR CHICKENS"


def test_before_and_after_overlaps_two_phrases_on_a_shared_word(rules, wheel_spec):
    words = {"piece": 1e-4, "of": 2e-2, "cake": 5e-5, "walk": 1e-4, "talk": 1e-4, "bake": 5e-5}
    phrases = [("piece of cake", "phrase", 3.0), ("cake walk", "noun", 1.0)]
    r = reader(words, phrases)
    b = r.read(view_for(rules, wheel_spec, "PIECE OF CAKE WALK", used="E", category="Before & After"))
    assert b.best == "PIECE OF CAKE WALK"
    plain = r.read(view_for(rules, wheel_spec, "PIECE OF CAKE WALK", used="E", category="Phrase"))
    assert dict(b.answers)["PIECE OF CAKE WALK"] > dict(plain.answers).get("PIECE OF CAKE WALK", 0)


def test_what_are_you_doing_favors_ing_words(rules, wheel_spec):
    words = {"walking": 1e-5, "walkers": 4e-5, "the": 5e-2, "dog": 1e-4}
    r = reader(words)
    used = "WALKTHDO"  # WALK___ fits both words
    doing = r.read(view_for(rules, wheel_spec, "WALKING THE DOG", used=used, category="What Are You Doing?"))
    thing = r.read(view_for(rules, wheel_spec, "WALKING THE DOG", used=used, category="Thing"))
    assert doing.best == "WALKING THE DOG" and thing.best == "WALKERS THE DOG"


def test_same_letter_favors_neighbors_with_one_first_letter(rules, wheel_spec):
    words = {"big": 1e-4, "blue": 3e-5, "clue": 6e-5, "bubbles": 1e-6}
    r = reader(words)
    used = "IGLUES"  # _LUE fits both, with B and C hidden
    assert r.read(view_for(rules, wheel_spec, "BIG BLUE BUBBLES", used=used, category="Same Letter")).best == "BIG BLUE BUBBLES"
    assert r.read(view_for(rules, wheel_spec, "BIG BLUE BUBBLES", used=used, category="Thing")).best == "BIG CLUE BUBBLES"


def test_rhyme_time_favors_rhymes_even_with_a_word_between(rules, wheel_spec):
    words = {"wear": 1e-4, "and": 3e-2, "tear": 2e-5, "team": 8e-5}
    rhymes = {"wear": ["EH1 R"], "tear": ["EH1 R", "IH1 R"], "team": ["IY1 M"]}
    r = reader(words, rhymes=rhymes)
    used = "WEAND"  # TEA_ fits both, with R and M hidden
    assert r.read(view_for(rules, wheel_spec, "WEAR AND TEAR", used=used, category="Rhyme Time")).best == "WEAR AND TEAR"
    assert r.read(view_for(rules, wheel_spec, "WEAR AND TEAR", used=used, category="Thing")).best == "WEAR AND TEAM"


def test_same_name_checks_both_halves_share_the_ending(rules, wheel_spec):
    words = {"birthday": 2e-5, "wedding": 3e-5, "cake": 5e-5, "bell": 6e-5}
    phrases = [("birthday cake", "noun", 1.0), ("wedding cake", "noun", 1.0), ("wedding bell", "noun", 1.0)]
    r = reader(words, phrases)
    view = view_for(rules, wheel_spec, "BIRTHDAY & WEDDING CAKE", used="BIRTHDAYWEDNG", category="Same Name")
    assert r.read(view).best == "BIRTHDAY & WEDDING CAKE"


def test_hyphens_and_commas_stay_on_the_board(rules, wheel_spec):
    r = reader({"well": 1e-4, "known": 1e-4, "fact": 1e-4, "paris": 1e-4, "texas": 1e-4})
    assert r.read(view_for(rules, wheel_spec, "WELL-KNOWN FACT", used="WLKNOF")).best == "WELL-KNOWN FACT"
    assert r.read(view_for(rules, wheel_spec, "PARIS, TEXAS", used="PRSTX")).best == "PARIS, TEXAS"


def test_unknown_words_and_used_letters(rules, wheel_spec):
    r = reader({"cat": 1e-4, "cot": 1e-4}, knobs=replace(KNOBS, unknown_word=0.02))
    nothing = r.read(view_for(rules, wheel_spec, "ZEBRA"))
    assert nothing.answers == () and nothing.oov == pytest.approx(1.0)
    b = r.read(view_for(rules, wheel_spec, "CAT", used="O"))
    assert all("O" not in a for a, _ in b.answers) and b.best == "CAT"


def test_the_same_view_reads_the_same_way(rules, wheel_spec):
    r = reader({"back": 3e-4, "pack": 2e-4, "porch": 2e-5, "perch": 3e-5})
    view = view_for(rules, wheel_spec, "BACK PORCH")
    assert r.read(view) == r.read(view)


def test_a_phrase_claims_its_odds_against_every_free_sequence_of_its_shape():
    words = {"back": 3e-4, "pack": 2e-4, "porch": 2e-5, "perch": 3e-5, "torch": 2e-5}
    r = reader(words, [("back porch", "noun", 1.0), ("pack torch", "noun", 3.0)])
    lex, knobs = r.lexicon, r.knobs
    back, pack = (p for p in lex.phrases(((4, 5), (" ",))) if p.words[0] in ("BACK", "PACK"))
    if back.words[0] != "BACK":
        back, pack = pack, back
    mass = lex.length_mass[4] * lex.length_mass[5]
    share = (1 + math.log1p(1.0)) / ((1 + math.log1p(1.0)) + (1 + math.log1p(3.0)))
    assert r.match_weight(back, {"noun"}) == pytest.approx(knobs.phrase_odds * mass * share)
    assert r.match_weight(back, {"person"}) == pytest.approx(knobs.phrase_odds_other * mass * share)


def test_one_word_names_nudge_a_slot_without_taking_it_over():
    r = reader({"ohio": 1e-5, "back": 3e-4}, [("ohio", "state", 100.0)])
    ohio = next(r.lexicon.phrases(((4,), ())))
    assert r.match_weight(ohio, {"state"}) == pytest.approx(r.knobs.name_odds * r.lexicon.length_mass[4])


def test_popularity_grows_with_the_phrase_s_rarest_word_pair():
    words = {"blessing": 1e-5, "analysis": 1e-5, "in": 1e-2, "of": 2e-2, "disguise": 5e-6, "variance": 5e-6}
    lex = Lexicon.build(words, [("blessing in disguise", "noun", 1.0), ("analysis of variance", "noun", 1.0)],
                        pairs={("blessing", "in"): 13, ("in", "disguise"): 81, ("analysis", "of"): 322, ("of", "variance"): 3},
                        counts={"blessing": 20, "in": 900, "analysis": 400, "of": 999})
    blessing, analysis = sorted(lex.phrases(((8, 2, 8), (" ", " "))), key=lambda p: p.words[0], reverse=True)
    assert blessing.words[0] == "BLESSING"
    assert blessing.popularity == pytest.approx((1 + math.log1p(1.0)) * (1 + math.log1p(13)))
    assert blessing.popularity > analysis.popularity


def test_structural_categories_let_any_kind_of_phrase_fit():
    assert category_kinds("Before & After") == {"*"} and category_kinds("Same Name") == {"*"}
    r = reader({"cake": 1e-4, "walk": 1e-4}, [("cake walk", "noun", 1.0)])
    phrase = next(r.lexicon.phrases(((4, 4), (" ",))))
    assert r.match_weight(phrase, {"*"}) == r.match_weight(phrase, {"noun"})


def test_unseen_pairs_cost_more_after_a_word_with_plenty_of_evidence():
    words = {"county": 1.5e-4, "your": 3.4e-3, "fair": 1e-4}
    lex = Lexicon.build(words, pairs={("county", "fair"): 24, ("county", "line"): 30}, counts={"county": 2000})
    r = FullReader(lex, KNOBS)
    county = _slot_for(r, "COUNTY")
    nxt = _slot_for(r, "____")
    links = dict(zip(nxt.words, r._links(county, nxt, "EVENT")[0]))
    assert links["FAIR"] > 50 and links["YOUR"] < 0.2
    assert lex.distinct[lex.pair_ids["COUNTY"]] == 2


def _slot_for(r, pattern):
    return r._slot(pattern, set(), "EVENT")


# Version 5, R1: one-letter words

def test_a_word_that_uppercases_like_another_keeps_the_larger_frequency():
    words = {"i": 0.0123, "ı": 2e-7, "have": 1e-3}  # the Turkish dotless ı uppercases to I
    assert Lexicon.build(words).freq("I") == pytest.approx(2e-7)  # version 4's lexicon, kept as it was
    assert Lexicon.build(words, cased=True).freq("I") == pytest.approx(0.0123)


def test_a_one_letter_slot_holds_only_a_i_and_o():
    words = {"a": 0.02, "i": 0.012, "o": 1e-4, "s": 7e-4, "b": 2e-4}
    five = reader(words, knobs=replace(KNOBS, one_letter=("A", "I", "O")))
    assert set(five._slot("_", set(), "Phrase").words) == {"A", "I", "O"}
    assert "S" in reader(words)._slot("_", set(), "Phrase").words  # version 4 keeps every letter


def test_the_bot_reads_i_once_the_lexicon_keeps_its_frequency(rules, wheel_spec):
    words = {"i": 0.0123, "ı": 2e-7, "b": 2e-4, "have": 1e-3, "no": 1e-3, "idea": 1e-4}
    view = view_for(rules, wheel_spec, "I HAVE NO IDEA", used="HVNDE", category="Phrase")
    five = FullReader(Lexicon.build(words, cased=True), replace(KNOBS, one_letter=("A", "I", "O")))
    assert five.read(view).best == "I HAVE NO IDEA"


def test_each_lexicon_variant_has_its_own_cache(tmp_path):
    from rstlne.players.bot.lexicon import cache_path
    assert cache_path(tmp_path, "abc123", cased=False).name == "compiled-abc123.pickle"  # version 4's, unchanged
    assert cache_path(tmp_path, "abc123", cased=True).name == "compiled-abc123-cased.pickle"


# Version 5, R2 to R5: Wikipedia pairs and triples, vectors for unseen pairs, single words

from rstlne.players.bot.lexicon import Ngrams  # noqa: E402

V5 = replace(KNOBS, cased_lexicon=True, one_letter=("A", "I", "O"))


def best(lex, knobs, rules, spec, answer, used, category="Thing"):
    return FullReader(lex, knobs).read(view_for(rules, spec, answer, used=used, category=category)).best


def test_wikipedia_pair_counts_join_the_links(rules, wheel_spec):
    lex = Lexicon.build({"ramp": 1e-4, "damp": 1e-5, "socks": 1e-5})
    lex.ngrams = Ngrams.build({"ramp": 900, "damp": 100, "socks": 300}, pairs={("damp", "socks"): 60})
    assert best(lex, V5, rules, wheel_spec, "DAMP SOCKS", "AMPSOCK") == "RAMP SOCKS"  # version 4 never looks
    assert best(lex, replace(V5, ngrams=True), rules, wheel_spec, "DAMP SOCKS", "AMPSOCK") == "DAMP SOCKS"


def test_triples_judge_the_whole_phrase(rules, wheel_spec):
    words = {"come": 1e-3, "down": 1e-3, "join": 1e-4, "the": 5e-2, "party": 1e-4}
    unigrams = {"come": 20000, "down": 30000, "join": 3000, "the": 900000, "party": 4000}
    pairs = {("come", "down"): 180, ("come", "join"): 40, ("down", "the"): 3300, ("join", "the"): 200, ("the", "party"): 800}
    lex = Lexicon.build(words)
    triples = {("join", "the", "party"): 300, ("come", "join", "the"): 30, ("come", "down", "the"): 5}  # never DOWN THE PARTY
    lex.ngrams = Ngrams.build(unigrams, pairs=pairs, triples=triples)
    knobs = replace(V5, ngrams=True)
    assert best(lex, knobs, rules, wheel_spec, "COME JOIN THE PARTY", "CMEOHTPARYN") == "COME DOWN THE PARTY"
    assert best(lex, replace(knobs, triple_weight=1.0), rules, wheel_spec, "COME JOIN THE PARTY", "CMEOHTPARYN") == "COME JOIN THE PARTY"


def test_unseen_pairs_lean_on_how_close_the_words_are(rules, wheel_spec):
    vectors = {"damp": np.array([1.0, 0.2, 0.0]), "socks": np.array([0.9, 0.3, 0.1]), "ramp": np.array([0.0, 0.1, 1.0])}
    lex = Lexicon.build({"ramp": 2e-5, "damp": 1e-5, "socks": 1e-5}, vectors=vectors)
    assert best(lex, V5, rules, wheel_spec, "DAMP SOCKS", "AMPSOCK") == "RAMP SOCKS"
    assert best(lex, replace(V5, vector_pair_weight=4.0), rules, wheel_spec, "DAMP SOCKS", "AMPSOCK") == "DAMP SOCKS"


def test_a_one_word_answer_leans_harder_on_the_category(rules, wheel_spec):
    vectors = {"waving": np.array([1.0, 0.1]), "having": np.array([0.1, 1.0]), "doing": np.array([0.95, 0.2])}
    lex = Lexicon.build({"having": 1e-3, "waving": 2e-5, "doing": 1e-3}, vectors=vectors)
    category = "What Are You Doing?"
    assert best(lex, V5, rules, wheel_spec, "WAVING", "AVING", category) == "HAVING"
    assert best(lex, replace(V5, single_fit_weight=12.0), rules, wheel_spec, "WAVING", "AVING", category) == "WAVING"


def test_wikipedia_counts_load_from_the_fetched_files(tmp_path):
    from rstlne import data
    words = ["damp", "socks", "the"]
    counter = data.NgramCounter(words)
    counter.add([["damp", "socks"], ["damp", "socks"], ["the", "damp", "socks"]])
    unigrams, (pk, pc), (tk, tc) = counter.result()
    (tmp_path / "enwiki-words.txt").write_text("\n".join(words) + "\n")
    for name, array in (("unigrams", unigrams), ("pair-keys", pk), ("pair-counts", pc), ("triple-keys", tk), ("triple-counts", tc)):
        np.save(tmp_path / f"enwiki-{name}.npy", array)
    grams = Ngrams.load(tmp_path)
    ids = grams.ids_of(["DAMP", "SOCKS", "THE", "ZEBRA"])
    assert ids[-1] == -1 and grams.pair(ids[:1], ids[1:2])[0, 0] == 3
    assert grams.triple(ids[2], ids[0], ids[1]) == 1 and grams.followers[ids[0]] == 1


def test_coherence_links_words_that_aren_t_neighbours(rules, wheel_spec):
    vectors = {"baking": np.array([1.0, 0.1, 0.0]), "having": np.array([0.0, 0.2, 1.0]),
               "cake": np.array([0.95, 0.2, 0.05]), "pound": np.array([0.6, 0.6, 0.2])}
    lex = Lexicon.build({"having": 1e-3, "baking": 1e-4, "a": 2e-2, "pound": 1e-4, "cake": 1e-4}, vectors=vectors)
    answer, used = "BAKING A POUND CAKE", "AINGPOUDCE"  # _A_ING: HAVING or BAKING, three words from CA_E
    assert best(lex, V5, rules, wheel_spec, answer, used) == "HAVING A POUND CAKE"
    assert best(lex, replace(V5, coherence_weight=8.0), rules, wheel_spec, answer, used) == "BAKING A POUND CAKE"


def test_wikipedia_s_word_list_keeps_i_when_the_dotless_one_uppercases_alike():
    grams = Ngrams.build({"i": 4_000_000, "ı": 0, "have": 4_000_000}, pairs={("i", "have"): 90_000})
    ids = grams.ids_of(["I", "HAVE"])
    assert grams.pair(ids[:1], ids[1:])[0, 0] == 90_000


def test_processes_compiling_the_same_lexicon_at_once_each_finish(tmp_path, monkeypatch):
    from rstlne.players.bot import lexicon as lexicon_module
    cache = tmp_path / "compiled-abc123-cased.pickle"
    for pid in (101, 102):  # two workers, each saving through its own temporary file
        monkeypatch.setattr(lexicon_module.os, "getpid", lambda pid=pid: pid)
        lexicon_module.save_cache(Lexicon.build({"a": 1.0}), cache)
    assert cache.exists() and not list(tmp_path.glob("*.partial"))
