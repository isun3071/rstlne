# rstlne

Named after R, S, T, L, N, and E, the letters the bonus round hands every player.

Wheel of Fortune with language models at the table, in the terminal or in a browser. Each of the three seats is you, a model called through [OpenRouter](https://openrouter.ai), the project's own bot, a hybrid of the bot and a model, or a decision model. The game follows the current show's rules, including the Mystery and Express wedges, the Wild Card, the Million wedge, and the bonus round. Toss-ups are left out on purpose.

The same engine runs seeded tournaments that compare how well players pick letters, take risks, and time their solves. Seven models from five labs played 30 lineups, 10,800 games in all, against the bot and each other. [FINDINGS.md](FINDINGS.md) has the short version: GPT-6.1 Sol and Terra beat the bot, the other five models don't, a weak model wins 26 to 29 points more often reading the board for the bot than playing alone, and every model would beat the average contestant in the bonus round. The paper in [paper/](paper/) has the full method and results.

## Status

| Part | State |
|---|---|
| Game engine, covering every rule in `documentation.md` | Done |
| Seats: you, models by tool calls, decision models, hybrids, the bot | Done |
| Bot | Version 6 (2026-11-05), the only bot in the results. Version 7's letter knobs tied it and are parked |
| Terminal game and browser game, with replays | Done |
| Tournament runner, bonus test, puzzle generator, self-play | Done |
| The v6 lineups: 30 lineups, 10,800 games | Done |
| The paper | Being written in `paper/` |

## Setup

You need [uv](https://docs.astral.sh/uv/) and an OpenRouter API key. uv sets up Python 3.11 or newer if your machine doesn't have it.

```
uv sync
cp .env.example .env
```

`uv sync` builds `.venv` with the exact package versions in `uv.lock`, so every game and tournament runs on the same code. After changing dependencies in `pyproject.toml`, run `uv lock` and commit the new `uv.lock`.

Put your key in `.env` as `OPENROUTER_API_KEY=...`. Git ignores `.env`.

The bot plays at full strength only with its word data (see [The bot's word data](#the-bots-word-data)). Without it, the bot reads by letter frequency alone.

## Play in the terminal

```
uv run python -m rstlne.cli --seats human,bot,llm:openai/gpt-6.1-sol
```

Each seat is `human`, `llm:<slug>`, `bot`, `hybrid:<slug>`, or `decision[:<model>[@<solver>]]`:

- `llm:<slug>` is a chat model making every move by tool calls. Any OpenRouter model whose `supported_parameters` include `tools` can sit.
- `bot` is the project's own player. It reads the board with word and phrase lists and scores every move with one value function, as `documentation.md` describes. No API calls.
- `hybrid:<slug>` is the bot making every move and asking the model to read the board on its turns. Only models with trust curves in `config.toml` can sit: Terra, Luna, Haiku and DeepSeek. `hybrid:<slug>+trust_fit` takes the model's first fitting answer at its word.
- `decision` is a decision model, GPT-6 Luna Decisions by default, making every choice through OpenRouter's Decisions API, including when to solve, with an LLM writing the answer. `[decision]` in `config.toml` names both; `decision:<model>@<solver>` overrides them for one seat.

[HOW_TO_PLAY.md](HOW_TO_PLAY.md) covers the commands, the rules, and tables to try.

| Option | Effect |
|---|---|
| `--seed N` | Plays seed N. The same seed and the same moves replay the same game. Without it, the game picks a seed and prints it. |
| `--live` | Redraws one fixed screen after every move: the board as tiles, the letters left, each seat's money, cards, and thinking, and the latest moves. |
| `--show-thinking` | Prints each seat's reasoning before its move: a model's reasoning, a decision seat's probabilities, the bot's likeliest answers and move values. |
| `--verbose` | `--show-thinking`, plus the bot's working: each move's worth as a formula with its numbers. |
| `--show-puzzle` | Prints the board, letters, banks, cards, and wedge after every move. |
| `--pause S` | Pauses S seconds after each move. The default is 1.5. |
| `--puzzles PATH` | Reads puzzles from PATH. The default is `puzzles/dev.json`. |
| `--log-dir PATH` | Writes game logs to PATH. The default is `logs/`. |

## Play in a browser

```
uv run python -m rstlne.decks mega   # once: the mega deck, every aired and generated puzzle (stays out of git)
uv run python -m rstlne.web          # then open http://127.0.0.1:8000
```

Pick the three seats on the page, then play or watch. Up to three people can share the screen, each with a nickname. You play with the mouse or the keyboard: `s` spins, a typed vowel buys it, a typed consonant calls it, and `?` opens a How to play sheet in plain words. The landed wedge shows over the board for a moment after every spin. The Replays tab replays any game in the log folder move by move, with breakpoints at solves, Bankrupts, new rounds, or a seat's moves.

`--host`, `--port`, `--puzzles`, `--log-dir`, and `--verbose` (the bot's working in the Thinking panel) are the options. Without the mega deck, the page plays `puzzles/dev.json`. `python -m rstlne.decks aired` builds the aired puzzles alone, `puzzles/aired-all.json`.

To keep the page running on a home server, install [deploy/rstlne-web.service](deploy/rstlne-web.service) as a systemd user service. Its header has the commands. Keep it on the home network or a VPN into it: model seats spend the key in `.env`.

## Tournaments

```
uv run python -m rstlne.tournament --seats llm:openai/gpt-6.1-sol,bot,bot --sets 60 --seed 707 --puzzles puzzles/generated/grading-606b.json
```

`--seats` takes any three seats, as in the CLI, and `--models a,b,c` is short for three `llm:` seats.

A tournament plays `--sets` puzzle sets with duplicate scoring. A set is 6 games, one for every ordering of the 3 entrants across the seats, all with the set's seed and puzzles. So within a set, each entrant sits in each seat twice and plays against the same spins. `--sets 60` is 360 games, and `--sets 1` is a 6-game trial for checking cost; trial at least 3 sets before trusting a cost estimate, since a few long-thinking moves can dominate it.

Puzzles are dealt across sets without replacement, 4 main and 1 bonus per set, and reshuffled when the pool runs out. A deck that tags its main puzzles by round, as grading-606b does, deals each round from its own puzzles. `--puzzles generate` plays on fresh puzzles made for the tournament: a generator model writes them, code checks them, and a judge model from another lab confirms each one. `python -m rstlne.puzzlegen` makes a batch on its own.

| Option | Effect |
|---|---|
| `--parallel N` | Plays N games at once. The default is 6, a whole set. |
| `--max-cost D` | Stops starting new games once spending reaches D dollars. |
| `--puzzles PATH` | The default is `puzzles/dev.json`, which marks the run as development. Scored runs use a generated deck or `puzzles/private.json`. |
| `--out PATH` | The tournament folder. The default covers the entrants, seed, puzzles, and every setting that changes play, so rerunning the same command resumes it. |

Each game writes its log into the tournament folder, and rerunning skips finished games. At the end, `report.json` and a printed table give each entrant's win rate overall and by seat, totals and main-round winnings, bonus rounds reached and won, solve accuracy, board showing at a correct solve, invalid moves, and cost. Intervals come from resampling whole sets, since the 6 games in a set share puzzles and spins. Tied leaders split a win.

## Self-play

```
uv run python -m rstlne.selfplay --help
```

Bot against bot, with no API calls: strategy variants against two copies of the unchanged bot, and the tuning runs behind each bot version. Runs shard across processes and resume where they stopped. Fits and tuning use tuning decks only, never the grading, dev or private decks.

## Analyses and the paper

`lineups.toml` maps each lineup id to its tournament folder, by phase: `v6` for the results, `v4` for the earlier grid. The analyses read it, so they take lineup ids, and they count finished games only.

```
uv run python -m rstlne.analysis.progress 2 3            # win rates so far, with intervals
uv run python -m rstlne.analysis.detail 2 3              # rounds won, banks, board showing at a winning solve, wrong solves
uv run python -m rstlne.analysis.milking 2 3             # rounds a bot milked, and what came of them
uv run python -m rstlne.analysis.odds 2 3                # the bot's logged steal odds and win chances against what happened
uv run python -m rstlne.analysis.reading_gap 2 3 --walk  # what the bot's reader made of the boards a model won on, and the letters it was short (word data)
uv run python -m rstlne.analysis.letters read 2 3 --out logs/analysis/letters.json   # judge every letter choice (word data)
uv run --with matplotlib python figures/make_figures.py figures                     # the charts
```

The paper's numbers all come from one file, `paper/numbers.json`. Run the two word-data analyses with `--out` first, over every lineup, so it can fold them in. They take a while, so run them on a server:

```
L="2 2t 3 3b 3c 3d 3r 3m 3f 3t 3tf 3lf 6a 6b 6d1 6d2 d1 d2 dj 6dj d2h d1h djh dg dgh 6dg d2t d1t djt dgt"
uv run python -m rstlne.analysis.letters read $L --out logs/analysis/letters-v6.json
uv run python -m rstlne.analysis.reading_gap $L --version 6 --walk 2 2t 3b 3c 3d 3m 3r --out logs/analysis/reading-gap-v6.json
uv run python -m rstlne.analysis.numbers --out paper/numbers.json
uv run python paper/make_numbers.py                      # numbers.json -> numbers.tex, one LaTeX macro per number
cd paper && latexmk -pdf main.tex                        # builds paper/build/main.pdf
```

The paper's text never types a result. It uses the macros, and a number `numbers.json` doesn't hold yet prints as a red placeholder.

## The bonus test

```
uv run python -m rstlne.bonustest --players llm:openai/gpt-6.1-sol,bot --puzzles puzzles/generated/grading-606b.json --seed 707
```

Plays the bonus round alone: every player meets every bonus puzzle in the file, with no wheel and no opponents, for a pure bonus solve rate on the same puzzles.

## The bot's word data

```
uv run python -m rstlne.data fetch
uv run python -m rstlne.data fetch enwiki
uv run python -m rstlne.data status
```

`fetch` streams each source and keeps only pruned tables in `data/`, which git ignores: about 8 minutes and 0.2 GB. Bots from version 5 on also read word pair and triple counts from all of English Wikipedia (`enwiki`). That fetch streams the whole dump: about 2 CPU-hours, up to 50 GB of temporary files, and 0.85 GB kept. It's best run on a server, then copied: the `enwiki-*` files, plus the `enwiki` entry in `data/manifest.json`. Without them, the bot refuses the data it finds. `data/manifest.json` records each file's hash, so a bot version pins its data. `status` lists what's fetched, its size, and its license. Sources, with thanks:

| source | used for | license |
|---|---|---|
| [wordfreq](https://github.com/rspeer/wordfreq) | the word list and word frequencies | data CC BY-SA 4.0, code MIT |
| [Wiktionary](https://www.wiktionary.org), extracted by [wiktextract](https://github.com/tatuylonen/wiktextract) at [kaikki.org](https://kaikki.org) | multiword entries: idioms, proverbs, phrases | CC BY-SA 4.0 and GFDL |
| [Wikidata](https://www.wikidata.org), queried through [QLever](https://qlever.dev) | names of people, places, landmarks, foods, titles, animals | CC0 |
| [CMU Pronouncing Dictionary](https://github.com/cmusphinx/cmudict) | rhymes for Rhyme Time | BSD 2-clause |
| [Tatoeba](https://tatoeba.org) | word pair counts from everyday sentences | CC BY 2.0 FR |
| [Simple English Wikipedia](https://simple.wikipedia.org) | word pair counts from encyclopedia text | CC BY-SA 4.0 |
| [English Wikipedia](https://en.wikipedia.org) | word pair and triple counts, from version 5 | CC BY-SA 4.0 |
| [fastText](https://fasttext.cc/docs/en/crawl-vectors.html) | word vectors, for how well a word fits a category | CC BY-SA 3.0 |

## Calibration

```
uv run python -m rstlne.calibrate --models openai/gpt-6-luna-decisions,typesafe/jev-1.14 --count 50
uv run python -m rstlne.calibrate trust --models openai/gpt-6.1-terra --logs <tournament folder>
```

The first picks each decision model's solve threshold, for `solve = "threshold"` under `[decision]`; by default (`solve = "choice"`) a decision model chooses when to solve on its own. The second measures the trust and steal curves a model needs before it can sit in a hybrid, on real game boards from tournament logs.

## Configuration

- `wheel.toml` holds the 24 wedges, what each round adds to the wheel, the special wedge values, and the bonus envelopes. [WHEEL.md](WHEEL.md) draws and explains it.
- `config.toml` holds the bot version, the decision seat's models, the hybrids' trust curves, provider pins, the round count, vowel cost, solve minimum, turn cap, an optional temperature, and the CLI pause and bonus timer.
- `puzzles/dev.json` holds development puzzles. Aired puzzles go in `puzzles/private.json`, which git ignores, because puzzles from the show are likely in model training data. Generated decks go in `puzzles/generated/`, also ignored, so they never leak into training data either.

A puzzle looks like `{"category": "Phrase", "answer": "BETTER LATE THAN NEVER", "bonus": false}`.

## Logs

Each game writes `logs/<date>-<time>-seed<N>.jsonl` with:

- a header with the seed, each seat's model and temperature, the rules, the wheel, and the puzzles
- one line per move or invalid try, with the state before it, the model's raw output, the parsed action, the result, the wedge, and token usage
- a summary with final totals, token use and cost per seat, and invalid moves by category

Token use includes how many prompt tokens each provider read from its cache. Each seat sends a session ID so OpenRouter keeps it on one provider, and `[providers]` in `config.toml` can pin a model to one.

## Tests

```
uv run pytest
```

The suite runs about 1,050 tests. A fake client stands in for OpenRouter, so it never makes a network call, and it never reads `data/`. `uv run pytest -m slow` runs the few tests that read the real word data.

## Layout

```
rstlne/engine/        the rules engine: no I/O, no network, every chance outcome from the seeded wheel
rstlne/players/       your seat, model seats, decision seats, hybrid seats, and the bot (bot/)
rstlne/llm/           the OpenRouter chat and Decisions API clients, with retries and usage tracking
rstlne/runner.py      the game loop: retries, forfeits, and logs
rstlne/cli.py         the terminal game
rstlne/web/           the browser game: server.py (FastAPI), session.py, replay.py, static/ (the page)
rstlne/tournament.py  seeded tournaments with duplicate scoring
rstlne/bonustest.py   the bonus round alone
rstlne/selfplay.py    bot self-play and tuning, no API calls
rstlne/puzzlegen.py   fresh puzzles: written by one model, checked in code, judged by another
rstlne/decks.py       play decks: the mega deck and the aired deck
rstlne/analysis/      analyses of finished games, and numbers.py, which builds the paper's numbers
paper/                the paper: main.tex, sections/, numbers.json and the macros made from it
figures/              the charts, and the script that draws them from the logs
deploy/               the web page as an always-on systemd service
notes/                planning notes from building the project, not kept up to date
lineups.toml          each lineup's tournament folder, by phase
FINDINGS.md           the results, short
documentation.md      the full game specification
CLAUDE.md             build notes for Claude Code
```
