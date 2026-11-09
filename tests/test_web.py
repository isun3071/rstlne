import json
import threading
import time

import pytest
from fastapi.testclient import TestClient

from rstlne.engine.puzzle import Puzzle
from rstlne.engine.rules import new_game
from rstlne.engine.state import BonusSolve, Forfeit, Phase, Spin
from rstlne.players.bot.player import BotPlayer
from rstlne.players.bot.reader import FrequencyReader
from rstlne.web import server
from rstlne.web.session import WebGame, WebHuman, table_json

PUZZLES = [Puzzle("Phrase", "BREAK THE ICE"), Puzzle("Thing", "SPARE TIRE"), Puzzle("Place", "HOT SPRINGS"),
           Puzzle("Food & Drink", "HOT COCOA")]
BONUS = Puzzle("Phrase", "GOOD LUCK", bonus=True)


def state(rules, wheel_spec, seed=7):
    return new_game(seed, rules, wheel_spec, PUZZLES, BONUS)


def bot(seat, rules, wheel_spec):
    return BotPlayer(seat, rules, wheel_spec, FrequencyReader())


def collect(game, until, timeout=30.0):
    """Events until `until(event)` is true, from a game running on its thread."""
    seen, sub = [], game.subscribe()
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        event = game.next_event(sub, timeout=0.5)
        if event is None:
            continue
        seen.append(event)
        if until(event):
            return seen
    raise AssertionError(f"timed out; last events: {seen[-5:]}")


# A human seat in the browser

def test_the_human_seat_reads_the_same_commands_as_the_terminal(rules, wheel_spec):
    from rstlne.engine.rules import public_view
    events = []
    human = WebHuman(0, emit=events.append, seconds=10)
    human.submit("s")
    view = public_view(state(rules, wheel_spec), 0)
    assert human.decide(view) == Spin()
    assert events[-1]["type"] == "prompt" and "spin" in events[-1]["legal"]


def test_a_typo_reprompts_with_a_hint_and_waits_for_the_next_command(rules, wheel_spec):
    from rstlne.engine.rules import public_view
    events = []
    human = WebHuman(0, emit=events.append, seconds=10)
    human.submit("hello")
    human.submit("s")
    assert human.decide(public_view(state(rules, wheel_spec), 0)) == Spin()
    assert [e["type"] for e in events] == ["prompt", "prompt"]
    assert events[1]["error"].startswith("Try:")


def test_the_bonus_solve_has_a_clock_and_a_late_or_empty_answer_forfeits(rules, wheel_spec):
    from dataclasses import replace

    from rstlne.engine.rules import public_view
    view = replace(public_view(state(rules, wheel_spec), 0), phase=Phase.BONUS_SOLVE)
    events = []
    human = WebHuman(0, emit=events.append, seconds=0.05)
    assert human.decide(view) == Forfeit()  # nothing typed in time
    assert events[0]["seconds"] == 0.05
    human.seconds = 2
    threading.Timer(0.05, human.submit, ["good luck"]).start()  # typed while the clock runs
    assert human.decide(view) == BonusSolve("good luck")
    threading.Timer(0.05, human.submit, ["   "]).start()
    assert human.decide(view) == Forfeit()
    human.submit("typed too early")  # before the clock starts: it doesn't count
    threading.Timer(0.05, human.submit, ["good luck"]).start()
    assert human.decide(view) == BonusSolve("good luck")


def test_the_table_sent_to_the_browser_is_the_public_view(rules, wheel_spec):
    from rstlne.engine.rules import public_view
    t = table_json(public_view(state(rules, wheel_spec), 0), ["You", "bot v6", "bot v6"])
    assert t["category"] == "Phrase" and t["round"] == 1
    assert all(tile in "_ " for row in t["rows"] for tile in row)  # a fresh board: hidden squares and gaps only
    assert t["banks"] == [0, 0, 0] and t["legal"] and t["seats"][0] == "You"
    assert len(t["wheel"]) == 72 and {"number", "kind", "value", "text"} <= set(t["wheel"][0])
    assert "BREAK" not in json.dumps(t)


