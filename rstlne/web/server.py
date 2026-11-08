"""The web page's server: one page, a setup call, and a game per websocket. Model seats use the key in .env."""

from __future__ import annotations

import asyncio
import os
import random
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from rstlne import settings
from rstlne.cli import build_players, clients, log_path, parse_seats, pick_puzzles
from rstlne.engine.rules import new_game
from rstlne.players.bot import versions
from rstlne.players.hybrid import curves_for
from rstlne.web.replay import list_logs, replay
from rstlne.web.session import WebGame, WebHuman

STATIC = Path(__file__).parent / "static"
MODEL_KINDS = {"llm", "decision", "hybrid"}


class NewGame(BaseModel):
    seats: list[str]
    seed: int | None = None


def create_app(*, config: dict | None = None, puzzles_path: Path | None = None, log_dir: Path | None = None,
               pause: float | None = None, solve_pause: float | None = None, replays: bool = True) -> FastAPI:
    """The app. `replays` serves the log folder's games for replay: right on this machine, never on a shared host."""
    config = config or settings.load_config()
    rules, spec = settings.load_rules(), settings.load_wheel()
    puzzles = settings.load_puzzles(Path(puzzles_path or settings.ROOT / "puzzles" / "dev.json"))
    log_dir = Path(log_dir or settings.ROOT / "logs")
    pause = config["cli"]["model_pause"] if pause is None else pause
    solve_pause = config["cli"]["solve_pause"] if solve_pause is None else solve_pause
    games: dict[str, WebGame] = {}

    app = FastAPI(title="rstlne", docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/")
    def page() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    @app.get("/api/setup")
    def setup() -> dict:
        models = list(config.get("web", {}).get("models", []))
        return {
            "kinds": ["human", "bot", "llm", "hybrid", "decision"],
            "models": models,
            "hybrid_models": [m for m in models if all(c is not None for c in curves_for(config, m))],
            "decision_models": list(config.get("web", {}).get("decision_models", [])),
            "bot_version": versions.current(config),
            "bonus_solve_seconds": config["cli"]["bonus_solve_seconds"],
        }

    @app.post("/api/games")
    def create(new: NewGame) -> dict:
        try:
            seats = parse_seats(",".join(new.seats))
        except ValueError as err:
            raise HTTPException(400, str(err)) from None
        kinds = {kind for kind, _ in seats}
        if kinds & MODEL_KINDS:
            load_dotenv(settings.ROOT / ".env")
            if not os.environ.get("OPENROUTER_API_KEY"):
                raise HTTPException(400, "model seats need OPENROUTER_API_KEY in .env")
        seed = new.seed if new.seed is not None else random.randrange(1_000_000)
        main, bonus = pick_puzzles(puzzles, rules.main_rounds, seed)
        path = log_path(log_dir, seed)
        try:
            client, decisions = clients(kinds, None, None)
            players = build_players(seats, rules, spec, config, client, decisions, path.stem)
        except ValueError as err:
            path.unlink(missing_ok=True)
            raise HTTPException(400, str(err)) from None
        seconds = config["cli"]["bonus_solve_seconds"]
        players = [WebHuman(i, emit=lambda e: None, seconds=seconds) if kind == "human" else p
                   for i, ((kind, _), p) in enumerate(zip(seats, players))]
        game = WebGame(new_game(seed, rules, spec, main, bonus), players, path, pause=pause, solve_pause=solve_pause)
        game_id = uuid.uuid4().hex[:12]
        games[game_id] = game
        game.start()
        return {"id": game_id, "seed": seed}

    def log_file(name: str) -> Path:
        path = (log_dir / name).resolve()
        if path.parent != log_dir.resolve() or path.suffix != ".jsonl":
            raise HTTPException(400, "replays read game logs in the log folder only")
        if not path.is_file():
            raise HTTPException(404, f"no log named {name}")
        return path

    @app.get("/api/logs")
    def logs() -> dict:
        if not replays:
            raise HTTPException(404, "replays are off")
        return {"folder": str(log_dir), "logs": list_logs(log_dir)}

    @app.get("/api/logs/{name}")
    def replay_log(name: str) -> dict:
        if not replays:
            raise HTTPException(404, "replays are off")
        try:
            return replay(log_file(name))
        except ValueError as err:
            raise HTTPException(422, str(err)) from None

    @app.delete("/api/games/{game_id}")
    def close(game_id: str) -> dict:
        game = games.pop(game_id, None)
        if game:
            game.stop()
        return {"closed": game is not None}

    @app.websocket("/api/games/{game_id}")
    async def play(ws: WebSocket, game_id: str) -> None:
        game = games.get(game_id)
        await ws.accept()
        if game is None:
            await ws.send_json({"type": "failed", "text": "No such game. It may have ended when the server restarted."})
            await ws.close()
            return
        sub = game.subscribe()

        async def send() -> None:
            while True:
                event = await asyncio.to_thread(game.next_event, sub, 0.5)
                if event is not None:
                    await ws.send_json(event)

        async def receive() -> None:
            while True:
                message = await ws.receive_json()
                if isinstance(message, dict) and isinstance(message.get("command"), str):
                    seat = message.get("seat")
                    game.submit(message["command"], seat if isinstance(seat, int) else None)

        tasks = [asyncio.create_task(send()), asyncio.create_task(receive())]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        except WebSocketDisconnect:
            pass
        finally:
            for task in tasks:
                task.cancel()
            game.unsubscribe(sub)

    return app
