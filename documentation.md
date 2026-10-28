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
- Tournament mode plays each puzzle set three times with the seats rotated, so every model sits in every position against the same spins. This is duplicate bridge scoring. It strips most of the luck out of model comparisons.

## LLM player

- Use only models that support tool calling: their `supported_parameters` on OpenRouter include `tools`.
- Send the rules once in the system prompt. Send the public view each turn, with a short recap of what the other seats did since the model's last move.
- Render the board with spaces between characters: `_ _ E _ L   _ _ _`. Show word boundaries with three spaces.
- Also show the board as a compact pattern with each word's length, such as `Pattern: A ____ TAN_ __ _A_ (word lengths 1, 4, 4, 2, 3)`, so models don't have to count spaced tiles.
- Every model reasons at its own default. Claude models get reasoning turned on with no effort level, which runs their native adaptive thinking, because OpenRouter leaves it off unless asked. Other models already reason by default. `reasoning_effort` in `config.toml` can set one level for every model instead. A thinking Claude model gets `tool_choice: auto` in place of a required tool call, because forcing a call switches its thinking off; a reply without a tool call gets the usual reprompt.
- Moves are tool calls. Each request offers only the tools that are legal right now and requires one call: `spin`, `buy_vowel(letter)`, `solve(answer)`, `call_consonant(letter)`, `call_letter(letter)` on Free Play, `keep` or `flip` on Mystery, `pass` or `play` on Express, `use_wild(use)` after a correct consonant while holding the Wild Card, and `bonus_picks(consonants, vowel)` and `bonus_solve(answer)` in the bonus round.
- Letter arguments are plain strings. The engine checks them, so every model faces the same validation whatever its provider enforces.
- Only the first tool call in a response counts. Log any extra calls.
- A spin takes two calls. The model calls `spin`, the tool result reveals the wedge, and the model then calls `call_consonant`. The model sees the wedge value before it picks.
- During Express mode, the tools shrink to `call_consonant`, `buy_vowel`, and `solve`. Say so in the view.
- Bonus round picks take one call, with 4 consonants when the model holds the Wild Card. The solve takes one more call.
- The `solve` and `bonus_solve` tools say that the answer is the whole puzzle and must match the board: the same words, word lengths, revealed letters, and punctuation. A wrong solve passes the turn.
- On a response with no tool call, a tool that isn't on offer, unreadable arguments, or an illegal move, reprompt with the error up to 2 times. After the third failure, pass the turn. On a keep or flip, pass or play, or Wild Card prompt, the third failure takes the safe choice (keep, pass, don't spend the card) and then passes the turn. During Express mode, the third failure counts as Bankrupt. In the bonus round, failed picks reveal no extra letters and the solve still happens. A failed bonus solve counts as wrong.
- Log every invalid response with its category: bad tool call, not a letter, vowel on a spin, consonant on a vowel buy, insufficient funds, malformed solve, bad bonus picks. Also log repeated letters as their own category, but never reprompt them: a repeated letter is a legal call that takes the game penalty. Likewise log a wrong solve that doesn't fit the board (wrong word count, wrong word length, a revealed letter changed, a used letter in a hidden square, or punctuation changed) as "solve doesn't fit the board". It still takes the wrong solve penalty. Report these separately from game outcomes.
- Keep the conversation history per round so the model remembers its own reasoning. Reset it each round.

## Baseline bot

The bot gives every model a floor to beat.

- Call consonants in English frequency order, skipping used letters. On Free Play, call the next consonant in that order.
- Buy a vowel when the bank allows it and no consonant has been revealed in the last 2 turns at the table, counting every seat's turns. Buy vowels in the order E, A, O, I, U, skipping used ones.
- Load the 50,000 most common English words from the `wordfreq` package. Set the count in `config.toml`. A candidate phrase is a phrase of list words that fits the board: every revealed letter in place, and no used letter in a hidden spot. The best candidate is the one whose words are most common.
- Solve when the board matches exactly one candidate phrase. Otherwise keep spinning. This solve rule applies in configuration 4; see Player configurations.
- When a spin risks a large round bank, apply the threshold rule: stop when the expected spin gain is below P(Bankrupt) times the bank.
  - Expected spin gain = (average spin value) × P(hit) × E[count].
  - The average spin value is the mean over the round's wheel in `wheel.toml`, with Bankrupt and Lose a Turn counted as $0. Recompute it each round.
  - P(hit) is the share of candidate phrases that contain the bot's next consonant. E[count] is that consonant's average count in the candidates that contain it.
  - P(Bankrupt) is 1/9 in rounds 1 to 3 and 1/12 from round 4 on, the Bankrupt share of each round's wheel as it starts.
  - On a stop, the bot buys a vowel if it can. Otherwise it solves with its best candidate, and with no candidate it spins anyway. In configurations 2 and 3 it never solves on a stop: it buys a vowel if it can, and spins otherwise.
- On Mystery, flip when the round bank B satisfies B < 10000 − 2000k, where k is the letter count. Count the Wild Card and Million card inside B at a value set in `config.toml`.
- On Express, play only when the board matches exactly one candidate phrase.
- In the bonus round, pick the consonants and vowel that appear in the most surviving candidates, then answer with the best candidate.
- Keep the Wild Card for the bonus round. Never spend it in a main round.

## Player configurations

