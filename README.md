# rstlne

Named after R, S, T, L, N, and E, the letters the bonus round hands every player.

Wheel of Fortune in the terminal, with language models at the table. Each of the three seats is you or a model called through [OpenRouter](https://openrouter.ai). The game follows the current show's rules, including the Mystery and Express wedges, the Wild Card, the Million wedge, and the bonus round.

The same engine runs seeded, model-only tournaments that compare how well models pick letters, take risks, and time their solves.

[FINDINGS.md](FINDINGS.md) covers what about 4,000 scored games showed: the best model beats our bot, most don't, models have distinct temperaments, and letting a model read while the bot decides lifts weak models by about 28 points.

## Status

| Part | State |
|---|---|
| Game engine, covering every rule in `documentation.md` | Done |
| Model seats, which move by tool calls | Done |
| Decision model seats | Done |
| Hybrid seats: the bot decides, a model reads the board | Done |
| Your seat in the terminal | Done |
| Game logs | Done |
| Bot | Version 5 (2026-11-02): v4 with better reading and Express play. Version 4 is the checkpoint version |
| Tournament runner, bonus test, puzzle generator | Done |
| The v4 checkpoint: the grading runs in `FINDINGS.md`, all against bot v4 | Done (2026-11-01) |
| The v5 phase: a stronger bot (Express play, word-pair reading), checked against v4 | v5 adopted (+12.6 points over v4 in self-play); Sol against two v5 bots next |
| Local web page, starting with a solver | Planned for phase 2 |

## Setup

You need [uv](https://docs.astral.sh/uv/) and an OpenRouter API key. uv sets up Python 3.11 or newer if your machine doesn't have it.

```
uv sync
cp .env.example .env
```

`uv sync` builds `.venv` with the exact package versions in `uv.lock`, so every game and tournament runs on the same code. After changing dependencies in `pyproject.toml`, run `uv lock` and commit the new `uv.lock`.

Put your key in `.env` as `OPENROUTER_API_KEY=...`. Git ignores `.env`.

## Play

```
uv run python -m rstlne.cli --seats human,llm:anthropic/claude-haiku-5.5,llm:openai/gpt-6-luna
```

Each seat is `human`, `llm:<slug>`, `decision[:<model>]`, `bot`, or `hybrid:<slug>`. Three seats without a human play a model-only game. In a `decision` seat, a decision model, GPT-6 Luna Decisions by default, makes every choice through OpenRouter's Decisions API, including when to solve, and an LLM writes the answer. `[decision]` in `config.toml` names both models, and `decision:<model>` overrides the decision model for one seat, and `decision:<model>@<solver>` its solver too. In a `hybrid` seat the bot makes every move and asks the model to read the board on its turns. A `bot` seat is the project's own versioned player: it reads the board with word and phrase lists and scores every move with one value function, as `documentation.md` describes. It reads with its full reader once `python -m rstlne.data fetch` has run (see below). Without the data, it reads by letter frequency alone and solves only once the board gives the answer away. A model needs tool calling: check that its `supported_parameters` on OpenRouter include `tools`. [HOW_TO_PLAY.md](HOW_TO_PLAY.md) covers the commands and rules.

| Option | Effect |
|---|---|
| `--seed N` | Plays seed N. The same seed and the same moves replay the same game. Without it, the game picks a seed and prints it. |
| `--show-thinking` | Prints each model's reasoning and message before its move. For a decision seat, it prints P(solvable) and the probability of each pick. |
| `--verbose` | `--show-thinking`, plus the bot's working: each move's worth as a formula with its numbers, and the planner's solve-now against spin-again once it knows the answer. |
| `--live` | Model-only games: redraws one fixed screen after every move, with the board as tiles, the letters left, each seat's money, cards, and thinking, and the latest moves. |
| `--show-puzzle` | Prints the board, letters, banks, cards, and wedge after every move, so you can follow a model-only game. |
| `--pause S` | Pauses S seconds after each model move. The default is 1.5. |
| `--puzzles PATH` | Reads puzzles from PATH. The default is `puzzles/dev.json`. |
| `--log-dir PATH` | Writes game logs to PATH. The default is `logs/`. |

The grading runs used GPT-6.1 Sol, GPT-6 Luna, Claude Haiku 5.5, and DeepSeek V4.1 Flash (its October 17, 2026 snapshot). Any OpenRouter model with tool calling can sit.

## Play in a browser

```
uv run python -m rstlne.decks mega   # once: the mega deck, every aired and generated puzzle (stays out of git)
uv run python -m rstlne.decks aired  # or the aired puzzles alone: puzzles/aired-all.json (stays out of git)
uv run python -m rstlne.web          # then open http://127.0.0.1:8000
```

Pick the three seats on the page, then play or watch. Up to three humans can share the screen, taking turns with the same controls. Each can type a nickname. Model seats use the key in `.env`. `--port`, `--puzzles` and `--log-dir` work as in the CLI. Games log to `logs/` like CLI games. The Replays tab replays any game in the log folder, move by move, with breakpoints: stop at solves, Bankrupts, new rounds, a seat's moves, and more. The arrow keys step and the space bar plays.

## Tournaments

Add `--puzzles generate` to play on fresh puzzles made for the tournament: a generator model writes them, code checks them, and a judge model from another lab confirms each one. `documentation.md` has the details. A 50-set pool costs about a cent. `python -m rstlne.puzzlegen --main 40 --bonus 10 --seed 7 --out puzzles/generated/batch.json` makes a batch on its own.

```
uv run python -m rstlne.tournament --seats llm:openai/gpt-6.1-sol,bot,bot --sets 60 --seed 707 --puzzles puzzles/generated/grading-505.json
```

`--seats` takes any three seats, as in the CLI, and `--models a,b,c` is short for three `llm:` seats.

A tournament plays `--sets` puzzle sets with duplicate scoring. A set is 6 games, one for every ordering of the 3 entrants across the seats, all with the set's seed and puzzles. So within a set, each entrant sits in each seat twice and plays right after each other entrant 3 times, against the same spins. `--sets 60` is 360 games, and `--sets 1` is a 6 game trial for checking cost. Setting `set_permutations = "cyclic"` in `config.toml` plays the old 3 seat rotations instead.

Puzzles are dealt across sets without replacement, 4 main and 1 bonus per set, and reshuffled when the pool runs out, so no set repeats a puzzle. A deck that tags its main puzzles by round (grading-606b, or `private.json` by the round each puzzle aired in) deals each round from its own puzzles.

| Option | Effect |
|---|---|
| `--parallel N` | Plays N games at once. The default is 6, a whole set. |
| `--max-cost D` | Stops starting new games once spending reaches D dollars. |
| `--puzzles PATH` | The default is `puzzles/dev.json`, which marks the run as development. Scored runs use a generated deck, as the grading runs did, or `puzzles/private.json`. |
| `--out PATH` | The tournament folder. The default covers the entrants, seed, puzzles, and every setting that changes play, so rerunning the same command resumes it, and changing a setting starts a fresh folder. |

Each game writes its usual log into the tournament folder, and rerunning skips finished games and replays unfinished ones. At the end, `report.json` and a printed table give each entrant's win rate overall and by seat, average final total and main round winnings, bonus rounds reached and won, solve accuracy, how much of the board showed at a correct solve, money left on the table, invalid moves, and cost. The report also lists each set's results and how many sets used each puzzle.

Confidence intervals come from resampling whole sets, since the 6 games in a set share puzzles and spins and aren't independent. The table shows a 95% interval on each win rate and on the win rate gap between each pair of entrants; `report.json` also has intervals on average totals, main round winnings, and solve accuracy. A game's winner is the highest final total, and tied leaders split the win. The table also shows each entrant's main-round money, its total minus any bonus envelope. Cost per game runs from under 1 cent (Luna, Haiku) to about 2 cents (Sol), with bot seats free. A 60-set lineup took 1 to 5 hours on 4 cores.

## Analyses

`lineups.toml` maps each lineup to its tournament folder, by phase: `v6` for the reruns on bot v6 and grading-606b, `v4` for the earlier grid. The analyses and the charts read it, so they take lineup ids, and they count finished games only, so they can run while a lineup plays. Add `--phase v4` for the earlier grid.

```
uv run python -m rstlne.analysis.progress 2 3            # win rates so far, with intervals
uv run python -m rstlne.analysis.detail 2 3              # rounds won, bank and board showing at a winning solve, wrong solves
uv run python -m rstlne.analysis.milking 2 3             # rounds a bot milked, and what came of them
uv run python -m rstlne.analysis.odds 2 3                # the bot's logged steal odds and win chances against what happened
uv run python -m rstlne.analysis.reading_gap 2 3         # what the bots lacked on the rounds an LLM won (reads boards: needs the word data)
uv run python -m rstlne.analysis.letters read 2 3 --out logs/analysis/letters.json   # judge every letter choice (word data)
uv run python -m rstlne.analysis.letters report logs/analysis/letters.json
uv run --with matplotlib python figures/make_figures.py figures            # the charts, for lineups.toml's default phase
```

The paper's numbers all come from one file. Run the two word-data analyses with `--out` first, so it can fold them in:

```
uv run python -m rstlne.analysis.letters read 2 2t 3 3b 3c 3d 3r 3f 6a 6b 6d1 6d2 d1 d2 --out logs/analysis/letters-v6.json
uv run python -m rstlne.analysis.reading_gap 2 2t 3 3b 3c 3d 3r 3f 6a 6b 6d1 6d2 d1 d2 --out logs/analysis/reading-gap-v6.json
uv run python -m rstlne.analysis.numbers --out paper/numbers.json   # every lineup, the set-by-set pairs, the bonus test
```

## The bonus test

```
uv run python -m rstlne.bonustest --players llm:openai/gpt-6.1-sol,bot --puzzles puzzles/generated/grading-505.json --seed 707
```

Plays the bonus round alone: every player meets every bonus puzzle in the file, with no wheel and no opponents, for a pure bonus solve rate on the same puzzles.

## The bot's word data

```
uv run python -m rstlne.data fetch
uv run python -m rstlne.data fetch enwiki
uv run python -m rstlne.data status
```

Bot version 5, the default, also reads word pair and triple counts from all of English Wikipedia (`enwiki`). That fetch streams the whole dump: about 2 CPU-hours, up to 50 GB of temporary files, and 0.85 GB kept. It's best run on a server, then copied: the `enwiki-*` files, plus the `enwiki` entry in `data/manifest.json`. Without them, a version 5 bot refuses the data it finds. Set `[bot] version = 4` to play the older bot on the other sources alone.

`fetch` streams each source and keeps only pruned tables in `data/`, which git ignores, under a 2.5 GB cap. It took about 8 minutes and keeps about 0.2 GB. `status` lists what's fetched, its size, and its license. `data/manifest.json` records each file's hash, so a bot version can pin its data. Sources, with thanks:

| source | used for | license |
|---|---|---|
| [wordfreq](https://github.com/rspeer/wordfreq) | the word list and word frequencies | data CC BY-SA 4.0, code MIT |
| [Wiktionary](https://www.wiktionary.org), extracted by [wiktextract](https://github.com/tatuylonen/wiktextract) at [kaikki.org](https://kaikki.org) | multiword entries: idioms, proverbs, phrases | CC BY-SA 4.0 and GFDL |
| [Wikidata](https://www.wikidata.org), queried through [QLever](https://qlever.dev) | names of people, places, landmarks, foods, titles, animals | CC0 |
| [CMU Pronouncing Dictionary](https://github.com/cmusphinx/cmudict) | rhymes for Rhyme Time | BSD 2-clause |
| [Tatoeba](https://tatoeba.org) | word pair counts from everyday sentences | CC BY 2.0 FR |
| [Simple English Wikipedia](https://simple.wikipedia.org) | word pair counts from encyclopedia text | CC BY-SA 4.0 |
| [English Wikipedia](https://en.wikipedia.org) | word pair and triple counts, for version 5 | CC BY-SA 4.0 |
| [fastText](https://fasttext.cc/docs/en/crawl-vectors.html) | word vectors, for how well a word fits a category | CC BY-SA 3.0 |

## Calibrating decision models

By default (`solve = "choice"` under `[decision]`), a decision model chooses when to solve on its own. With `solve = "threshold"`, the seat solves once the model's P(solvable) passes a threshold instead. Decision models put P(solvable) on different scales: Jev 1.14 gives a fully revealed board about 0.75, while GPT-6 Luna Decisions gives about 0.99. So each decision model gets its own threshold, picked from data:

```
uv run python -m rstlne.calibrate --models openai/gpt-6-luna-decisions,typesafe/jev-1.14 --count 50
```

The command reveals 50 seeded puzzles step by step, asks each decision model for P(solvable) at every step, and has the solver attempt each board. A model's threshold is the lowest P(solvable) where the solver's accuracy, fit as a never decreasing curve, reaches 80%. It prints the lines to paste under `[decision.thresholds]` in `config.toml` and saves every board's result in `logs/calibration/`. 50 puzzles took about 8 minutes and a few cents.

## Configuration

- `wheel.toml` holds the 24 wedges, what each round adds to the wheel, the special wedge values, and the bonus envelopes.
- `config.toml` holds the decision seat's models and solve mode, the hybrid's trust curves, provider pins, the round count, vowel cost, solve minimum, round turn cap, model slugs, an optional temperature, the CLI pause and bonus timer, and the bot version.
- `puzzles/dev.json` holds development puzzles. Aired puzzles go in `puzzles/private.json`, which git ignores, because puzzles from the show are likely in model training data. Generated decks go in `puzzles/generated/`, also ignored, so they never leak into training data either.

A puzzle looks like `{"category": "Phrase", "answer": "BETTER LATE THAN NEVER", "bonus": false}`.

## Logs

Each game writes `logs/<date>-<time>-seed<N>.jsonl` with:

- a header with the seed, each seat's model and temperature, the rules, the wheel, and the puzzles
- one line per move or invalid try, with the state before it, the model's raw output, the parsed action, the result, the wedge, and token usage
- a summary with final totals, token use and cost per seat, and invalid moves by category

Token use includes how many prompt tokens each provider read from its cache. Models from OpenAI, DeepSeek, and Z.AI cache on their own. Anthropic models get asked for caching on every request. Qwen's provider caches only up to a marked message, so each Qwen request marks its system prompt and its newest message. Each seat sends a session ID so OpenRouter keeps it on one provider.

## Tests

```
uv run pytest
```

The suite runs about 770 tests in under two minutes. A fake client stands in for OpenRouter, so it never makes a network call. It also never reads `data/`, and the bot falls back to letter frequency there. `uv run pytest -m slow` runs the tests that read the real word data.

## Layout

```
rstlne/engine/        the rules engine: no I/O, no network, every chance outcome from the seeded wheel
rstlne/players/       your seat (human_cli.py), model seats (llm.py), decision seats (decision.py), hybrid seats (hybrid.py), and the bot (bot/)
rstlne/llm/           the OpenRouter chat and Decisions API clients, with retries and usage tracking
rstlne/runner.py      the game loop: retries, forfeits, and logs
rstlne/narrate.py     move text for the screen and the model prompts
rstlne/cli.py         the terminal game
rstlne/web/          the browser game: server.py (FastAPI), session.py (a game on its thread), replay.py (logs back into games), static/ (the page)
rstlne/tournament.py  seeded tournaments with duplicate scoring
rstlne/bonustest.py   the bonus round alone
rstlne/puzzlegen.py   fresh puzzles: written by one model, checked in code, judged by another
rstlne/selfplay.py    bot self-play and tuning, no API calls
rstlne/analysis/      analyses of finished tournament games, for the findings
figures/              the charts in FINDINGS.md, and the script that draws them from the logs
lineups.toml       each lineup's tournament folder, by phase
FINDINGS.md        what the grading runs found
documentation.md   the full game specification
CLAUDE.md          build notes for Claude Code
```
