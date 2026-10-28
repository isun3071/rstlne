# CLAUDE.md

## Project

The repo is called rstlne, after R S T L N E, the letters the bonus round gives every player. The Python package is `rstlne`.

A Wheel of Fortune game where LLMs and a human play at the same table. Three seats. Each seat holds a human, an LLM (called through OpenRouter), a decision model, or the bot. The game runs the show's rules, round by round, through the bonus round.

The project serves two goals. Ian plays against models from the terminal for fun. The same engine runs seeded, model only tournaments that measure how well models handle letter choice, risk, and solve timing.

Build the CLI first. A local web page comes in phase 2 and reuses the engine untouched.

## Read first

`documentation.md` holds the full game specification: the wheel, every special wedge, turn rules, the bonus round, seeding, the LLM player protocol, the bot, the CLI, puzzles, and logging.

- Read `documentation.md` before you write or change anything in `engine/`, `players/`, `cli.py`, or `tournament.py`.
- Build gameplay exactly as `documentation.md` states it.
- When the spec is silent or ambiguous on a rule, stop and ask Ian. Never invent a game rule.
- When Ian changes a rule, update `documentation.md` in the same commit as the code.

## Stack

- Python 3.11 or newer
- `openai` Python SDK pointed at OpenRouter
- `pytest` for tests
- `python-dotenv` for the API key
- `uv` for the environment. Dependencies live in `pyproject.toml`, and `uv.lock` pins their exact versions. Commit `uv.lock` with every dependency change.

## OpenRouter

OpenRouter exposes an OpenAI compatible endpoint. Create the client like this:

```python
from openai import OpenAI
client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=os.environ["OPENROUTER_API_KEY"])
```

- Read `OPENROUTER_API_KEY` from `.env`. Never commit `.env`.
- Store model slugs in `config.toml`, never in code. Ian picks them from the OpenRouter catalog (`GET /api/v1/models`).
- Record the model slug and `temperature` in every game log. Temperature is unset by default, so each model plays at its own default and the log records `null`. When `config.toml` sets one, it must be 0.2 to 0.4.
- OpenRouter returns token usage on every response. Log it per call and total it per game.
- Wrap every call with retries and exponential backoff for 429 and 5xx responses.

## Layout

```
rstlne/
  engine/
    wheel.py       # wedge definitions, per round overlays, seeded spins
    puzzle.py      # board, reveal logic, letter counts
    state.py       # GameState, RoundState, public view
    rules.py       # apply(action) -> new state, legal_actions(state)
    bonus.py       # bonus wheel and bonus round flow
  players/
    base.py        # Player interface: decide(view) -> Action
    human_cli.py
    llm.py
    decision.py    # decision seat: decision model choices, LLM solves
    bot/           # the versioned bot
      player.py    # BotPlayer: one decision per phase, steal odds from observed play
      belief.py    # Belief: per letter odds, top answers, out of vocabulary share
      reader.py    # readers: letter frequency, and sampled whole answers from a word list
      info.py      # how a reveal moves the chance the best guess is right
      objective.py # dollars in rounds 1 and 2, win chance from round 3, card values, ties
      steal.py     # steal odds per opponent, in sequence around the table
      value.py     # the one value function for every move
      planner.py   # the known answer planner
      bonus.py     # bonus round picks and solve
      seed.py      # sampling seeds from a hash of the view
      versions.py  # versions and their frozen knobs; config.toml picks one
  llm/
    openrouter.py  # client, retries, usage tracking
    decisions.py   # Decisions API client for decision models like Jev
  settings.py      # loads wheel.toml and config.toml, so engine/ stays free of I/O
  runner.py        # game loop shared by cli and tournament: retries, forfeits, JSONL logs
  narrate.py       # plain-English text for the table and results, for the CLI and model prompts
  show.py          # line-by-line game printout
  live.py          # --live: one fixed screen, redrawn with rich
  cli.py           # play a game in the terminal
  tournament.py    # seeded model only runs
  calibrate.py     # picks each decision model's solve threshold from data
  data.py          # fetches the bot's word data into data/, streamed and pruned
puzzles/
  dev.json         # puzzles for development, committed
  private.json     # scored puzzles, gitignored
logs/              # JSONL per game, gitignored
data/              # the bot's fetched word data, gitignored
tests/
wheel.toml         # wheel template, round overlays, bonus envelopes
config.toml        # model slugs, round count, card values
documentation.md   # game specification
.env               # OPENROUTER_API_KEY, gitignored
.gitignore
```

## Architecture rules

- Keep the engine pure. `engine/` does no I/O, no printing, no network calls, and no randomness outside the seeded wheel.
- `rules.apply(state, action)` returns a new state. Never mutate state in place.
- Players see a public view only. A view contains the category, the spaced board, used letters, all three banks, held cards, whose turn it is, the current wedge, the wheel as it stands, and the list of legal actions. A view never contains the answer or a hidden Mystery side or bonus envelope.
- Every action goes through `rules.legal_actions`. The engine rejects illegal actions and never trusts a player.
- Load wheel layouts and envelope values from `wheel.toml`. Never hardcode wedge values.

## Testing

- Write the test before the feature.
- Unit test every rule in `rules.py` with fixed seeds.
- Test the wheel per round: over 720,000 seeded spins, each wedge lands within 2.5% (relative) of 1/24, and Bankrupt lands within 2.5% (relative) of 1/9 in rounds 1 to 3 and of 1/12 in round 4 onward.
- Test every special wedge path: keep, flip to $10,000, flip to Bankrupt, the second Mystery after a flip, Express pass, Express solve, Express bust, Wild use, and held cards lost to Bankrupt across rounds.
- Test the bonus round: qualification, tie draw, RSTLNE reveal, pick validation, the Wild Card's extra consonant, the Million envelope swap, and correct and wrong solves.
- Mock OpenRouter in every test. Tests never make network calls.

## Commands

```
uv run python -m rstlne.cli --seats human,llm:<slug>,bot
uv run python -m rstlne.tournament --models <slug1>,<slug2>,<slug3> --sets 100 --puzzles puzzles/private.json --seed 42
uv run pytest
```