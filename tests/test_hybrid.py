import json
import math
from dataclasses import replace

import pytest
from fakes import completion, router
from helpers import BONUS, PUZZLES, set_seat, solve, spin_to, start

from rstlne.engine.puzzle import LETTERS
from rstlne.engine.rules import apply, public_view
from rstlne.engine.state import BonusPicks, BonusSolve, Phase, Solve
from rstlne.players.bot import versions
from rstlne.players.bot.player import BotPlayer
from rstlne.players.bot.reader import WordListReader
from rstlne.players.hybrid import HybridPlayer, HybridSteal
from rstlne.runner import GameLog, play_game

KNOBS = replace(versions.knobs(1), samples=120)
WORDS = {w: 50 for p in (*PUZZLES, BONUS) for w in p.answer.replace("-", " ").split()}
WORDS.update({"WHOOL": 60, "GOLDEN": 30, "BIG": 60})
MODEL = "deepseek/deepseek-v4.1-flash-1017"


def logit(p):
    return math.log(p / (1 - p))


TRUST = (logit(0.8), 0.0, 0.0, 0.0, 0.0)  # trust 0.8 on every board
STEAL = (-3.0, 2.5, 2.0, 0.0)


def says(solvable, answer=None):
    args = {"solvable": solvable} | ({"answer": answer} if answer is not None else {})
    return completion(("read_board", args))


def hybrid(rules, spec, replies, trust=TRUST, steal=STEAL):
    client = router(replies)
    player = HybridPlayer(0, MODEL, client, trust, steal, rules, spec, WordListReader(WORDS, KNOBS),
                          knobs=KNOBS, session_id="g-seat1")
    return player, client.client.calls


OPEN = "RLNWH"  # WH__L __ __R__N_: WHEEL and WHOOL both fit


def shown(state, letters):
    return replace(state, round=replace(state.round, used=frozenset(letters)))


def user_text(call):
    return next(m["content"] for m in call["messages"] if m["role"] == "user")


# When it asks


def test_one_ask_per_new_board_and_the_consonant_pick_reuses_it(rules, wheel_spec):
    state = spin_to(start(rules, wheel_spec), 3)  # seat 0 holds a cash wedge, waiting on a consonant
    player, calls = hybrid(rules, wheel_spec, [says(False)])
    player.decide(public_view(start(rules, wheel_spec), 0))
    player.decide(public_view(state, 0))  # same board, same used letters
    assert len(calls) == 1
    assert calls[0]["tools"][0]["function"]["name"] == "read_board"


def test_the_ask_holds_the_puzzle_only(rules, wheel_spec):
    state = set_seat(shown(start(rules, wheel_spec), "RLNEWH"), 0, bank=5000)
    player, calls = hybrid(rules, wheel_spec, [says(False)])
    player.decide(public_view(state, 0))
    text = user_text(calls[0])
    assert "Category: Phrase" in text and "WHEEL __ __R__NE (word lengths 5, 2, 7)" in text
    assert "Used letters: E H L N R W" in text and "Proven wrong this round: none" in text
    assert "$" not in text and "bank" not in text.lower()  # no money, no scores
    system = calls[0]["messages"][0]["content"]
    assert "strategy" not in system.lower() and "spin" not in system.lower()


def test_it_never_asks_on_an_opponents_turn(rules, wheel_spec):
    player, calls = hybrid(rules, wheel_spec, [])
    state = replace(start(rules, wheel_spec), seat=1)
    after = apply(state, Solve("WHEEL OF FORTUNE"))
    player.observe(public_view(after, 0), after.last)
    assert calls == []


# Using the answer


