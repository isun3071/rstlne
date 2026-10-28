# Wheel of Fortunate LLMs

Wheel of Fortune in the terminal, with language models at the table. Each of the three seats is you or a model called through [OpenRouter](https://openrouter.ai). The game follows the current show's rules, including the Mystery and Express wedges, the Wild Card, the Million wedge, and the bonus round.

The same engine is built to run seeded, model-only tournaments that compare how well models pick letters, take risks, and time their solves.

## Status

| Part | State |
|---|---|
| Game engine, covering every rule in `documentation.md` | Done |
| Model seats, which move by tool calls | Done |
| Decision model seats (configuration 5) | Done |
| Your seat in the terminal | Done |
| Game logs | Done |
| Baseline bot | Not started |
| Tournament runner | Not started |
| Local web page | Planned for phase 2 |

## Setup

You need Python 3.11 or newer and an OpenRouter API key.

```
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cp .env.example .env
```

Put your key in `.env` as `OPENROUTER_API_KEY=...`. Git ignores `.env`.

## Play

```
.venv/bin/python -m wof.cli --seats human,llm:anthropic/claude-haiku-5.5,llm:openai/gpt-6-luna
```

Each seat is `human`, `llm:<slug>`, or `decision`. Three model seats play a model-only game. A `decision` seat is configuration 5: a decision model such as Jev makes every choice through OpenRouter's Decisions API, and an LLM writes the answer when the decision model calls a solve. `[decision]` in `config.toml` names both models and the solve threshold, and `decision:<model>` overrides the decision model for one seat. A model needs tool calling: check that its `supported_parameters` on OpenRouter include `tools`. [HOW_TO_PLAY.md](HOW_TO_PLAY.md) covers the commands and rules.

| Option | Effect |
|---|---|
| `--seed N` | Plays seed N. The same seed and the same moves replay the same game. Without it, the game picks a seed and prints it. |
| `--show-thinking` | Prints each model's reasoning and message before its move. For a decision seat, it prints P(solvable) and the probability of each pick. |
| `--pause S` | Pauses S seconds after each model move. The default is 1.5. |
| `--puzzles PATH` | Reads puzzles from PATH. The default is `puzzles/dev.json`. |
| `--log-dir PATH` | Writes game logs to PATH. The default is `logs/`. |

The slugs in `config.toml` are the models picked so far: Claude Haiku 5.5, GPT-6 Luna, and DeepSeek V4.1 Flash, with Qwen 3.8 Flash and GLM 5.3 Flash as backups.

## Configuration

- `wheel.toml` holds the 24 wedges, what each round adds to the wheel, the special wedge values, and the bonus envelopes.
- `config.toml` holds the decision seat's models and solve threshold, the round count, vowel cost, solve minimum, round turn cap, model slugs, an optional temperature, the CLI pause and bonus timer, and the bot's card values.
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
.venv/bin/pytest
```

The suite runs about 310 tests in around 5 seconds. It never calls OpenRouter; a fake client stands in.

## Layout

```
wof/engine/        the rules engine: no I/O, no network, every chance outcome from the seeded wheel
wof/players/       your seat (human_cli.py), model seats (llm.py), and decision seats (decision.py)
wof/llm/           the OpenRouter chat and Decisions API clients, with retries and usage tracking
wof/runner.py      the game loop: retries, forfeits, and logs
wof/narrate.py     move text for the screen and the model prompts
wof/cli.py         the terminal game
documentation.md   the full game specification
CLAUDE.md          build notes for Claude Code
```
