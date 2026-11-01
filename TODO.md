# To do (2026-10-31)

Commands for every lineup are in `GRADING_PLAN.md`.

## Today

1. **6b** (bot, two Haikus) and **3c** (DeepSeek alone, two bots): about $9.
2. **3e** (DeepSeek hybrid, two bots) and **6c** (bot, two DeepSeeks): about $13, slow.
3. Report the grid, then update `GRADING_PLAN.md` and `HANDOFF.md`.
4. Redraw the charts with DeepSeek in: `uv run --with matplotlib python figures/make_figures.py figures`.

## Optional

- Lineups **4** (Sol, hybrid, bot) and **5** (Sol, two hybrids): Sol and the hybrid at one table. About $13; skipped for now.
- Lineup 2 rerun with v3 bots: does v4 help against an LLM? About $6.
- Blank-board memory probe on aired bonus puzzles: about $1.
- **Decision seat with d1-ultra** (the top of Artificial Analysis's Decision Index) alone against two bots, Luna writing the solves: about $2. In choice mode (config's default) d1-ultra decides when to solve itself, so it needs no calibration: `--seats decision:liquid/d1-ultra,bot,bot`. Same reader, three deciders: Luna itself (17.5%), the bot (the hybrid, 45%), or a decision model.

## Waiting for a grant

- Gemini 4 Argon, Gemini 3.8 Flash, Sonnet, Opus, Fable, GLM 5.3. Argon's and Flash's set 0 trials are done, on the laptop.
- Apply for OpenAI's Researcher Access Program (up to $1,000), framed around model behaviour.

## Later

- Bot v5: refit the win table and the stealer's gain under the round 4 start rule. The grid stays on v4; no lineup needs redoing. Check v5 against v4 in self-play first, and rerun only the lineups where the bot's strength matters (2 and the solo yardsticks), reported as a v5 update. Probably not worth it before the write-up.
- Tighten the puzzle generator's near-repeat check.
- The write-up, framed by the four questions.
