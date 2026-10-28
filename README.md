# rstlne

Named after R, S, T, L, N, and E, the letters the bonus round hands every player.

Wheel of Fortune in the terminal, with language models at the table. Each of the three seats is you or a model called through [OpenRouter](https://openrouter.ai). The game follows the current show's rules, including the Mystery and Express wedges, the Wild Card, the Million wedge, and the bonus round.

The same engine is built to run seeded, model-only tournaments that compare how well models pick letters, take risks, and time their solves.

## Status

| Part | State |
|---|---|
| Game engine, covering every rule in `documentation.md` | Done |
| Model seats, which move by tool calls | Done |
| Decision model seats | Done |
| Your seat in the terminal | Done |
| Game logs | Done |
| Bot (v1) | Decisions built; it reads by letter frequency until its word data is fetched |
| Tournament runner | Done |
| Local web page | Planned for phase 2 |

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

Each seat is `human`, `llm:<slug>`, `decision`, or `bot`. Three seats without a human play a model-only game. In a `decision` seat, a decision model, GPT-6 Luna Decisions by default, makes every choice through OpenRouter's Decisions API, and an LLM writes the answer when the decision model calls a solve. `[decision]` in `config.toml` names both models and the solve threshold, and `decision:<model>` overrides the decision model for one seat. A `bot` seat is the project's own versioned player: it reads the board with word and phrase lists and scores every move with one value function, as `documentation.md` describes. Until its word data is fetched, it reads the board by letter frequency alone, so it solves only once the board gives the answer away. A model needs tool calling: check that its `supported_parameters` on OpenRouter include `tools`. [HOW_TO_PLAY.md](HOW_TO_PLAY.md) covers the commands and rules.

| Option | Effect |
|---|---|
| `--seed N` | Plays seed N. The same seed and the same moves replay the same game. Without it, the game picks a seed and prints it. |
| `--show-thinking` | Prints each model's reasoning and message before its move. For a decision seat, it prints P(solvable) and the probability of each pick. |
| `--live` | Model-only games: redraws one fixed screen after every move, with the board as tiles, the letters left, each seat's money, cards, and thinking, and the latest moves. |
| `--show-puzzle` | Prints the board, letters, banks, cards, and wedge after every move, so you can follow a model-only game. |
| `--pause S` | Pauses S seconds after each model move. The default is 1.5. |
| `--puzzles PATH` | Reads puzzles from PATH. The default is `puzzles/dev.json`. |
| `--log-dir PATH` | Writes game logs to PATH. The default is `logs/`. |

The slugs in `config.toml` are the models picked so far: Claude Haiku 5.5, GPT-6 Luna, and DeepSeek V4.1 Flash, with Qwen 3.8 Flash and GLM 5.3 Flash as backups.

## Tournaments

```
uv run python -m rstlne.tournament --models anthropic/claude-haiku-5.5,openai/gpt-6-luna,deepseek/deepseek-v4.1-flash-1017 --sets 50 --seed 42
```

A tournament plays `--sets` puzzle sets with duplicate scoring. A set is 6 games, one for every ordering of the 3 entrants across the seats, all with the set's seed and puzzles. So within a set, each entrant sits in each seat twice and plays right after each other entrant 3 times, against the same spins. `--sets 50` is 300 games, and `--sets 1` is a 6 game trial for checking cost. `--models a,b,c` is short for three `llm:` seats. Setting `set_permutations = "cyclic"` in `config.toml` plays the old 3 seat rotations instead.

Puzzles are dealt across sets without replacement, 4 main and 1 bonus per set, and reshuffled when the pool runs out, so no set repeats a puzzle.

| Option | Effect |
|---|---|
| `--parallel N` | Plays N games at once. The default is 6, a whole set. |
| `--max-cost D` | Stops starting new games once spending reaches D dollars. |
| `--puzzles PATH` | The default is `puzzles/dev.json`, which marks the run as development. Scored runs use `puzzles/private.json`. |
| `--out PATH` | The tournament folder. The default covers the entrants, seed, puzzles, and every setting that changes play, so rerunning the same command resumes it, and changing a setting starts a fresh folder. |

Each game writes its usual log into the tournament folder, and rerunning skips finished games and replays unfinished ones. At the end, `report.json` and a printed table give each entrant's win rate overall and by seat, average final total and main round winnings, bonus rounds reached and won, solve accuracy, how much of the board showed at a correct solve, money left on the table, invalid moves, and cost. The report also lists each set's results and how many sets used each puzzle.

Confidence intervals come from resampling whole sets, since the 6 games in a set share puzzles and spins and aren't independent. The table shows a 95% interval on each win rate and on the win rate gap between each pair of entrants; `report.json` also has intervals on average totals, main round winnings, and solve accuracy. A game's winner is the highest final total; tied leaders split the win. With Claude Haiku thinking, a game takes about 6 to 7 minutes and 1 to 2 cents, so 50 sets (300 games) at 6 games at once take about 5 hours.

## The bot's word data

```
uv run python -m rstlne.data fetch
uv run python -m rstlne.data status
```

`fetch` streams each source and keeps only pruned tables in `data/`, which git ignores, under a 2.5 GB cap; it took about 8 minutes and keeps about 0.2 GB. `status` lists what's fetched, its size, and its license. `data/manifest.json` records each file's hash, so a bot version can pin its data. Sources, with thanks:

| source | used for | license |
|---|---|---|
| [wordfreq](https://github.com/rspeer/wordfreq) | the word list and word frequencies | data CC BY-SA 4.0, code MIT |
| [Wiktionary](https://www.wiktionary.org), extracted by [wiktextract](https://github.com/tatuylonen/wiktextract) at [kaikki.org](https://kaikki.org) | multiword entries: idioms, proverbs, phrases | CC BY-SA 4.0 and GFDL |
| [Wikidata](https://www.wikidata.org), queried through [QLever](https://qlever.dev) | names of people, places, landmarks, foods, titles, animals | CC0 |
| [CMU Pronouncing Dictionary](https://github.com/cmusphinx/cmudict) | rhymes for Rhyme Time | BSD 2-clause |
| [Tatoeba](https://tatoeba.org) | word pair counts from everyday sentences | CC BY 2.0 FR |
| [Simple English Wikipedia](https://simple.wikipedia.org) | word pair counts from encyclopedia text | CC BY-SA 4.0 |
| [fastText](https://fasttext.cc/docs/en/crawl-vectors.html) | word vectors, for how well a word fits a category | CC BY-SA 3.0 |

## Calibrating decision models

Decision models put P(solvable) on different scales: Jev 1.14 gives a fully revealed board about 0.75, while GPT-6 Luna Decisions gives about 0.99. So each decision model gets its own solve threshold, picked from data:

```
uv run python -m rstlne.calibrate --models openai/gpt-6-luna-decisions,typesafe/jev-1.14 --count 50
```

The command reveals 50 seeded puzzles step by step, asks each decision model for P(solvable) at every step, and has the solver attempt each board. A model's threshold is the lowest P(solvable) where the solver's accuracy, fit as a never decreasing curve, reaches 80%. It prints the lines to paste under `[decision.thresholds]` in `config.toml` and saves every board's result in `logs/calibration/`. 50 puzzles took about 8 minutes and a few cents.

## Configuration

- `wheel.toml` holds the 24 wedges, what each round adds to the wheel, the special wedge values, and the bonus envelopes.
- `config.toml` holds the decision seat's models and solve threshold, the round count, vowel cost, solve minimum, round turn cap, model slugs, an optional temperature, the CLI pause and bonus timer, and the bot version.
- `puzzles/dev.json` holds development puzzles. Scored tournament puzzles go in `puzzles/private.json`, which git ignores, because puzzles from the show are likely in model training data.

A puzzle looks like `{"category": "Phrase", "answer": "BETTER LATE THAN NEVER", "bonus": false}`.

## Logs

Each game writes `logs/<date>-<time>-seed<N>.jsonl` with:

- a header with the seed, each seat's model and temperature, the rules, the wheel, and the puzzles
- one line per move or invalid try, with the state before it, the model's raw output, the parsed action, the result, the wedge, and token usage
- a summary with final totals, token use and cost per seat, and invalid moves by category

Token use includes how many prompt tokens each provider read from its cache. Models from OpenAI, DeepSeek, and Z.AI cache on their own. Anthropic and Qwen models get asked for caching on every request, and each seat sends a session ID so OpenRouter keeps it on one provider.

## Tests

```
uv run pytest
```

The suite runs about 390 tests in under 20 seconds. It never calls OpenRouter; a fake client stands in.

## Layout

```
rstlne/engine/        the rules engine: no I/O, no network, every chance outcome from the seeded wheel
rstlne/players/       your seat (human_cli.py), model seats (llm.py), decision seats (decision.py), and the bot (bot/)
rstlne/llm/           the OpenRouter chat and Decisions API clients, with retries and usage tracking
rstlne/runner.py      the game loop: retries, forfeits, and logs
rstlne/narrate.py     move text for the screen and the model prompts
rstlne/cli.py         the terminal game
documentation.md   the full game specification
CLAUDE.md          build notes for Claude Code
```
