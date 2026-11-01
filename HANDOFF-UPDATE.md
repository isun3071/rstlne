# rstlne: update since the briefing (2026-10-31 evening to 2026-11-01)

This update follows the briefing you already have and covers only what changed since. Where the two disagree, this one is newer.

## 1. New results

### Luna alone against two bots (60 sets)

| Against two bots | Luna alone | Hybrid (bot + Luna) | Sol alone |
|---|---|---|---|
| Win rate | **17.5%** (12–23%) | 45% | 58% |
| 1st / 2nd / 3rd | 63 / 196 / 101 | 163 / 105 / 92 | 209 / 99 / 52 |
| Rounds won per game | 1.79 | 1.74 | 2.26 |
| Main-round money per round won | about $2,460 | about $5,400 | about $4,270 |
| Wrong solves per game | 0.70 | 0.04 | 0.09 |
| Solves right | 72% | 97.5% | 96% |

- **Set-by-set gaps:**
  - hybrid − Luna alone **+27.8 points** (+20.8 to +34.7)
  - Sol − Luna alone +40.6 (+32.5 to +48.3)
  - Sol − hybrid +12.8 (+5.6 to +20.0)
- The hybrid recovers about two-thirds of the gap between Luna and Sol.
- Luna wins as many rounds as the hybrid, but cheap ones: it keeps losing the wheel, so its bank is small when it solves.

### Lineup 6a: the bot against two Lunas (60 sets)

The bot won **50%** (43–57%), the Lunas 26% and 24%. The bot leads each by about 25 points (13 to 36). The Lunas solve at 47–48% of the board and get 70% right.

### Lineup 3d: Haiku alone against two bots (60 sets)

Haiku won **14%** (10–19%), the bots 40% and 46%. Haiku is right 95% of the time but solves at 72% of the board, later than the bots, and wins only 1.22 rounds a game.

### The pattern

| Alone against two bots | Win rate | Solves right | Board showing at a solve | Wrong solves a game |
|---|---|---|---|---|
| Sol | 58% | 96% | 52% | 0.09 |
| Luna (reckless) | 17.5% | 72% | 51% | 0.70 |
| Haiku (passive) | 14% | 95% | 72% | 0.07 |

Opposite faults, the same poor result. Sol is the only model that is both early and right, and the only one that beats the bots.

### Why Luna loses: discipline, not reading or tools

- Luna does support tool calls; that was checked on OpenRouter.
- **219 solves that don't fit the board:**
  - **Ignoring called letters:** LUCKY for `L__KY`, when C was already showing elsewhere and so couldn't be hidden.
  - **Repeating refuted answers:** TAKING OUT A PICNIC BLANKET guessed, ruled wrong, then guessed again.
  - **Wild guesses on near-empty boards:** SUNRISE SUNSET TIMES for VINTAGE POCKET WATCH, with five letters showing.
- **150 bad tool calls,** almost all a consonant called without spinning first. Every tool is offered on every move to keep prompts cacheable (it halved costs), and the engine refuses illegal calls and reprompts. Strong models barely trip on this; it goes in the caveats.
- **Its reading is decent:** inside the hybrid, 84% of the answers it gave were right.

### Lineups 6b and 3c (added later the same evening)

- **The bot against two Haikus:** bot 56% (50–63%), Haikus 23% and 20%. The Haikus both wait (71–74% of the board), so the bot milks freely: $8,933 a game in main-round money.
- **DeepSeek alone against two bots: 37% (31–43%), a tie.** Its interval includes the 33% null. It's eager and mostly right: 2.12 rounds won a game (more than any model but Sol), at a median bank of only $1,300, 89% of solves right, 0.27 wrong solves a game. The bots' bigger banks balance its many small rounds.
- **The yardstick, each alone against two bots:**

  | Sol | Hybrid | DeepSeek | Luna | Haiku |
  |---|---|---|---|---|
  | 58% | 45% | 37% | 17.5% | 14% |

  Set by set, the hybrid beats DeepSeek by 8.6 points (+2.8 to +14.4).
