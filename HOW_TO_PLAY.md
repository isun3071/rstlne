# How to play

You sit at a three-seat table with any mix of models, bots, and hybrids, or watch them play each other. The game plays four rounds of puzzles. Then the player with the most money plays the bonus round alone. The dollar amounts here are the defaults in `config.toml` and `wheel.toml`.

## Start a game

```
uv run python -m rstlne.cli --seats human,bot,hybrid:anthropic/claude-haiku-5.5
```

`--seats` takes three seats, in order: seat 1, seat 2, seat 3. You play the seat marked `human`. The other moves print as they happen, with a short pause between them.

## Who can sit

| Seat | Who plays it | Cost |
|---|---|---|
| `human` | You, typing commands (below) | Free |
| `llm:<slug>` | A chat model through OpenRouter, making every move itself, such as `llm:openai/gpt-6.1-sol` or `llm:openai/gpt-6-luna`. Any model with tool calling works. | About 0.5 to 2 cents a game |
| `bot` | The project's own player. It reads the board with word and phrase lists and scores every move for money and its chance of winning. No API calls. `[bot] version` in `config.toml` picks the version, 4 by default. | Free |
| `hybrid:<slug>` | The bot makes every move, and on its turns asks the model to read the board. Only models with measured trust curves in `config.toml` can sit: `openai/gpt-6-luna`, `anthropic/claude-haiku-5.5`, and `deepseek/deepseek-v4.1-flash-1017`. | About 0.5 to 3 cents a game |
| `decision` or `decision:<model>` | A decision model, GPT-6 Luna Decisions by default, picks every move from the legal options, including when to solve. An LLM, Luna by default, writes the answer when it solves. `[decision]` in `config.toml` sets both. | Under 1 cent a game |

The bot, and so the hybrid, plays at full strength only with its word data fetched once: `uv run python -m rstlne.data fetch` (about 8 minutes, 0.2 GB). Without it, the bot reads by letter frequency alone.

You can repeat a seat kind, such as two `bot` seats or the same `llm:` slug twice. Each seat still plays on its own.

## Tables to try

Some tables to measure yourself against. [FINDINGS.md](FINDINGS.md) has how these players fared against each other over hundreds of games:

```
# The bot and the strongest model tested, GPT-6.1 Sol
uv run python -m rstlne.cli --seats human,bot,llm:openai/gpt-6.1-sol

# Two bots
uv run python -m rstlne.cli --seats human,bot,bot

# A hybrid and the model it's built on, playing alone
uv run python -m rstlne.cli --seats human,hybrid:openai/gpt-6-luna,llm:openai/gpt-6-luna

# A decision model and a bot
uv run python -m rstlne.cli --seats human,decision,bot
```

Every kind at one table, with nobody typing:

```
uv run python -m rstlne.cli --seats bot,hybrid:anthropic/claude-haiku-5.5,llm:openai/gpt-6.1-sol --live
```

Seat order matters a little: seat 1 starts round 1, seat 2 round 2, and seat 3 round 3. Move `human` to try a different seat.

## What you see

On your turn, the screen shows the table and then a prompt:

```
Round 2. Category: Food & Drink
Board: B A N A N A   _ _ _ _ _
Used letters: A B N Z
Round banks: You $1,750 | Seat 2 $0 | Seat 3 $600
Game totals: You $1,000 | Seat 2 $0 | Seat 3 $0
Cards: You hold the Wild Card.
s to spin, v E to buy a vowel, solve <answer>:
```

Underscores are hidden letters, and three spaces separate words. Punctuation shows from the start.

## Commands

| When | Type | What happens |
|---|---|---|
| Your turn | `s` | Spin the wheel |
| Your turn | `v E` | Buy a vowel, E here, for $250 |
| Your turn | `solve banana split` | Solve the puzzle |
| After a spin | `T` | Call a consonant |
| Free Play | `A` | Call any letter |
| Mystery wedge | `keep` or `flip` | Take $1,000 per copy, or flip for $10,000 or Bankrupt |
| Express wedge | `pass` or `play` | Keep playing normally, or ride the Express |
| Riding the Express | `T`, `v E`, or `solve ...` | Call, buy, or solve with no spinning |
| Wild Card offer | `wild` or `no` | Spend the Wild Card on an extra consonant, or keep it |
| Bonus letters | `B G H I` | Your consonants and one vowel |
| Bonus solve | your answer | You have 10 seconds |

Case doesn't matter. After a typo or an illegal move, the game just asks again.

## Rules

