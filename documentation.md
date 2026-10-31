# Wheel of Fortune: game specification

This file defines how the game plays. CLAUDE.md defines how to build it. When the two seem to disagree, the rules here decide gameplay and CLAUDE.md decides code structure.

## The wheel

The wheel follows the show's layout per round. One base template of 24 equal wedges stays put, and the special wedges change by round. Define every round in `wheel.toml` so Ian can edit layouts without touching code.

### Base template (clockwise)

| # | wedge | # | wedge |
|---|---|---|---|
| 1 | TOP | 13 | $600 |
| 2 | $800 | 14 | Bankrupt |
| 3 | $600 | 15 | $650 |
| 4 | $700 | 16 | Free Play |
| 5 | $600 | 17 | $700 |
| 6 | $650 | 18 | Lose a Turn |
| 7 | $500 | 19 | $800 |
| 8 | $700 | 20 | $500 |
| 9 | $800 | 21 | $650 |
| 10 | $600 | 22 | $500 |
| 11 | $550 | 23 | $900 |
| 12 | $500 | 24 | Bankrupt |

### Per round overlays

| round | TOP | Wild Card | Million wedge | Mystery | Express |
|---|---|---|---|---|---|
| 1 | $2,500 | on wedge 2 | on wedge 9 | none | none |
| 2 | $3,500 | on wedge 2 | on wedge 9 | wedges 5 and 17 | none |
| 3 | $3,500 | on wedge 2 | on wedge 9 | none | wedge 12 |
| 4+ | $5,000 | none | none | none | none |

An overlay covers the wedge beneath it. When an overlay leaves the wheel, the wedge beneath plays at face value. The Wild Card and the Million wedge leave the wheel when a player claims them. In rounds 1 to 3, each sits on the wheel at the start of a round only if no seat holds its card. Once one leaves during a round, it stays off until the next round.

## Special wedges

- **Million wedge:** split wedge 9 into thirds. The outer thirds resolve as Bankrupt. The center third plays as $500. A correct consonant on the center third earns $500 per copy and hands the player the Million card. The whole Million wedge then leaves the wheel, Bankrupt thirds included, and wedge 9 plays as a full $800 wedge for the rest of the round. The player keeps the card only by solving that round. If another seat solves, or nobody does, the card is lost. The card matters only in the bonus round, where it swaps the $100,000 envelope for $1,000,000.
- **Wild Card:** a correct consonant on wedge 2 earns the wedge value and hands the player the Wild Card. The card stays with the player across rounds, whether or not they solve. After a correct consonant on a plain dollar wedge (a cash value or TOP), the holder may spend the card to call one extra consonant at the same wedge value. This includes the spin on which they claimed the card, and holds even when no consonants remain hidden. Free Play, Mystery, Express, and the Million center third don't qualify. A missing or repeated extra consonant passes the turn, and the card is spent either way. An unspent card grants one extra consonant in the bonus round.
- **Bankrupt takes held cards.** Bankrupt removes the Wild Card and the Million card, even when the player picked them up in an earlier round.
- **Free Play:** the player calls any letter. A correct consonant earns $500 per copy. A vowel costs nothing. A wrong or repeated letter keeps the turn. A Free Play spin takes a letter, not a solve.
- **Mystery (round 2):** face value $1,000 per letter. After a correct consonant, the player chooses `keep` or `flip`. Keep earns $1,000 per copy. Flip forfeits that money and reveals the back. One Mystery wedge hides $10,000, which goes to the round bank, and the player keeps the turn. The other hides Bankrupt. Seed which wedge holds the $10,000. Once a player flips one, the flipped wedge leaves the wheel and the wedge beneath plays at face value. The other plays as a plain $1,000 wedge, which counts as a plain dollar wedge for the Wild Card.
- **Express (round 3):** face value $1,000 per letter. After a correct consonant, the player chooses `pass` or `play`. Pass continues normal play. Play locks the player into Express mode: they call consonants at $1,000 per copy and buy vowels at $250, with no spinning, until they solve. A wrong letter, a repeated letter, a wrong solve, or a third invalid response counts as Bankrupt. Calling a consonant becomes illegal once every consonant is revealed, as spinning does in normal play.
- With equal thirds, P(Bankrupt) = 8/72 = 1/9 per spin in rounds 1 to 3 while the Million wedge is on the wheel, and 2/24 = 1/12 otherwise, including round 4 onward. A test checks both.

## Turn rules

On their turn, a player picks one action from the legal list:

1. **Spin, then call a consonant.** A consonant in the puzzle earns the wedge value times its count and keeps the turn. A missing or repeated letter passes the turn.
2. **Buy a vowel** for $250 from the round bank. The $250 is paid even when the vowel is missing or repeated. A present vowel keeps the turn. A missing or repeated vowel passes the turn. The action stays illegal below $250 and once every vowel in the puzzle is revealed.
3. **Solve.** A correct solve adds the round bank to the game total and ends the round. A wrong solve passes the turn. A solve must match the answer's letters, word breaks, and punctuation exactly. Case and extra spaces don't matter: for `WELL-KNOWN FACT`, `well-known  fact` is correct and `WELL KNOWN FACT` is wrong.

- **Bankrupt** zeroes the round bank, removes held cards, and passes the turn. Game totals from earlier rounds stay safe.
- **Lose a Turn** passes the turn.
- Once every consonant is revealed, spinning becomes illegal.
- A repeated letter is a legal call. It takes the same penalty as a missing letter.
- Only the solver banks round money. The other two seats lose their round banks.
- A solver who banks under $1,000 in a round gets raised to $1,000.
- The starting seat rotates each round.
- A round ends after 200 turns if nobody solves. Each pass to the next seat starts a new turn. No seat banks its round money, and nobody gets the $1,000 minimum. Set the cap in `config.toml`.
- A game runs 4 main rounds by default, then the bonus round. Set both in `config.toml`.

## Bonus round

The seat with the highest game total after the main rounds plays the bonus round alone. A seeded draw breaks ties.

### Bonus wheel

24 equal envelopes. Define them in `wheel.toml`. Defaults:

| envelope | count |
|---|---|
| $40,000 | 6 |
| $45,000 | 6 |
| $50,000 | 6 |
| $55,000 | 5 |
| $100,000 | 1 |

A player holding the Million card swaps the $100,000 envelope for a $1,000,000 envelope before the spin.

### Flow

1. The player spins the bonus wheel. The engine records the envelope and keeps it hidden.
2. The engine shows the category and reveals R, S, T, L, N, and E.
3. The player picks 3 consonants and 1 vowel. A held Wild Card adds a 4th consonant. Picks exclude RSTLNE and repeats.
4. The engine reveals the picked letters.
5. The player gets one solve attempt. A human gets 10 seconds. A model gets one response.
6. The engine reveals the envelope. A correct solve adds its value to the player's game total.

Bonus puzzles carry `"bonus": true` in the puzzle file. Keep them short, like the show's.

## Seeding

