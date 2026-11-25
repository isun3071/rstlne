# rstlne: where the project stands (2026-10-31)

This briefing is complete in itself. It describes Ian's project, a Wheel of Fortune engine where language models, a hand-built bot, and hybrids play at the same table. It covers the rules as built, how the bot plays, every result so far, the decisions made, and what's next. Ian runs the code himself, and this conversation is for thinking, analysis, and writing.

## 1. The project

Ian watched Wheel of Fortune at dinner as a kid and wondered whether a machine could play it. The project and any write-up are framed around four questions:

1. Can LLMs play Wheel of Fortune?
2. How good are they?
3. Can we do better, with a purpose-built bot or a hybrid?
4. How would human contestants fare? LLMs stand in as the closest available surrogate for contestants, checked against real contestant data where it exists (bonus solve rates, letter picks).

One engine has two uses. Ian plays against models in the terminal for fun, and the same engine runs seeded, model-only tournaments that measure letter choice, risk, and solve timing.

The name, rstlne, comes from R S T L N E, the letters the bonus round gives every player.

## 2. Ian's standing preferences

- Game rules come from Ian. When a rule is unspecified, ask him with a concrete play-by-play example ("Haiku solves round 3, Sol solves round 4: who starts round 5?"). Never invent a rule.
- Some departures from the show are deliberate, so don't "correct" them: the special wedges' positions, the Million wedge sitting on an $800 wedge with a $500 centre, Free Play kept (the show retired it in 2021), the bonus envelope counts, seeded tiebreaks, one solve response with no clock for models (humans get 10 seconds), the round 4 start rule, and no toss-ups.
- Aired show puzzles are never published. Puzzles used for scoring are never used to tune or fit anything.
- Prompts to models give the rules and no strategy coaching. Odd play is measured and left alone.
- The hybrid uses a weaker model on purpose (see section 9).
- No runs with Sonnet or Gemini for now.
- Write-ups use the dinner-table origin and the four questions. Ian declined a draft write-up for now.

## 3. The game as built

### The wheel

24 equal wedges, each split into three thirds, so a spin lands on one of 72 equally likely thirds. Clockwise from wedge 1:

| # | Wedge | # | Wedge | # | Wedge |
|---|---|---|---|---|---|
| 1 | Top value | 9 | $800 | 17 | $700 |
| 2 | $800 | 10 | $600 | 18 | Lose a Turn |
| 3 | $600 | 11 | $550 | 19 | $800 |
| 4 | $700 | 12 | $500 | 20 | $500 |
| 5 | $600 | 13 | $600 | 21 | $650 |
| 6 | $650 | 14 | Bankrupt | 22 | $500 |
| 7 | $500 | 15 | $650 | 23 | $900 |
| 8 | $700 | 16 | Free Play | 24 | Bankrupt |

Special wedges cover the base wedge, round by round:

| Round | Top value | Wild Card | Million wedge | Mystery | Express |
|---|---|---|---|---|---|
| 1 | $2,500 | wedge 2 | wedge 9 | | |
| 2 | $3,500 | wedge 2 | wedge 9 | wedges 5 and 17 | |
| 3 | $3,500 | wedge 2 | wedge 9 | | wedge 12 |
| 4 and later | $5,000 | | | | |

- Wild Card (wedge 2): a correct consonant there earns $800 and the card. After any later correct consonant on a plain dollar wedge, the holder may spend it to call one extra consonant at the same value. Unspent, it gives a fourth consonant in the bonus round. It's on the wheel only while no one holds it.
- Million wedge (wedge 9): outer thirds are Bankrupt, the centre third plays $500. A correct consonant on the centre takes the Million card, kept only by solving that round. In the bonus round it turns the $100,000 envelope into $1,000,000.
- Mystery (round 2): $1,000 a copy. After a correct consonant: keep the money, or flip. One Mystery hides $10,000, the other Bankrupt, decided by a seeded draw.
- Express (round 3): $1,000 a copy. After a correct consonant: pass, or ride (call consonants at $1,000 a copy, buy vowels at $250, no spinning, until you solve). Any miss or wrong solve while riding is Bankrupt.
- Free Play (wedge 16): call any letter. Consonants earn $500 a copy, vowels are free, and a miss keeps the turn.
- Bankrupt zeroes the round bank and takes held cards. Lose a Turn passes the turn.

