# Toss-up plan

**Status:** an idea, not in the spec yet. Do this after the v3 faceoff and the `grading-505` puzzles are done.

## On the show

- **Introduced:** in 2000.
- **How it works:** letters appear one at a time in random order, and the first contestant to ring in with the right answer wins the cash.
- **One try each:** each contestant rings in once per puzzle at most. A wrong answer locks them out while the others keep watching.
- **No winner:** if the last letter appears and nobody has solved it, there's no cash.
- **Values, 2019 to 2026:**
  - $1,000, then $2,000.
  - Then a Triple Toss-Up before round 4: three puzzles at $2,000 each, plus $4,000 for solving all three.
  - The Triple Toss-Up winner spins first in the next round.
- **Season 44 (2026):** "Fortune Frenzy" replaces the first two toss-ups with a 30-second race, $1,000 per puzzle.

## Why we want it

A toss-up is solve timing with nothing else in the way. There's no wheel and no money decisions, just one question: ring in now, or wait for more letters and risk someone beating you? It shows how eager each player is: LLMs tend to jump in early and the bot tends to wait.

## Proposed design

1. **Reveal step by step.** Each step shows one more letter, in a seeded random order.
2. **Ask everyone at every step.** Each player still in the puzzle says "ring in with this answer" or "wait".
3. **Earliest step wins.** The earliest correct ring-in takes the puzzle.
4. **Ties go to the fastest thinker.** If several players ring in on the same step, the one who wrote the fewest tokens, reasoning included, goes first.
   - Tokens measure the model, not the host. Wall-clock time depends on the host: the same model ran 3× faster on one host than another.
   - Tokens are logged, so a replay gives the same result. Wall-clock time doesn't.
5. **A wrong ring-in locks that player out** for the rest of the puzzle.

There's no real clock, so a slow host never costs anyone a puzzle.

## Questions for Ian

| # | Question | Example | My suggestion |
|---|---|---|---|
| 1 | Who wins a tie? | 4 of 18 letters showing. Terra rings in after 60 tokens, DeepSeek after 900, and both are right. | Terra |
| 2 | What happens when the first ring-in in a tie is wrong? | Terra is first but wrong, and DeepSeek is right on the same step. | DeepSeek wins at once, as on the show |
| 3 | How fast is the bot? | It thinks in milliseconds, so it would win every tie. | Zero tokens, or a fixed reaction time |
| 4 | Where do toss-ups go in a game? | | Before round 1 and before round 4, as on the show |
| 5 | What are they worth? | | $1,000, $2,000, then a triple at $2,000 each, plus $4,000 for all three |
| 6 | Real seconds when you play live? | Tournaments use tokens. | Your call |

## Build order

1. Write the spec section in `documentation.md`.
2. Write the tests.
3. Build it.
4. Run a small test: one model, a few toss-ups, to check the cost.

## Cost and data

- **Cost:** asking every player at every step adds up to roughly 15 steps × 3 players per puzzle. That's fine for cheap models but could double what a game costs. To save money, ask every second step, or stop asking a player once it has rung in.
- **Data:** the archive of aired puzzles holds about 10,000 toss-ups (rounds T1 to T5). They're good for a private real-puzzle test. Never publish or commit them.