def test_a_fitting_answer_is_mixed_in_with_the_trust_curves_share(rules, wheel_spec):
    state = shown(start(rules, wheel_spec), "RLNEWH")
    player, _ = hybrid(rules, wheel_spec, [says(True, "WHEEL OF FORTUNE")])
    view = public_view(state, 0)
    alone = player.reader.read(view)
    player.decide(view)
    ask = player.last_call.raw["ask"]
    p_reader = dict(alone.answers).get("WHEEL OF FORTUNE", 0.0)
    assert ask["status"] == "used" and ask["trust"] == pytest.approx(0.8)
    assert player.last_call.raw["best"] == "WHEEL OF FORTUNE"
    assert player.last_call.raw["confidence"] == pytest.approx(0.8 + 0.2 * p_reader)
    assert ask["reader_confidence"] == pytest.approx(alone.confidence)


def test_trust_reads_shown_agreement_the_readers_probability_and_its_confidence(rules, wheel_spec):
    state = shown(start(rules, wheel_spec), OPEN)
    view = public_view(state, 0)
    player, _ = hybrid(rules, wheel_spec, [says(True, "WHOOL OF FORTUNE")], trust=(0.0, 1.0, 2.0, 3.0, 4.0))
    alone = player.reader.read(view)
    player.decide(view)
    p = dict(alone.answers).get("WHOOL OF FORTUNE", 0.0)
    assert 0 < p < 1
    share = 5 / 14
    x = 0.0 + 1.0 * share + 2.0 * (alone.best == "WHOOL OF FORTUNE") + 3.0 * p + 4.0 * alone.confidence
    assert player.last_call.raw["ask"]["trust"] == pytest.approx(1 / (1 + math.exp(-x)))


@pytest.mark.parametrize("answer, status", [
    ("WHEEL OF FORTUNA", "doesn't fit"),  # the board shows an E in the last square
    ("WHEEL OF FORTUNE IS", "doesn't fit"),
])
def test_an_answer_that_doesnt_fit_is_ignored(rules, wheel_spec, answer, status):
    state = shown(start(rules, wheel_spec), "RLNEWH")
    player, _ = hybrid(rules, wheel_spec, [says(True, answer)])
    player.decide(public_view(state, 0))
    raw = player.last_call.raw
    assert raw["ask"]["status"] == status and raw["ask"]["trust"] is None
    assert raw["best"] != answer


def test_a_refuted_answer_is_listed_and_never_used(rules, wheel_spec):
    state = shown(start(rules, wheel_spec), OPEN)
    wrong = apply(replace(state, seat=1), Solve("WHOOL OF FORTUNE"))  # seat 2 solves wrong
    player, calls = hybrid(rules, wheel_spec, [says(True, "WHOOL OF FORTUNE")])
    player.observe(public_view(wrong, 0), wrong.last)
    player.decide(public_view(replace(wrong, seat=0), 0))
    assert "Proven wrong this round: WHOOL OF FORTUNE" in user_text(calls[0])
    assert player.last_call.raw["ask"]["status"] == "refuted"


def test_not_solvable_leaves_the_reader_alone(rules, wheel_spec):
    view = public_view(shown(start(rules, wheel_spec), "RLNEWH"), 0)
    player, _ = hybrid(rules, wheel_spec, [says(False)])
    alone = player.reader.read(view)
    player.decide(view)
    assert player.last_call.raw["ask"]["status"] == "not solvable"
    assert player.last_call.raw["confidence"] == pytest.approx(alone.confidence)


def test_bad_replies_are_reprompted_and_a_third_failure_counts_as_not_solvable(rules, wheel_spec):
    replies = [completion(content="hmm"), completion(("read_board", "{not json")), says(True)]  # no answer given
    player, calls = hybrid(rules, wheel_spec, replies)
    player.decide(public_view(start(rules, wheel_spec), 0))
    ask = player.last_call.raw["ask"]
    assert len(calls) == 3 and ask["status"] == "failed" and ask["attempts"] == 3
    assert calls[1]["messages"][-1]["content"].startswith("Error:")
    assert player.last_call.usage.calls == 3