- Derive every spin from `(game_seed, round_index, spin_index)`. Two games with the same seed and the same decisions produce identical spins.
- The bot seeds any sampling from a hash of its view, so the same seed and the same moves replay the same game.
- Tournament mode plays each puzzle set once for every ordering of the players across the seats, against the same spins. This is duplicate bridge scoring. It strips most of the luck out of model comparisons.
- `python -m rstlne.tournament --seats <seat>,<seat>,<seat> --sets N --seed S` plays N puzzle sets. Seats use the CLI's model forms (`llm:<slug>`, `decision[:<model>]`, `bot`), and `--models a,b,c` is short for three `llm:` seats. `--sets 1` is the trial run for checking cost.
- With `set_permutations = "all"` in `config.toml`, the default, a set is 6 games, one for each ordering of the 3 entrants across the 3 seats. Each entrant sits in each seat twice per set and directly follows each other entrant 3 times, counting turn order around the table, where Seat 3 passes to Seat 1. `"cyclic"` plays the 3 rotations instead, where each entrant sits in each seat once but always follows the same entrant.
- All games in a set share the set's seed, derived from the tournament seed and the set index, and the set's puzzles.
- Puzzles are dealt across sets without replacement. The main and bonus pools are each shuffled from the tournament seed and dealt 4 main puzzles and 1 bonus puzzle per set. When a pool runs out, it is reshuffled and dealing continues. A set that straddles a reshuffle skips puzzles it already holds, which stay in the new pile for later sets, so no set repeats a puzzle.
- Each game log is tagged with its set index, its ordering, and the entrant in each seat.
- A game's winner is the seat with the highest final total, bonus included. Seats tied for the highest total split the win evenly.
- Games run in parallel (`--parallel`, default 6, a whole set at once). Each game prints a line when it starts and when it ends, with how long it took, and every 2 minutes a status line lists the games in progress with their round and move count, the time elapsed, and once a game has finished, about how long the rest will take. A game that fails says which seat and model failed, in which round, and what the provider said. The run ends with its total time. Each writes its usual log into the tournament's folder. Rerunning a tournament skips finished games and replays unfinished ones. `--max-cost` stops starting new games once spending reaches a limit. Tournaments with a bot seat play each game in its own process, since the bot computes rather than waits.
- The report gives, per entrant: games, win rate overall and by seat, average final total and main round winnings, bonus rounds reached and won, solve accuracy, average board shown at a correct solve, money left on the table, invalid moves by category, and tokens and cost. It also gives each set's wins and average totals per entrant, and how many sets used each puzzle. Runs on `dev.json` are marked as development runs; scored runs use `private.json` or generated puzzles, and a generated run names its generator and judge.
- Confidence intervals come from bootstrapping over sets, not games, since the games in a set share puzzles and spins and are not independent: 10,000 seeded resamples of the sets, 95% percentile intervals, for each entrant's win rate, average final total, average main round winnings, and solve accuracy, and for the win rate gap between each pair of entrants.
- A tournament's default folder name covers its entrants, seed, puzzle file, `set_permutations`, and the settings that change play (provider pins, LLM settings, decision settings, the bot version), so a rerun resumes only an identical tournament.

## LLM player

- Use only models that support tool calling: their `supported_parameters` on OpenRouter include `tools`.
- A request gets 300 seconds. One that times out is tried once more; a second timeout fails the game, and a rerun replays it. DeepSeek V4.1 Flash sometimes thinks for over 6,000 tokens on a hard board, about 4 minutes on its host, and the hard bonus puzzles bring that out.
- `[providers]` in `config.toml` can pin a model to one OpenRouter provider with no fallback, so every game runs on the same build of the model. Each game log records the pinned provider. GPT-6.1 Terra and Sol are pinned to OpenAI's flex tier, the same models at half price with lower priority. Xiaomi MiMo V2.6 Flash is pinned to Cohere, the fastest of its hosts that kept the model's thinking and took forced tool calls in a one-game-per-host screen. DeepSeek V4.1 Flash is pinned to Inference.net's FP8 build, which thinks about three times as fast as DeepInfra's FP8 build, so its long thinks finish inside the request time limit. DeepInfra's FP8 build served every DeepSeek game before 2026-10-30. DeepSeek's own servers are blocked by the account's privacy setting, and the cheapest host served an FP4 build that stalled requests.
- Send the rules once in the system prompt. Send the public view each turn, with a short recap of what the other seats did since the model's last move.
- The public view includes the wheel as it stands: whether the Wild Card and the Million wedge are still on it, and which Mystery wedge has been flipped. Contestants can see the wheel.
- Render the board with spaces between characters: `_ _ E _ L   _ _ _`. Show word boundaries with three spaces.
- Also show the board as a compact pattern with each word's length, such as `Pattern: A ____ TAN_ __ _A_ (word lengths 1, 4, 4, 2, 3)`, so models don't have to count spaced tiles.
- Every model reasons at its own default. Claude models get reasoning turned on with no effort level, which runs their native adaptive thinking, because OpenRouter leaves it off unless asked. Other models already reason by default. `reasoning_effort` in `config.toml` can set one level for every model instead. `[llm.effort]` sets one model's own level, overriding that. OpenAI models keep their reasoning hidden, so a log can show no reasoning text while the model still reasons: GPT-6.1 Sol spends 25 to 40 reasoning tokens on a simple solve at its default, about what medium gives, and played the same at both in 8 test games. Thinking Claude and Qwen models get `tool_choice: auto` in place of a required tool call: forcing a call switches Claude's thinking off, and Qwen's provider rejects it. A reply without a tool call gets the usual reprompt.
- Moves are tool calls. By default each request offers only the tools that are legal right now and requires one call. With `tools = "all"` in `[llm]` it offers every tool in one fixed order instead, since a provider caches a prompt only as far as it starts the same and the tool list comes first; the view still names the legal moves, and the engine refuses an illegal call as a bad tool call. `config.toml` sets `all` since 2026-10-30: on 4 seeded Terra games it lifted the cached share of input from 36% to 80% and halved the cost per game, with no invalid moves either way. The tools are: `spin`, `buy_vowel(letter)`, `solve(answer)`, `call_consonant(letter)`, `call_letter(letter)` on Free Play, `keep` or `flip` on Mystery, `pass` or `play` on Express, `use_wild(use)` after a correct consonant while holding the Wild Card, and `bonus_picks(consonants, vowel)` and `bonus_solve(answer)` in the bonus round.
- Letter arguments are plain strings. The engine checks them, so every model faces the same validation whatever its provider enforces.
- Only the first tool call in a response counts. Log any extra calls.
- A spin takes two calls. The model calls `spin`, the tool result reveals the wedge, and the model then calls `call_consonant`. The model sees the wedge value before it picks.
- During Express mode, the tools shrink to `call_consonant`, `buy_vowel`, and `solve`. Say so in the view.
- Bonus round picks take one call, with 4 consonants when the model holds the Wild Card. The solve takes one more call.
- The `solve` and `bonus_solve` tools say that the answer is the whole puzzle and must match the board: the same words, word lengths, revealed letters, and punctuation. A wrong solve passes the turn.
- On a response with no tool call, a tool that isn't on offer, unreadable arguments, or an illegal move, reprompt with the error up to 2 times. After the third failure, pass the turn. On a keep or flip, pass or play, or Wild Card prompt, the third failure takes the safe choice (keep, pass, don't spend the card) and then passes the turn. During Express mode, the third failure counts as Bankrupt. In the bonus round, failed picks reveal no extra letters and the solve still happens. A failed bonus solve counts as wrong.
- Log every invalid response with its category: bad tool call, not a letter, vowel on a spin, consonant on a vowel buy, insufficient funds, malformed solve, bad bonus picks. Also log repeated letters as their own category, but never reprompt them: a repeated letter is a legal call that takes the game penalty. Likewise log a wrong solve that doesn't fit the board (wrong word count, wrong word length, a revealed letter changed, a used letter in a hidden square, or punctuation changed) as "solve doesn't fit the board". It still takes the wrong solve penalty. Report these separately from game outcomes.
- Keep the conversation history per round so the model remembers its own reasoning. Reset it each round.

