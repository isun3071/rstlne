# Grading plan: six lineups

Six tournaments that pit every kind of player against every other: LLMs, the bot, and the hybrid (the bot plus Luna reading the board).

## The rules for every run

- **Same deck:** `puzzles/generated/grading-505.json`, the realistic v6 puzzles (400 main, 100 bonus).
- **Same seed:** `707`. Set 17 has the same spins and puzzles in every lineup, so differences between lineups come from the players, not luck.
- **Bot v3**, set in `config.toml`.
- **W** is the winner of lineup 1 (the highest win rate). W fills every LLM seat in lineups 2 to 6.

## The six lineups

| # | Seats | What it tells us | Sets |
|---|---|---|---|
| 1 | Terra, DeepSeek, MiMo | Which LLM is best, with no bot around | 100 |
| 2 | W, bot, bot | Can a good LLM beat the bot? | 50 |
| 3 | hybrid, bot, bot | How much does Luna's reading add to the bot? | 100 |
| 4 | W, hybrid, bot | All three player types at one table | 50 |
| 5 | W, hybrid, hybrid | Can an LLM beat the strongest seats? | 50 |
| 6 | bot, W, W | Can the bot beat two good LLMs? | 50 |

**More sets if needed:** if a lineup's key result is too close to call, rerun its command with `--sets 100`. It picks up from set 51.

## Order

1. **Wait:** the v3 faceoff must finish.
2. **Make the deck:** generate `grading-505`, then copy it back so the bad puzzles get fixed by hand.
3. **Run 1 and 3** together.
4. **Pick W** from lineup 1. If #1 and #2 are within each other's error bars, note that it's a close call.
5. **Run 2, 4, 5, and 6** together.

## Commands (on the server)

The same flags go at the end of every command:

```
--puzzles puzzles/generated/grading-505.json --seed 707
```

| # | Command |
|---|---|
| 1 | `uv run python -m rstlne.tournament --seats llm:openai/gpt-6.1-terra,llm:deepseek/deepseek-v4.1-flash-1017,llm:xiaomi/mimo-v2.6-flash --sets 100 --parallel 24 --max-cost 45` |
| 3 | `uv run python -m rstlne.tournament --seats hybrid:openai/gpt-6-luna,bot,bot --sets 100 --parallel 5 --max-cost 5` |
| 2 | `uv run python -m rstlne.tournament --seats llm:W,bot,bot --sets 50 --parallel 5 --max-cost 15` |
| 4 | `uv run python -m rstlne.tournament --seats llm:W,hybrid:openai/gpt-6-luna,bot --sets 50 --parallel 5 --max-cost 15` |
| 5 | `uv run python -m rstlne.tournament --seats llm:W,hybrid:openai/gpt-6-luna,hybrid:openai/gpt-6-luna --sets 50 --parallel 5 --max-cost 15` |
| 6 | `uv run python -m rstlne.tournament --seats bot,llm:W,llm:W --sets 50 --parallel 5 --max-cost 20` |

Replace `W` with the winner's model name, such as `openai/gpt-6.1-terra`.

- **Logs:** add `2>&1 | tee -a logs/grid-N.txt` to keep each run's output.
- **Hitting the cost cap:** a run that stops at its `--max-cost` resumes when you rerun it with a higher cap.

## Watch out for

- **Memory.** Every bot or hybrid seat loads about 420 MB per game process, and the server has 15 GB. Keep lineups 2 to 6 at `--parallel 5` each. Lineup 1 has no bots, so it can use `--parallel 24`.
- **Time.** Lineup 1 is the slow one: three thinking models play every move, about 4 to 5 hours. The rest take a few hours together.
- **Cost.** Lineup 1 is about $28. Lineups 2 to 6 at 50 sets are about $41 if Terra wins, and about $18 if DeepSeek or MiMo wins.

## Afterwards

Copy each tournament folder back:

```
rsync -av server:rstlne/logs/tournaments/ logs/tournaments/
```

The analysis compares the same sets across lineups.