def test_a_good_reply_after_a_bad_one_is_used(rules, wheel_spec):
    state = shown(start(rules, wheel_spec), "RLNEWH")
    player, calls = hybrid(rules, wheel_spec, [completion(content="no tool"), says(True, "WHEEL OF FORTUNE")])
    player.decide(public_view(state, 0))
    assert player.last_call.raw["ask"]["status"] == "used" and player.last_call.raw["ask"]["attempts"] == 2


# Steal odds


def test_steal_odds_rise_when_the_model_can_read_the_board(rules, wheel_spec):
    steal = HybridSteal(0, KNOBS, (-3.0, 2.0, 1.0, 2.5))
    blind = steal.prior(0.4, 0.2)
    steal.readable = 1
    assert steal.prior(0.4, 0.2) == pytest.approx(1 / (1 + math.exp(-(-3.0 + 0.8 + 0.2 + 2.5))))
    assert steal.prior(0.4, 0.2) > blind


def test_steal_odds_read_the_readers_confidence_not_the_mixed_one(rules, wheel_spec):
    view = public_view(shown(start(rules, wheel_spec), OPEN), 0)
    player, _ = hybrid(rules, wheel_spec, [says(True, "WHEEL OF FORTUNE")], steal=(-3.0, 2.0, 1.0, 0.0))
    alone = player.reader.read(view)
    player.decide(view)
    plain = BotPlayer(0, rules, wheel_spec, player.reader, knobs=replace(KNOBS, steal_prior=(-3.0, 2.0, 1.0)))
    plain.decide(view)
    assert player.last_call.raw["p_steal"] == pytest.approx(plain.last_call.raw["p_steal"])
    assert alone.confidence < player.last_call.raw["confidence"]


def test_readable_resets_each_round(rules, wheel_spec):
    state = shown(start(rules, wheel_spec), "RLNEWH")
    player, _ = hybrid(rules, wheel_spec, [says(True, "WHEEL OF FORTUNE")])
    player.decide(public_view(state, 0))
    assert player.steal.readable == 1
    after = solve(state)  # round 2 begins
    player.observe(public_view(after, 0), after.last)
    assert player.steal.readable == 0


# Bonus round


def bonus_state(rules, wheel_spec):
    return solve(start(rules, wheel_spec, main_rounds=1))


def test_bonus_picks_come_from_the_reader_alone(rules, wheel_spec):
    player, calls = hybrid(rules, wheel_spec, [])
    action = player.decide(public_view(bonus_state(rules, wheel_spec), 0))
    assert isinstance(action, BonusPicks) and calls == []


def test_the_bonus_solve_asks_once_and_solves_the_mixed_best(rules, wheel_spec):
    state = apply(bonus_state(rules, wheel_spec), BonusPicks(("C", "D", "M"), "A"))
    assert state.phase is Phase.BONUS_SOLVE
    player, calls = hybrid(rules, wheel_spec, [says(True, "BIG CITY")], trust=(logit(0.95), 0, 0, 0, 0))
    assert player.decide(public_view(state, 0)) == BonusSolve("BIG CITY")
    assert len(calls) == 1


# A whole game, and the log


def fake_model(request):
    """Answers once half the board shows, reading the answer from a lookup of the test puzzles."""
    text = next(m["content"] for m in request["messages"] if m["role"] == "user")
    pattern = text.split("Pattern: ")[1].split(" (word lengths")[0]
    for puzzle in (*PUZZLES, BONUS):
        if len(puzzle.answer) == len(pattern) and all(p in ("_", a) for p, a in zip(pattern, puzzle.answer)):
            letters = [c for c in pattern if c in LETTERS or c == "_"]
            if sum(c != "_" for c in letters) * 2 >= len(letters):
                return says(True, puzzle.answer)
    return says(False)


