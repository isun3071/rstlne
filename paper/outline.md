# Paper outline (draft for Ian's approval)

Working title: Can a Language Model Play Wheel of Fortune? Reading, Risk, and When to Solve

Format: arXiv preprint in LaTeX, about 8 pages plus appendices. Every number comes from `paper/numbers.json` (made at commit 84734ad, with Ember). Each claim below names its source: the JSON path in `numbers.json`, then the figure. "Gap" marks a number that `numbers.json` doesn't hold yet, or a citation we still need.

Notation: `L[2].Sol` means `lineups["2"].entrants["llm:openai/gpt-6.1-sol"]`. `P["…"]` means the pair with that label in `pairs`.

## Abstract (about 150 words)

The abstract has one sentence for each of the four questions, plus cost:
- Every model finished every game.
- Against two copies of our bot, only GPT-6.1 Sol and Terra won more than a third of games (46.1%, 45.3%).
- What decides it is being early and right at once.
- Putting a weak model inside the bot as its reader adds 26 to 29 points.
- Handing choices to decision models costs ground.
- In the bonus round, models solve 57–100% of puzzles with no clock, against contestants' 38%.
- Cost per game depends on how a model thinks, not on its token price.

## 1. Introduction

- Where the project started: Wheel of Fortune at the dinner table, which led to the three questions, can LLMs play it, how well, and can we do better, plus the fourth, how human contestants would fare.
- Why this game. It chains letter choice, the risk of a spin, and the timing of a solve against opponents. Each choice has a price, and the opponents set it. Whether to spin again depends on how sure a player is of the answer, which no observer can see.
- Contributions:
  - an engine that plays the full current show rules, with three seats and duplicate scoring
  - a deterministic bot, with no LLM inside, as the yardstick
  - four kinds of seat: LLM, bot, hybrid, and decision seat
  - 15 lineups and 5,400 games on a fresh deck that no model can have trained on, seven models from five labs
  - the results below, with code and logs released

## 2. Related work

This is mostly already written in the earlier FINDINGS.md, in git history at `a86efcc:FINDINGS.md`, "Related work":
- LLMike (CLiC-it 2025): single player, Bankrupt removed, 80 Kaggle puzzles.
- Game shows in economics: Gertner 1993, Metrick 1995, Post et al. 2008, Pacheco et al. 2023.
- Puzzle statistics: Blatt 2014 and the Upshot in 2023.
- Hangman solvers.
- Games chosen for what they test: Watson, Hanabi, Cicero.
- Gap: a paragraph on LLM game benchmarks, such as multi-game text arenas and agent game suites. These need a literature search, and nothing is cited until it's checked.

## 3. The game

- Rules as played:
  - a 24-wedge wheel with per-round overlays
  - specials: Wild Card, Million, Mystery, Express, Free Play
  - vowels cost $250
  - the solver banks at least $1,000
  - bonus round: R S T L N E plus three consonants and a vowel, and the envelopes
