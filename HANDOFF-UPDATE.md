# rstlne: update since the briefing (2026-10-31, evening)

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

## 2. Corrections to the briefing

- **The hybrid is a division of labour, not a verification wrapper.** The bot makes every decision (money, letters, risk, and when to solve); Luna only reads the board. Checking answers for fit is one part of it. The parts weren't measured separately, so the lift belongs to the whole split: "the LLM reads, the bot decides". The chess "centaur" comparison fits.
- **The bonus round doesn't decide who wins.** Only the leader after round 4 plays it, so a solve or a miss leaves the winner unchanged. Bonus rates inflate average totals but aren't a reason anyone wins. Main-round money ("total minus bonus") is the money figure that tracks win rate, and tournament output now prints it.
- **The two bots are deterministic,** with sampling seeded from the board, so the same position gives the same move. Sol can't exploit that, because it has no memory across games. But two bots at one table are one program twice: they hold back on the same boards and are equally patient, which is part of why Sol takes rounds from them.
- **DeepSeek V4.1 Flash "1017"** is the October 17, 2026 snapshot of V4.1 Flash, not a different model. Every DeepSeek game and its hybrid curves used that one fixed snapshot. Name it that way in the write-up.

## 3. Plan changes

- **Lineup 6 changed opponents.** One Sol beat two bots 58% to 21% each, so the bot against two Sols would be a massive underdog, in betting terms a long shot likely winning 10% or less. That's a predictable result for about $12. Lineup 6 keeps its format (the bot against two copies of one model) but against weaker pairs: two Lunas (done), two Haikus, two DeepSeeks. Each mirrors that model's solo run. The two-Sols version is optional.
- **Spreading across labs.** After lineup 1, every LLM seat was OpenAI's. To keep this from being a study of one lab:
  - **Solo yardsticks** (a model alone against two bots) for DeepSeek and Haiku.
  - **A DeepSeek hybrid,** to test whether the hybrid's lift holds on a second lab.
- **Remaining today:**
  1. The bot against two Haikus, and DeepSeek alone (done)
  2. The DeepSeek hybrid, and the bot against two DeepSeeks

  About $22 in all. Ian plans to stop the day after these.
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

1. The four remaining runs today, then a full grid write-up of results.
2. **Optional, later:**
   - lineups 4 and 5
   - the Sol-against-bots lineup rerun with version 3 bots (does v4 help against LLMs?)
   - a blank-board memory probe on aired bonus puzzles (about $1)
3. **When there's a grant:** the frontier models, starting with Gemini 4 Argon.
4. **Later:** bot version 5 (probably skipped), a tighter near-repeat check in puzzle generation, and the write-up.
