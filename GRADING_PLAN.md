# Grading plan: six lineups

Six tournaments that pit every kind of player against every other: LLMs, the bot, and the hybrid (the bot plus Luna reading the board).

## The rules for every run

- **Same deck:** `puzzles/generated/grading-505.json`, the realistic v6 puzzles (400 main, 100 bonus).
- **Same seed:** `707`. Set 17 has the same spins and puzzles in every lineup, so differences between lineups come from the players, not luck.
- **Bot v4**, once its self-play check confirms it. `config.toml` moves to version 4 only then. Lineup 3 first ran on v3 and was scrubbed on 2026-10-31, so every bot lineup runs on one version.
- **W** is the winner of lineup 1 (the highest win rate). W fills every LLM seat in lineups 2 to 6.

## The six lineups

| # | Seats | What it tells us | Sets |
|---|---|---|---|
| 1 | Sol, DeepSeek, Haiku | Which LLM is best, with no bot around: three labs (OpenAI, DeepSeek, Anthropic) | 50 |
| 2 | W, bot, bot | Can a good LLM beat the bot? | 50 |
| 3 | hybrid, bot, bot | How much does Luna's reading add to the bot? | 100 |
| 4 | W, hybrid, bot | All three player types at one table | 50 |
| 5 | W, hybrid, hybrid | Can an LLM beat the strongest seats? | 50 |
| 6 | bot, W, W | Can the bot beat two good LLMs? | 50 |

**More sets if needed:** if a lineup's key result is too close to call, rerun its command with `--sets 100`. It picks up from set 51.

**Lineup 1 was cut to 50 sets on 2026-10-31, at 10 games at a time:** Sol won its first 19 games outright, and 24 at a time made MiMo's host time out. Second place goes on rounds won, money, and second-place finishes, since DeepSeek and MiMo barely win.

**MiMo was dropped from lineup 1 on 2026-10-31.**
- **Why:** about 1 call in 4 ran away into 6,000 to 58,000 tokens of thinking. Those calls timed out games and made up two thirds of MiMo's spend, so it cost more per game than Sol and DeepSeek combined.
- **The record:** its partial run (23 games, all won by Sol) was scrubbed at Ian's request.
- **The replacement:** Claude Haiku 5.5, for Anthropic.

## Order

1. **Now:** run lineup 1 (LLMs only, so the bot version doesn't matter). Alongside it, run v4's data run:
   ```
   uv run python -m rstlne.selfplay round-banks --puzzles puzzles/generated/tuning-101.json --sets 334 --seed 909 --out logs/selfplay/round-banks-v3 --workers 4
   ```
2. **Fit and freeze v4:** copy the data run back, run `selfplay v4-fit`, and freeze v4.
3. **Check v4:** in self-play, v4 against v3 against an eager v3, on grading-202, about 2,000 games.
4. **If v4 beats v3,** move `[bot] version` to 4. If not, stay on v3.
5. **Pick W** from lineup 1. If #1 and #2 are within each other's error bars, note that it's a close call.
6. **Run 3, 2, 4, 5, and 6.**

## Commands (on the server)

The same flags go at the end of every command:

```
--puzzles puzzles/generated/grading-505.json --seed 707
```

| # | Command |
|---|---|
| 1 | `uv run python -m rstlne.tournament --seats llm:openai/gpt-6.1-sol,llm:deepseek/deepseek-v4.1-flash-1017,llm:anthropic/claude-haiku-5.5 --sets 50 --parallel 16 --max-cost 20` |
| 3 | `uv run python -m rstlne.tournament --seats hybrid:openai/gpt-6-luna,bot,bot --sets 100 --parallel 5 --max-cost 5` |
| 2 | `uv run python -m rstlne.tournament --seats llm:W,bot,bot --sets 50 --parallel 5 --max-cost 10` |
| 4 | `uv run python -m rstlne.tournament --seats llm:W,hybrid:openai/gpt-6-luna,bot --sets 50 --parallel 5 --max-cost 10` |
| 5 | `uv run python -m rstlne.tournament --seats llm:W,hybrid:openai/gpt-6-luna,hybrid:openai/gpt-6-luna --sets 50 --parallel 5 --max-cost 10` |
| 6 | `uv run python -m rstlne.tournament --seats bot,llm:W,llm:W --sets 50 --parallel 5 --max-cost 15` |

Replace `W` with the winner's model name, such as `openai/gpt-6.1-sol`.

- **Logs:** add `2>&1 | tee -a logs/grid-N.txt` to keep each run's output.
- **Hitting the cost cap:** a run that stops at its `--max-cost` resumes when you rerun it with a higher cap.

## Watch out for

- **Memory.** Every bot or hybrid seat loads about 420 MB per game process, and the server has 15 GB. Keep lineups 2 to 6 at `--parallel 5` each. Lineup 1 has no bots, so it can use `--parallel 24`.
- **Time.** Lineup 1 is the slow one: three thinking models play every move, about 4 to 5 hours. The rest take a few hours together.
- **Cost.** These estimates include OpenAI's flex tier for Terra and Sol, and the cache fix that sends every tool on every move (`tools = "all"`). Together they cut cost per game about 4×.
  - Lineup 1 is about $17.
  - Lineups 2 to 6 at 50 sets are about $26 if Sol wins, about $15 if Terra wins, and about $12 if DeepSeek wins.
  - Sol hasn't played our game yet, so its figure is a guess until its first games.

## Afterwards

Copy each tournament folder back:

```
rsync -av server:rstlne/logs/tournaments/ logs/tournaments/
```

The analysis compares the same sets across lineups.
