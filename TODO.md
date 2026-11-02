# To do (2026-11-02, v5 frozen)

Commands for every lineup are in `GRADING_PLAN.md`.

## The v4 checkpoint (done, 2026-11-01)

The findings, claims, statistics, and charts are frozen on bot v4. Nothing below changes them; later results are reported beside them, marked with their bot version.

Every planned lineup but 6c ran: 1, 2, 3, 3b, 3c, 3d, 3f (the Haiku hybrid, in place of the stopped DeepSeek hybrid 3e), 6a, 6b, and the decision seats d1 (d1-ultra) and d2 (Luna Decisions). Recorded in `FINDINGS.md`, `GRADING_PLAN.md`, `CLAIMS.md`, `STATS.md` and `HANDOFF-UPDATE.md`, with charts 1–12. The memory probe found no sign that models remember aired bonus puzzles.

## Next: the v5 phase

1. **Build the reading fixes** and test them offline on tuning puzzles. Done: R1–R7 built, tuned, and calibrated (`documentation.md`, Version 5).
2. **Build the Express fix.** Done: E1 (safe vowels while riding) built; E2 measured on 130 self-play rides, whose estimates ran low (76% estimated, 88% solved), so no correction (Ian, 2026-11-02).
3. **v5 frozen 2026-11-02.** Now: self-play it against two v4 bots on grading-505 (the grid's deck; grading-202's puzzles are too short to show the reading fixes): v5 in 2,004 games. Done: v5 41.7% against v4's 29.1%, gap +12.6 (95% +9.6 to +15.6); solves right 96.8% against 89.4%, bonus 94.9% against 87.0%, Express rides solved 87% against 64%. The split runs (reading fixes alone, Express fix alone) were dropped (Ian, 2026-11-02). Bot-only play mainly shows "no worse"; bots don't exploit slow reading. Each run also records both versions' Express rides on the same puzzles.
4. **Hybrid curves for v5:** done, free (`[hybrid.trust.v5]`, `[hybrid.steal.v5]`). The model's room to add shrinks by a quarter (Luna, DeepSeek) to two-fifths (Haiku).
5. **Lineup 2 with v5 bots:** done (2026-11-02, $5.86). Sol won 49% against v4's 58%; its lead over each bot fell from 37 to 23 points, mostly on long puzzles. v5 adopted the same day. Next: a v5 addendum in `FINDINGS.md`, beside v4's numbers.
6. **Later, maybe v6:** the ride estimate plans only letters safe at boarding, while rides keep finding more (about 5 calls against 4 planned), so it runs low. Counting the letters that turn safe as each one shows, from the answers the bot already holds, would make it honest without a fitted correction.

### What v5 fixes

- **The Express.** In 249 rides across the grid the bot busted 107 (43%): it boarded 106 times while under 50% sure and solved only 20% of those, and it never bought a vowel while riding, since its Express rule is "call every safe consonant, then solve". Two changes: let it buy a vowel ($250) when one separates its top answers, and board on its measured Express success, not the optimistic estimate (which assumes the safe consonants will make the answer clear). The hybrids, with the LLM's read, busted 2 of 20.
- **Word pairs it never saw.** In the bonus test its vocabulary covered every word of all three decks, and it solved every generated puzzle whose adjacent word pairs all appear in its pair data; every generated-deck miss had a pair it never saw (72–74% solved there; 54% on aired puzzles). Without pair counts it falls back on word frequency: JUMP WOOL SOCKS for DAMP WOOL SOCKS, BOBBY WINDSHIELD for FOGGY WINDSHIELD. Two steps, measured on tuning puzzles only: (1) pair counts from a much bigger corpus than Tatoeba and Simple English Wikipedia, such as full English Wikipedia or Google Books bigrams; (2) score an unseen pair by how close its word vectors are, as the reader already does for category fit. A small language model scoring whole answers would fix more, but it puts an LLM inside the bot, so that's Ian's call.
- **The gap on aired bonus puzzles.** Of the 10 aired bonus misses where the bot had seen every word pair, the causes were:
  - **A bug: one-letter words.** The vocabulary holds all 26 letters as words (frequency lists keep the S of "it's", the T of "don't"), and ranks I as the rarest, so it read B HAVE NO IDEA and A BOUGHT A VOWEL. Allow only A, I and O. 1.3% of aired puzzles hold the word I (340 times, against 2,093 for A); the grading deck has 6 of 500.
  - **Single-word answers** (3 misses): no pairs to go on, so word frequency decides among fitting words (HAVING over WAVING for What Are You Doing?, WAIVER over JUICER). Category fit should weigh more here. Aired bonus puzzles are sometimes one word (5 of 100); generated ones never are, since the generator asks for a phrase.
  - **Pairs that each make sense, wholes that don't** (4 misses): COME DOWN THE PARTY, HAVING A POUND CAKE, BIAS AND PYTHONS. The reader scores a chain of word pairs, so it never sees the whole phrase, and it was 93–97% sure of three of them, which also says its confidence is off on these.
  - **A rarer near-miss** (1): CUSP for WISP, with almost equal pair counts.
- **Long puzzles.** v4 needed 59% of the board on 16–17-letter puzzles and 68% on 27+, where LLMs stayed near 50%: more words means more pairs to miss, and the chain only links neighbours. R2 and R3 help; R7 adds whole-answer coherence from the word vectors (BAKING … CAKE), and the reading summary now breaks results down by length to show whether the gap narrows. If long puzzles still lag, try more samples for boards with many open slots (the `samples` knob, 400 now).
- **Refit** the win table and the stealer's gain under the round 4 start rule.

## Phase 2: the local web page

A solver first: enter a board, letters, and banks, and get each player's advice. Then full games in the browser. The engine stays untouched.

## Optional, at the checkpoint

- **6c** (bot, two DeepSeeks): about $10, slow.
- Lineups **4** (Sol, hybrid, bot) and **5** (Sol, two hybrids): Sol and the hybrid at one table. About $13.
- Lineup 2 rerun with v3 bots: does v4 help against an LLM? About $6.
- The write-up for a wider audience (blog post or paper), framed by the four questions; `FINDINGS.md` is the base.

## Waiting for a grant

- Gemini 4 Argon, Gemini 3.8 Flash, Sonnet, Opus, Fable, GLM 5.3. Argon's and Flash's set 0 trials are done, on the laptop.
- Apply for OpenAI's Researcher Access Program (up to $1,000), framed around model behaviour.

## Later

- Tighten the puzzle generator's near-repeat check.