## Bot

The `bot` seat is the project's own player: a fixed, strong opponent to measure models against. It sees only the public view and the results every seat observes, never the answer and never who sits in the other seats.

### Versions

- The bot is versioned: bot v1, v2, and so on. A version fixes the bot's code, its data files, and its knobs. `[bot] version` in `config.toml` picks one, and every log header records it.
- Versions 1 and 2 were frozen on 2026-10-29. They differ only in how they read win chances from round 3 on: v1 uses the formula, and v2 the win table built from 1,998 bot games. In 1,998 bot games on grading puzzles they tied, at 37% wins each (gap +0%, 95% interval −2% to +3%), so both are kept. A change to either is a new version.
- Each version is pinned to the word data it was frozen with, by fingerprint: 0640bcd6a420 for all three. A bot or hybrid seat refuses to play a version on other data. Self-play experiments aren't checked.
- A tournament never changes the bot. Its default folder name covers the bot version, and a rerun refuses to resume a tournament whose finished games used another version.
- Self-play may try knobs away from a version's values. Those runs are experiments, not versions, and tournaments refuse them.

### Version 3 (frozen 2026-10-30)

Version 3 is version 1 with two changes. Every other knob, the reader, the calibration, the steal prior, and the word data pin stay as in version 1.

- **Why.** Versions 1 and 2 give an opponent who takes the round only the bank it holds right now, or the $1,000 minimum. They never count what the opponent adds before it solves. In round 4, with no rounds after it, a lead bigger than an opponent's bank plus $1,000 then looks certain, and every move scores the same. In the 300 hybrid games of seed606, a bot or hybrid seat saw every move at exactly 1 in 163 games and lost 30 of them. It saw every move at exactly 0 in 103 games and won 5. In one game, a hybrid led $4,000 to $2,000 entering round 4, rated every move 1, made a wild solve at 2% confidence, and lost to an opponent who built an $18,950 round.
- **Change 1: the stealer's gain.** When the bot weighs an opponent taking the round, that opponent banks max(its bank now + G, $1,000), where G is what it adds between now and its solve. G is a spread, not one number: 20 equally likely values, the midpoints of its twentieths (the 2.5th, 7.5th, … 97.5th percentiles). The bot averages its win chance over the 20 values. Twenty rather than ten halves the steps in the chance an opponent overtakes, and reaches further into the rare big rounds that make a late lead unsafe; past 20, the fit's own sampling noise outweighs the finer steps. G can be negative, when the opponent hits Bankrupt and rebuilds.
  - G depends on how many letter squares are still hidden, in bands: 0–2, 3–5, 6–9, 10–14, and 15 or more. The bot can't see which hidden squares hold consonants, so the bands count every hidden letter square. G is fit separately for rounds 1 to 3 and for round 4 on, whose wedges are bigger. A band with fewer than 200 data points merges into its neighbor with fewer hidden squares, or with more when it has no such neighbor. The bot reads G at the board as it stands.
  - It applies wherever a steal counts against the bot: a lost round in the value function, and V(continue later). The bot's own future bank is unchanged, since the value function already plans it.
- **Change 2: flat choices go to dollars.** When every option of a choice scores within the tie margin of the best, the bot chooses as in rounds 1 and 2: by expected dollars, with cards at their dollar values. This covers every choice the bot makes: the move, the letter, keep or flip, the Wild Card, and riding the Express. A bot certain of the result plays out the round for money and solves an answer it knows, instead of taking the first option in the list. With change 1, such choices come up only when the result really is settled.
- **Fitting G.** `selfplay stealer-gain` fits it from two sources, weighted half and half, so neither kind of opponent dominates:
  - LLM opponents: the prior-101 tournament, 180 games of three chat models on the tuning puzzles.
  - Bot opponents: `selfplay round-banks`, about 2,000 bot v1 games on the tuning puzzles that record the data points below.
  - In each round that ended in a correct solve, every turn decision (spin, buy a vowel, or solve) by a seat other than the solver is one data point: the round, the hidden letter squares then, and G = the solver's bank when it solved minus its bank at that decision. These are the moments a bot weighs a steal. Within a band, the 20 gains are the weighted midpoints of the twentieths. LLM and bot opponents weigh half and half only where each has at least 50 points in the band; elsewhere every point counts the same, so a handful of points can't set half the spread.
  - It refuses logs played on grading puzzles, `dev.json`, or `private.json`: a tournament folder must hold a report.json naming its puzzles, and a round-banks folder a round-banks.json. It reports each band's count, median, and 90th percentile, for each source, and the 20 gains. The fit is frozen into version 3 as `stealer-gain-v3.json`: 2,043 points from LLM opponents and 36,012 from 2,004 bot games. With 10 to 14 squares hidden in rounds 1 to 3, an LLM opponent added a median $350 before solving (90th percentile $3,200) and a bot $2,500 ($6,800); the blend's 20 gains run from $0 to $10,500, half of them $1,050 or less. Round 4's bands reach $15,000, from its $5,000 top wedge.
- **Checking it.** `selfplay games` with variants v3, v1, v1 on grading-202, about 2,000 games with duplicate scoring, on the server. It reports v3's win rate against the v1 seats' with a 95% interval, average totals, in how many games each version saw every move score exactly 1 or exactly 0 and how often that proved wrong, and how many choices a game went to dollars under change 2. If v3 wins more, with the interval clear of zero, Ian decides whether `[bot] version` moves to 3. Version 1 stays frozen either way.
- **Logging.** Each bot decision records `flat: true` when change 2 chose it.
- **Adopted.** `config.toml` moved to version 3 on 2026-10-30. In the full check, 2,004 games against two v1 bots on grading-202, it won 43% (95% interval 41% to 46%) to their 28% each, a gap of +15 points (+12 to +18). v1 was sure it had won in 473 games and lost 114 of them; v3 was sure in 186 and lost 2. It played about 5 choices a game for dollars, and won $6,758 a game in the main rounds to v1's $4,727. It is sure it has lost more often than v1 (542 games to 460) and wrong about it 4% of the time: the stealer's gain makes it expect opponents to build big banks, while its own comeback chances weren't modeled the same way.

### Version 4 (built 2026-10-31, not yet fit)

Version 4 is version 3 with one change: each opponent gets its own stealer's gain, from how that seat plays this game. Everything else stays as in version 3. The grading grid runs on version 3, and version 4 is checked after it.

