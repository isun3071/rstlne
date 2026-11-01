# rstlne: every statistic (as of 2026-11-01)

This is the complete set of numbers behind the project, for reference. The briefing and its update explain the project and the story; this document only reports figures. Where a figure here and an earlier one disagree, this one is newer.

## How to read the numbers

- **Players:** an **LLM** moves itself by tool calls, with a neutral rules-only prompt. The **bot** (version 4) is the project's own player with no LLM inside. A **hybrid** is the bot making every move while an LLM reads the board on its turns. A **decision seat** is a decision model choosing every move, including when to solve, while GPT-6 Luna writes the answers.
- **Models:** Sol is GPT-6.1 Sol (OpenAI, half-price tier). Luna is GPT-6 Luna (OpenAI). Haiku is Claude Haiku 5.5 (Anthropic). DeepSeek is DeepSeek V4.1 Flash, its October 17, 2026 snapshot. Luna Decisions is GPT-6 Luna Decisions (OpenAI). d1-ultra is Liquid AI's d1-ultra, first on Artificial Analysis's Decision Index.
- **Every lineup:** 60 sets of 6 games (360 games), one game per seating order, all on one deck of 500 generated puzzles (400 main, 100 bonus) and one seed, so the same set has the same spins and puzzles in every lineup. Four main rounds, then the bonus round.
- **Win rate:** share of games won; tied leaders split the win. A fair share at a three-seat table is 33%.
- **Intervals:** 95%, from resampling whole sets (the 6 games of a set share puzzles and spins). **Set-by-set gaps** compare two lineups on the same sets.
- **Total − bonus (main-round money):** a seat's final total minus any bonus envelope it won. It tracks winning better than the total, which $40,000+ envelopes inflate.
- **Board showing at a correct solve:** share of the puzzle's letters revealed when the player solved correctly; lower is earlier.
- **Money left per solve:** the reveal value left on the board at a correct solve, a measure of how early a player cashes in.
- **Average place:** 1st to 3rd, ties sharing; 2.00 is par.

## The setup in numbers

| | |
|---|---|
| Lineups scored | 11 (3,960 games) |
| Deck | 400 main, 100 bonus generated puzzles; main 16–35 letters, median 23 |
| Puzzle category mix, length and letters | matched to 8,856 aired main and 2,153 aired bonus puzzles from 2013–2025 |
| API spend on the 11 lineups | about $45 |
| Bot | version 4 in every lineup with a bot |
| Round 4 starter | the round 3 solver (random if none); lineup 1 played the old rule (seat 1 always), which moved no win rate by more than a point in 100 self-play sets |

## Each lineup

### 1 · Sol, DeepSeek, Haiku (no bots)

| Seat | Win rate (95%) | By seat 1/2/3 | Avg total | Total − bonus | Bonus won/played | Solves right | Board showing at a correct solve (mean) | Money left per solve | Invalid moves/game | Cost |
|---|---|---|---|---|---|---|---|---|---|---|
| Sol | **65.8%** (61–70%) | 73/65/59% | $39,477 | $8,449 | 236/237 | 96% | 48% | $4,668 | 0.02 | $5.43 |
| DeepSeek | 24.7% (21–29%) | 32/24/18% | $15,573 | $4,726 | 84/89 | 89% | 46% | $5,256 | 0.39 | $5.17 |
| Haiku | 9.4% (6–13%) | 10/7/12% | $9,051 | $2,634 | 28/34 | 91% | 67% | $3,408 | 0.20 | $1.86 |

- Gaps: Sol − DeepSeek +41.1 (+33.6 to +48.6); Sol − Haiku +56.4 (+49.2 to +63.3); DeepSeek − Haiku +15.3 (+9.4 to +20.8).
- Finishes (1st/2nd/3rd, games): Sol 237/75/48; DeepSeek 89/186/85; Haiku 34/99/227.
- Rounds won per game: Sol 1.92, DeepSeek 1.54, Haiku 0.55.
- In Sol's 123 losses it won no round 40 times, won at least as many rounds as the winner 31 times, and made a wrong solve in only 12.
- MiMo V2.6 Flash was in the original lineup and was dropped: about 1 call in 4 ran away into 6,000–58,000 thinking tokens. Its partial run (23 games, all won by Sol) was discarded.

### 2 · Sol alone vs two bots