- **Consonants:** spin, then call a consonant. Each copy earns the wedge's value, and you keep your turn. A letter that's missing or already called passes your turn.
- **Vowels:** each costs $250 from your round bank, even when it misses. A missing or repeated vowel passes your turn. You can't buy one once every vowel is showing.
- **Solving:** type the answer with its punctuation. `WELL-KNOWN FACT` needs the hyphen, but case and extra spaces don't matter. A wrong solve passes your turn.
- **Banking:** only the solver keeps round money, and banks at least $1,000. The other seats lose their round money. Game totals from earlier rounds are safe.
- **No more consonants:** once every consonant is showing, you can't spin. Buy vowels or solve.
- **Bankrupt** wipes your round bank and any Wild Card or Million card you hold. **Lose a Turn** passes your turn.
- **Who starts:** seat 1 starts round 1, seat 2 round 2, and seat 3 round 3. From round 4, whoever solved the round before starts; if nobody did, a seeded draw picks. There are no toss-ups.
- A round with no solver ends after 200 turns, and nobody banks.

## Special wedges

- **TOP:** $2,500 in round 1, $3,500 in rounds 2 and 3, and $5,000 in round 4.
- **Free Play:** call any letter. A consonant earns $500 per copy, a vowel is free, and a miss keeps your turn.
- **Wild Card** (rounds 1 to 3): a correct consonant on its wedge claims it, and you keep it across rounds. After a correct consonant on a plain dollar wedge, you can spend it to call one more consonant at the same value. If that consonant misses, your turn passes. Unspent, it becomes a 4th consonant in the bonus round.
- **Million wedge** (rounds 1 to 3): Bankrupt on both outer thirds, $500 in the middle. A correct consonant on the middle claims the Million card, which you keep only by solving that round. In the bonus round, it swaps the $100,000 envelope for $1,000,000.
- **Mystery** (round 2): $1,000 per copy. After a correct consonant, keep the money or flip the wedge. One Mystery wedge hides $10,000, the other Bankrupt. Once one is flipped, the other plays as a plain $1,000 wedge.
- **Express** (round 3): $1,000 per copy. After a correct consonant, pass or play. If you play, you call consonants for $1,000 each and buy vowels for $250, with no spinning, until you solve. Any miss, repeat, or wrong solve is Bankrupt.

## Bonus round

The highest game total plays, and a seeded draw breaks a tie. R, S, T, L, N, and E are revealed. Pick 3 consonants and 1 vowel, or 4 consonants if you hold the Wild Card, typed like `B G H I`. Then you have 10 seconds for one solve. A correct solve wins the envelope, which holds $40,000 to $55,000, or $100,000. With the Million card, the $100,000 envelope becomes $1,000,000.

## Watch them play

Fill all three seats with anything but `human` and the game runs by itself, start to finish. Nobody types anything.

Three chat models:

```
uv run python -m rstlne.cli --seats llm:anthropic/claude-haiku-5.5,llm:openai/gpt-6-luna,llm:deepseek/deepseek-v4.1-flash-1017
```

A decision model against two chat models:

```
uv run python -m rstlne.cli --seats decision,llm:openai/gpt-6-luna,llm:deepseek/deepseek-v4.1-flash-1017
```

Three decision models:

```
uv run python -m rstlne.cli --seats decision,decision:typesafe/jev-1.14,decision:liquid/d1-ultra
```

Two hybrids built on different labs' models, and the bot they're built on:

```
uv run python -m rstlne.cli --seats hybrid:openai/gpt-6-luna,hybrid:anthropic/claude-haiku-5.5,bot
```

Options worth knowing:

- `--live` turns the terminal into one fixed screen that redraws after every move: the board as tiles, the letters still available, each seat's bank, total, and cards, a Thinking panel with up to 5 lines per seat, and the last 10 moves. It needs a real terminal. With you seated, the screen redraws after every move with your prompt under it, and the Thinking panel stays hidden, since it would show you the other seats' best guesses. Combine it with `--pause 3` to follow along.
- After a correct solve, the solved board stays up for 10 seconds before the next round starts (`solve_pause` in `config.toml`). `--pause 0` skips that wait too.
- `--show-puzzle` prints the table after every move: the board, category, used letters, round banks, game totals, held cards, and the current wedge.
- `--show-thinking` prints what each seat weighed before its move. For a chat model, that's its reasoning. For a decision seat, it's each choice's top options with their probabilities. For the bot, it's its best answer, its confidence, how it valued each move, and why it picked its letter; a hybrid adds the model's reading and how much the bot trusted it. When you play, it shows you the other seats' guesses too, so leave it off unless you want hints.
- `--pause 0` removes the pause after each move, so the game runs as fast as the models answer. `--pause 3` slows it down to read along.
- `--seed N` replays a game's spins. Every game prints its seed at the start, so you can rerun a game you liked, or give different models the same spins.

At the end you see the bonus answer, each seat's money before the bonus round, each seat's final total, and each model's calls, tokens, and cost. A game costs about 0.5 to 2 cents per model seat, and nothing for `human` and `bot` seats. Every move also goes to a log in `logs/`. Press Ctrl+C to stop a game early; the log keeps every move up to that point.

A single game is one sample, not a fair comparison. Seat order matters, and each seat sees different spins.