- **Both formats agree.** Luna and Haiku lose to the bot by similar margins whether alone against two bots or as two copies against one bot. The copies of each model passed their A/A test.
- **The null:** if a model played like the bot, each seat would win a third. Win rate against that null shows whether a model is better or worse; the logs show why.

### Decision models (added later the same evening)

- **Decision seats now let the decision model decide when to solve** ("choice" mode, the default). Solve is one of the moves it can pick, and the solver (Luna) writes the answer when it does; no calibrated threshold. Ian wants decision models in the wild.
- **Artificial Analysis's Decision Index** (v1.0, October 2026) ranks 17 decision models on knowledge, hard multiple choice, tool-use choices, and safety classification. d1-ultra (Liquid AI) leads at 65.2. GPT-6 Luna Decisions, the old default here, is 15th at 48.5. Decisions cost $8–200 per million.
- **In a one-set trial, d1-ultra never chose to solve,** and won nothing.
- **A probe explained why** (30 tuning puzzles revealed letter by letter, 289 boards):

  | | First picks solve, on average |
  |---|---|
  | Luna, the solver | can solve from 30% of the board |
  | Luna Decisions | 31% |
  | d1-ultra | 86% |
  | Jev 1.14 | 90% |

  With 60–69% of the board showing, Luna solves every board, but d1-ultra rates it solvable at 0.17 and Jev at 0.35.
- **On this task the top decision models are strongly underconfident.** They seem to judge by their own reading, though the seat hands the solve to a better reader. Luna Decisions, from the solver's own family, picks solve about as often as Luna can succeed. A capability index's measured overconfidence didn't carry over to reading a board.
- **A d1-ultra lineup is running,** expected near 0%. A second, the bot against two d1-ultra seats, was skipped as predictable.
- **3e (the DeepSeek hybrid) is slow,** about 6.5 minutes a game. DeepSeek's board reads take a median 4 seconds but average 27 (some take minutes), and the server's CPU was saturated by the d1-ultra lineup. It costs about 2.8¢ a game, roughly $10 for the run.

### d1-ultra's full run, and finishing places (added later the same evening)

- **The d1-ultra decision seat alone against two bots: 4%** (2–7%), the weakest player tested, for 35¢ over 360 games. It did solve 243 times, 87% right, but late (median 75% of the board) and often for the $1,000 minimum.
- **Finishing places**, with 2.00 as par (contestants keep what they bank even if they miss the bonus, so place matters too). Alone against two bots:

  | | Average place | 1st / 2nd / 3rd |
  |---|---|---|
  | Sol | 1.57 | 58 / 27 / 15% |
  | Hybrid (Luna) | 1.81 | 45 / 28 / 27% |
  | DeepSeek | 1.87 | 37 / 40 / 23% |
  | Luna | 2.12 | 18 / 53 / 30% |
  | Haiku | 2.33 | 14 / 38 / 47% |
  | d1-ultra seat | 2.63 | 4 / 28 / 67% |