| Round | Bankrupt odds | Average dollar wedge, per copy | Average per spin (non-dollar spins as $0) |
|---|---|---|---|
| 1 | 1 in 9 | $721 | $611 |
| 2 | 1 in 9 | $805 | $682 |
| 3 | 1 in 9 | $795 | $674 |
| 4+ | 1 in 12 | $848 | $742 |

Round 4 is the richest and safest round.

### Turns and rounds

- A turn is one of three moves. Spin and call a consonant: a hit pays the wedge value times its copies and keeps the turn, and a miss or repeat passes it. Buy a vowel for $250, and a hit keeps the turn. Or solve, which needs an exact match of letters, word breaks and punctuation. A wrong solve passes the turn.
- Only the solver banks the round's money, and the others lose theirs. A solver banks at least $1,000.
- Seats 1, 2 and 3 start rounds 1, 2 and 3. From round 4 on, the seat that solved the previous round starts the next, and if nobody solved it, a seeded draw picks. (Before 2026-10-31, seat 1 also started round 4.)
- There are no toss-ups, on purpose. A toss-up is a pure recognition race, and the main rounds and the bonus test already measure recognition. A turn-based game has no real reaction time, only "which revealed letter did you answer on". And polling every model on every letter would cost more than the rest of the game.
- A round ends after 200 turns if nobody solves. A game is 4 main rounds, then the bonus round.

### Bonus round

The leader after round 4 plays alone (seeded draw on ties). R S T L N E are revealed, the player picks 3 consonants and a vowel (4 consonants with the Wild Card), then gets one solve. The envelope, drawn before the picks and hidden until after the solve, is one of 24: six each of $40,000, $45,000 and $50,000, five of $55,000, and one of $100,000 (or $1,000,000 with the Million card).

## 4. How tournaments are scored

- Scoring is duplicate, as in bridge. A set is 6 games: the same 4 main puzzles, bonus puzzle and wheel spins, played once for every ordering of the 3 players across the seats. Luck from the wheel and the seats largely cancels out.
- Win rate is the share of games finished first, ties split. A fair share at a three-seat table is 33%.
- Intervals come from resampling whole sets, since a set's games share puzzles and spins. All intervals quoted here are 95%.
- The whole grid uses one seed, so set 17 has the same spins and puzzles in every lineup. That lets two lineups be compared set by set with the luck held equal.
- Every lineup in the grid is 60 sets (360 games). If a comparison between two lineups is too close to call, both get extended to 100 sets together, so the extra sets still pair up.

## 5. The players

| Seat | Who makes the moves | Who writes the solve |
|---|---|---|
| LLM | the model, through tool calls | the model |
| Bot | the bot | the bot |
| Hybrid | the bot, with a model reading the board for it | the bot, often using the model's answer |
| Decision | a decision model choosing from probabilities | an LLM, when the decision model triggers a solve |
| Human | the player at the terminal | the player |

- An LLM seat gets the rules once, in the system prompt. Each turn it gets the public view (category, the board with spaces between letters and a compact pattern with word lengths, used letters, all banks, held cards, the wheel as it stands, legal moves) plus a recap of what opponents did. Moves are tool calls: spin, buy a vowel, solve, call a consonant, call a letter on Free Play, keep or flip, pass or play, use the Wild Card, bonus picks, bonus solve. History resets each round. Each model reasons at its own default. An invalid move gets two reprompts, then a safe default or a passed turn. A wrong solve that doesn't fit the board (wrong word lengths, a revealed letter changed) is counted separately as a "misfit".
- In the hybrid seat the bot makes every move. On each new board it acts on, it asks the model only "is this solvable, and if so, what's the answer?", with no money or score in the question. A fitting answer joins the bot's own candidate answers, weighted by a trust curve measured for that model on real game boards. The bot then decides what to do with it, including whether to keep milking the board. The hybrid uses GPT-6 Luna, a cheaper and weaker model.
- In the decision seat a decision model makes every choice and an LLM writes solves. An early trial found decision models pick letters by plain English frequency and lose the wheel about twice as often. It's likely a negative result and isn't in the grid.