A model seat runs one of five configurations. Configurations 2, 3, and 5 split the seat's decisions between two players.

| configuration | letters, vowels, and risk choices | when to solve | the solve itself |
|---|---|---|---|
| 1 | model | model | model |
| 2 | bot | model | model |
| 3 | bot | bot | model |
| 4 | bot | bot | bot |
| 5 | decision model | decision model | model |

- **Configuration 1:** the model plays every move, as the LLM player section describes.
- **Configuration 2:** the bot plays every move except solving. At each point in the seat's own turn where solving is legal and the board has changed since the model last declined, the model gets one call with two tools, `solve(answer)` and `keep_playing`. When solving is the only legal move, it gets `solve` alone.
- **Configuration 3:** the bot plays every move and decides when to solve, ignoring its word list for that choice. It solves when at least 70% of the puzzle's letters are revealed, or when no consonants remain, whichever comes first. Set the 70% in `config.toml`. The model then gets one call with the `solve(answer)` tool and writes the answer.
- **Configuration 4:** the bot plays alone and solves by the rule in the Baseline bot section.
- In the bonus round, the bot picks the letters in configurations 2 to 4. The seat that writes solves in that configuration writes the bonus solve.
- **Configuration 5:** a decision model, called through OpenRouter's Decisions API, makes every choice except the answer text: spin, buy a vowel, or solve; which consonant; which vowel; keep or flip on Mystery; pass or play on Express; whether to spend the Wild Card; and the bonus round letter picks. An LLM writes the solve answer, and only when the decision model triggers a solve.
  - **Solve trigger:** every turn, before any other choice, ask the decision model a yes or no question: "Can the puzzle be solved correctly from this board right now?" If P(yes) is at or above `solve_threshold`, the LLM writes the answer. A wrong answer passes the turn as usual. Otherwise, ask which action to take, with the options restricted to legal non-solve actions. Ask both questions in one call. When buying a vowel is legal, ask which vowel in the same call, and during Express mode ask which consonant too, so the pick is ready if that action wins. After each action that keeps the turn, ask again before the next action.
  - **Nothing to choose:** when only one non-solve action is legal, skip the action question and still ask whether to solve. When solving is the only legal move, skip both questions and the LLM writes the answer.
  - **Choices:** every question offers only legal options. Consonant questions list only unused consonants, and vowel questions list only unused vowels. On Free Play, the letter question lists every unused letter, consonants and vowels together.
  - **Bonus round:** ask for the 3 consonants one at a time, removing RSTLNE and each pick from the options, then the vowel, then a 4th consonant if the player holds the Wild Card. Then the LLM writes the bonus solve.
  - **State:** send the public view as the decision model's state: category, spaced board, used letters, all banks, held cards, round, current wedge, and the rules summary.
  - **Config:** set `decision_model` (any Decisions API model ID, default `typesafe/jev-1.14`, pinned so results don't shift with new releases), `solver_model` (any OpenRouter chat model slug, default `openai/gpt-6-luna`, the solver in every configuration), and `solve_threshold` (default 0.8) in `config.toml`.
  - **Logging:** log the full probability distribution returned for every question, the chosen option, and the threshold. For every triggered solve, log P(yes) and whether the answer was correct, so calibration can be plotted later.

## Human player (CLI)

- Print the board, category, used letters, all banks, and the wedge after each spin.
- Accept short commands: `s` to spin, `v E` to buy a vowel, `solve <answer>`, `keep`, `flip`, `pass`, `play`, `wild`.
- In the bonus round, accept picks as `B G H I` and start a 10 second timer for the solve. A solve entered after 10 seconds counts as wrong.
- A human's typo or illegal move just reprompts. The three-strike rule applies to models only.
- Show model turns as they happen, with a short pause, so the game reads like a show.
- Add a `--show-thinking` flag that prints each model's raw response.
- Add a `--live` flag for model-only games that redraws one fixed screen after every move: the board as tiles, unused letters, each seat's bank, total, cards, and latest thinking, and the recent moves. It refuses a human seat, and it falls back to plain lines when output is not a terminal.
- After a correct solve, show the solved board and hold it for `solve_pause` seconds (default 10, in `config.toml`) before the next round starts: on the `--live` screen, and in plain output with `--show-puzzle`. `--pause 0` skips the hold. When the game ends, the `--live` screen reveals the last puzzle.
- Add a `--show-puzzle` flag that prints the public table after every move: board, category, used letters, banks, totals, held cards, and wedge. It never shows the answer.

## Puzzles

- Store puzzles as `{"category": "...", "answer": "...", "bonus": false}`.
- Real show puzzles likely sit in model training data. Use them only in `dev.json`. Score tournaments on `private.json`, written fresh by Ian.
- Normalize answers to uppercase letters, spaces, and basic punctuation. Punctuation shows on the board from the start.

## Logging

Write one JSONL file per game to `logs/`. Each line records the state before the action, the seat, the raw model output, the parsed action, the result, the wedge, and token usage.

## Phase 2 (planned)

- Local web page with FastAPI, reusing the engine and player interface.
- Tournament report: win rate, average banked, invalid action rate, and solve completion percentage per model.
- Risk report: Mystery flip rate against the B < 10000 − 2000k rule, and Express ride rate against how much of the board was revealed. A model that rides the Express and bankrupts on a mostly empty board shows a calibration failure.