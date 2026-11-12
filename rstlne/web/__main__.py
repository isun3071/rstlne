"""Serve the web page on this machine: python -m rstlne.web, then open the address it prints."""

from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

from rstlne import settings
from rstlne.web.server import create_app


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m rstlne.web", description="Play rstlne in a browser.")
    parser.add_argument("--host", default="127.0.0.1", help="the address to serve on; this machine only by default")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--puzzles", help="the deck to play: puzzles/mega.json when it's been built, else puzzles/dev.json")
    parser.add_argument("--log-dir", default=str(settings.ROOT / "logs"))
    parser.add_argument("--verbose", action="store_true",
                        help="show the bot's working in its thinking: each move's worth as a formula with its numbers")
    args = parser.parse_args(argv)
    app = create_app(puzzles_path=Path(args.puzzles) if args.puzzles else None, log_dir=Path(args.log_dir),
                     verbose=args.verbose)
    print(f"rstlne is at http://{args.host}:{args.port}, playing {app.state.deck}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