# A whole game on its thread

def test_a_spectated_game_streams_moves_thoughts_and_the_result_and_never_leaks_an_answer_early(rules, wheel_spec, tmp_path):
    players = [bot(i, rules, wheel_spec) for i in range(3)]
    game = WebGame(state(rules, wheel_spec), players, tmp_path / "game.jsonl", pause=0, solve_pause=0)
    game.start()
    events = collect(game, lambda e: e["type"] == "over")
    kinds = {e["type"] for e in events}
    assert {"start", "table", "move", "thoughts", "over"} <= kinds  # no human: the bots' thinking is shown
    over = events[-1]
    assert len(over["totals"]) == 3 and over["log"].endswith("game.jsonl")
    # every answer stays out of the stream until its round is solved or over
    for puzzle in PUZZLES:
        first_seen = next((i for i, e in enumerate(events) if puzzle.answer in json.dumps(e)), None)
        if first_seen is not None:
            assert events[first_seen]["type"] in ("move", "solved", "round_over", "over"), events[first_seen]
    assert (tmp_path / "game.jsonl").read_text().splitlines()[-1].startswith('{"type": "summary"')


def test_with_a_human_seated_the_thinking_panel_stays_hidden(rules, wheel_spec, tmp_path):
    human = WebHuman(0, emit=lambda e: None, seconds=10)
    players = [human, bot(1, rules, wheel_spec), bot(2, rules, wheel_spec)]
    game = WebGame(state(rules, wheel_spec), players, tmp_path / "game.jsonl", pause=0, solve_pause=0)
    game.start()
    events = collect(game, lambda e: e["type"] == "prompt")
    assert events[-1]["seat"] == 0
    game.submit("solve break the ice")
    events += collect(game, lambda e: e["type"] == "move" and e["seat"] == 0)
    assert not any(e["type"] == "thoughts" for e in events)
    game.stop()


def test_stopping_a_game_ends_its_thread(rules, wheel_spec, tmp_path):
    human = WebHuman(0, emit=lambda e: None, seconds=10)
    game = WebGame(state(rules, wheel_spec), [human, bot(1, rules, wheel_spec), bot(2, rules, wheel_spec)],
                   tmp_path / "game.jsonl", pause=0, solve_pause=0)
    game.start()
    collect(game, lambda e: e["type"] == "prompt")
    game.stop()
    game.thread.join(5)
    assert not game.thread.is_alive()


# The server

@pytest.fixture
def client(tmp_path):
    app = server.create_app(log_dir=tmp_path, pause=0, solve_pause=0)
    with TestClient(app) as c:
        yield c


def test_the_page_names_rstlne_and_says_it_is_not_affiliated_with_the_show(client):
    page = client.get("/").text
    assert "rstlne" in page and "not affiliated" in page.lower()


def test_setup_lists_the_seat_kinds_and_the_models_from_config(client):
    setup = client.get("/api/setup").json()
    assert {"human", "bot", "llm", "hybrid"} <= set(setup["kinds"])
    assert isinstance(setup["models"], list) and setup["bot_version"] >= 1


def test_a_bad_seat_list_is_refused_with_the_reason(client):
    response = client.post("/api/games", json={"seats": ["human", "bot"]})
    assert response.status_code == 400 and "three seats" in response.json()["detail"]


