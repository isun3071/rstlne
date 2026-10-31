# What we can claim (2026-10-31)

All lineups use one deck of 400 main and 100 bonus generated puzzles, one seed, 60 sets (360 games each), duplicate scoring (every seating order on the same spins and puzzles), and bot version 4. Intervals are 95%, from resampling whole sets. "Against two bots" means one seat against two identical bots. A fair share at a three-seat table is 33%.

## Strong: well supported

1. **LLMs can play the whole game.** Every model played complete, legal games through tool calls. Invalid moves ranged from 0.02–0.03 a game (Sol) to about 1 a game (Luna); the engine refuses and reprompts, so none corrupt a game.

2. **The best LLM beats the bot clearly.** GPT-6.1 Sol alone against two bots won 58% (51–64%) to their 21% each, leading each by 37–38 points (27 to 47).

3. **Weaker LLMs lose to the bot, alone or in pairs.**
   - Luna alone: 17.5% (12–23%).
   - Haiku alone: 14% (10–19%).
   - The bot against two Lunas: 50% (43–57%), leading each by about 25 points (13 to 36).

4. **Models fail in opposite ways and land in the same place.** Being early and being right are both needed; only Sol has both.

   | Alone against two bots | Win rate | Solves right | Board showing at a solve | Wrong solves a game |
   |---|---|---|---|---|
   | Sol | 58% | 96% | 52% | 0.09 |
   | Luna (reckless) | 17.5% | 72% | 51% | 0.70 |
   | Haiku (passive) | 14% | 95% | 72% | 0.07 |

5. **Letting the LLM read and the bot decide lifts a weak model a lot.** The hybrid (the bot makes every move and decides when to solve; Luna only reads the board) won 45% against two bots. Luna alone won 17.5%. Set by set, that's +27.8 points (+20.8 to +34.7), about two-thirds of the 40.6-point gap between Luna and Sol.

6. **A strong reader still beats a weak reader with good strategy.** Set by set against the same bots, Sol alone beat the hybrid by 12.8 points (+5.6 to +20.0).

7. **Two bots are tougher opponents for Sol than two mid-tier LLMs.** Sol won 66% (61–70%) against DeepSeek and Haiku, and 58% against two bots: −7.8 points set by set (−15.0 to −0.6). The bots win fewer rounds but bank about 1.6 times as much per round won.

8. **Luna's losses are discipline, not reading or tool support.**
   - 219 of its solves didn't fit the board: an already-called letter put in a hidden square, a refuted answer repeated, wild guesses on near-empty boards.
   - 150 bad tool calls, almost all a consonant called without spinning first.
   - Its reading is decent: 84% of the answers it gave the hybrid were right, and it won 58 of 63 bonus rounds.

9. **The bot's money strategy matters.** Version 3, which changed only how the bot values an opponent taking the round, beat version 1 by 15 points (+12 to +18) in 2,004 bot games.

10. **Cheap tokens aren't a cheap game.** Cost per game depends on verbosity and caching as much as on token price. In a matching one-set trial, Gemini 3.8 Flash's cheaper tokens cost about four times as much per game as Sol.

    | Model | Cost per game |
    |---|---|
    | Luna | 0.4¢ |
    | Haiku | 0.5¢ |
    | DeepSeek | 1.4¢ |
    | Sol (half-price tier) | 1.8¢ |
    | Gemini 3.8 Flash (half-price tier) | 6.9¢ |
    | Gemini 4 Argon (half-price tier) | 9.6¢ |

## Moderate: supported, with caveats

11. **The bot loses rounds to Sol mostly by reading late, not by milking.** In rounds Sol took, the bot already knew the answer only 3% of the time. Of the ~15-point gap in solve timing, about 4 points is milking and about 10 slower reading. *Caveat: one lineup.*

12. **LLMs beat contestants' bonus rate by a wide margin.** On 100 aired bonus puzzles:

    | Sol | DeepSeek | Haiku | Bot | Contestants |
    |---|---|---|---|---|
    | 99% | 90% | 53% | 67% | about 38% |

    *Caveats: no 10-second clock, and models may remember aired puzzles (untested).*

13. **The bot plays unlike a person; LLMs play more like contestants.** The bot:
    - keeps spinning once it knows the answer, hitting Bankrupt in 16% of those rounds
    - solves only when nearly certain
    - flips every Mystery wedge
    - buys few vowels
    - uses near-fixed bonus picks (D, C, H, A)

    *Caveat: the bot's habits were measured in 40 bot-only games.*

14. **Our generated bonus puzzles can be made as hard as aired ones for LLMs, but not for the bot.** After a prompt change, DeepSeek and Haiku scored near their aired rates while the bot barely moved. What makes a puzzle hard differs between a word-list reader and an LLM.

## Pending: wait for the remaining runs

- DeepSeek alone against two bots (the solo yardstick on a third lab).
- **The DeepSeek hybrid.** Does the reading-and-deciding split lift a second lab's model too? Until it's in, claim 5 is shown for one model.
- The bot against two Haikus and against two DeepSeeks.

## Don't claim

- **"LLMs are superhuman at the bonus round."** No clock, possible memory. Say "far above contestants' rate, without the clock."
- **"Frontier models generally have both reading and discipline."** Only Sol was fully tested. Two Gemini models each won 5 of 6 in one trial set: a hint, not evidence.
- **"A verification wrapper explains the lift."** The hybrid hands the bot all decisions, of which checking answers is only one part; the parts weren't separated.
- **"Bot v4 is better than v3 against LLMs."** It tied v3 in bot-only play and was adopted as no worse. The test against LLMs wasn't run.
- **"The bot would lose to two Sols."** It's a reasonable inference from lineup 2, but it wasn't run.
- **Broad real-world implications.** This is one game, with our rules (deliberately different from the show in places), one deck of generated puzzles, and one bot design. Lessons like "models can understand a problem and still break its rules" are illustrations, not general laws.
- **Strategy advice for contestants, as proven.** Flip the Mystery, ride the Express only when sure: these are simulation results under our rules.

## How to frame the contribution

> Recent work argues that benchmarks reward guessing and should penalize confident errors (Kalai et al., 2025). Wheel of Fortune is a natural instance of such a scoreboard, where guessing wrong and waiting too long both cost you, and opponents set the price. Here models show distinct temperaments (one guesses recklessly, one waits too long, one gets it right), and letting a model read while a calculating bot decides recovers about two-thirds of the gap between a weak model and a strong one. We don't rank models; capability indices do that. We watch how they behave when a wrong answer costs them.