- **DeepSeek ties the bots on wins but beats them on place,** since it rarely finishes last. Luna is second 53% of the time, so its place is near par despite few wins. The bots are boom or bust: against two Lunas the bot won 50% and was last 32%. The LLMs' frequent small rounds buy consistency; the bot's milking buys big wins and big losses.
- **Run next, and since reported below:** the Haiku hybrid against two bots (Haiku's hybrid curves were measured first: it says "solvable" rarely early and is right 85–100% from 20% of the board) and a full run of the Luna Decisions seat.

### Money, margins, leads, and risk (added later the same evening)

- **Main-round money (before the bonus), median per game:**

  | Hybrid | Sol | Bot, against two Haikus | Bot, against two Lunas | DeepSeek | Luna | Haiku | d1-ultra seat |
  |---|---|---|---|---|---|---|---|
  | $9.2k | $8.6k | $7.3k | $5.3k | $4.9k | $3.5k | $3.0k | $0 |

  The bot banked nothing in 35% of its games against two Lunas, while the LLMs bank something in about 92% of games.
- **Take-home money is skewed** by $40k+ bonus wins: Sol's median take-home is $49.6k, everyone else's under $17k. Medians tell the truth here.
- **Leads hold:** a lead after round 3 holds 80–90% of the time for strong players. Sol comes back from behind 23% of the time, Luna 7%, and Haiku 5%.
- **Risk:** the bot-based players hit Bankrupt 1.25–1.61 times a game, from milking; the early solvers Luna (0.60) and DeepSeek (0.73) least.
- **Only bot-based players ever won the $1M envelope,** 2–6 times per lineup. No LLM did: the bot keeps the Million card into the bonus.
- **Gaps between places:** 1st to 2nd is typically $4.5–6.6k, 2nd to 3rd $2.5–5.0k; 9–19% of games are won by under $1,000.

### The Haiku hybrid and the Luna Decisions seat (2026-11-01)

- **The DeepSeek hybrid was stopped after 9 games.** DeepSeek's runaway thinking made it slow and costly: some board reads ran past 10,000 tokens, mostly on boards less than 40% revealed. The Haiku hybrid replaced it as the second lab.
- **The Haiku hybrid alone against two bots: 44%** (38–49%), the bots 28% and 29%. $4.76 for 360 games.

  | Set by set | Gap (95%) |
  |---|---|
  | **Haiku hybrid − Haiku alone** | **+29.2 (+22.2 to +36.1)** |
  | Haiku hybrid − Luna hybrid | −1.7 (−7.2 to +3.9), a tie |
  | Haiku hybrid − DeepSeek alone | +6.9 (+0.3 to +13.6) |
  | Haiku hybrid − Sol alone | −14.4 (−20.0 to −8.6) |

- **The hybrid's lift replicates on a second lab, and on the opposite fault.** Luna (OpenAI, reckless) gains 28 points and Haiku (Anthropic, passive) 29. The bot stops Luna guessing too early and makes Haiku act sooner.
- **The two hybrids tie** on wins, average place (1.81 and 1.85) and money. The bot's strategy sets the level; the reader only needs to be accurate. Inside the hybrid Haiku was right on 95% of solves, with no invalid moves.
- **The Luna Decisions seat alone against two bots: 8%** (4–12%), the bots 45% and 47%. 96¢ for 360 games. GPT-6 Luna Decisions made every move and chose when to solve; Luna wrote the answers.
  - **Worse than Luna alone:** −9.4 points set by set (−15.8 to −3.6).
  - **It solves as early as Luna and as often wrongly:** 1.9 attempts a game, 65% right, at 54% of the board; 0.67 wrong solves a game (Luna alone 0.70).
  - **And it plays the wheel worse:** it misses consonants twice as often as Luna (1.56 a game against 0.75), almost never buys a vowel (0.08 a game against 2.67), and holds only 20% of turns. Its median bank per round won is $1,000, the minimum.
- **Who decides, with the reader fixed** (alone against two bots):

  | Who decides | Luna reading | Haiku reading |
  |---|---|---|
  | A decision model | 8% (Luna Decisions), 4% (d1-ultra) | |
  | The model itself | 17.5% | 14% |
  | **The bot (the hybrid)** | **45%** | **44%** |

  The two decision models fail in opposite ways: d1-ultra solves too late, Luna Decisions too early and too often wrong. Neither matches the bot.
- **Memory probe: models don't remember aired bonus puzzles.** Sol, DeepSeek and Haiku each made one bonus solve on 100 aired and 100 generated bonus puzzles (the generated deck matches aired puzzles' share of stock phrases), first from a blank board, then with R S T L N E alone showing. $2.29.

  | Solved | Blank board: aired | Blank board: generated | R S T L N E only: aired | R S T L N E only: generated | Gap with R S T L N E (95%) |
  |---|---|---|---|---|---|
  | Sol | 5% | 3% | 89% | 90% | −1 (−9 to +7) |
  | DeepSeek | 4% | 5% | 72% | 67% | +5 (−8 to +18) |
  | Haiku | 0% | 0% | 22% | 30% | −8 (−20 to +4) |

  From a blank board nobody recalls aired answers; with R S T L N E, aired and generated puzzles score alike. The bonus-round caveat narrows to the missing clock. Sol solves about 90% with only R S T L N E showing, before any picks.
