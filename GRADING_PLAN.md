# Grading plan: six lineups

Six tournaments that pit every kind of player against every other: LLMs, the bot, and the hybrid (the bot plus Luna reading the board).

## The rules for every run

- **Same deck:** `puzzles/generated/grading-505.json`, the realistic v6 puzzles (400 main, 100 bonus).
- **Same seed:** `707`. Set 17 has the same spins and puzzles in every lineup, so differences between lineups come from the players, not luck.
- **Bot v4**, adopted on 2026-10-31: in its self-play check it tied v3 (−0.05 points, −0.65 to +0.55), and Ian adopted it as no worse. Lineup 3 first ran on v3 and was scrubbed, so every bot lineup runs on v4.
- **W** is the winner of lineup 1 (the highest win rate). W fills every LLM seat in lineups 2 to 6.

## The six lineups

| # | Seats | What it tells us | Sets |
|---|---|---|---|
| 1 | Sol, DeepSeek, Haiku | Which LLM is best, with no bot around: three labs (OpenAI, DeepSeek, Anthropic) | 60 |
| 2 | W, bot, bot | Can a good LLM beat the bot? | 60 |
| 3 | hybrid, bot, bot | How much does Luna's reading add to the bot? | 60 |
| 3b | Luna, bot, bot | What does the bot's strategy add to Luna? (added 2026-10-31) | 60 |
| 4 | W, hybrid, bot | All three player types at one table | 60 |
| 5 | W, hybrid, hybrid | Can an LLM beat the strongest seats? | 60 |
| 6 | bot, W, W | Can the bot beat two good LLMs? | 60 |

**Sets:** 60 for every lineup, matching lineup 1, so any two lineups pair up set by set (Ian, 2026-10-31; lineup 3 was planned at 100 until its early gap proved large). **More sets if needed:** if a result is too close to call, rerun the commands of both lineups being compared with `--sets 100`, so the extra sets still pair; a rerun picks up where its folder stopped.

**Lineup 1 was cut to 50 sets on 2026-10-31, at 10 games at a time:** Sol won its first 19 games outright, and 24 at a time made MiMo's host time out. Second place goes on rounds won, money, and second-place finishes, since DeepSeek and MiMo barely win.

**MiMo was dropped from lineup 1 on 2026-10-31.**
- **Why:** about 1 call in 4 ran away into 6,000 to 58,000 tokens of thinking. Those calls timed out games and made up two thirds of MiMo's spend, so it cost more per game than Sol and DeepSeek combined.
- **The record:** its partial run (23 games, all won by Sol) was scrubbed at Ian's request.
- **The replacement:** Claude Haiku 5.5, for Anthropic.

## Lineup 1 result (2026-10-31): W is Sol

**Rule change after lineup 1:** from 2026-10-31 the solver of round 3 starts round 4 (before, seat 1 always did). Lineup 1 played under the old rule and is not rerun: W is Sol either way, and in 100 self-play sets the change moved no player's win rate by more than a point (`logs/selfplay/v4-check-newstart`). Lineups 2 to 6 play under the new rule. Don't extend lineup 1's folder with more sets, since it would mix the two rules.

360 games in 60 sets, `logs/tournaments/seed707-d7589355`, $12.46 in all.

| | Sol | DeepSeek | Haiku |
|---|---|---|---|
| Win rate | **66%** (61–70%) | 25% (21–29%) | 9% (6–13%) |
| 1st / 2nd / 3rd | 237 / 75 / 48 | 89 / 186 / 85 | 34 / 99 / 227 |
| Rounds won per game | 1.92 | 1.54 | 0.55 |
| Solves right | 96% | 89% | 91% |
| Board showing at a correct solve | 48% | 46% | 67% |
| Bonus won | 236 / 237 | 84 / 89 | 28 / 34 |
| Invalid moves per game | 0.02 | 0.39 | 0.20 |
| Cost per game | $0.015 | $0.014 | $0.005 |

Every gap clears zero: Sol leads DeepSeek by 41 points (34 to 49), and DeepSeek leads Haiku by 15 (9 to 21). In Sol's 123 losses it won no round 40 times, won at least as many rounds as the winner 31 times, and made a wrong solve in only 12.

## Lineup 2 result (2026-10-31): Sol beats two bots, but less easily than two LLMs

360 games in 60 sets, `logs/tournaments/seed707-e250a942`, $6.35, bot v4, round 3's solver starting round 4.

| | Sol | Each bot |
|---|---|---|
| Win rate | **58%** (51–64%) | 21% (17–25%) |
| Rounds won per game | 2.26 | 0.87 |
| Median bank when winning a round (rounds 1–3) | $3,350–3,975 | $5,300–7,000 |
| Solves right | 96% | 90% |
| Board showing at a correct solve | 52% | 65% |
| Bonus won | 205 / 209 | 129 / 151 (both bots) |