| Seat | Win rate (95%) | By seat 1/2/3 | Avg total | Total − bonus | Bonus won/played | Solves right | Board showing (mean) | Money left per solve | Invalid/game | Cost |
|---|---|---|---|---|---|---|---|---|---|---|
| Sol | **58.1%** (51–64%) | 55/53/66% | $36,603 | $9,645 | 205/209 | 96% | 52% | $4,130 | 0.03 | $6.35 |
| Bot #1 | 20.6% (17–24%) | 17/21/24% | $16,154 | $5,223 | 64/74 | 90% | 65% | $2,205 | 0 | $0 |
| Bot #2 | 21.4% (18–25%) | 17/26/22% | $16,783 | $5,492 | 65/77 | 90% | 65% | $2,140 | 0 | $0 |

- Gaps: Sol − bot #1 +37.5 (+27.2 to +47.2); Sol − bot #2 +36.7 (+26.7 to +46.7); bot #1 − bot #2 −0.8 (−4.7 to +3.1).
- Sol took 56% of rounds (2.26 a game against 0.87 per bot), but the bots banked about half again as much per round won (median $5,300–7,000 against Sol's $3,350–3,975 in rounds 1–3).
- In 125 of Sol's 151 losses a bot took round 4.
- Set by set, Sol won 7.8 points less against two bots than against DeepSeek and Haiku (−15.0 to −0.6).
- The bots read Sol as LLM-like (median 0.87 at game end on the bot's 0-to-1 scale).
- In rounds Sol took, the bot already knew the answer only 3% of the time. Of the ~15-point gap in solve timing, about 4 points is the bot milking a known answer and about 10 is slower reading.

### 3 · Hybrid (bot + Luna) vs two bots

| Seat | Win rate (95%) | By seat 1/2/3 | Avg total | Total − bonus | Bonus won/played | Solves right | Board showing (mean) | Money left per solve | Invalid/game | Cost |
|---|---|---|---|---|---|---|---|---|---|---|
| Hybrid (Luna) | **45.3%** (40–51%) | 49/37/50% | $33,788 | $9,399 | 147/163 | 98% | 65% | $2,047 | 0 | $1.93 |
| Bot #1 | 26.7% (23–30%) | 25/23/32% | $22,812 | $6,687 | 84/96 | 93% | 66% | $1,877 | 0 | $0 |
| Bot #2 | 28.1% (25–31%) | 25/24/35% | $23,107 | $6,802 | 85/101 | 92% | 66% | $1,932 | 0 | $0 |

- Gaps: hybrid − bot #1 +18.6 (+10.0 to +27.2); hybrid − bot #2 +17.2 (+8.9 to +25.8); bot #1 − bot #2 −1.4 (−5.3 to +2.5).
- Rounds won per game: hybrid 1.74, each bot 1.13. Median bank per round won (rounds 1–3): hybrid $4,900–5,375, bots $4,900–6,550.
- 84% of the answers Luna gave the hybrid were right.

### 3b · Luna alone vs two bots

| Seat | Win rate (95%) | By seat 1/2/3 | Avg total | Total − bonus | Bonus won/played | Solves right | Board showing (mean) | Money left per solve | Invalid/game | Cost |
|---|---|---|---|---|---|---|---|---|---|---|
| Luna | **17.5%** (12–23%) | 17/12/23% | $11,728 | $4,409 | 58/63 | 72% | 51% | $4,615 | 1.02 | $1.33 |
| Bot #1 | 45.3% (41–50%) | 41/46/49% | $28,005 | $7,352 | 135/163 | 92% | 65% | $2,422 | 0 | $0 |
| Bot #2 | 37.2% (32–42%) | 32/38/42% | $24,087 | $6,726 | 112/134 | 91% | 65% | $2,419 | 0 | $0 |

- Gaps: Luna − bot #1 −27.8 (−36.4 to −18.9); Luna − bot #2 −19.7 (−28.3 to −10.3); bot #1 − bot #2 +8.1 (+0.6 to +15.8), the widest gap between identical bots, most likely chance.
- Rounds won per game 1.79; main-round winnings per round won about $2,460 (hybrid about $5,400, Sol about $4,270). Wrong solves per game 0.70 (hybrid 0.04, Sol 0.09).
- Luna's faults: 219 solves that didn't fit the board (already-called letters placed in hidden squares, refuted answers repeated, wild guesses on near-empty boards) and 150 bad tool calls, almost all a consonant called without spinning first.

### 3c · DeepSeek alone vs two bots

| Seat | Win rate (95%) | By seat 1/2/3 | Avg total | Total − bonus | Bonus won/played | Solves right | Board showing (mean) | Money left per solve | Invalid/game | Cost |
|---|---|---|---|---|---|---|---|---|---|---|
| DeepSeek | **36.7%** (31–43%) | 32/38/40% | $21,699 | $6,199 | 120/132 | 89% | 49% | $4,597 | 0.57 | $6.20 |
| Bot #1 | 31.1% (28–35%) | 22/32/40% | $26,767 | $6,100 | 98/112 | 89% | 63% | $2,475 | 0 | $0 |
| Bot #2 | 32.2% (28–36%) | 26/33/38% | $26,842 | $6,106 | 99/116 | 88% | 63% | $2,457 | 0 | $0 |

- Gaps: DeepSeek − bot #1 +5.6 (−3.6 to +15.3); DeepSeek − bot #2 +4.4 (−5.3 to +14.4); bot #1 − bot #2 −1.1 (−5.6 to +3.3). DeepSeek ties the bots.
- 2.12 rounds won a game at a median bank of $1,300; 0.27 wrong solves a game.

### 3d · Haiku alone vs two bots

| Seat | Win rate (95%) | By seat 1/2/3 | Avg total | Total − bonus | Bonus won/played | Solves right | Board showing (mean) | Money left per solve | Invalid/game | Cost |
|---|---|---|---|---|---|---|---|---|---|---|
| Haiku | **14.4%** (10–19%) | 12/13/18% | $8,954 | $4,370 | 36/52 | 95% | 72% | $2,510 | 0.29 | $2.61 |
| Bot #1 | 39.7% (35–44%) | 40/38/41% | $27,991 | $7,713 | 114/143 | 91% | 68% | $1,974 | 0 | $0 |
| Bot #2 | 45.8% (42–50%) | 46/42/49% | $28,799 | $8,257 | 136/165 | 91% | 66% | $2,192 | 0 | $0 |

- Gaps: Haiku − bot #1 −25.3 (−33.1 to −17.2); Haiku − bot #2 −31.4 (−38.3 to −23.6); bot #1 − bot #2 −6.1 (−13.3 to +1.1).
- 1.22 rounds won a game; 0.07 wrong solves a game.

### 3e · Hybrid (bot + DeepSeek) vs two bots: stopped

Stopped after 9 games, about $0.58: DeepSeek's board reads took a median 4 seconds but averaged 27 (some ran minutes), about 6.5 minutes a game, about 2.8¢ a game. Replaced by 3f.

### 3f · Hybrid (bot + Haiku) vs two bots

| Seat | Win rate (95%) | By seat 1/2/3 | Avg total | Total − bonus | Bonus won/played | Solves right | Board showing (mean) | Money left per solve | Invalid/game | Cost |
|---|---|---|---|---|---|---|---|---|---|---|
| Hybrid (Haiku) | **43.6%** (38–49%) | 37/46/48% | $31,323 | $8,851 | 133/157 | 95% | 65% | $1,997 | 0 | $4.76 |
| Bot #1 | 27.5% (24–31%) | 21/31/31% | $23,641 | $7,141 | 86/99 | 90% | 66% | $1,772 | 0 | $0 |
| Bot #2 | 28.9% (26–32%) | 25/28/33% | $24,001 | $7,320 | 88/104 | 91% | 67% | $1,779 | 0 | $0 |

- Gaps: hybrid − bot #1 +16.1 (+7.8 to +24.4); hybrid − bot #2 +14.7 (+6.9 to +22.5); bot #1 − bot #2 −1.4 (−4.7 to +1.9).
- 1.58 rounds won a game at a median bank of $4,750. Ran 2h34m.
- Haiku's trust curve was measured beforehand on 1,327 practice boards ($0.98): it says "solvable" rarely early and is right 85–100% of the time from 20% of the board.

### 6a · Bot vs two Lunas

| Seat | Win rate (95%) | By seat 1/2/3 | Avg total | Total − bonus | Bonus won/played | Solves right | Board showing (mean) | Money left per solve | Invalid/game | Cost |
|---|---|---|---|---|---|---|---|---|---|---|
| Bot | **50.3%** (43–57%) | 48/49/53% | $32,579 | $6,885 | 154/181 | 90% | 63% | $2,929 | 0 | $0 |
| Luna #1 | 25.6% (21–31%) | 24/22/30% | $13,096 | $3,776 | 74/92 | 70% | 48% | $5,436 | 0.94 | $1.26 |
| Luna #2 | 24.2% (20–28%) | 20/21/32% | $14,015 | $3,848 | 77/87 | 70% | 47% | $5,451 | 0.89 | $1.32 |

- Gaps: bot − Luna #1 +24.7 (+13.3 to +35.6); bot − Luna #2 +26.1 (+16.1 to +36.1); Luna #1 − Luna #2 +1.4 (−4.2 to +7.5).

### 6b · Bot vs two Haikus

| Seat | Win rate (95%) | By seat 1/2/3 | Avg total | Total − bonus | Bonus won/played | Solves right | Board showing (mean) | Money left per solve | Invalid/game | Cost |
|---|---|---|---|---|---|---|---|---|---|---|
| Bot | **56.4%** (50–62%) | 53/56/60% | $33,614 | $8,933 | 167/203 | 90% | 66% | $2,350 | 0 | $0 |
| Haiku #1 | 23.3% (19–28%) | 21/18/31% | $13,784 | $4,992 | 66/84 | 93% | 74% | $2,623 | 0.33 | $2.87 |
| Haiku #2 | 20.3% (16–25%) | 17/22/22% | $11,344 | $4,650 | 52/73 | 93% | 71% | $2,725 | 0.30 | $2.68 |

- Gaps: bot − Haiku #1 +33.1 (+22.5 to +42.8); bot − Haiku #2 +36.1 (+25.3 to +46.1); Haiku #1 − Haiku #2 +3.1 (−3.1 to +9.2).

### d1 · d1-ultra decision seat vs two bots

| Seat | Win rate (95%) | By seat 1/2/3 | Avg total | Total − bonus | Bonus won/played | Solves right | Board showing (mean) | Money left per solve | Invalid/game | Cost |
|---|---|---|---|---|---|---|---|---|---|---|
| d1-ultra seat | **4.2%** (2–7%) | 4/5/3% | $3,907 | $2,059 | 15/15 | 87% | 76% | $2,413 | 0.07 | $0.35 |
| Bot #1 | 46.9% (43–51%) | 42/45/53% | $32,706 | $9,317 | 139/169 | 91% | 68% | $1,948 | 0 | $0 |
| Bot #2 | 48.9% (45–53%) | 42/49/56% | $34,289 | $9,762 | 147/176 | 91% | 69% | $1,832 | 0 | $0 |

- Gaps: seat − bot #1 −42.8 (−47.8 to −37.5); seat − bot #2 −44.7 (−50.6 to −38.3); bot #1 − bot #2 −1.9 (−9.4 to +5.6).
- 243 solve attempts, 87% right, at a median 75% of the board, often for the $1,000 minimum.
- Turn moves per game: 9.04 spins, 1.77 vowels bought, 0.67 solves (0.59 right, 0.09 wrong); 0.90 Bankrupts.

### d2 · Luna Decisions seat vs two bots

| Seat | Win rate (95%) | By seat 1/2/3 | Avg total | Total − bonus | Bonus won/played | Solves right | Board showing (mean) | Money left per solve | Invalid/game | Cost |
|---|---|---|---|---|---|---|---|---|---|---|
| Luna Decisions seat | **8.1%** (4–12%) | 10/7/8% | $6,038 | $2,760 | 26/29 | 65% | 54% | $3,544 | 0.53 | $0.96 |
| Bot #1 | 45.3% (43–48%) | 42/47/48% | $33,395 | $8,048 | 134/163 | 90% | 64% | $2,248 | 0 | $0 |
| Bot #2 | 46.7% (44–49%) | 44/48/48% | $31,917 | $8,278 | 140/168 | 90% | 64% | $2,196 | 0 | $0 |

- Gaps: seat − bot #1 −37.2 (−42.8 to −31.4); seat − bot #2 −38.6 (−44.4 to −32.5); bot #1 − bot #2 −1.4 (−4.2 to +1.1).
- 695 solve attempts (1.93 a game), 65% right. Ran 1h07m.
- Turn moves per game, against Luna alone: spins 6.57 (5.74), vowels bought 0.08 (2.67), solves 1.93 (2.49; right 1.26 against 1.79, wrong 0.67 against 0.70), Bankrupts 0.74 (0.57).
- Consonants per game, against Luna alone: right 3.89 (4.08), missing 1.56 (0.75).

## Comparisons across lineups (set by set, 95%)

| Comparison | Gap |
|---|---|
| Hybrid (Luna) − Luna alone | **+27.8** (+20.8 to +34.7) |
| Hybrid (Haiku) − Haiku alone | **+29.2** (+22.2 to +36.1) |
| Hybrid (Haiku) − Hybrid (Luna) | −1.7 (−7.2 to +3.9) |
| Sol − Luna alone | +40.6 (+32.5 to +48.3) |
| Sol − Hybrid (Luna) | +12.8 (+5.6 to +20.0) |
| Sol − Hybrid (Haiku) | +14.4 (+8.6 to +20.0) |
| Sol − DeepSeek | +21 (+14 to +28) |
| Hybrid (Luna) − DeepSeek | +8.6 (+2.8 to +14.4) |
| Hybrid (Haiku) − DeepSeek | +6.9 (+0.3 to +13.6) |
| DeepSeek − Luna | +19 |
| DeepSeek − Haiku | +22 |
| Luna Decisions seat − Luna alone | −9.4 (−15.8 to −3.6) |
| Sol against two bots − Sol against DeepSeek and Haiku | −7.8 (−15.0 to −0.6) |

## Places, money, rounds, leads, and risk

Main-round money is the total before the bonus. "Led after R3 / held" is the share of games the player led on money after round 3, and how often it then finished first on main-round money; "trailed / came back" likewise. "Share of turns" is the share of all turns at the table the player held.

| Player | Avg place | 1st / 2nd / 3rd | Main-round $: median (mean, sd) | Best game | $0 games | Take-home median | Rounds won/game | Median bank per round won | Led after R3 / held | Trailed / came back | Bankrupts/game | Wrong solves/game | Vowels bought/game | Share of turns | $1M won |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Sol (lineup 1) | 1.47 | 66 / 21 / 13% | $7.5k ($8.4k, $5.8k) | $34.0k | 11% | $51.2k | 1.92 | $3,600 | 61% / 89% | 39% / 29% | 0.82 | 0.09 | 1.90 | 37.0% | 0 |
| DeepSeek (lineup 1) | 2.01 | 25 / 50 / 26% | $3.3k ($4.7k, $4.7k) | $28.6k | 15% | $3.3k | 1.54 | $1,800 | 27% / 66% | 73% / 10% | 0.66 | 0.19 | 2.00 | 30.9% | 0 |
| Haiku (lineup 1) | 2.52 | 9 / 29 / 62% | $0 ($2.6k, $4.5k) | $29.6k | 57% | $0 | 0.55 | $4,050 | 12% / 59% | 88% / 3% | 0.86 | 0.05 | 1.99 | 32.1% | 1 |
| Sol alone vs bots | **1.57** | 58 / 27 / 15% | $8.6k ($9.6k, $6.4k) | $27.9k | 9% | $49.6k | 2.26 | $3,400 | 53% / 89% | 47% / 23% | 0.92 | 0.09 | 2.21 | 38.5% | 0 |
| ↳ its bots, each | 2.21 | 21 / 37 / 42% | $3.2k ($5.4k, $6.5k) | $31.4k | 43% | $3.2k | 0.87 | $5,500 | 23% / 70% | 77% / 6% | 1.10 | 0.10 | 1.47 | 30.7% | 2 |
| Hybrid (Luna) vs bots | **1.81** | 45 / 28 / 27% | $9.2k ($9.4k, $7.3k) | $41.6k | 14% | $11.9k | 1.74 | $4,825 | 43% / 78% | 57% / 20% | 1.32 | 0.04 | 1.66 | 35.5% | 2 |
| ↳ its bots, each | 2.09 | 27 / 36 / 37% | $5.5k ($6.7k, $6.5k) | $31.4k | 28% | $5.5k | 1.13 | $5,300 | 28% / 66% | 72% / 12% | 1.33 | 0.09 | 1.80 | 32.2% | 4 |
| Hybrid (Haiku) vs bots | **1.85** | 44 / 28 / 29% | $7.8k ($8.9k, $7.4k) | $34.6k | 18% | $9.5k | 1.58 | $4,750 | 38% / 80% | 62% / 21% | 1.33 | 0.08 | 1.59 | 34.5% | 2 |
| ↳ its bots, each | 2.07 | 28 / 36 / 36% | $6.2k ($7.2k, $6.6k) | $33.5k | 24% | $6.4k | 1.21 | $5,300 | 31% / 64% | 69% / 12% | 1.36 | 0.12 | 1.82 | 32.8% | 4 |
| DeepSeek vs bots | **1.87** | 37 / 40 / 23% | $4.9k ($6.2k, $5.4k) | $31.1k | 8% | $5.5k | 2.12 | $1,300 | 32% / 81% | 68% / 16% | 0.73 | 0.27 | 2.27 | 31.4% | 0 |
| ↳ its bots, each | 2.07 | 32 / 30 / 38% | $4.5k ($6.1k, $7.2k) | $50.6k | 40% | $4.6k | 0.94 | $5,800 | 34% / 77% | 66% / 9% | 1.19 | 0.12 | 1.64 | 34.3% | 6 |
| Luna vs bots | **2.12** | 18 / 53 / 30% | $3.5k ($4.4k, $3.8k) | $17.8k | 8% | $3.5k | 1.79 | $1,300 | 18% / 62% | 81% / 7% | 0.60 | 0.70 | 2.67 | 28.8% | 0 |
| ↳ its bots, each | 1.94 | 41 / 24 / 35% | $5.8k ($7.0k, $7.5k) | $58.1k | 33% | $6.4k | 1.10 | $5,450 | 41% / 85% | 59% / 12% | 1.34 | 0.11 | 1.82 | 35.6% | 2 |
| Haiku vs bots | **2.33** | 14 / 38 / 47% | $3.0k ($4.4k, $4.9k) | $25.9k | 21% | $3.0k | 1.22 | $2,175 | 18% / 56% | 82% / 5% | 1.04 | 0.07 | 2.94 | 30.4% | 0 |
| ↳ its bots, each | 1.84 | 43 / 31 / 26% | $6.8k ($8.0k, $7.1k) | $50.6k | 21% | $8.6k | 1.39 | $4,900 | 41% / 79% | 59% / 18% | 1.46 | 0.14 | 2.11 | 34.8% | 3 |
| Luna Decisions seat vs bots | **2.42** | 8 / 42 / 50% | $2.0k ($2.8k, $3.1k) | $23.9k | 18% | $2.0k | 1.26 | $1,000 | 11% / 61% | 89% / 2% | 0.75 | 0.67 | 0.08 | 20.2% | 0 |
| ↳ its bots, each | 1.79 | 46 / 29 / 25% | $7.0k ($8.2k, $7.2k) | $43.4k | 22% | $10.0k | 1.37 | $5,000 | 45% / 84% | 55% / 15% | 1.51 | 0.15 | 2.52 | 39.9% | 5 |
| d1-ultra seat vs bots | **2.63** | 4 / 28 / 67% | $0 ($2.1k, $3.5k) | $27.4k | 52% | $0 | 0.59 | $1,825 | 9% / 42% | 91% / 1% | 0.94 | 0.09 | 1.81 | 24.1% | 0 |
| ↳ its bots, each | 1.68 | 48 / 36 / 16% | $8.4k ($9.5k, $7.7k) | $50.6k | 15% | $11.9k | 1.71 | $4,700 | 46% / 84% | 54% / 17% | 1.60 | 0.16 | 2.49 | 38.0% | 4 |
| Bot vs two Lunas | **1.82** | 50 / 18 / 32% | $5.3k ($6.9k, $7.4k) | $37.9k | 35% | $9.9k | 1.06 | $5,350 | 49% / 87% | 51% / 14% | 1.25 | 0.11 | 1.74 | 37.6% | 2 |
| ↳ the Lunas, each | 2.09 | 25 / 41 / 34% | $2.6k ($3.8k, $4.1k) | $21.0k | 22% | $2.8k | 1.47 | $1,650 | 25% / 75% | 75% / 7% | 0.62 | 0.62 | 2.62 | 31.2% | 0 |
| Bot vs two Haikus | **1.65** | 56 / 23 / 21% | $7.3k ($8.9k, $8.1k) | $49.8k | 19% | $16.5k | 1.56 | $4,900 | 53% / 87% | 47% / 21% | 1.61 | 0.16 | 2.46 | 37.7% | 1 |
| ↳ the Haikus, each | 2.18 | 22 / 39 / 40% | $2.7k ($4.8k, $5.9k) | $33.4k | 25% | $2.7k | 1.22 | $2,650 | 23% / 72% | 76% / 7% | 1.10 | 0.09 | 3.03 | 31.1% | 0 |

Average-place intervals (95%) for the solo players: Sol 1.48–1.67; Hybrid (Luna) 1.72–1.91; Hybrid (Haiku) 1.77–1.94; DeepSeek 1.76–1.98; Luna 2.03–2.21; Haiku 2.24–2.41; Luna Decisions seat 2.35–2.48; d1-ultra seat 2.56–2.70.

**The $1,000,000 envelope:** won 38 times in all; 37 by bots or hybrids (2–6 per lineup), once by an LLM (Haiku, in lineup 1, with no bots at the table). It needs the Million card held into the bonus round, which the bot values and keeps.

### Gaps between places, per lineup

Median gap in main-round money between neighbouring places, and the share of games won by under $1,000.

| Lineup | 1st − 2nd | 2nd − 3rd | Won by under $1,000 |
|---|---|---|---|
| 1 · Sol, DeepSeek, Haiku | $5.7k | $2.8k | 12% |
| 2 · Sol, bot, bot | $6.2k | $4.6k | 9% |
| 3 · Hybrid (Luna), bot, bot | $5.0k | $5.0k | 19% |
| 3b · Luna, bot, bot | $5.7k | $3.5k | 14% |
| 3c · DeepSeek, bot, bot | $5.5k | $3.9k | 14% |
| 3d · Haiku, bot, bot | $5.5k | $3.9k | 16% |
| 3f · Hybrid (Haiku), bot, bot | $5.2k | $5.0k | 18% |
| 6a · bot, Luna, Luna | $4.5k | $2.5k | 14% |
| 6b · bot, Haiku, Haiku | $6.6k | $2.6k | 12% |
| d1 · d1-ultra seat, bot, bot | $6.5k | $4.3k | 13% |
| d2 · Luna Decisions seat, bot, bot | $6.8k | $3.5k | 17% |

### Close games, turns, and round 4

| Player | Close games (within $1,000 of the leader or runner-up) | Share of turns | Won round 4 |
|---|---|---|---|
| Sol vs bots | 8% | 38.5% | 58% |
| Hybrid (Luna) | 13% | 35.5% | 43% |
| Hybrid (Haiku) | 14% | 34.5% | 42% |
| DeepSeek | 11% | 31.4% | 51% |
| Luna | 8% | 28.8% | 45% |
| Haiku | 7% | 30.4% | 30% |
| Luna Decisions seat | 7% | 20.2% | 29% |
| d1-ultra seat | 4% | 24.1% | 14% |
| Bot vs two Lunas | 9% | 37.6% | 26% |
| Bot vs two Haikus | 11% | 37.7% | 38% |

## Puzzle length

Share of solved main rounds won against two bots (a third is fair), by letters in the puzzle. Solved rounds per band in Sol's lineup: 192, 138, 312, 402, 396.

| Player | 16–17 | 18–19 | 20–22 | 23–26 | 27+ | 27+ minus 16–19 (95%) |
|---|---|---|---|---|---|---|
| Sol | 49% | 54% | 55% | 53% | 65% | **+13.7** (+4.1 to +23.9) |
| Hybrid (Luna) | 40% | 39% | 46% | 41% | 47% | +7.8 (−1.1 to +16.8) |
| Hybrid (Haiku) | 36% | 38% | 39% | 40% | 41% | +4.4 (−4.0 to +13.3) |
| DeepSeek | 51% | 51% | 52% | 51% | 58% | +7.2 (−3.5 to +17.8) |
| Luna | 44% | 43% | 46% | 41% | 49% | +5.4 (−7.4 to +18.6) |
| Haiku | 28% | 22% | 31% | 31% | 34% | +8.4 (−1.4 to +18.6) |
| Luna Decisions seat | 29% | 31% | 28% | 27% | 40% | +10.2 (−2.2 to +22.2) |
| d1-ultra seat | 15% | 12% | 12% | 13% | 20% | +6.1 (−1.6 to +13.8) |
| **All 8, averaged** | | | | | | **+7.9** (+0.3 to +15.6) |

Median board showing at the player's correct solves, by the same bands:

| Player | 16–17 | 18–19 | 20–22 | 23–26 | 27+ |
|---|---|---|---|---|---|
| The bots (all lineups) | 59% | 67% | 65% | 68% | 68% |
| Sol | 50% | 53% | 50% | 52% | 48% |
| DeepSeek | 47% | 47% | 45% | 48% | 50% |
| Luna | 53% | 53% | 55% | 48% | 50% |
| Haiku | 75% | 76% | 76% | 68% | 75% |
| Hybrid (Luna) | 62% | 67% | 65% | 62% | 69% |
| Hybrid (Haiku) | 62% | 65% | 65% | 64% | 67% |
| Luna Decisions seat | 59% | 56% | 52% | 48% | 53% |
| d1-ultra seat | 76% | 81% | 80% | 75% | 75% |

Caveats: long puzzles are more often phrases and titles, so part of this may be category; the 8 lineups share the same bots and puzzles.

## The bonus round

**Bonus test:** each player alone on every bonus puzzle of a deck, one solve each, no clock for the models (contestants get 10 seconds).

| Solved | Aired puzzles (100) | Grading deck (100) | Harder generated deck, prompt v7 (100) |
|---|---|---|---|
| Sol | 99% | 99% | 98% |
| DeepSeek | 90% | 95% | 89% |
| Haiku | 53% | 67% | 57% |
| Bot | 67% | 88% | 86% |
| Contestants (with the clock) | about 38% | | |

- The bot solved 79% of 500 other aired bonus puzzles. 32% of the grading deck's bonus answers are whole stock phrases in the bot's word data, against 12% of aired ones (Phrase category: 70% against 13%); the v7 deck has 12%.
- On the v7 deck, 34 of Haiku's 43 misses were answers that didn't fit the board, and Sol beat the bot by 12 points (+5 to +19); DeepSeek and the bot were even.
- Contestants' most common picks: C, M, D, A. The bot's: D, C, H, A, nearly every time.

**Memory probe:** one bonus solve per puzzle with almost nothing showing; aired against generated puzzles that no model can have seen (the v7 deck). 1,199 of 1,200 asks finished, $2.29.

| Solved | Blank board: aired | Blank board: generated | R S T L N E only: aired | R S T L N E only: generated | Gap with R S T L N E (95%) |
|---|---|---|---|---|---|
| Sol | 5% | 3% | 89% | 90% | −1 (−9 to +7) |
| DeepSeek | 4% | 5% | 72% | 67% | +5 (−8 to +18) |
| Haiku | 0% | 0% | 22% | 30% | −8 (−20 to +4) |

Thinking tokens on blank boards: Sol median 194 (max 952), Haiku 2,015 (max 10,017), DeepSeek 1,043 (max 54,171).

## Decision models: when they choose to solve (probe)

30 practice puzzles revealed one letter at a time (289 boards). At each step, each decision model was asked which move to make and, separately, whether the board was solvable; Luna tried one solve on every board.

| | First picks solve, on average (share of board) | P(solvable) at 60–69% of the board |
|---|---|---|
| Luna, the solver | can solve from 30%; right on every board at 60–69% | |
| Luna Decisions (index rank 15, score 48.5) | 31% | 0.56 |
| d1-ultra (index rank 1, score 65.2) | 86% (26 of 30 puzzles) | 0.17 |
| Jev 1.14 (index rank 5) | 90% (20 of 30 puzzles) | 0.35 |

In a one-set trial before the full run, d1-ultra never chose to solve.

## Bot versions (bot-only self-play)

| Check | Games | Result |
|---|---|---|
| Version 3 vs two version 1 bots | 2,004 | v3 43% (41–46%), v1 28% each: **+15 points** (+12 to +18). v1 was sure it had won in 473 games and lost 114; v3 was sure in 186 and lost 2. |
| Version 4 vs version 3 vs an eager version 3 | 2,004 (334 sets) | v4 37.8% (36.6–39.0%), v3 37.9% (36.7–39.1%), eager 24.3%: gap −0.05 points (−0.65 to +0.55). Adopted as no worse. |
| Round 4 start rule change | 100 self-play sets | no player's win rate moved more than a point |

Bot habits, measured in 40 bot-only games: it keeps spinning once it knows the answer (hitting Bankrupt in 16% of those rounds), solves only when nearly certain, flips every Mystery wedge, buys few vowels, and uses near-fixed bonus picks.

## Cost

| Player | Cost per game (one seat) |
|---|---|
| Luna | 0.4¢ |
| Haiku | 0.5¢ |
| Luna hybrid | 0.5¢ |
| Luna Decisions seat | 0.3¢ |
| d1-ultra seat | 0.1¢ |
| Haiku hybrid | 1.3¢ |
| DeepSeek | 1.4¢ |
| Sol (half-price tier) | 1.8¢ |
| DeepSeek hybrid (stopped) | about 2.8¢ |
| Gemini 3.8 Flash (half-price tier, one-set trial) | 6.9¢ |
| Gemini 4 Argon (half-price tier, one-set trial) | 9.6¢ |
| GLM 5.3 (trial, stopped) | about 8–12¢ |

- Sol writes about 880 output tokens a game, and 83% of its prompt is cached.
- Google caches only prompts of 4,096 tokens or more; a round's conversation starts at about 1,700. Flash also writes about 1,500 tokens a move.
- One-set trials (set 0, six games, alone against two bots): Argon won 5 of 6, Flash 5 of 6; on the same set Sol won 3, the Luna hybrid 3, Luna 2. One set is too small to rank anyone.