- Source for the rules: `documentation.md` (The wheel, Special wedges, Turn rules, Bonus round). The full table goes in Appendix A.
- Deliberate differences from the show:
  - one solve response and no clock
  - no toss-ups
  - from round 4, the previous round's solver starts
  - Free Play kept
  - Million wedge placement
  - Source: WHEEL.md, the memory note [Ian's design decisions].
- The engine:
  - Pure, with every random draw seeded.
  - Players see a public view, legal actions are enforced, and an illegal move is refused and asked again.
  - Three invalid replies forfeit the turn (`runner.py`).

## 4. Players

- LLM seat:
  - OpenRouter, moves as tool calls.
  - A neutral system prompt with rules and goal only (Appendix B, verbatim).
  - Each model at its default reasoning and temperature.
  - Prompt caching.
- Bot v6:
  - Reader: word, phrase and name lists from Wikipedia, Wiktionary and Wikidata, plus a calibration curve.
  - One value function: dollars in rounds 1 and 2, win chance from round 3.
  - Steal odds per turn, a known-answer planner (it keeps spinning on a known board), and the bonus round.
  - Source: `documentation.md` (Bot, Version 6). Version history v1 to v6 gets one appendix paragraph.
- Hybrid: the bot moves. On its turns it asks the model whether it can solve and what the answer is, then weighs the reply with trust curves measured on practice boards (`documentation.md`, Hybrid seat).
- Decision seat:
  - A decision model chooses every move through OpenRouter's Decisions API, and Luna writes the answer.
  - Models: d1-ultra (first on Artificial Analysis's Decision Index) and Luna Decisions.
  - Gap: cite the Decision Index page and its date.

## 5. Puzzles and scoring

- Deck: grading-606b.
  - 400 main-round puzzles in four round chunks, matched to aired rounds 1 to 4 in category and length and dealt by round, plus 100 bonus puzzles.
  - Written by MiniMax M3, checked by code, judged by GLM 5.3 Flash (`meta.deck_made_by`), then frozen.
  - Neither lab plays.
  - Pipeline in Appendix D.
- Why generated puzzles: no model can have seen them.
- The memory probe: on aired puzzles, no model solved from a blank board, so generated and aired puzzles play alike.
  - Gap: the probe's numbers are in HANDOFF-UPDATE.md (v4-era, $2.29) and not in `numbers.json`. Add them to `numbers.json` from its logs, or cite them as an earlier experiment.
- Duplicate scoring:
  - 60 sets × 6 seatings = 360 games per lineup, seed 707 (`meta`).
  - Each set replays the same puzzles and spins in every seating.
  - Intervals are 95%, from resampling whole sets with 10,000 resamples and a fixed seed (`meta.interval`).
- Noise floor: two identical bots in one lineup differ by:
  - Gap: compute this from each lineup's `pairwise` of bot #1 against bot #2 (e.g. `L[2].pairwise`), and give its range across lineups.

## 6. Can LLMs play it?

- Every game finished.
  - Invalid replies per game come from `L[x].<model>.invalid_per_game`.
  - Gap: forfeits per lineup, which are inside `invalid` by kind and need a line in `numbers.json`.

## 7. How well do they play?

- Table 1, alone against two bots:
  - For each model: wins with interval, average place, rounds won per game, solve accuracy, median board showing at a right solve, wrong solves per game.
  - Lineups 2, 2t, 3c, 3m, 3r, 3b, 3d.
  - Source: `L[id].<model>`: `win_rate`, `win_ci95`, `place`, `rounds_won_per_game`, `solve_accuracy`, `shown_at_correct_solve.median`, `wrong_solves_per_game`.
  - Figure 1, chart 1.
- Pairs:
  - Terra ties Sol: −0.8 points (−6.9 to +5.0), `P["Terra minus Sol"]`.
  - DeepSeek beats Qwen by 7.2 points and Luna by 9.2.
  - Qwen ties Luna.
  - Ember ties DeepSeek (−0.8, −7.5 to +5.8) and beats Qwen (+8.1), Luna (+10.0) and Haiku (+16.9), `P["... Ember ..."]`.
- Temperament:
  - Early and right wins.
  - Sol and Terra are right on 94–97% of solves with half the board showing.
  - Luna is as early, with 71% right and 0.64 wrong solves a game.
  - Haiku and Qwen wait until 65–70% shows.
  - Ember is the most accurate (98% right, 0.03 wrong solves a game) but solves at a median 64% showing, about when the bot would, and buys the most vowels (3.9 a game). It pays for certainty, in vowels and in thinking.
  - Figure 2, chart 2.
  - Wrong solves by kind: `L[id].<model>.play.wrong_solves` (filled; Luna: 143 put a called letter in a blank, 59 fit but were wrong, 21 contradict a shown letter, 6 have the wrong shape).
- Rounds and banks:
  - The bots win fewer rounds but bank more in each: a median of $4,600–5,400 against Sol's $3,350 and Luna's $1,350.
  - Source: `money_per_round_won`. Figure 3, chart 4.
- Letter choice:
  - Sol's and Terra's consonants hit 94%, against the reader's expected 84–85%, and they take its top pick only 63–64% of the time.
  - The bots hit 90–93% against 91–94% expected.
  - Every model playing alone beats its reader's expectation by 3–10 points: Sol +10, Terra +9, Luna +6, DeepSeek and Qwen +5, Ember and Haiku +3.
  - Why the bot takes the reader's top letter only 74% of the time: it trades hit chance for copies (60% of its off-top calls had more expected copies).
  - Source: `letters.rows[id][player].consonant`. Table 2.
- The reading gap:
  - 60% of Sol's and Terra's winning rounds came on boards the bot's reader got wrong or wasn't sure of.
  - For Haiku that share is 36%, for Qwen 41% and for Ember 46%. Those three mostly win boards a bot would have known, by getting there on their own turn.
  - Figure 4 is chart 13 (`figures/13-reading-gap.png`).
  - Source: `reading_gap.lineups[id].players`. Figure 4, a stacked bar.
- Puzzle length:
  - Long puzzles favour LLMs.
  - `L[id].<model>.play.by_length` and `reading_gap.by_length` (filled). Chart 12.

## 8. Can we do better?

- Table 3, hybrids:
  - Luna goes from 14.4% to 40.6%, +26.1 (+19.2 to +32.8). Haiku goes from 7.5% to 36.1%, +28.6 (+23.3 to +33.9).
  - Source: `P[...]`.
  - The Luna hybrid beats the Haiku hybrid by +4.4 (0.0 to +8.9). Sol alone beats the Luna hybrid by +5.6 (−1.1 to +12.5), a tie.
  - Why the hybrid works: the bot stops Luna guessing early and makes Haiku act sooner. Inside the hybrid, 98% and 97% of solves are right.
  - Ask statistics: `L[3|3f].<hybrid>.play.hybrid_asks` (filled): Luna said solvable with a fitting answer on 49% of asks, first at a median 36% showing; Haiku 29%, at 50%.
- The bot against two copies of one player: 58.6% against Lunas, 65.8% against Haikus, 83.3% against Luna Decisions seats, 88.3% against d1-ultra seats (`L[6a|6b|6d2|6d1].bot`).
- Decision seats:
  - 3.9% and 1.9% wins.
  - Luna alone minus the Luna Decisions seat: +10.6 (+5.8 to +15.6).
  - Their consonants hit 68% and 71%, below the frequency rule's 79% and 74% on the same boards.
  - d1-ultra solves late, at 76% showing. Luna Decisions solves early, at 47% showing and 57.5% right.
  - Earlier probe: d1-ultra judges a board solvable by its own reading.
  - Gap: that probe was on v4 (GRADING_PLAN.md, "When decision models choose to solve"). Cite it as an earlier experiment.

## 9. How would human contestants fare?

- Bonus test:
  - Sol 100, Terra 98, Ember 94, DeepSeek 92, Luna 79, Qwen 74, Haiku 57.
  - Bot 95; hybrids 99 and 97 with the bot's own picks.
  - Contestants 38% with a 10-second clock.
  - Our bonus boards start fuller: R S T L N E fills 35% of their letters against 29% aired (`bonus.rstlne_share`). By band, the weaker readers gain about 4 points from it; the ranking holds (`bonus.by_rstlne_share`). The comparison with contestants is not like for like on two counts: the clock and the fuller boards.
  - Source: `bonus.entrants`. Figure 5, chart 6.
  - Source: Spaniel 2014, The New Republic: 37.76% over bonus puzzles from 2007 to January 2014.
- Picks:
  - Sol's and Terra's letters leave 77% of the board showing, against the bot's 55%, and Sol still solves every puzzle.
  - The bot picks D, H, C, A on almost every puzzle. Contestants favour C, M, D, A.
  - Source: Spaniel 2013 (blog): C, M, D and A called 64.6%, 59.9%, 57.9% and 48.3% of the time, over about 1,166 bonus puzzles.
- Style:
  - The bot plays nothing like a contestant: it flips every Mystery and keeps spinning on known boards.
  - LLMs play closer to contestants.
  - Mystery flips and Express rides: `L[id].<seat>.play.specials` (filled). Vowel buys: `L[id].<seat>.vowels` (filled). Spins on known boards: `play.milking` (filled).

## 10. Cost

- Per game, one model seat:
  - Luna 0.3¢, Haiku 0.6¢, Terra 0.9¢, DeepSeek 1.4¢, Sol 1.6¢ (flex tier), Ember 2.3¢, Qwen 2.9¢ with 10% of games above 5.7¢.
  - Ember's tail: its one-set trial said 0.67¢ a game. 5.6% of its calls ran past 5,000 output tokens, some hit the 65,536 ceiling with no move, and one round cost 20.7¢, its reasoning summaries drifting into text about buffers and deployments. In the bonus test it spent $2.53, more than the other eleven players together ($1.91).
  - Source: `L[id].<model>.cost`. Figure 6, chart 5.
- Why:
  - Output tokens and cache hits, not token price.
  - Qwen's provider caches only up to marked messages. The fix took caching from 19% to 74–91% of input.
  - A few long-thinking moves dominate spend.
  - Cached share and cost spread: `L[id].<model>.play.usage` (filled).
- Total: $53.02 for 5,400 games (the sum of `L[*].cost`), plus $4.43 for the bonus test (`bonus.entrants[*].cost`).

## 11. Limitations (short, factual)

- One deck, one seed, one bot design, and our rule choices, above all no clock.
- Seven LLMs from five labs. Frontier models from Google, Anthropic and others were left out for cost.
- The bonus deck gives away more than the show's (35% against 29% filled by R S T L N E).
- Decision seats pair a decision model with Luna as the writer.

## 12. Conclusion

One paragraph that answers the four questions in order.

## Appendices

- A. Full rules: wheel layout per round, special wedges, bonus envelopes (from `wheel.toml` and `documentation.md`).
- B. The LLM system prompt and tool schema, verbatim.
- C. Bot v6 in detail, plus one paragraph on v1 to v6 (each version's self-play result).
- D. Puzzle generation: prompts, the checks, the judge, and how the round chunks were matched to aired rounds.
- E. Every lineup: wins, places, rounds, money and cost for each seat (Table A1, from `lineups`). This takes in charts 3, 7, 8, 9, 10 and 11.
- F. Reproducing the work: commands, commit, seed, `numbers.json`, and what's released.

## Figures for the main text

1. Alone against two bots (chart 1).
2. Early and right (chart 2).
3. Rounds and banks (chart 4).
4. The reading gap (chart 13).
5. The bonus test (chart 6).
6. Cost per game (chart 5).

Charts 3 and 7 to 12 go in the appendices.

## Before drafting

1. Done (2026-11-09): every gap above is in `numbers.json`, plus R S T L N E's fill and the bonus solves by it (`bonus.rstlne_share`, `bonus.by_rstlne_share`; needs one more rebuild on the server).
2. The v4-era probes (memory and decision timing) are cited as earlier experiments. The memory probe's table is in Appendix D.
3. Citations: found for the contestants' bonus rate and letter picks (Spaniel 2014 and 2013), the Decision Index, and the LLM game benchmarks; refs.bib marks fields still to verify.