Sol leads each bot by 37 to 38 points (27 to 47). Set by set, Sol wins 7.8 points less against two bots than against DeepSeek and Haiku in lineup 1 (−15.0 to −0.6), with the caveat that lineup 1 ran under the old round 4 rule (worth under a point in self-play). Sol takes 56% of rounds, but the bots bank half again as much when they win one, and in 125 of Sol's 151 losses a bot took round 4. The bots read Sol as LLM-like (median w 0.87 at game end), so v4's per-opponent gain was in use; only a rerun with v3 seats would show whether it helped.

## Lineup 3 result (2026-10-31): the hybrid beats two bots, but Sol alone does better

360 games in 60 sets, `logs/tournaments/seed707-ca968604`, $1.93, bot v4, round 3's solver starting round 4.

| | Hybrid (bot + Luna) | Each bot | Sol in lineup 2, same bots |
|---|---|---|---|
| Win rate | **45%** (40–51%) | 27–28% | 58% |
| Rounds won per game | 1.74 | 1.13 | 2.26 |
| Median bank when winning a round (rounds 1–3) | $4,900–5,375 | $4,900–6,550 | $3,350–3,975 |
| Solves right | 97.5% | 92.5% | 96% |
| Board showing at a correct solve | 65% | 66% | 52% |
| Bonus won | 147 / 163 | 169 / 197 (both bots) | 205 / 209 |

The hybrid leads each bot by 17 to 19 points (9 to 27). Set by set, it wins 12.8 points less than Sol did against the same two bots (−20.0 to −5.6). It asked Luna 5,817 times (16 a game, about 6 seconds each): Luna called the board not solvable 2,484 times and gave an answer 3,333 times, 84% of them right. Luna's reads made the hybrid surer (median +0.20 confidence) and more accurate, but it still solved at the bots' 65% of the board, milking as they do. The bots read it as bot-like (median w 0.31). A Luna-alone lineup on the same sets would show what the bot's strategy adds to Luna.

## Lineup 3b result (2026-10-31): Luna alone loses to two bots; the bot's strategy adds 28 points to Luna

360 games in 60 sets, `logs/tournaments/seed707-e71dd1af`, $1.33. Luna, bot, bot: Luna playing every move itself, against the same two bots and sets as lineups 2 and 3.

| Against two bots | Luna alone | Hybrid (bot + Luna) | Sol alone |
|---|---|---|---|
| Win rate | **17.5%** (12–23%) | 45% | 58% |
| Rounds won per game | 1.79 | 1.74 | 2.26 |
| Main-round winnings per round won | about $2,460 | about $5,400 | about $4,270 |
| Wrong solves per game | 0.70 | 0.04 | 0.09 |
| Solves right | 72% | 97.5% | 96% |

Set by set: hybrid − Luna alone +27.8 points (+20.8 to +34.7), Sol − Luna alone +40.6 (+32.5 to +48.3), Sol − hybrid +12.8 (+5.6 to +20.0). Luna's losses are discipline: 219 solves that don't fit the board (it puts already-called letters in hidden squares, repeats refuted answers, guesses on near-empty boards) and 150 bad tool calls, almost all a consonant called without spinning first (every tool is offered on every move, for prompt caching). The hybrid's fit check, refuted-answer list, and the bot's choice of when to trust a read remove those faults. The two identical bots differed by 8 points (+0.6 to +16), most likely chance.

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
| 1 | `uv run python -m rstlne.tournament --seats llm:openai/gpt-6.1-sol,llm:deepseek/deepseek-v4.1-flash-1017,llm:anthropic/claude-haiku-5.5 --sets 60 --parallel 16 --max-cost 20` |
| 3 | `uv run python -m rstlne.tournament --seats hybrid:openai/gpt-6-luna,bot,bot --sets 60 --parallel 10 --max-cost 5` |
| 2 | `uv run python -m rstlne.tournament --seats llm:W,bot,bot --sets 60 --parallel 5 --max-cost 10` |
| 4 | `uv run python -m rstlne.tournament --seats llm:W,hybrid:openai/gpt-6-luna,bot --sets 60 --parallel 5 --max-cost 10` |
| 5 | `uv run python -m rstlne.tournament --seats llm:W,hybrid:openai/gpt-6-luna,hybrid:openai/gpt-6-luna --sets 60 --parallel 5 --max-cost 10` |
| 6 | `uv run python -m rstlne.tournament --seats bot,llm:W,llm:W --sets 60 --parallel 5 --max-cost 15` |

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