- **Ian has called the project done** after this: every planned lineup ran except the bot against two DeepSeeks.
- **The full order, alone against two bots, by average place:**

  | Sol | Hybrid (Luna) | Hybrid (Haiku) | DeepSeek | Luna | Haiku | Luna Decisions seat | d1-ultra seat |
  |---|---|---|---|---|---|---|---|
  | 1.57 | 1.81 | 1.85 | 1.87 | 2.12 | 2.33 | 2.42 | 2.63 |

## 2. Corrections to the briefing

- **The hybrid is a division of labour, not a verification wrapper.** The bot makes every decision (money, letters, risk, and when to solve); Luna only reads the board. Checking answers for fit is one part of it. The parts weren't measured separately, so the lift belongs to the whole split: "the LLM reads, the bot decides". The chess "centaur" comparison fits.
- **The bonus round doesn't decide who wins.** Only the leader after round 4 plays it, so a solve or a miss leaves the winner unchanged. Bonus rates inflate average totals but aren't a reason anyone wins. Main-round money ("total minus bonus") is the money figure that tracks win rate, and tournament output now prints it.
- **The two bots are deterministic,** with sampling seeded from the board, so the same position gives the same move. Sol can't exploit that, because it has no memory across games. But two bots at one table are one program twice: they hold back on the same boards and are equally patient, which is part of why Sol takes rounds from them.
- **DeepSeek V4.1 Flash "1017"** is the October 17, 2026 snapshot of V4.1 Flash, not a different model. Every DeepSeek game and its hybrid curves used that one fixed snapshot. Name it that way in the write-up.

## 3. Plan changes

- **Lineup 6 changed opponents.** One Sol beat two bots 58% to 21% each, so the bot against two Sols would be a massive underdog, in betting terms a long shot likely winning 10% or less. That's a predictable result for about $12. Lineup 6 keeps its format (the bot against two copies of one model) but against weaker pairs: two Lunas (done), two Haikus, two DeepSeeks. Each mirrors that model's solo run. The two-Sols version is optional.
- **Spreading across labs.** After lineup 1, every LLM seat was OpenAI's. To keep this from being a study of one lab:
  - **Solo yardsticks** (a model alone against two bots) for DeepSeek and Haiku.
  - **A second lab's hybrid,** to test whether the hybrid's lift holds beyond OpenAI. DeepSeek's was stopped for cost and speed; Haiku's ran instead.
- **Remaining today:**
  1. The bot against two Haikus, and DeepSeek alone (done)
  2. The DeepSeek hybrid (stopped; the Haiku hybrid ran instead), and the bot against two DeepSeeks (undecided)
- **Skipped for now:** lineups 4 (Sol, hybrid, bot) and 5 (Sol, two hybrids). They'd show the hybrid against Sol face to face, and whether the bot's strategy speeds up against a fast opponent. That's a natural follow-up, not needed for the main story.
- **Bot version 5 won't change the grid.** Every game records its bot version, and the grid stays on version 4. A future version would be checked against v4 in bot-only play first, and only the lineups where the bot's strength matters would be rerun, reported as an update. Probably not worth it before the write-up.

## 4. Pricier models wait for a grant