def test_model_seats_need_a_key(client, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(server, "load_dotenv", lambda *a, **k: None)
    response = client.post("/api/games", json={"seats": ["human", "llm:openai/gpt-6-luna", "bot"]})
    assert response.status_code == 400 and "OPENROUTER_API_KEY" in response.json()["detail"]


def test_a_game_plays_over_the_websocket(client):
    game_id = client.post("/api/games", json={"seats": ["human", "bot", "bot"], "seed": 5}).json()["id"]
    with client.websocket_connect(f"/api/games/{game_id}") as ws:
        first = ws.receive_json()
        assert first["type"] == "start" and first["seats"][0]["you"] is True
        while (event := ws.receive_json())["type"] != "prompt":
            pass
        ws.send_json({"command": "zzz"})
        assert ws.receive_json()["error"].startswith("Try:")
    client.delete(f"/api/games/{game_id}")


# Replays of logged games

def logged_game(rules, wheel_spec, path, seed=9):
    from rstlne.runner import GameLog, play_game
    players = [bot(i, rules, wheel_spec) for i in range(3)]
    s = state(rules, wheel_spec, seed)
    with GameLog(path, s, players) as log:
        return play_game(s, players, log)


def test_a_log_replays_move_by_move_to_the_same_result(rules, wheel_spec, tmp_path):
    from rstlne.web.replay import replay
    path = tmp_path / "game.jsonl"
    final = logged_game(rules, wheel_spec, path)
    out = replay(path)
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    moves = [e for e in out["events"] if e["type"] == "move"]
    assert len(moves) == sum(r["type"] == "action" for r in rows)
    assert [m["index"] for m in moves] == list(range(1, len(moves) + 1))
    assert out["events"][-1]["type"] == "over" and out["events"][-1]["totals"] == [s.total for s in final.seats]
    assert any(e["type"] == "thoughts" for e in out["events"])  # the bots' records give their thinking back
    assert out["meta"]["seats"] == ["bot v1", "bot v1", "bot v1"] and out["meta"]["finished"]
    assert all(r["answer"] for r in out["meta"]["rounds"])  # answers for the replay's show-the-answer switch


def test_a_log_that_no_longer_replays_is_refused(rules, wheel_spec, tmp_path):
    from rstlne.web.replay import replay
    path = tmp_path / "game.jsonl"
    logged_game(rules, wheel_spec, path)
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    first = next(r for r in rows if r["type"] == "action" and r["action"]["kind"] == "spin")
    first["result"]["wedge"]["number"] = first["result"]["wedge"]["number"] % 24 + 1  # a different wedge than the seed gives
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    with pytest.raises(ValueError, match="doesn't replay"):
        replay(path)


def test_the_log_list_shows_finished_and_unfinished_games_newest_first(rules, wheel_spec, tmp_path):
    from rstlne.web.replay import list_logs
    logged_game(rules, wheel_spec, tmp_path / "20261101-120000-seed9.jsonl")
    lines = (tmp_path / "20261101-120000-seed9.jsonl").read_text().splitlines()
    (tmp_path / "20261102-120000-seed4.jsonl").write_text("\n".join(lines[:5]) + "\n")  # stopped part way
    (tmp_path / "notes.txt").write_text("not a log")
    logs = list_logs(tmp_path)
    assert [l["name"] for l in logs] == ["20261102-120000-seed4.jsonl", "20261101-120000-seed9.jsonl"]
    assert logs[0]["finished"] is False and logs[1]["finished"] is True and logs[1]["seed"] == 9
    assert logs[1]["seats"] == ["bot v1", "bot v1", "bot v1"] and len(logs[1]["totals"]) == 3


def test_the_server_lists_and_replays_logs_but_never_reads_outside_the_log_folder(tmp_path, rules, wheel_spec):
    logged_game(rules, wheel_spec, tmp_path / "20261101-120000-seed9.jsonl")
    app = server.create_app(log_dir=tmp_path, pause=0, solve_pause=0)
    with TestClient(app) as c:
        listed = c.get("/api/logs").json()["logs"]
        assert listed[0]["name"] == "20261101-120000-seed9.jsonl"
        replayed = c.get("/api/logs/20261101-120000-seed9.jsonl").json()
        assert replayed["events"][0]["type"] == "start"
        assert c.get("/api/logs/..%2Fconfig.toml").status_code in (400, 404)
        assert c.get("/api/logs/missing.jsonl").status_code == 404


def test_each_bot_or_model_move_waits_a_beat_first_and_the_page_hears_who_is_thinking(rules, wheel_spec, tmp_path):
    waits = []
    players = [bot(i, rules, wheel_spec) for i in range(3)]
    game = WebGame(state(rules, wheel_spec), players, tmp_path / "game.jsonl", pause=1.5, solve_pause=0, sleep=waits.append)
    game.start()
    events = collect(game, lambda e: e["type"] == "over")
    moves = [i for i, e in enumerate(events) if e["type"] == "move"]
    for i in moves:  # the last event before each move, tables aside, says that seat is thinking
        before = next(e for e in reversed(events[:i]) if e["type"] != "table")
        assert before == {"type": "thinking", "seat": events[i]["seat"]}
    assert waits.count(1.5) == len(moves)


def test_no_beat_before_the_humans_own_move(rules, wheel_spec, tmp_path):
    waits = []
    human = WebHuman(0, emit=lambda e: None, seconds=10)
    game = WebGame(state(rules, wheel_spec), [human, bot(1, rules, wheel_spec), bot(2, rules, wheel_spec)],
                   tmp_path / "game.jsonl", pause=1.5, solve_pause=0, sleep=waits.append)
    game.start()
    events = collect(game, lambda e: e["type"] == "prompt")
    assert not any(e["type"] == "thinking" for e in events) and waits == []
    game.stop()



# Several humans at one screen

def test_two_humans_share_the_screen_and_each_command_goes_to_the_seat_it_names(rules, wheel_spec, tmp_path):
    a, b = WebHuman(0, emit=lambda e: None, seconds=10), WebHuman(1, emit=lambda e: None, seconds=10)
    game = WebGame(state(rules, wheel_spec), [a, b, bot(2, rules, wheel_spec)], tmp_path / "game.jsonl", pause=0, solve_pause=0)
    game.start()
    events = collect(game, lambda e: e["type"] == "prompt")
    start = events[0]
    assert [s["you"] for s in start["seats"]] == [False, False, False]  # nobody is "You" when two share the screen
    assert [s["kind"] for s in start["seats"]] == ["human", "human", "bot"]
    assert events[-1]["seat"] == 0
    game.submit("solve break the ice", seat=1)  # not seat 2's turn: ignored
    game.submit("solve not it", seat=0)
    events = collect(game, lambda e: e["type"] == "move")
    assert events[-1]["seat"] == 0 and events[-1]["text"].startswith("Seat 1 tried")
    assert not any(e["type"] == "thoughts" for e in game.history)
    game.stop()


def test_a_command_for_a_seat_that_isnt_human_is_ignored(rules, wheel_spec, tmp_path):
    human = WebHuman(0, emit=lambda e: None, seconds=10)
    game = WebGame(state(rules, wheel_spec), [human, bot(1, rules, wheel_spec), bot(2, rules, wheel_spec)],
                   tmp_path / "game.jsonl", pause=0, solve_pause=0)
    game.submit("s", seat=1)
    game.submit("s", seat=7)
    assert human.inbox.empty()
    game.submit("s")  # one human: a command with no seat is theirs
    assert human.inbox.get_nowait() == "s"


def test_the_server_seats_up_to_three_humans(client):
    game_id = client.post("/api/games", json={"seats": ["human", "human", "human"], "seed": 5}).json()["id"]
    with client.websocket_connect(f"/api/games/{game_id}") as ws:
        while (event := ws.receive_json())["type"] != "prompt":
            pass
        assert event["seat"] == 0
        ws.send_json({"command": "zzz", "seat": 0})
        assert ws.receive_json()["error"].startswith("Try:")
    client.delete(f"/api/games/{game_id}")


def test_the_page_and_its_files_are_checked_for_changes_on_every_load(client):
    # Without this, a browser keeps an old app.js after the server updates it
    for path in ("/", "/static/app.js", "/static/style.css"):
        assert client.get(path).headers.get("cache-control") == "no-cache", path
    assert "cache-control" not in client.get("/api/setup").headers or client.get("/api/setup").headers["cache-control"] != "no-cache"


# Nicknames for human seats

def test_a_move_names_a_seat_by_its_nickname(rules, wheel_spec):
    from rstlne.engine.rules import apply
    from rstlne.narrate import describe
    after = apply(state(rules, wheel_spec), Spin())
    assert describe(after.last, viewer=0, names=["Ian", None, None]).startswith("Ian spun")
    assert describe(after.last, viewer=0).startswith("You spun")  # no nickname: as before
    assert describe(after.last).startswith("Seat 1 spun")


def test_nicknames_reach_the_page_and_the_log_and_replays_keep_them(rules, wheel_spec, tmp_path):
    from rstlne.web.replay import replay
    a = WebHuman(0, emit=lambda e: None, seconds=10, name="Ian")
    b = WebHuman(1, emit=lambda e: None, seconds=10, name="Mom")
    game = WebGame(state(rules, wheel_spec), [a, b, bot(2, rules, wheel_spec)], tmp_path / "game.jsonl", pause=0, solve_pause=0)
    game.start()
    events = collect(game, lambda e: e["type"] == "prompt")
    assert [s["label"] for s in events[0]["seats"]] == ["Ian", "Mom", "bot v1"]
    assert [s.get("name") for s in events[0]["seats"]] == ["Ian", "Mom", None]
    game.submit("solve not it", seat=0)
    events = collect(game, lambda e: e["type"] == "move")
    assert events[-1]["text"].startswith('Ian tried "NOT IT"')
    game.stop()
    game.thread.join(5)
    header = json.loads((tmp_path / "game.jsonl").read_text().splitlines()[0])
    assert header["seats"][0] == {"kind": "human", "name": "Ian"}
    out = replay(tmp_path / "game.jsonl")
    assert out["meta"]["seats"][:2] == ["Ian", "Mom"]
    assert next(e for e in out["events"] if e["type"] == "move")["text"].startswith("Ian tried")


def test_the_server_takes_a_nickname_for_each_human_seat_and_checks_it(client):
    ok = client.post("/api/games", json={"seats": ["human", "bot", "human"], "names": ["  Ian ", None, "Mom"], "seed": 5})
    assert ok.status_code == 200
    with client.websocket_connect(f"/api/games/{ok.json()['id']}") as ws:
        start = ws.receive_json()
        assert [s["label"] for s in start["seats"]][::2] == ["Ian", "Mom"]
    client.delete(f"/api/games/{ok.json()['id']}")
    long = client.post("/api/games", json={"seats": ["human", "bot", "bot"], "names": ["x" * 21, None, None]})
    assert long.status_code == 400 and "20" in long.json()["detail"]
    bot_named = client.post("/api/games", json={"seats": ["human", "bot", "bot"], "names": [None, "Robo", None]})
    assert bot_named.status_code == 400 and "human" in bot_named.json()["detail"]


def test_the_bonus_answer_fills_the_board_after_the_bonus_solve_right_or_wrong(rules, wheel_spec, tmp_path):
    from rstlne.web.replay import replay
    path = tmp_path / "game.jsonl"
    logged_game(rules, wheel_spec, path)
    events = replay(path)["events"]
    bonus = next(i for i, e in enumerate(events) if e["type"] == "move" and e["kind"] == "bonus_solve")
    shown = events[bonus + 1:]
    reveal = next(e for e in shown if e["type"] == "solved")
    assert reveal["bonus"] is True and reveal["category"] == BONUS.category
    assert "".join(c for row in reveal["rows"] for c in row if c.strip()) == BONUS.answer.replace(" ", "")
    assert reveal["solved"] == (events[bonus]["outcome"] == "bonus_solved")
    assert shown.index(reveal) < shown.index(next(e for e in shown if e["type"] == "over"))


# Games nobody is watching

def test_a_game_counts_its_watchers_and_notes_when_the_last_one_left(rules, wheel_spec, tmp_path):
    clock = [100.0]
    game = WebGame(state(rules, wheel_spec), [bot(i, rules, wheel_spec) for i in range(3)], tmp_path / "g.jsonl",
                   pause=0, solve_pause=0, clock=lambda: clock[0])
    assert game.watchers == 0 and game.idle_since == 100.0  # made, never opened: idle from the start
    a, b = game.subscribe(), game.subscribe()
    clock[0] = 150.0
    game.unsubscribe(a)
    assert game.watchers == 1 and game.idle_since is None
    clock[0] = 160.0
    game.unsubscribe(b)
    assert game.watchers == 0 and game.idle_since == 160.0


def test_the_reaper_stops_games_left_alone_too_long_and_keeps_the_rest(rules, wheel_spec, tmp_path):
    clock = [0.0]
    def make(name):
        human = WebHuman(0, emit=lambda e: None, seconds=10)
        return WebGame(state(rules, wheel_spec), [human, bot(1, rules, wheel_spec), bot(2, rules, wheel_spec)],
                       tmp_path / f"{name}.jsonl", pause=0, solve_pause=0, clock=lambda: clock[0])
    games = {"left": make("left"), "watched": make("watched"), "recent": make("recent")}
    for g in games.values():
        g.start()
    games["watched"].subscribe()
    clock[0] = 200.0
    games["recent"].idle_since = 150.0  # its page closed 50 seconds ago
    stopped = server.reap(games, timeout=120.0, now=clock[0])
    assert stopped == ["left"] and set(games) == {"watched", "recent"}
    stopped_game_thread = games.get("left")
    assert stopped_game_thread is None
    for g in games.values():
        g.stop()


def test_the_server_reads_the_idle_window_from_config(tmp_path):
    from rstlne import settings
    config = settings.load_config()
    assert config["web"]["idle_minutes"] > 0
    app = server.create_app(config={**config, "web": {**config["web"], "idle_minutes": 0.5}}, log_dir=tmp_path, pause=0, solve_pause=0)
    assert app.state.idle_seconds == 30


# A model's calls failing after their retries

class Flaky(BotPlayer):
    """A bot whose first `fails` decisions raise, as a model's do when its provider keeps failing."""

    def __init__(self, *args, fails=1, **kwargs):
        super().__init__(*args, **kwargs)
        self.fails = fails

    def decide(self, view, error=None):
        if self.fails:
            self.fails -= 1
            raise RuntimeError("EmptyResponse: the provider returned no choices")
        return super().decide(view, error)


def flaky_game(rules, wheel_spec, tmp_path, fails):
    players = [Flaky(0, rules, wheel_spec, FrequencyReader(), fails=fails), bot(1, rules, wheel_spec), bot(2, rules, wheel_spec)]
    return WebGame(state(rules, wheel_spec), players, tmp_path / "game.jsonl", pause=0, solve_pause=0)


def test_a_failed_model_call_pauses_the_game_and_try_again_resumes_it(rules, wheel_spec, tmp_path):
    game = flaky_game(rules, wheel_spec, tmp_path, fails=2)
    game.start()
    stalled = collect(game, lambda e: e["type"] == "stalled")[-1]
    assert stalled["seat"] == 0 and "no choices" in stalled["text"]
    assert game.thread.is_alive()  # waiting, not dead
    game.control("retry")
    collect(game, lambda e: e["type"] == "stalled" and e is not stalled)  # it failed again, and asks again
    game.control("retry")
    move = collect(game, lambda e: e["type"] == "move")[-1]
    assert move["seat"] == 0 and move["outcome"] != "forfeit"
    game.stop()


def test_skip_the_turn_forfeits_it_and_the_log_says_why(rules, wheel_spec, tmp_path):
    game = flaky_game(rules, wheel_spec, tmp_path, fails=1)
    game.start()
    collect(game, lambda e: e["type"] == "stalled")
    game.control("skip")
    move = collect(game, lambda e: e["type"] == "move")[-1]
    assert move["seat"] == 0 and move["outcome"] == "forfeit"
    assert move["text"] == "Seat 1's turn was skipped: its model didn't answer."
    game.stop()
    game.thread.join(5)
    rows = [json.loads(line) for line in (tmp_path / "game.jsonl").read_text().splitlines()]
    forfeit = next(r for r in rows if r["type"] == "action" and r["result"]["outcome"] == "forfeit")
    assert "no choices" in forfeit["raw"]["api_failure"] and forfeit["raw"]["skipped"] is True


def test_a_stray_control_does_nothing_while_the_game_isnt_stalled(rules, wheel_spec, tmp_path):
    game = flaky_game(rules, wheel_spec, tmp_path, fails=0)
    game.control("skip")
    assert game.controls.empty()


def test_the_page_sends_retry_and_skip_over_the_websocket(client, monkeypatch):
    from rstlne.web import session
    seen = []
    monkeypatch.setattr(session.WebGame, "control", lambda self, what: seen.append(what))
    game_id = client.post("/api/games", json={"seats": ["bot", "bot", "bot"], "seed": 5}).json()["id"]
    with client.websocket_connect(f"/api/games/{game_id}") as ws:
        ws.receive_json()
        ws.send_json({"control": "retry"})
        ws.send_json({"control": "nonsense"})
        ws.send_json({"control": "skip"})
        ws.receive_json()
    client.delete(f"/api/games/{game_id}")
    assert seen == ["retry", "skip"]


# Where a puzzle came from

AIRED = {"kind": "aired", "airings": [{"season": 31, "episode": 5851, "date": "2013-09-16", "round": "R1"}]}
GENERATED = {"kind": "generated", "decks": ["grading-606b"]}


def test_a_solved_board_says_where_its_puzzle_came_from_and_the_log_keeps_it(rules, wheel_spec, tmp_path):
    from rstlne.web.replay import replay
    sources = {"rounds": [AIRED, GENERATED, None, None], "bonus": GENERATED}
    human = WebHuman(0, emit=lambda e: None, seconds=10)
    game = WebGame(state(rules, wheel_spec), [human, bot(1, rules, wheel_spec), bot(2, rules, wheel_spec)],
                   tmp_path / "g.jsonl", pause=0, solve_pause=0, sources=sources)
    game.start()
    collect(game, lambda e: e["type"] == "prompt")
    assert not any("source" in e for e in game.history)  # nothing about the source before the round is over
    game.submit("solve break the ice", seat=0)
    solved = collect(game, lambda e: e["type"] == "solved")[-1]
    assert solved["source"] == AIRED
    game.stop()
    game.thread.join(5)
    header = json.loads((tmp_path / "g.jsonl").read_text().splitlines()[0])
    assert header["puzzle_sources"] == sources
    out = replay(tmp_path / "g.jsonl")
    assert next(e for e in out["events"] if e["type"] == "solved")["source"] == AIRED


def test_the_server_reads_each_puzzles_source_from_the_deck(tmp_path):
    deck = tmp_path / "mega.json"
    deck.write_text(json.dumps({"name": "mega", "puzzles": [
        {"category": "Phrase", "answer": "BREAK THE ICE", "bonus": False, "round": 1, "source": AIRED},
        {"category": "Thing", "answer": "SPARE TIRE", "bonus": False, "round": 2, "source": GENERATED},
        {"category": "Place", "answer": "HOT SPRINGS", "bonus": False, "round": 3},
        {"category": "Food & Drink", "answer": "HOT COCOA", "bonus": False, "round": 4},
        {"category": "Phrase", "answer": "GOOD LUCK", "bonus": True, "source": GENERATED},
    ]}))
    app = server.create_app(puzzles_path=deck, log_dir=tmp_path, pause=0, solve_pause=0)
    assert app.state.sources[("BREAK THE ICE", False)] == AIRED and ("HOT SPRINGS", False) not in app.state.sources
    assert app.state.deck == "mega.json"


def test_the_web_page_plays_the_mega_deck_when_there_is_one(tmp_path, monkeypatch):
    from rstlne import settings
    assert server.default_deck(tmp_path) == settings.ROOT / "puzzles" / "dev.json"
    (tmp_path / "mega.json").write_text("[]")
    assert server.default_deck(tmp_path) == tmp_path / "mega.json"