The models in play are GPT-6.1 Sol (OpenAI, the strongest), GPT-6.1 Terra (OpenAI), GPT-6 Luna (OpenAI, cheap), DeepSeek V4.1 Flash, and Claude Haiku 5.5 (Anthropic). Xiaomi MiMo V2.6 Flash was dropped: about one call in four ran away into thousands of tokens of thinking, which timed games out and made it the costliest player.

## 6. How the bot plays

The bot is a calculator with a word list. No language model is involved.

### The reader

- It splits the board into word slots and samples whole candidate answers across them. Each slot can be a dictionary word (weighted by how common it is, how well it fits the category, and how often it follows the previous word in real text), a position inside a known phrase or name, or an unknown word.
- Category rules help: ING words for What Are You Doing?, rhymes for Rhyme Time, shared first letters for Same Letter, overlapping phrases for Before & After.
- From the samples it gets each letter's chance of appearing and its expected copies, the top answers with probabilities, and a confidence in the best answer, calibrated against how often that confidence has actually been right.
- Wrong solves by anyone rule that answer out for the round.
- Its word data is about 150,000 words, 406,000 phrases and names, and 1.8 million word pairs, drawn from word frequency lists, Wiktionary, Wikidata, a pronouncing dictionary and sentence collections, and never from show puzzle archives.
- It knows 99.7% of the words in aired bonus answers, so its weakness is ranking. The right answer is usually among its candidates, but something likelier-looking ranks higher, especially when the answer has a rare word or an unusual word pairing.

### One value function for every move

Every turn it scores spin, buy a vowel, and solve with one formula:

> value = immediate gain + chance it keeps the wheel × value of continuing + chance it loses the wheel × (1 − chance an opponent steals) × value of continuing later

- A spin is averaged over all 72 thirds as the wheel stands. A dollar third pays the best consonant's chance × value × expected copies.
- Buying a vowel is worth −$250 plus the information it gives.
- Solving is worth confidence × the payoff of banking, plus (1 − confidence) × the race carrying on. With no candidate answer, it never guesses.
- Steal odds for each opponent come from a curve on how much of the board shows and how readable the board looks. The curve starts from a prior fit on LLM play and updates during the game from what each seat actually does. Opponents act in turn order.
- It maximizes expected dollars in rounds 1 and 2, and from round 3 the chance of finishing first. Cards count at their value.
- A letter's information is valued in dollars (how much a letter raises its chance of solving first, times the round's value). On a dollar wedge it calls the consonant with the best money plus information.
- Once it's 95% sure of an answer, a small planning routine decides which consonants to call, how long to keep spinning, and when to solve. This is "milking" a known answer.
- It plays the Mystery by expected value and nearly always flips. It boards the Express only when it's sure, calling only near-certain consonants. It spends the Wild Card only when the extra consonant beats its bonus-round value, so it usually keeps it.
- In the bonus round it tries every legal pick set and chooses the one most likely to leave its best guess right, then solves with that guess. In practice it picks D, C, H and A almost every time.

### Versions