- **Why.** Version 3's gain G blends two kinds of opponents half and half. LLM opponents pounce and add little before solving. With 10 to 14 squares hidden in rounds 1 to 3, an LLM's median is $350 and its 90th percentile $3,200. Bot opponents milk the board: a median of $2,500 and a 90th percentile of $6,800. Against an eager LLM, version 3 overrates how much it might add; against a patient seat, it underrates it.
- **Two gain tables.** G_llm is fit from LLM opponents only and G_bot from bot opponents only. Both use version 3's bands, its 20 values per band, and its merging of sparse bands, applied within each source.
- **Is this seat like an LLM or a bot?** Each opponent has a weight w, the chance it plays like an LLM rather than a bot. w starts at 1/2 every game and updates on every turn where the seat could have solved, the same turns the steal odds learn from:
  - the turn is scored under two curves, q_llm (the version 1 steal prior, fit on chat models) and q_bot (the same logistic form, fit on bot play)
  - the chance of what the seat did is q if it solved and 1 − q if it didn't
  - the log of w / (1 − w) grows by the log of that chance under q_llm divided by its chance under q_bot
  - so a seat that solves early climbs toward 1, and a seat that passes up boards it could read falls toward 0
- **Using it.** When the bot weighs that seat taking the round, it averages its win chance over G_llm with weight w and over G_bot with weight 1 − w, in place of version 3's single table. The steal odds themselves are unchanged. At w = 1/2 this is close to version 3: the average of the two tables against their pooled one.
- **No identities and no memory.** w comes only from what the seat does at this table, and resets every game.
- **Fitting.** `selfplay round-banks` gains a record of every opportunity: the share showing, the deciding bot's confidence, and whether it solved correctly. In self-play every seat runs the same bot and reader, so the deciding bot's confidence stands in for the observer's. A new run of about 2,000 version 3 games on the tuning puzzles fits both G_bot and q_bot. G_llm is refit from prior-101 on its own. All three are frozen into version 4 with its word data pin. Nothing is fit on grading, dev, or private puzzles.
- **Logging.** Each bot decision records every opponent's w as `llm_like`, keyed by seat number.
- **Commands.** `selfplay round-banks` now records every chance to solve beside the gain points. `selfplay v4-fit --logs <tournament folders> --games <round-banks folders> --out <folder>` writes `stealer-gain-llm.json`, `stealer-gain-bot.json`, and `steal-bot.json`, the three knobs version 4 freezes.
- **Checking it.** `selfplay games` with v4, v3, and an eager v3 (`eager_solve=0.65`, which pounces like an LLM) on grading-202, about 2,000 games. It reports:
  - win rates with 95% intervals
  - the average w each version 4 seat gave the eager seat and the plain version 3 seat, which should land high and low
  - the settled-result counts
  - money
  If version 4 beats version 3 with the interval clear of zero, Ian decides whether `[bot] version` moves to 4. Lineups 2 or 6 of the grid can then be rerun on version 4 to check the gain against real LLMs.
- **Expected gain:** a few points. Version 3 already closed the big gap (+15). Version 4 sharpens G for opponents that differ from the blend: against a patient opponent, close out rounds sooner; against an eager one, milk a little more.

### Objective

- Rounds 1 and 2: maximize the bot's expected game total, whatever the number of main rounds.
- Rounds 3 and later: maximize the chance of finishing ahead of both opponents after the last main round. Every payoff converts into the change in that chance. A tie for first counts as a shared win, as in tournament scoring.
- From round 3 on, only finishing first counts: winning by $100 is as good as winning by 10 times second place. A lead still matters as a means, since it raises the chance of finishing first. With a commanding lead, the best move is often to solve at once, ending the round before an opponent banks anything.
- The bonus round is secondary. It matters through the Wild Card's saved value, the Million card's value, and the bonus round itself. In rounds 1 and 2 those values count in dollars. From round 3 on, they only break ties: moves whose win chances sit within a set margin of the best (a knob) count as tied, and the tied move with the most bonus value wins.
- The win chance comes from a simple formula, P = Φ(lead / (σ √(rounds left))) with σ a knob, or in versions that carry one, from a table of P(finish first | lead, rounds left) built from self-play games, with the formula standing in where the table has no row. Lead is the bot's game total minus the highest opponent total. Once no rounds are left, the lead decides: 1, 0, or a shared win. From version 3, an opponent who takes the round banks what it holds plus what it adds before solving (see Version 3).

### Reader

- The reader turns the board and category into a frozen Belief:
  - for every letter: p_hit, the chance it appears; E[count | hit]; and the entropy of where it would show
  - the top whole answers with their probabilities
  - an explicit out of vocabulary share: the chance the answer holds a word or name the reader doesn't know
- The board splits into word slots at spaces and hyphens, with punctuation kept in place. Each slot holds one of three kinds of state:
  - a free word from the vocabulary that fits the slot, weighted by its frequency and its category fit from word vectors, and linked to the free word before it by word pair counts (Witten-Bell smoothed, so a pair never seen after a well-attested word costs more)
  - an unknown word, whose letters come from letter frequency
  - a position inside a known phrase or name that fits a run of slots, which may start part way into the board (A + BLESSING IN DISGUISE)
