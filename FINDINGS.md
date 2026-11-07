# Findings

Ian grew up watching *Wheel of Fortune* at dinner. When large language models arrived, he wondered whether one could play his childhood game show, how well, and whether we could build something that plays better. rstlne is a full Wheel of Fortune engine where language models, a hand-built bot, and mixes of the two play at the same table. This is the short version; the paper has the method and the detail.

Every result here is from bot v6 on the grading-606b deck: 400 main-round puzzles in four round chunks, each matched to aired rounds 1 to 4 in category and length, and 100 bonus puzzles. MiniMax M3 wrote the puzzles and GLM 5.3 Flash judged them, so none can be in a model's training data. Each lineup played 60 sets of 6 games, one per seating order, on seed 707. A set replays the same puzzles and spins in every seating, so lineups compare set by set, and intervals are 95% from resampling whole sets. That's 14 lineups and 5,040 games for $44.67 in API calls. Every number below comes from `paper/numbers.json`, built by `python -m rstlne.analysis.numbers`.

## Can LLMs play it?

Yes. Every model finished every game through tool calls. The engine refuses an illegal move, such as a consonant called without a spin or an answer that doesn't fit the board, and asks again.

## How well do they play?

One model sat alone against two copies of the bot. A player as good as the bot would win a third of the games.

![Each player alone against two bots](figures/1-alone-against-two-bots.png)

| Alone against two bots | Wins | Solves right | Board showing at a right solve (median) |
|---|---|---|---|
| GPT-6.1 Sol | 46.1% (40.3–51.9) | 97% | 50% |
| GPT-6.1 Terra | 45.3% (38.9–51.9) | 94% | 48% |
| DeepSeek V4.1 Flash | 23.6% (18.9–28.6) | 87% | 45% |
| Qwen 3.8 Flash | 16.4% (12.5–20.3) | 85% | 65% |
| GPT-6 Luna | 14.4% (10.0–19.2) | 71% | 48% |
| Claude Haiku 5.5 | 7.5% (5.0–10.3) | 93% | 70% |

Sol and Terra tie (Terra minus Sol, set by set: −0.8 points, −6.9 to +5.0), and they're the only models above a third. What sets them apart is being early and right at once. DeepSeek and Luna solve as early but are wrong more often: Luna makes 0.64 wrong solves a game to Sol's 0.07. Haiku and Qwen are mostly right but wait until about two-thirds of the board shows, and by then a bot usually has the round.

Sol and Terra also win on boards the bot reads badly. Of the rounds they won, 60% were on boards where the bot's reader had the wrong answer or wasn't sure of the right one. Their consonants hit 94% of the time, where the bot's reader expected 84–85% for the same letters, and they took the reader's top pick only 63–64% of the time.

## Can we do better?

Yes. In a hybrid the bot makes every move and, on its turns, asks a model whether it can solve the board and what the answer is. The bot handles the money, the risk, and when to solve; the model only reads.

| | Wins alone | Wins as a hybrid | Gain, set by set |
|---|---|---|---|
| Luna | 14.4% | 40.6% | +26.1 points (+19.2 to +32.8) |
| Haiku | 7.5% | 36.1% | +28.6 points (+23.3 to +33.9) |

The lift works on two labs' models with opposite faults: the bot stops Luna from guessing early and makes Haiku act sooner. Sol alone still wins 5.6 points more than the Luna hybrid, an interval that crosses zero (−1.1 to +12.5).

Handing every choice to a decision model makes play worse. With Luna writing every answer, the Luna Decisions seat won 3.9% and the d1-ultra seat 1.9%. The Luna Decisions seat is 10.6 points (5.8 to 15.6) below Luna playing alone. Its consonants hit 68% and d1-ultra's 71%, where always calling the most common open consonant (T, N, S, H, R…) would have hit 74–79% on the same boards. Against two copies of one player the bot won 58.6% against Lunas, 65.8% against Haikus, 83.3% against Luna Decisions seats, and 88.3% against d1-ultra seats.

## How would human contestants fare?

There were no human players, so the bonus round is the comparison: contestants solve about 38% of aired bonus puzzles with a 10-second clock. Alone on grading-606b's 100 bonus puzzles, with no clock, Sol solved 100, Terra 98, DeepSeek 92, Luna 79, Qwen 3.8 Flash 74, and Haiku 57. The bot solved 95 and the hybrids, which make the bot's letter picks, 99 (Luna) and 97 (Haiku).

![The bonus round, alone](figures/6-bonus-test.png)

Memory doesn't explain these rates. In a probe on the earlier decks, Sol, DeepSeek and Haiku solved no more than 5% of aired or generated bonus puzzles from a blank board, and with R S T L N E alone the two decks scored the same.

## Cost

Token price predicts little. Per game for one model seat, Luna cost 0.3¢, Haiku 0.6¢, Terra 0.9¢ and DeepSeek 1.4¢. Sol cost 1.6¢ on OpenAI's half-price flex tier, even at $5 per million output tokens. Qwen 3.8 Flash costs $0.47 per million output tokens and was the dearest, at 2.9¢ a game with 1 game in 10 above 5.7¢, because some of its moves think for thousands of tokens.

![Cost per game](figures/5-cost-per-game.png)

## Charts

All are in [figures/](figures/), drawn from the game logs.

| Chart | Shows |
|---|---|
| [1](figures/1-alone-against-two-bots.png) | Win rate of each player alone against two bots |
| [2](figures/2-temperament.png) | How early each player solves, and how often it's right |
| [3](figures/3-every-lineup.png) | Who won each lineup |
| [4](figures/4-rounds-and-banks.png) | Rounds won, and money per round won |
| [5](figures/5-cost-per-game.png) | Cost per game |
| [6](figures/6-bonus-test.png) | The bonus round, alone |
| [7](figures/7-finishing-places.png) | Finishing places |
| [8](figures/8-money-spread.png) | Money banked, game to game |
| [9](figures/9-gaps-between-places.png) | Gaps between places |
| [10](figures/10-leads-and-comebacks.png) | Holding a lead, and coming back |
| [11](figures/11-risk.png) | Bankrupts and wrong solves |
| [12](figures/12-puzzle-length.png) | Puzzle length: how much board each needs, and each player's gain on long puzzles |

The rules, the bot and the hybrid are specified in [documentation.md](documentation.md), and [README.md](README.md) covers setup and commands.
