# How to play

You sit at a three-seat table, usually with two models. The game plays four rounds of puzzles. Then the player with the most money plays the bonus round alone. The dollar amounts here are the defaults in `config.toml` and `wheel.toml`.

## Start a game

```
uv run python -m rstlne.cli --seats human,llm:anthropic/claude-haiku-5.5,llm:deepseek/deepseek-v4.1-flash-1017
```

You play the seat marked `human`. Model moves print as they happen, with a short pause between them.

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
- The starting seat rotates each round. A round with no solver ends after 200 turns, and nobody banks.

## Special wedges

- **TOP:** $2,500 in round 1, $3,500 in rounds 2 and 3, and $5,000 in round 4.
- **Free Play:** call any letter. A consonant earns $500 per copy, a vowel is free, and a miss keeps your turn.
- **Wild Card** (rounds 1 to 3): a correct consonant on its wedge claims it, and you keep it across rounds. After a correct consonant on a plain dollar wedge, you can spend it to call one more consonant at the same value. If that consonant misses, your turn passes. Unspent, it becomes a 4th consonant in the bonus round.
- **Million wedge** (rounds 1 to 3): Bankrupt on both outer thirds, $500 in the middle. A correct consonant on the middle claims the Million card, which you keep only by solving that round. In the bonus round, it swaps the $100,000 envelope for $1,000,000.
- **Mystery** (round 2): $1,000 per copy. After a correct consonant, keep the money or flip the wedge. One Mystery wedge hides $10,000, the other Bankrupt. Once one is flipped, the other plays as a plain $1,000 wedge.
- **Express** (round 3): $1,000 per copy. After a correct consonant, pass or play. If you play, you call consonants for $1,000 each and buy vowels for $250, with no spinning, until you solve. Any miss, repeat, or wrong solve is Bankrupt.

## Bonus round

The highest game total plays, and a seeded draw breaks a tie. R, S, T, L, N, and E are revealed. Pick 3 consonants and 1 vowel, or 4 consonants if you hold the Wild Card, typed like `B G H I`. Then you have 10 seconds for one solve. A correct solve wins the envelope, which holds $40,000 to $55,000, or $100,000. With the Million card, the $100,000 envelope becomes $1,000,000.

## Watch the models play

Fill all three seats with models and the game runs by itself, start to finish. Nobody types anything. There are two kinds of model seat:

- `llm:<slug>` is a chat model, such as Claude Haiku or GPT-6 Luna, that makes every move itself.
- `decision` is a decision model, GPT-6 Luna Decisions by default, that picks every move from the legal options. An LLM writes its answer whenever it decides to solve. `[decision]` in `config.toml` sets both models and the solve threshold. Use `decision:<model>` to give one seat a different decision model.

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
uv run python -m rstlne.cli --seats decision,decision:typesafe/jev-1.14,decision:typesafe/jev-1.13
```

You can repeat a model, for example three `decision` seats or the same `llm:` slug twice. Each seat still plays on its own.

Options worth knowing:

- `--live` turns the terminal into one fixed screen that redraws after every move: the board as tiles, the letters still available, each seat's bank, total, cards, and latest thinking, and the last 10 moves. It needs a real terminal and works only when no human is seated. Combine it with `--pause 3` to follow along.
- After a correct solve, the solved board stays up for 10 seconds before the next round starts (`solve_pause` in `config.toml`). `--pause 0` skips that wait too.
- `--show-puzzle` prints the table after every move: the board, category, used letters, round banks, game totals, held cards, and the current wedge.
- `--show-thinking` prints what each seat weighed before its move. For a chat model, that's its reasoning. For a decision seat, it's P(solvable) and the probability of each pick.
- `--pause 0` removes the pause after each move, so the game runs as fast as the models answer. `--pause 3` slows it down to read along.
- `--seed N` replays a game's spins. Every game prints its seed at the start, so you can rerun a game you liked, or give different models the same spins.

At the end you see the bonus answer, each seat's final total, and each model's calls, tokens, and cost. Our test games each cost about 1 to 2 cents. Every move also goes to a log in `logs/`. Press Ctrl+C to stop a game early; the log keeps every move up to that point.

A single game is one sample, not a fair comparison. Seat order matters, and each seat sees different spins.