- A run of slots is a known phrase with prior odds against free words (knobs: higher when the phrase's kind fits the category, much lower for a one-word name), times the free words' total frequency over those lengths, times the phrase's share of popularity among phrases of the same shape. Popularity is its sitelinks or sense count times how often its rarest word pair appears in text. Wiktionary placeholders like ONE'S also read as YOUR, HIS, HER, MY, THEIR, and OUR.
- Category rules: ING words for What Are You Doing?; neighbors sharing a first letter for Same Letter; rhymes from the CMU Pronouncing Dictionary for Rhyme Time; two phrases overlapping on a shared word for Before & After (PIECE OF CAKE + CAKE WALK). For Same Name (BIRTHDAY & WEDDING CAKE) and for rhymes that skip a word (WEAR AND TEAR), the sampled answers are reweighted as a whole. Categories that name a shape rather than a topic (Before & After, Same Name, Rhyme Time, Same Letter, Megaword) let a phrase of any kind fit.
- p_hit, E[count | hit], and entropy come from whole answers sampled across the slots by forward filtering, backward sampling.
- A wrong solve by any seat rules its answer out for the rest of the round. The reader drops refuted answers from its samples before it sums them up, so the letter odds and the top answers come only from answers still standing. When none is left standing, the answer counts as unknown. A guess with no candidate answer fills the hidden squares with the commonest unused letter, skipping fills already refuted.
- Confidence in the top answer is calibrated: a never-decreasing curve from raw confidence to how often that confidence was actually right, fit on the tuning puzzles' main round boards and checked on held out ones, then frozen into the version's knobs as up to 21 points. The decision layer uses calibrated confidence; the steal curve's input stays raw, because a, b, and c were fit on raw confidence.
- When nothing in the vocabulary fits, the reader falls back to plain English letter frequency.
- Share revealed always means letter squares showing, not distinct letters.

### One value function

- On a turn, the bot scores every legal action, spin, buy a vowel, or solve (and call a consonant on the Express), with one formula and takes the best:

  V(action) = immediate gain + P(keep the wheel) × V(continue) + P(lose the wheel) × (1 − p_steal) × V(continue later)

- Payoffs are dollars in rounds 1 and 2 and changes in win chance from round 3 on.
- B is the round bank plus held cards at their values: the Wild Card at its saved value, the Million card at its expected bonus value.
- Spin: each wheel outcome is one branch, over the wheel as it stands. A dollar wedge pays the best consonant's p_hit × value × E[count | hit] and keeps the wheel with chance p_hit. Lose a Turn passes the wheel. Bankrupt zeroes B and passes the wheel, and counts only in that branch. Free Play, Mystery, and Express follow their own rules below.
- Buy a vowel: −$250 plus the vowel's information value. It keeps the wheel with chance p_hit.
- Solve: c × the payoff of banking max(B, $1,000) + (1 − c) × (1 − p_steal) × V(continue later), where c is the calibrated confidence. A solve never keeps the wheel. With no candidate answer at all, the bot doesn't guess unless solving is its only legal move.
- Losing the wheel costs the round's whole value: a steal leaves the bot nothing from the round, not even the $1,000 minimum. From round 3 on, the stealer's gain also counts against the bot's win chance. Versions 1 and 2 count the stealer's bank as it stands now; version 3 adds the spread G of what it banks before solving.
- V(continue) is a race from the board the move leads to. Each turn the bot holds the wheel, it takes the round with chance t: its confidence c, or while c is low, the chance any seat solves on its turn at that board (the steal prior), since holding the wheel lets it reveal more. Between its turns the opponents get their steal odds, so the bot takes the round with chance t / (t + (1 − t) × p_steal), and the payoff follows. V(continue later) is the same race once the wheel comes back.

### Steal odds

- For each opponent, q is the chance that seat solves correctly on its next turn, as a function of share revealed and the bot's own confidence in the board. A shared prior is fit on LLM tournament play on fresh puzzles, since self-play bots would only predict each other; version 1 uses a = −3.27, b = 2.61, c = 1.92, from 4,303 turns of three chat models. During the game, each seat's estimate updates from what it does: its solve attempts and their results, and the turns where it could have solved and didn't. The bot never uses identities.
- Opponents act in sequence around the table: p_steal = q_next + (1 − q_next) × q_after, where q_after is the following seat's chance at the board expected after the next seat's turn.

### Letters

- Information is valued in dollars: a letter's information is worth its increase in P(solving before the opponents) times the round's value.
- On a dollar wedge, call the consonant with the best p_hit × value × E[count | hit] plus information value. Buy the vowel with the best information value. On Free Play, call the letter with the best money ($500 per consonant copy) plus information value; a miss keeps the wheel.
- A consonant with p_hit near 1 (a knob) is safe to call, whatever the confidence in the full answer.

### Known answers

- At high confidence (a knob, default 0.95), a memoized dynamic program over (bank, consonants left) plans the rest of the round: which consonants to call, how long to keep spinning, and when to solve.
- Its hits are a mixture: with chance c the answer is right and every hidden consonant hits; with 1 − c it is wrong, and several calls miss together.

### Special wedges

- Mystery: the value function picks keep, k × $1,000, or flip: half the time $10,000 and the bot keeps the wheel, half the time Bankrupt.
- Express: board only when the bot is sure enough to succeed, when the value function, counting the chance that the final solve is right, favors playing over passing. Then ride while safe consonants remain, calling them, and solve.
- Wild Card: spend it when the extra consonant is worth more than the card's saved value, which is its value in the bonus round times P(reaching the bonus round).

### Bonus round

- Picks: brute force every legal set (3 consonants and 1 vowel, plus a 4th consonant with the Wild Card), scored by the chance that the reader's best guess after the reveal is right. Reveal patterns that only out of vocabulary answers fit are worth about zero.
- Solve: the reader's best guess.

### Data

- wordfreq, Wiktionary multiword entries, Wikidata labels filtered by sitelinks, the CMU Pronouncing Dictionary, word pair counts from Tatoeba's English sentences and Simple English Wikipedia, and fastText vectors for category fit. Google Books n-grams were dropped: their 2-gram files alone stream about 233 GB.
- No Wheel of Fortune puzzle archives, and never `dev.json` or `private.json`.
- A fetch step streams each source and prunes it into numpy or SQLite files under `data/`, which git ignores. Nothing is stored whole, and the pruned files stay under 2.5 GB in total. The bot loads them once per process.

## Self-play

- `python -m rstlne.selfplay` plays bot-only games. It tunes the knobs, builds the win chance table, fits the steal prior, and fits the reader's confidence calibration.
- Every job splits into shards (`--shard i/n`) so several machines can share it, writes compact JSONL, resumes where it stopped, and prints a status line every 2 minutes with an estimated finish. No job calls an API.
- `games` plays bot-only games between three bot variants, each a name and knob changes (`eager:eager_solve=0.65`), with duplicate scoring: each set's six games share its seed and puzzles, one per seat ordering. Variants share one reader, so they can only change decision knobs. Each game is one line: who sat where, final totals, totals after each main round, the bonus, and each seat's solve attempts, correct solves, board shown when solving, and Bankrupts. `games-summary` gives each variant's win rate with 95% intervals from resampling whole sets, results by seat, money, bonus, and solving, and the gap between each pair.
- `tune-decisions` tunes the decision knobs (the known-answer threshold, the safe-letter bar, the tie margin, the Wild Card's bonus lift, and the assumed bonus solve rate) one at a time. Each candidate value plays as a variant against the current settings and the eager bot in the same duplicate-scored games, every comparison on the same seed. A value is adopted only if the variant's win rate beats the current one with its 95% interval clear of zero; otherwise the current value stays, and later knobs start from what was adopted. `--knobs` limits the run to some of these knobs, comma separated.
- `win-table` builds P(finish first | lead, rounds left) from bot games: every seat at every round boundary gives its lead over the best opponent and whether it finished first after the main rounds, ties shared. Leads group into $1,000 bands, sparse bands are dropped, and the chance is made to rise with the lead. It becomes the `win_table` knob, which the bot reads from round 3 on where it has a row; elsewhere it falls back to the formula, and with no rounds left the lead decides. Large knobs load from a file: `--knob win_table=@win-table.json`.
- `eager_solve` is a self-play knob: a bot with it set solves as soon as its calibrated confidence reaches it, the way LLMs pounce (the median LLM attempt came at confidence 0.65), and plays normally otherwise. v1 leaves it off.
- `reads` reveals each puzzle in English letter frequency order, calling every letter, hit or miss, and stops once each tenth of the board shows. At each stop it records the reader's best answer, its confidence, whether it was right, and the probability it gave the true answer. Bonus puzzles are read the way the bot meets them: R S T L N E and its own picks. `summary` reports accuracy by confidence across every shard.
- `tune-reader` tunes the reader's knobs (phrase odds, name odds, category fit weight, word pair weight) one at a time over a small grid, in passes, scoring each setting by the average log probability the reader puts on the true answer across every board of the tuning puzzles. Paired knobs move together, keeping their ratio. It then scores the tuned and untuned knobs on held out puzzles, so a gain that only fits the tuning puzzles shows up.
- `calibrate` reads the tuning and held out puzzles, fits the confidence curve on the tuning puzzles' main round boards, and reports calibration error and Brier score before and after on both, with accuracy by band of confidence on the held out boards.
- `round-banks` plays bot games on a tuning batch, like `games` with three plain bots, and records each game's stealer's gain points (see Version 3). It refuses grading, dev, and private puzzle files, and notes the puzzle file in round-banks.json. `stealer-gain` fits the gain from tournament folders (`--logs`, LLM opponents) and round-banks folders (`--games`, bot opponents) into stealer-gain.json, which `--knob stealer_gain=@stealer-gain.json` reads.
- Every `games` record notes, per seat, whether the bot ever saw every move score exactly 1 or exactly 0, and how many of its choices went to dollars; `games-summary` reports how often those settled results proved wrong.
- `steal` fits the steal prior from tournament logs: every main round turn where a player had the wheel and could have solved becomes a data point, with the share of the board showing, the reader's confidence on that board, and whether the player solved correctly. It fits a, b, and c of q = 1 / (1 + e^-(a + b × shown + c × confidence)) by maximum likelihood, with 95% intervals from resampling whole sets, and reports predicted against actual solve rates, a fit per model, and where players stand when they try to solve. The fit is tied to the reader, so it runs again after the reader is tuned.
- It never tunes on `dev.json` or `private.json`. It tunes on boards generated from the phrase sources and grades on held out seeds.

## Bonus test

`python -m rstlne.bonustest --players <seat>,<seat>,... --puzzles <file> --seed <n>` plays the bonus round alone. Every player meets every bonus puzzle in the file, with no wheel and no opponents. That gives each player a pure bonus solve rate on the same puzzles. In a tournament, only the game's winner plays the bonus.

- **Players:** any seat but `human`, as many as wanted: `llm:<slug>`, `decision[:<model>]`, `bot`, `hybrid:<slug>`. A human takes the bonus round in the CLI.
- **Each puzzle:** the player sits in seat 1, with no Wild or Million card, and the bonus round runs exactly as in a game (see Bonus round), from the spin to the one solve attempt. Seats 2 and 3 are empty. The envelope comes from the puzzle's seed, so every player sees the same envelope on the same puzzle. A model starts with a fresh conversation, as it does at the start of a game's bonus round.
- **Logs:** each player and puzzle is one game log in `logs/bonustest/<folder>/<player>/puzzleNNN.jsonl`. The folder name covers the puzzle file, the seed, and the settings that change play, but not the players, so a later run can add one. A rerun skips finished puzzles. `--max-cost` stops starting new puzzles at a budget, and `--limit` takes only the first puzzles.
- **Report:** per player, puzzles solved with a Wilson 95% interval, the share of the board showing after the picks, the letters picked, refused responses, solves that don't fit the board, and cost. For each pair of players, the gap in solve rate on the puzzles both finished, with a 95% interval from resampling puzzles.
- **Puzzles:** a scoring run, like a tournament. Aired puzzles (`private.json`) and generated ones (a grading batch) can be compared directly. Never tune on the results.

## Seats

Each seat is one of five kinds.

| seat | moves and risk choices | the solve itself |
|---|---|---|
| `human` | the player at the terminal | the player |
| `llm:<slug>` | the model | the model |
| `decision[:<model>]` | a decision model | an LLM, the solver |
| `bot` | the bot | the bot |
| `hybrid:<slug>` | the bot, with the model's reading of the board | the bot, often with the model's answer |

- **`llm:<slug>`:** the model plays every move, as the LLM player section describes.
- **`bot`:** the bot plays every move and solves as the Bot section describes, bonus round included.
- **`hybrid:<slug>`:** the bot plays every move, and the model reads the board for it, as the Hybrid seat section describes.
- **`decision`:** a decision model, called through OpenRouter's Decisions API, makes every choice except the answer text: spin, buy a vowel, or solve; which consonant; which vowel; keep or flip on Mystery; pass or play on Express; whether to spend the Wild Card; and the bonus round letter picks. An LLM writes the solve answer, and only when the decision model triggers a solve. `decision:<model>` names the decision model for one seat.
  - **Solve trigger:** every turn, before any other choice, ask the decision model a yes or no question: "Can the puzzle be solved correctly from this board right now?" If P(yes) is at or above `solve_threshold`, the LLM writes the answer. A wrong answer passes the turn as usual. Otherwise, ask which action to take, with the options restricted to legal non-solve actions. Ask both questions in one call. When buying a vowel is legal, ask which vowel in the same call, and during Express mode ask which consonant too, so the pick is ready if that action wins. After each action that keeps the turn, ask again before the next action.
  - **Nothing to choose:** when only one non-solve action is legal, skip the action question and still ask whether to solve. When solving is the only legal move, skip both questions and the LLM writes the answer.
  - **Choices:** every question offers only legal options. Consonant questions list only unused consonants, and vowel questions list only unused vowels. On Free Play, the letter question lists every unused letter, consonants and vowels together. A question left with one option isn't asked, since the Decisions API needs at least two: the seat takes that option and logs it as the only option. When no question is left to ask, no call is made.
  - **Bonus round:** ask for the 3 consonants one at a time, removing RSTLNE and each pick from the options, then the vowel, then a 4th consonant if the player holds the Wild Card. Then the LLM writes the bonus solve.
  - **State:** send the public view as the decision model's state: category, spaced board, used letters, all banks, held cards, round, current wedge, the wheel as it stands, and the rules summary.
  - **Config:** set `decision_model` (any Decisions API model ID, default `openai/gpt-6-luna-decisions`), `solver_model` (any OpenRouter chat model slug, default `openai/gpt-6-luna`), and `solve_threshold` (default 0.8) in `config.toml`. `[decision.thresholds]` overrides the threshold for named decision models, because their probabilities run on different scales: Jev 1.14 gives a fully revealed board about 0.75 on average, while GPT-6 Luna Decisions gives about 0.99.
  - **Calibration:** `python -m rstlne.calibrate --models <id>,<id>` picks each decision model's threshold from data. It samples main round puzzles with a seed, reveals each one in English letter frequency order (E T A O I N S H R D L C U M W F G Y P B V K J X Q Z), and stops at several points from an empty board to a full one. At each board, every decision model gives P(solvable) from the same state and question it gets in a game, and the solver gets one solve attempt with the same view and tool, shared across the models. A model's threshold is the lowest P(solvable) at which the calibration curve reaches 80%: the solver's accuracy, fit as a never-decreasing function of P(solvable). At least 5 boards must sit at or above the threshold. The command prints the `[decision.thresholds]` lines and saves every board's results.
  - **Logging:** log the full probability distribution returned for every question, the chosen option, and the threshold. For every triggered solve, log P(yes) and whether the answer was correct, so calibration can be plotted later.

## Hybrid seat

The `hybrid:<slug>` seat is the bot with a second reader. The bot makes every move as the Bot section describes. On its own turns it asks the model whether the board looks solvable and, if so, for the answer. The model never moves and never solves on its own: a fitting answer joins the reader's candidates, and the bot decides what to do with it, including whether to milk the board before solving. The hybrid tests whether the bot's strategy plus a model's recognition beats either one alone.

In this section, "ask" means one request to the model. "Call" still means calling a letter.

### When it asks

- Once for each new board the hybrid acts on in the main rounds. A board is new when the board or the used letters change. A spin and the consonant call that follows it share one ask.
- Never on an opponent's turn.
- In the bonus round, once, after R S T L N E and the hybrid's picks are revealed. The picks themselves come from the reader alone.

### The question

- The system prompt says what a solve must be: the whole puzzle, matching the board's words, word lengths, revealed letters, and punctuation. It carries no strategy advice.
- The request holds the category, the spaced board, the compact pattern with word lengths, the used letters, and the answers wrong solves have refuted this round. It holds no banks, totals, cards, or wheel: the question is recognition only.
- One tool, required: `read_board(solvable, answer)`. `solvable` is true or false, and `answer` is required when it is true.
- Models reason at their defaults, and tool choice follows the LLM player section.
- A response with no tool call or unreadable arguments is reprompted with the error up to 2 times. After the third failure, the ask counts as "not solvable".

### Using the answer

- An answer is used only if it fits the board (the same word count and word lengths, every revealed letter and punctuation mark in place, only unused letters in hidden squares) and isn't refuted. Otherwise it's ignored and logged as not fitting or refuted. A "not solvable" reply is ignored too, and the bot reads the board alone.
- A used answer A joins the reader's sampled answers with share t, the trust: the reader's samples carry weight 1 − t and A carries t. The merged confidence in A is t + (1 − t) × the reader's probability for A. Letter odds, copy counts, and entropy come from the merged samples, so letter choice, the known answer planner, and the Express ride all follow the model's answer.
- t comes from the model's trust curve: t = 1 / (1 + e^-(a + b × shown + c × agree + d × p_reader + g × reader_best)), where shown is the share of letters showing, agree is 1 when the reader's best answer is A, p_reader is the reader's probability for A, and reader_best is the reader's confidence in its own best answer. reader_best tells a reader that is confidently sure of another answer from one that has no idea. Each model has its own a, b, c, d, g in `[hybrid.trust]` in `config.toml`. A model with no trust curve can't sit in a hybrid seat.
- Steal odds use the model's steal curve instead of the bot's: q = 1 / (1 + e^-(a + b × shown + c × reader_best + d × readable)), where readable is 1 when the hybrid's latest ask on this board got a fitting answer. A board the model can read is likely readable to LLM opponents too, even when the reader can't read it, and the bot's curve would miss that. Each model has its own a, b, c, d in `[hybrid.steal]` in `config.toml`. Everything else about steal odds follows the bot: each opponent's estimate scales during the game from what it does, and opponents act in sequence. When it scales an opponent's estimate, the hybrid uses the verdict from its latest ask this round, or 0 before its first ask, since it never asks on an opponent's turn.
- A wrong solve refutes its answer, as for the bot. A refuted answer is listed in the next ask and never used again that round.
- Bonus solve: the best answer of the merged candidates.

### Logging

- The header records the bot version, its data fingerprint, the model slug, temperature, and any pinned provider.
- Every ask logs the board, the reply, whether the answer was used (or why not), t, the reader's and the merged confidence, token usage, and seconds taken. Usage totals per game, and a tournament's `--max-cost` counts it.

### Trust curves

`python -m rstlne.calibrate trust --models <slug>,<slug> --logs <tournament folders>` measures each model's trust curve on real game boards.

- Boards: main round turns on which a player had the wheel and could have solved, taken from the given finished tournament games, which hold the true answers. It samples 2,000 turns by default, an equal number from each tenth of the share showing (all of a tenth that has fewer), with a seed. Each distinct board is asked once. The refuted answers each board's ask lists are the ones refuted at that point in the logged game.
- Each board gets the exact hybrid question from every model, and the bot's reader reads it. Every ask is saved under `trust-asks/` in the output folder as it completes, with the temperature, reasoning effort, and provider it ran with. A rerun reuses the saved asks that match, so a stopped run picks up where it left off. A board that gets no reply at all, after the usual retries, is left out of the run and not saved, the report counts it, and a rerun asks it again. A model that replies but fails the format 3 times is data, not an outage: that ask counts as failed and is saved.
- Each ask records: the share showing, whether the model said solvable, its answer, whether it fits, whether it was right, the reader's best answer and confidence, whether they agree, the reader's probability for the model's answer, whether the logged player on that turn solved correctly, tokens, cost, and seconds.
- The trust fit: a, b, c, d, g by maximum likelihood on the asks that said solvable with a fitting answer, with 95% intervals from resampling whole puzzles.
- The steal fit: a, b, c, d by maximum likelihood on every sampled board, from whether the logged player solved correctly on that turn, with the same intervals.
- The report, per model:
  - the share of asks that said solvable, and their accuracy, by tenth of the board showing
  - disagreements: boards where the reader's confidence is at least 0.95 and the model gives another fitting answer, and how often each was right
  - agreeing and wrong: boards where the model's answer is the reader's best answer and both are wrong, by tenth of the board showing and separately for a reader at 0.95 or more. This is the risk behind riding the Express on an answer both believe
  - the steal curve with and without readable, and how much readable moves the odds
  - the share of answers that don't fit the board
  - cost and seconds per ask, and an estimated cost per game at 15 asks
  - the `[hybrid.trust]` and `[hybrid.steal]` lines to paste into `config.toml`
- `--held-out <tournament folders>` checks a fitted curve on other boards, reporting predicted against actual accuracy without refitting.
- Fit only on tournaments played on tuning puzzles. Grading puzzles may serve only as the held-out check.

## Human player (CLI)

- Print the board, category, used letters, all banks, the wheel as it stands, and the wedge after each spin.
- Accept short commands: `s` to spin, `v E` to buy a vowel, `solve <answer>`, `keep`, `flip`, `pass`, `play`, `wild`.
- In the bonus round, accept picks as `B G H I` and start a 10 second timer for the solve. A solve entered after 10 seconds counts as wrong.
- A human's typo or illegal move just reprompts. The three-strike rule applies to models only.
- Show model turns as they happen, with a short pause, so the game reads like a show.
- Add a `--show-thinking` flag that prints each model's raw response.
- Add a `--live` flag that redraws one fixed screen after every move: the board as tiles, unused letters, each seat's bank, total, cards, and latest thinking, and the recent moves. It falls back to plain lines when output is not a terminal. With a human seat, the screen is cleared and drawn again after every move instead of updating in place, and the human's prompt sits under it; a typo's hint and the bonus round's 10-second clock show there too. The thinking column stays hidden while a human plays, since a model's or the bot's thoughts would show its best guess.
- After a correct solve, show the solved board and hold it for `solve_pause` seconds (default 10, in `config.toml`) before the next round starts: on the `--live` screen, and in plain output with `--show-puzzle`. `--pause 0` skips the hold. When the game ends, the `--live` screen reveals the last puzzle.
- Add a `--show-puzzle` flag that prints the public table after every move: board, category, used letters, banks, totals, held cards, and wedge. It never shows the answer.

## Puzzles

- Store puzzles as `{"category": "...", "answer": "...", "bonus": false}`.
- Real show puzzles likely sit in model training data. Use them only in `dev.json`. Score tournaments on `private.json`, written fresh by Ian, or on generated puzzles.
- Normalize answers to uppercase letters, spaces, and basic punctuation. Punctuation shows on the board from the start.

### Generated puzzles

- `python -m rstlne.puzzlegen` writes fresh puzzles on demand, and `--puzzles generate` makes a tournament's whole pool before its first game. It prints a line when it starts, a line per category as each fills, a status line every 2 minutes (the category's progress, requests, cost so far, puzzles accepted overall, and time elapsed), and a summary of rejections at the end. A request that fails or takes over 60 seconds is skipped; five failures in a row stop the run. The batch file is rewritten after every accepted puzzle, so it always matches the registry, and rerunning the same command tops it up. `--recheck FILE --against FILE...` holds an existing batch to the current checks, dropping near repeats of the hand-written puzzles, of the other files, and of itself, bonus puzzles that are too short or too easy, and misspelled answers, then a rerun of its command tops it up. `--rejudge` also sends every puzzle back to the current judge; the batch then names that judge, since every puzzle left has passed it, and its history records the judge before.
- A generator model writes the answers and a judge model checks each one. Both are cheap, and both come from labs apart from every player model: MiniMax M3 generates and GLM 4.7 judges, set in `[puzzlegen]` in `config.toml`. Mistral Small 3.2 generated every batch before 2026-10-29; MiniMax M3 replaced it after a trial on hard bonus answers, where it wrote the most that were both hard and familiar. It runs on Together, one of the few MiniMax hosts that accept a JSON schema. Gemma 3 27B judged every batch before 2026-10-29. GLM 4.7 replaced it after a trial of nine judges on grading-303's 250 answers: it caught 17 of the 18 that shouldn't have passed and kept 92% of the good ones, where Gemma 3 27B caught 3. It runs on DeepInfra's FP4 build, since only FP4 hosts of it accept a JSON schema.
- Every request stands alone: a short system prompt and one request, never a growing conversation. The prompts never mention the show. A request names the category in plain terms, asks for a batch of 10 answers as JSON, and carries a few seeded everyday topics for variety, which it may ignore; every request draws fresh topics. A main request asks for three to six words with at least 16 letters, fitting the board; a bonus request asks for two to four everyday words with at least 10 letters. The system prompt asks for natural English: a well-known saying, name, or title, or a vivid everyday description whose words go together, as aired puzzles are.
- Prompt version 6 (2026-10-30) brought generated puzzles in line with aired ones. Compared with 8,856 aired main puzzles and 2,153 bonus puzzles from 2013 to 2025, earlier batches matched their letters (44% R S T L N E, 37% vowels) but were too short (median 13 letters against 20), leaned on idioms (23 to 32% Phrase against 13%), and their bonus puzzles were too easy (Mistral Small) or too hard (MiniMax M3 under version 5: 59% hidden after R S T L N E and C D M A against 52%, with rarer words).
- Few-shot examples: each request shows three examples of its category, chosen by seed from `rstlne/puzzle_examples.py`, which holds three to six per category. They were written for this project in the style of aired puzzles and checked against the archive of aired puzzles, the hand-written puzzles, and every generated batch; any that matched or nearly matched was replaced. Songs, quotations, and titles in them come from public-domain works. Every example counts as already used, so the generator can't hand one back. The judge sees twelve worked verdicts before each answer, from the same file.
- Songs, quotations, titles, headlines, and characters must be real. For those categories the generator names each answer's source (song and artist, film, book and author, speaker, or event and year), the judge rates how sure it is that the exact words are real and come from that source rather than how common they are, and the batch file keeps the source beside the puzzle. Such an answer must pass the judge twice: in the first v6 trial a single call let two invented lyrics through, which the same judge rejected every time it was asked again. Song categories ask for album tracks and lesser-known songs by well-known artists rather than the most famous hits.
- Both models are pinned to one host in `[providers]`, as player models can be, and up to 16 judge calls run at once. The judges stay busy across generator replies: while verdicts are pending, the generator is asked for more answers only when the ones with the judge couldn't fill the category even if all passed.
- The category mix follows aired puzzles from 2013 to 2025: each category's share, for the 35 main categories and 16 bonus categories with a description, covering 90% of aired main puzzles, set in `config.toml`. Batches before prompt version 6 followed `dev.json`'s proportions.
- Code checks every answer before the judge sees it:
  - it normalizes to board text
  - a main puzzle wraps into the board's rows of 12, 14, 14, and 12 squares without splitting a word, and has enough letters; a bonus puzzle fits 2 rows of 14 squares and has at least 10 letters, a phrase like JUMBO SHRIMP rather than one short word; a main puzzle has at least 16 letters, near the shortest tenth of aired ones (all set in `config.toml`; 8 before prompt version 6)
  - a bonus puzzle isn't too easy: with R S T L N E and C D M A showing, the most common picks, at least 45% of its letter squares stay hidden, as 76% of aired bonus puzzles do; a trial at 40% averaged 47% hidden against the show's 52%. FUZZY SOCKS keeps 70% hidden and passes; LEATHER WALLET keeps 15% and fails. From 2026-10-29 to prompt version 6 the bar was half, with requests for less common letters, which made bonus puzzles harder than aired ones; batches made before 2026-10-29 had no bar, and their players solved about 97% of bonus puzzles
  - Same Letter words all start with one letter, and aren't one word repeated; Rhyme Time has two words that rhyme; Same Name has a shared ending after the &; Before & After has at least three words; What Are You Doing? has an ING word
  - it doesn't come near any puzzle in `dev.json`, `private.json`, the batch, or any earlier generated set. Near means the same main words in any order, ignoring case, punctuation, articles, and plurals (IT'S RAINING and ITS RAINING; BIG BROWN BEAR and BEARS), or one answer's main words running inside another's and covering at least half of them (LET SLEEPING DOGS in LET SLEEPING DOGS LIE, but not ON THE ROCKS in SEA LIONS SUNBATHING ON THE ROCKS). Every accepted answer joins `puzzles/generated/seen.txt`, so no puzzle ever comes back.
  - a contraction keeps its apostrophe: DONT and ITS NOT fail
  - every word is spelled as the bot's word data knows it: a wordfreq word, or a word of one of its phrases or names. WAKIKI BEACH and SPAGHETTI BOLGNESE fail. Without the word data, this check is off