def test_a_hybrid_plays_a_whole_game_and_the_log_names_both_halves(rules, wheel_spec, tmp_path):
    client = router(fake_model)
    reader = WordListReader(WORDS, KNOBS)
    players = [HybridPlayer(0, MODEL, client, TRUST, STEAL, rules, wheel_spec, reader, knobs=KNOBS),
               BotPlayer(1, rules, wheel_spec, reader, knobs=KNOBS), BotPlayer(2, rules, wheel_spec, reader, knobs=KNOBS)]
    path = tmp_path / "game.jsonl"
    with GameLog(path, start(rules, wheel_spec), players) as log:
        final = play_game(start(rules, wheel_spec), players, log)
    assert final.phase is Phase.GAME_OVER
    lines = [json.loads(line) for line in path.read_text().splitlines()]
    seat = lines[0]["seats"][0]
    assert seat["kind"] == "hybrid" and seat["model"] == MODEL and seat["version"] == 1 and seat["temperature"] is None
    asked = [r for r in lines if r.get("type") == "action" and r["seat"] == 0 and (r.get("raw") or {}).get("ask")]
    assert asked and all(r["raw"]["ask"]["model"] == MODEL for r in asked)
    assert players[0].label() == f"bot v1 + {MODEL}"


# Seats


def test_hybrid_seats_parse_with_their_model():
    from rstlne import cli
    assert cli.parse_seats("hybrid:a/one,bot,llm:b/two") == [("hybrid", "a/one"), ("bot", None), ("llm", "b/two")]
    with pytest.raises(ValueError, match="slug"):
        cli.parse_seats("hybrid:,bot,bot")


def curves(model=MODEL):
    return {"trust": {model: list(TRUST)}, "steal": {model: list(STEAL)}}


def test_a_hybrid_seat_reads_its_curves_and_provider_from_config(rules, wheel_spec):
    from rstlne import cli, settings
    config = {**settings.load_config(), "hybrid": curves(), "providers": {MODEL: "deepinfra/fp8"}}
    players = cli.build_players([("hybrid", MODEL), ("bot", None), ("bot", None)], rules, wheel_spec, config,
                                router([]), None, "game")
    seat = players[0]
    assert isinstance(seat, HybridPlayer) and seat.model == MODEL and seat.provider == "deepinfra/fp8"
    assert seat.trust == TRUST and seat.steal.coefficients == STEAL and seat.session_id == "game-seat1"


def test_a_model_with_no_trust_curve_cant_sit_in_a_hybrid_seat(rules, wheel_spec):
    from rstlne import cli, settings
    config = {**settings.load_config(), "hybrid": curves("other/model")}
    with pytest.raises(ValueError, match="calibrate trust"):
        cli.build_players([("hybrid", MODEL), ("bot", None), ("bot", None)], rules, wheel_spec, config,
                          router([]), None, "game")


def test_tournaments_hold_hybrid_seats_to_the_bot_version(tmp_path):
    from rstlne import tournament
    header = {"type": "header", "seats": [{"kind": "hybrid", "version": 0, "model": MODEL}]}
    (tmp_path / "set000-perm0.jsonl").write_text(json.dumps(header) + "\n" + json.dumps({"type": "summary"}) + "\n")
    with pytest.raises(ValueError, match="bot v0"):
        tournament.check_bot_versions(tmp_path, 1)


def test_a_hybrid_tournament_folder_covers_the_bot_version_and_the_curves(tmp_path):
    from rstlne import settings, tournament
    config = {**settings.load_config(), "hybrid": curves()}
    entrants = [f"hybrid:{MODEL}", "llm:a/one", "llm:b/two"]
    base = tournament.folder_name(entrants, 1, tmp_path / "p.json", config)
    other = {**config, "hybrid": {"trust": {MODEL: [0, 0, 0, 0, 0]}, "steal": curves()["steal"]}}
    assert tournament.folder_name(entrants, 1, tmp_path / "p.json", other) != base
    newer = {**config, "bot": {"version": 2}}
    assert tournament.folder_name(entrants, 1, tmp_path / "p.json", newer) != base