- **One-set trials** (alone against two bots, the same first set every lineup plays):

  | Model | Games won (of 6) | Cost per game |
  |---|---|---|
  | Gemini 4 Argon (Google's flagship, half-price tier) | 5 | 9.6¢ |
  | Gemini 3.8 Flash (half-price tier) | 5 | 6.9¢ |
  | Sol | 3 | 1.8¢ |
  | The hybrid | 3 | |
  | Luna | 2 | |

  One set is far too small to rank anyone, but it hints that other frontier models have both reading and discipline.
- **GLM 5.3 was stopped:** about 8–12¢ a game, and very slow on its host. It would also be a disclosed exception to the rule that puzzle labs don't play, since Z.ai's older GLM 4.7 judged the puzzles. MiniMax, which wrote them, never plays.
- **Why Google costs about five times Sol here:**
  - Gemini caches only prompts of 4,096 tokens or more, and each round's conversation starts at about 1,700.
  - Flash also writes about 1,500 tokens a move.
  - Padding prompts for one model would break the same-prompt-for-everyone rule, so the cost stands.
- **Sol is the rare model with expensive tokens and very few of them:** about 880 output tokens a game, 83% of its prompt cached. Lesson of the day, in Ian's words: cheap tokens don't make a cheap game. Cost per game, or per win, says more than price per token.
- **Cheaper routes considered:**
  - **Research credits:** OpenAI's Researcher Access Program offers up to $1,000, and the behaviour framing fits.
  - **Batch APIs:** half price, but only usable for the two-call bonus test, not live games.
  - **Free tiers:** avoided for scored runs, since prompts may be used for training and would leak the puzzles.
  - **Self-hosting:** not cheaper at this scale.
- **Sonnet 5.5, Opus 5.5 and Fable 5.1** were priced (Sonnet's list price equals Sol's), but Ian deferred all of them.

## 5. Framing and related work

- **Capability against behaviour.** Artificial Analysis already ranks capability; its index is now v5.0, nine tests in four equal categories. This project doesn't rank models. It shows how they behave when a wrong answer costs them, which an index can't.
- **Related work:**
  - **Why benchmarks breed bluffing:** "Why Language Models Hallucinate" (Kalai et al., OpenAI, 2025) argues that accuracy-only scoring rewards guessing, and that scoreboards should penalize confident errors.
  - **Abstention:** AbstentionBench (NeurIPS 2025) found reasoning fine-tuning makes abstention worse.
  - **Games:** GTBench and BALROG use LLMs in games; Avalon and Werewolf benchmarks test deception, but their scoring tangles reasoning with persuasion.
  - **Risk:** risk-preference studies ask models about hypothetical gambles.
- **What's distinctive here:**
  - Guessing wrong and waiting too long both cost you, and opponents set the price.
  - Evidence arrives letter by letter.
  - Behaviour is revealed in play, not stated.
  - The same model alone and inside the hybrid measures what the split adds.
  - Scoring is clean and duplicate-scored.

  Say "to our knowledge"; it wasn't a full literature review.
- **Contribution sentence:**

  > Wheel of Fortune is a natural instance of a scoreboard that penalizes both confident errors and hesitation. Models show distinct temperaments (reckless, passive, early and right), and letting a model read while a calculating bot decides recovers about two-thirds of the gap between a weak model and a strong one.

- **Cognitive offloading** is real but the evidence is early: one correlational survey (Gerlich, 2025) and one small preprint (MIT's "Your Brain on ChatGPT", 54 people). The project measures what you'd be trusting when you offload, not offloading itself.
- **The poker parallel:** Libratus (2017) and Pluribus (2019) beat professionals, and their makers projected uses in negotiation and security that stayed mostly hypothetical. Keep real-world claims modest. The champions were classical game-theory systems, like our bot.
- **Wheel of Fortune as a testbed:** good for behaviour under consequences and for measuring the split. Weaker for ranking frontier models, which hit a ceiling on reading. Artificial Analysis covers that.
- **No prompt engineering, as a rule (Ian).** "LLMs in the wild" get the rules and nothing else; every gain comes from code around the model, never from coaching.

## 6. What's next

1. **Done:** every planned lineup except the bot against two DeepSeeks, which is undecided. Next is the full write-up of results.
2. **Optional, later:**
   - lineups 4 and 5
   - the Sol-against-bots lineup rerun with version 3 bots (does v4 help against LLMs?)
3. **When there's a grant:** the frontier models, starting with Gemini 4 Argon.
4. **Later:** bot version 5 (probably skipped), a tighter near-repeat check in puzzle generation, and the write-up.