- The judge must say the answer fits its category and rate it at least 4 of 5. Rhyme Time needed 5 of 5 before prompt version 6; on aired puzzles that kept 9 of 31 Rhyme Time puzzles where 4 kept 15, and both bars caught every made-up rhyme. From prompt version 6 the rating asks how natural the wording is (5 a well-known expression, 4 natural wording people would say or write, 3 understandable but forced), and the judge accepts natural descriptions as aired puzzles do; before, it was told to be strict and pass only common fixed phrases, a bar tuned on the idiom-heavy `dev.json` that aired puzzles don't meet. For Before & After and Same Name it names the two phrases, and code checks they rebuild the answer; a hyphen counts as a word break, and an article opening the second phrase may drop (MORE THAN MEETS THE EYE + THE EYE DOCTOR).
- A batch file keeps its history: one entry per run, with its rejections, the judge's reasons, and its cost, and every recheck with what it dropped. A tournament's generated pool is saved in its folder the same way, and a rerun reuses it. A pool that comes up short stops the tournament before any game, and the rerun tops it up: puzzles are never reused. Generated puzzles stay out of git, in `puzzles/generated/`, like `private.json`.

## Logging

Write one JSONL file per game to `logs/`. The header records each bot seat's version. Each line records the state before the action, the seat, the raw model output, the parsed action, the result, the wedge, and token usage.

Every main round solve also records its timing: the share of letters showing, the consonants still hidden and the squares they fill, and the money left on the table, which is those squares times the round's average spin value with Bankrupt and Lose a Turn counted as $0. The game summary totals each seat's correct solves, average board shown at a correct solve, and money left.

## Phase 2 (planned)

- Local web page with FastAPI, reusing the engine and player interface.
- Tournament report: win rate, average banked, invalid action rate, and solve completion percentage per model.
- Risk report: Mystery flip rate against the B < 10000 − 2000k rule, and Express ride rate against how much of the board was revealed. A model that rides the Express and bankrupts on a mostly empty board shows a calibration failure.