| Version | What changed | Result |
|---|---|---|
| 1 | win chance from a formula | baseline |
| 2 | win chance from a table built in self-play | tied version 1 |
| 3 | an opponent who takes the round is credited with what it adds before solving (the "stealer's gain", fit from LLM and bot play); evenly scored choices are decided by dollars (this fixed version 1's habit of calling B, C, D in alphabetical order once a game felt decided) | beat two version 1 bots 43% to 28% each (+15, +12 to +18), 2,004 games |
| 4, current | separate stealer's gain for LLM-like and bot-like opponents, mixed per opponent by a learned "how LLM-like does this seat play" weight | tied version 3: 37.8% to 37.9%, gap −0.05 points (−0.65 to +0.55), 2,004 bot-only games |

Version 4 was adopted on Ian's "no worse than version 3" bar. He set that bar after seeing the tie, and the original bar was "beats version 3". His reasoning was that version 4's case rests on LLM opponents, and bot-only games can't include one. In the grid, version 4 judged Sol strongly LLM-like (median 0.87) and the hybrid bot-like (0.31), so its LLM tables were in use against Sol. Whether that helps is untested. Rerunning the Sol-against-bots lineup with version 3 bots would show it.

### How it plays compared with people

From 40 bot-only games against the logs of the LLM players:

- The alphabetical openings are fixed. Version 1 opened round 4 with B in 218 games, and version 4 opens with T, N, R like everyone else.
- Still inhuman:
  - It keeps spinning once it knows. It reaches 95% in about 1.5 rounds a game, then calls a median of one more consonant, hitting Bankrupt in 16% of those rounds.
  - It solves late and sure, with 62% of the board showing and median confidence 1.00, and makes 0.07 wrong solves a game against DeepSeek's 0.41.
  - About one vowel a game, half what Sol and Haiku buy.
  - It flipped 14 of 14 Mysteries.
  - Near-fixed bonus picks.
- Some habits are no longer unique to the bot. Sol hoards the Wild Card even more (kept it 188 times, used it 11) and rode all 17 Expresses it landed on, and Haiku solves as late as the bot (68% of the board).
- The Sol-against-bots games show why it solves late. In rounds Sol took, the bot was under 50% confident 40% of the time, never got a turn 44% of the time, and already knew the answer only 3% of the time. Of the ~15-point gap in solve timing (bot 67% of the board, Sol 52%), about 4 points is milking and about 10 is slower reading.

## 7. Puzzles

- There's an archive of 22,934 aired puzzles (2013 to 2025) and a scoring set of 400 main and 100 bonus aired puzzles. Neither is ever published or used for tuning.
- For generated puzzles, a generator model (MiniMax M3) writes answers. Code checks board fit, length, how much a bonus puzzle keeps hidden after R S T L N E plus C D M A, category structure, near-repeats of anything ever used, and spelling. A judge model (GLM 4.7, from a different lab than any player) confirms category fit and natural wording. Weak answers are fixed or dropped by hand. Every accepted answer is registered so it never comes back.
- The grid deck ("grading-505") has 400 main and 100 bonus puzzles in the style of aired puzzles (prompt version 6), hand-fixed in four passes. It stays unchanged for the whole grid.
- Prompt version 7 (2026-10-31, bonus only) asks for a bonus Phrase in everyday talk instead of an idiom, and bonus words needn't be the commonest. The reason: 32% of the grid deck's bonus answers were stock phrases in the bot's word data, against 12% of aired ones, and the bot solves every stock phrase. A 100-puzzle trial under version 7 matched aired difficulty for the LLMs.

## 8. Results

All grid lineups use the grid deck, one seed, 60 sets (360 games) and bot version 4. All but lineup 1 use the new round 4 start rule.

### The grid

| # | Seats | Question | Status |
|---|---|---|---|
| 1 | Sol, DeepSeek, Haiku | which LLM is best (W) | done: W = Sol |
| 2 | Sol, bot, bot | can a good LLM beat the bot? | done |
| 3 | hybrid, bot, bot | how much does Luna's reading add to the bot? | done |
| 3b | Luna alone, bot, bot | what does the bot's strategy add to Luna? | done |
| 4 | Sol, hybrid, bot | all three player types at one table | not started |
| 5 | Sol, hybrid, hybrid | can an LLM beat the strongest seats? | not started |
| 6 | bot, Sol, Sol | can the bot beat two good LLMs? | optional: the bot would be a massive underdog |
| 6a | bot, Luna, Luna | can the bot beat a pair of reckless guessers? | done: bot 50%, Lunas 26% and 24% |
| 6b | bot, Haiku, Haiku | ...a pair of passive readers? | planned |
| 6c | bot, DeepSeek, DeepSeek | ...a pair of eager readers? | planned |
| 3c | DeepSeek alone, bot, bot | DeepSeek's solo yardstick | planned |
| 3d | Haiku alone, bot, bot | Haiku's solo yardstick | done: Haiku 14%, bots 40% and 46% |
| 3e | DeepSeek hybrid, bot, bot | does wrapping DeepSeek lift it too? | planned |

### Lineup 1: Sol, DeepSeek, Haiku ($12.46)

| | Sol | DeepSeek V4.1 Flash | Claude Haiku 5.5 |
|---|---|---|---|
| Win rate | 66% (61–70%) | 25% (21–29%) | 9% (6–13%) |
| Rounds won per game | 1.92 | 1.54 | 0.55 |
| Solves right | 96% | 89% | 91% |
| Board showing at a correct solve | 48% | 46% | 67% |
| Bonus won | 236 of 237 | 84 of 89 | 28 of 34 |
| Invalid moves per game | 0.02 | 0.39 | 0.20 |

Every gap clears zero (Sol over DeepSeek +41, DeepSeek over Haiku +15). Haiku is passive: it waits for most of the board and loses rounds it could have taken. This lineup was played under the old start rule. A bot-only check showed the rule change moves win rates by under a point, so it wasn't rerun.

### Lineup 2: Sol, bot, bot ($6.35)

| | Sol | Each bot |
|---|---|---|
| Win rate | 58% (51–64%) | 21% (17–25%) |
| Rounds won per game | 2.26 | 0.87 |
| Median bank when winning a round (rounds 1–3) | $3,350–3,975 | $5,300–7,000 |
| Solves right | 96% | 90% |
| Board showing at a correct solve | 52% | 65% |
| Money left on the board per solve | $4,130 | about $2,170 |
| Bonus won | 205 of 209 | 129 of 151 (both bots) |

- Sol leads each bot by 37–38 points (27 to 47).
- Two bots are tougher than DeepSeek and Haiku. Set by set, Sol wins 7.8 points less here than in lineup 1 (−15.0 to −0.6).
- Sol wins more rounds but fewer games. It takes 56% of rounds, solving the moment it knows, so it banks about $3,500 a round. When a bot wins a round it has usually had time to milk, and it banks about 1.6 times as much.
- Round 4 decides most of Sol's losses. A bot took round 4 in 125 of Sol's 151 non-wins.

### Lineup 3: hybrid (bot + Luna), bot, bot ($1.93)

| | Hybrid | Each bot | Sol in lineup 2 |
|---|---|---|---|
| Win rate | 45% (40–51%) | 27–28% | 58% |
| Rounds won per game | 1.74 | 1.13 | 2.26 |
| Solves right | 97.5% | 92.5% | 96% |
| Board showing at a correct solve | 65% | 66% | 52% |
| Bonus won | 147 of 163 | 169 of 197 (both bots) | 205 of 209 |

- The hybrid leads each bot by 17–19 points (9 to 27).
- Sol alone does better. Set by set, against the same two bots, the hybrid wins 12.8 points less than Sol did (−20.0 to −5.6).
- The hybrid asked Luna 5,817 times (16 a game, about 6 seconds each, which is why these games were slow). Luna said "not solvable" 2,484 times and gave 3,333 answers, 84% of them right.
- Luna's reading raised accuracy and rounds won but left timing where it was. The hybrid still solved at 65% of the board, the same as the bots. Its strategy judges both opponents slow and bot-like, so waiting looks safe.
- Read with lineup 3b, strategy plus a weak reader beats pure strategy but loses to a strong reader with no strategy.

### Lineup 3b: Luna alone against two bots ($1.33)

| Against two bots | Luna alone | Hybrid (bot + Luna) | Sol alone |
|---|---|---|---|
| Win rate | 17.5% (12–23%) | 45% | 58% |
| 1st / 2nd / 3rd | 63 / 196 / 101 | 163 / 105 / 92 | 209 / 99 / 52 |
| Rounds won per game | 1.79 | 1.74 | 2.26 |
| Main-round winnings per round won | about $2,460 | about $5,400 | about $4,270 |
| Wrong solves per game | 0.70 | 0.04 | 0.09 |
| Solves right | 72% | 97.5% | 96% |

- Set-by-set gaps:
  - hybrid − Luna alone **+27.8 points** (+20.8 to +34.7): what the bot's way of playing adds to Luna's reading
  - Sol − Luna alone +40.6 (+32.5 to +48.3)
  - Sol − hybrid +12.8 (+5.6 to +20.0)
- So the wrapper recovers about two-thirds of the gap between Luna and Sol.
- Luna wins as many rounds as the hybrid, but cheap ones. It keeps losing the wheel, so its bank is small when it finally solves, and it finishes second most often.
- Luna's losses come from discipline (it does support tool calls):
  - 219 solves that don't fit the board: an already-called letter put in a hidden square (LUCKY for L__KY with C already showing), a refuted answer repeated, wild guesses on near-empty boards
  - 150 bad tool calls, almost all a consonant called without spinning first. Every tool is offered on every move to keep the prompt cacheable, and the engine refuses illegal calls and reprompts.
- The hybrid's wrapper removes exactly these faults with the fit check, the list of refuted answers, and the bot deciding when to trust a read.
- Ian's line is no prompt engineering of the models. "LLMs in the wild" stay unprompted beyond the rules, and every gain comes from code around them.
- The two identical bots differed by 8 points (+0.6 to +16), most likely chance.

### Lineups 6a and 3d

- In 6a, the bot against two Lunas ($2.58), the bot won 50% (43–57%) and the Lunas 26% and 24%. The bot leads each by about 25 points. The Lunas solve at 47–48% of the board and get 70% right.
- In 3d, Haiku alone against two bots ($2.61), Haiku won 14% (10–19%) and the bots 40% and 46%. Haiku is right 95% of the time but solves at 72% of the board, later than the bots, and wins only 1.22 rounds a game.
- Luna and Haiku have opposite faults and the same result. Luna is reckless (early and often wrong, 0.7 wrong solves a game) and Haiku passive (right but late, 0.07). Both land well under a fair share. Sol, early and right, is the only one that beats the bots.

### Bonus test: each player alone on every bonus puzzle in a deck

| | Aired (100) | Grid deck (100) | Prompt v7 trial (100) |
|---|---|---|---|
| Sol | 99% | 99% | 98% |
| DeepSeek | 90% | 95% | 89% |
| Haiku | 53% | 67% | 57% |
| Bot | 67% | 88% | 86% |

- The bot solves 79% of a separate 500-puzzle sample of aired bonus puzzles, so the scoring set's 100 are harder than average.
- The grid deck's bonus puzzles are too easy for the bot (stock phrases). Prompt version 7 brought them to aired difficulty for the LLMs, but the bot barely noticed. On aired puzzles the bot trips on ranking rare words and odd pairings, and those aren't what trip the LLMs.
- Memory may help the LLMs on aired puzzles, since aired answers are all over the web. It's untested. Showing the models only the category and a blank board would tell.
- Haiku's misses are mostly misfits: answers that don't fit the board.
- Contestants solve about 38% of bonus puzzles, with a 10-second clock and no time to think, so the comparison with the models is loose.

### Self-play checks (bot-only games)

- Version 3 against version 1: +15 points.
- Version 4 against version 3: a tie.
- The round 4 start rule (100 sets, same spins under both rules) moved no player's win rate by more than a point. The seat edge moved and halved. Averaged over players, seats 1/2/3 won 42/29/30% under the old rule and 31/31/38% under the new one, because seat 3 opens round 3 and so often round 4 too. The show avoids this by giving round 4 to the Triple Toss-Up winner, and Ian kept the rule.

### Older findings (before the grid; older bot and different puzzles)

- Recognition decides most rounds. Once players recognize answers equally fast, patience wins.
- The bot boards the Express only when sure (median confidence 0.97) and never busted on a letter.
- DeepSeek won about 39% against Luna's 22% at a mixed table.
- An earlier Luna hybrid beat DeepSeek and a version 1 bot by about 9 points.

## 9. Decisions and reasoning worth keeping

- The hybrid uses Luna because a Sol hybrid would only ask "is Sol plus the bot better than Sol?", which is the "if you can't beat 'em, be 'em" move Ian rejected. A win would just be Sol in disguise. A Luna hybrid asks whether strategy can make up for weaker reading, keeps the three player types distinct, and is cheap. The cost is that claims about strategy hold only for a Luna-level reader.
- The bot is still worth having. It's free, deterministic and identical game after game, so it's the fixed yardstick the LLMs are measured against. For fun at home, LLM opponents feel more like real contestants.
- Generated bonus puzzles shouldn't be made harder for the bot specifically. That would mean writing puzzles around gaps in its word data, which tests its vocabulary instead of its play.
- Why there's so little research on Wheel of Fortune:
  - There's no fan database of in-game decisions like Jeopardy's. Only puzzle lists exist.
  - Risk-taking is tangled with reading skill, which makes it a poor experiment for economists.
  - For AI, the language half was too hard before LLMs, and the game looks too easy and too contaminated after.
  - It looks like a game of luck.
  - The engine is a lot of work to build.
  - The popular questions (bonus letters, vowel prices) were answered by journalists.

  The one direct LLM study (LLMike, 2025) tests a single model solving riddles alone, outside the competitive game. The show is in season 44 (from September 2026), with a new "Fortune Frenzy" round replacing the first toss-ups.
- Advice on publicizing, given but not acted on:
  - Lead with the story and the four questions. A video of a live game would travel best.
  - Post where the audience is: Hacker News, r/LocalLLaMA, game-show fans.
  - Report intervals and date the models.
  - Never publish aired puzzles. Publishing the grid deck would burn it for future scoring.
  - Use the show's name only in text, with a "not affiliated" line and none of its branding.

## 10. What's next

1. Spread the runs across labs. After lineup 1 every LLM seat was OpenAI's, so the next runs keep the study from becoming a test of one lab:
   - The solo yardstick (a model alone against two bots) for DeepSeek and Haiku.
   - A DeepSeek hybrid, to show the hybrid's lift on a second lab. DeepSeek already has its trust and steal curves.
   - Lineup 6's format against weaker pairs: the bot against two Lunas, two Haikus, and two DeepSeeks. Each mirrors that model's solo run.
   - Two Sols are out because one Sol beat two bots 58% to 21% each, so against two Sols the bot would be a massive underdog, in betting terms a long shot likely winning 10% or less. That's a predictable result for about $12. It stays optional, at 20 sets if run.
   - MiniMax and Z.ai can't play, since they write and judge the puzzles. Sonnet and Gemini are off for now.
   - Frontier and pricier models wait for a grant. One-set trials (alone against two bots, set 0): Gemini 4 Argon won 5 of 6 at 9.6¢ a game, Gemini 3.8 Flash 5 of 6 at 6.9¢, against Sol's 3 of 6 at 1.8¢. GLM 5.3 was stopped: very slow on its host and about 8–12¢ a game. One set is too small to rank anyone.
   - Google costs more here because Gemini caches only prompts of 4,096 tokens or more, and each round's conversation starts at about 1,700. Flash also writes about 1,500 tokens a move. Sol is the rare model with expensive tokens and very few of them (about 880 a game, 83% of its prompt cached).
   - GLM would be a disclosed exception to the rule that puzzle labs don't play, since Z.ai's older GLM 4.7 judged the puzzles. It only filtered answers and didn't write them. MiniMax, which wrote them, stays out without exception.
2. Lineups 4 and 5 (Sol with the hybrid at one table), to see whether the hybrid solves sooner against a fast opponent.
3. Optional checks:
   - Terra alone against two bots (about $3): one more OpenAI point between Luna (17.5%) and Sol (58%). Optional now that DeepSeek and Haiku give middle points from other labs.
   - The Sol-against-bots lineup rerun with version 3 bots (does version 4 help against LLMs?).
   - The blank-board memory probe on aired bonus puzzles (about $1).
   - The bot's habits measured against Sol, a real stealer.
4. Later:
   - A bot version 5 that refits its tables under the new start rule.
   - A tighter near-repeat check in puzzle generation.
   - The write-up.
