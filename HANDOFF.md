# Handoff: the state of rstlne on 2026-10-31

Context for a new chat session. It covers what the project is, how the code works, how the bot plays, every result so far, what's running, and what's next. `documentation.md` is the full spec and wins wherever this file is shorter or older. `GRADING_PLAN.md` has the grid's commands and results, and `WHEEL.md` the wheel.

## 1. The project in one paragraph

rstlne is a Wheel of Fortune engine where LLMs, a hand-built bot, a hybrid (the bot plus an LLM reading the board), decision models and a human share a three-seat table under the show's rules, through the bonus round. It started from Ian's childhood: watching the show at dinner and wondering whether a machine could play it. The write-up is framed around four questions:

1. Can LLMs play Wheel of Fortune?
2. How good are they?
3. Can we do better (the bot, the hybrid)?
4. How would human contestants fare? LLMs stand in as the closest available surrogate for contestants, and real contestant data (bonus solve rates, letter picks) is the check.

The CLI exists for Ian to play models for fun. The same engine runs seeded, duplicate-scored, model-only tournaments.

## 2. Working rules (from Ian, standing)

- **Git:** Claude may commit, never push. Ian pushes and pulls on the server. No `git init`. End commit messages with the Co-Authored-By line the session gives.
- **Rules of the game:** build gameplay exactly as `documentation.md` says. When the spec is silent, ask Ian, as a concrete play-by-play example. Never invent a rule. When a rule changes, update `documentation.md` in the same commit.
- **Ian's deliberate departures from the show** (don't "correct" them): special wedge positions (Wild on 2, Million on 9, Mystery on 5 and 17, Express on 12), the Million wedge on an $800 wedge with a $500 centre third, Free Play kept, bonus envelope counts 6/6/6/5/1, seeded tiebreaks, models get one solve response with no clock (humans 10 s), the round 4 start rule, and no toss-ups.
- **Tests:** write the test first. Mock OpenRouter in every test; tests never make network calls and never read `data/` (tests needing real word data are marked `slow`).
- **Puzzles:**
  - Never commit or publish aired puzzles: `puzzles/private.json` and `puzzles/all_recent_puzzles_ktebbe.csv` are gitignored.
  - Never tune or fit on `dev.json`, grading decks, or `private.json`. Grading decks are for scoring only; tuning uses `tuning-101`.
  - Fix weak generated puzzles by hand without asking, record each fix in the file's `rechecked` history, then report.
- **Prompts:** neutral. Rules only, no strategy coaching. Measure odd play in the logs instead.
- **Compute:** no self-play or long training on the laptop; that goes on the server.
- **Model choices:** generator and judge labs differ from player labs; hosts must support tool calls. No Sol hybrid (deliberate, see section 9), no Sonnet or Gemini runs for now.
- **Write-ups:** frame them with the dinner-table origin and the four questions.

## 3. Environment and operations

- **Laptop:** repo at `/home/ian/Documents/wheel-of-fortunate-llms`. `uv` is at `~/.local/bin/uv`, not on PATH: run `~/.local/bin/uv run pytest`, `~/.local/bin/uv run python -m rstlne.<module>`.
- **Server:** `ssh ian-sloptic` (Ian's rsync alias is `server:`), repo at `~/rstlne`, a tmux session named `rstlne`, 4 cores, 15 GB. It sometimes needs Ian's VPN. Ian runs long jobs there; Claude reads results over ssh and copies logs back with `rsync -a ian-sloptic:rstlne/logs/tournaments/<folder>/ logs/tournaments/<folder>/`.
- **Memory per game:** every bot or hybrid seat's game process loads the word data, about 420 MB. Tournaments with a bot play each game in its own process. 12 games at once used about 5 GB.
- **Read hook:** a hook (`~/.claude/hooks/cbm-code-discovery-gate`) blocks the Read tool. It's meant to allow a read after blocking once, but its marker file doesn't persist here, so it blocks every Read, including images. Read text with `cat`/`sed`/`grep` through Bash. Images can't be viewed; check generated images in code (element counts, pixel sampling with `magick`). The repo is indexed in codebase-memory as `home-ian-Documents-wheel-of-fortunate-llms`.
- **Costs:** OpenRouter, key in `.env` (never commit it). Sol and Terra run on OpenAI's flex tier (half price, slower).

## 4. How the code fits together

```
rstlne/engine/   pure game: no I/O, no randomness outside the seeded wheel
  wheel.py         wedges, per-round overlays, layout() of 72 thirds, seeded spins and draws
  puzzle.py        board, reveal, letter counts, solve matching
  state.py         GameState, RoundState, actions, public view types
  rules.py         apply(state, action) -> new state; legal_actions; round starts
  bonus.py         bonus wheel, picks, solve
players/
  base.py          Player.decide(view) -> Action
  llm.py           tool-calling LLM seat
  decision.py      decision-model seat (Decisions API makes choices, an LLM writes solves)
  hybrid.py        bot seat that asks an LLM to read the board on its own turns
  human_cli.py
  bot/             the bot (section 5)
llm/openrouter.py  client, retries with backoff, usage and cost tracking
runner.py          game loop shared by CLI and tournaments: reprompts, forfeits, JSONL logs
tournament.py      seeded duplicate-scored runs, reports with bootstrap intervals
selfplay.py        bot-only jobs on the server: games, games-summary, round-banks, fits
bonustest.py       every player on every bonus puzzle in a file, alone
puzzlegen.py       generated puzzles: generator writes, code checks, judge confirms
calibrate.py       decision thresholds, hybrid trust and steal curves
settings.py        loads wheel.toml and config.toml (so engine/ stays free of I/O)
cli.py, show.py, live.py, narrate.py   the terminal game
```

- **Config:** `wheel.toml` holds every wedge and envelope value; `config.toml` holds model slugs, provider pins, LLM settings, the bot version, puzzle generation settings, hybrid curves.
- **Views:** players see a public view only (category, spaced board and a compact pattern with word lengths, used letters, all banks, held cards, whose turn, wedge, the wheel as it stands, legal actions). Never the answer, a Mystery's hidden side, or the bonus envelope.
- **Every action goes through `rules.legal_actions`.** The engine rejects illegal moves; the runner reprompts an LLM up to 2 times, then takes the safe default or passes the turn.

### The game as built

- **Wheel:** 24 wedges of 3 thirds each. Round tops $2,500 / $3,500 / $3,500 / $5,000. Bankrupt odds 1 in 9 in rounds 1–3 (the Million wedge adds two Bankrupt thirds), 1 in 12 in round 4. Average per spin $611, $682, $674, $742. Details and a picture: `WHEEL.md`, `wheel.png`.
- **Turns:** spin and call a consonant, buy a vowel for $250, or solve. Only the solver banks; a solve banks at least $1,000. A round ends after 200 turns with nobody solving.
- **Who starts:** seats 1, 2, 3 start rounds 1, 2, 3. From round 4, the previous round's solver starts; a seeded draw if nobody solved. (Changed 2026-10-31; before, seat 1 also started round 4.)
- **Bonus round:** the leader after round 4 plays alone: R S T L N E shown, 3 consonants and a vowel (4 consonants with the Wild Card), one solve. Envelopes $40K–$55K and one $100K, which the Million card turns into $1M.

### Tournaments and duplicate scoring

- A set is 6 games: the same 4 main puzzles, bonus puzzle and spins, once for each ordering of the 3 entrants across the seats. This strips most of the wheel's luck.
- Intervals come from bootstrapping whole sets (games in a set aren't independent).
- The same seed gives the same sets in every lineup, so lineups can be compared set by set.
- Default folder: `logs/tournaments/seed<seed>-<hash>`, where the hash covers entrants, puzzle file and play settings (not the set count). Rerunning resumes; `--sets` can be raised to extend.
- **Gotcha:** three identical seats (e.g. `bot,bot,bot`) play the same game six times per set. For bot-only habit data, use distinct seeds instead.

### Self-play

- `selfplay games --entrant name:knob=v+knob=v ...` plays bot variants against each other with duplicate scoring and writes one summary line per game (no move logs).
- **Gotcha:** the base knobs come from `config.toml`'s bot version, plus `--knob` overrides. With config on v4, a plain v3 entrant needs v4's tables emptied: `v3:stealer_gain_llm=@logs/selfplay/empty-knob.json+stealer_gain_bot=@...+steal_bot=@...` (the file holds `{"knob": []}`; on the server it exists).
- `games-summary <folder>` gives win rates, intervals, by-seat results and gaps. A bug where a v4 seat's LLM-likeness overwrote its win share in the per-set rows was fixed in ab4dcc4.

## 5. How the bot plays

The bot (`rstlne/players/bot/`) is a calculator with a word list. No LLM.

**Reader (`full.py`, `reader.py`, `belief.py`).** It turns the board and category into a Belief:
- It splits the board into word slots and samples whole answers across them by forward filtering, backward sampling. Each slot can be a vocabulary word (weighted by word frequency, category fit from fastText vectors, and word-pair counts from Tatoeba and Simple Wikipedia), a position inside a known phrase or name (Wiktionary multiword entries, Wikidata labels), or an unknown word.
- Category rules: ING words for What Are You Doing?, rhymes (CMU dictionary) for Rhyme Time, shared first letters, Before & After overlaps, Same Name.
- Output: each letter's chance of appearing and expected copies, the top answers with probabilities, an out-of-vocabulary share, and a calibrated confidence in the best answer.
- Wrong solves by anyone are ruled out for the round.
- Data: about 150,000 words, 406,000 phrases and names, 1.8 million word pairs. It knows 99.7% of words in aired bonus answers; its weakness is ranking candidates, not missing words.

**One value function (`value.py`).** Every turn it scores spin, buy a vowel and solve:

V(action) = immediate gain + P(keep the wheel) × V(continue) + P(lose the wheel) × (1 − p_steal) × V(continue later)

- **Spin:** averaged over every third of the wheel as it stands; a dollar third pays the best consonant's chance × value × expected copies.
- **Vowel:** −$250 plus its information value.
- **Solve:** confidence × payoff of banking + (1 − confidence) × the race continuing. With no candidate answer it never guesses.
- **Losing the wheel** costs the round if an opponent then solves. **Steal odds** (`steal.py`): per opponent, a logistic in share showing and the bot's own confidence (prior fit on LLM play: a = −3.27, b = 2.61, c = 1.92), updated during the game from what each seat does, applied in turn order.
- **Objective (`objective.py`):** expected dollars in rounds 1 and 2; from round 3, the change in the chance of finishing first. Cards count at their values.

**Letters:** information is valued in dollars. On a dollar wedge it calls the consonant with the best money plus information; it buys the vowel with the best information; on Free Play it takes the best letter, often a vowel.

**Known answers (`planner.py`):** at 95% confidence a small dynamic program plans the rest of the round: which consonants to call, how long to keep spinning, when to solve. This is the "milking".

**Special wedges:** Mystery by value (it almost always flips); Express only when sure, riding safe consonants; Wild Card spent only when the extra consonant beats its bonus value (so it usually keeps it).

**Bonus (`bonus.py`):** brute-forces every legal pick set, scored by the chance its best guess is right afterwards; solves with the best guess. In practice it picks D, C, H and A almost every time.

### Bot versions (`versions.py`; config picks one; each frozen with its data fingerprint)

| Version | Change | Result |
|---|---|---|
| 1 | win chance from a formula | baseline |
| 2 | win chance from a self-play table | tied v1 |
| 3 | an opponent who takes the round banks what it holds **plus what it adds before solving** (the stealer's gain G, 20 values per band of hidden squares, fit from LLM and bot play); settled choices played for dollars (fixed v1's alphabetical B-C-D moves) | beat v1 43% to 28% (+15, +12 to +18), 2,004 games |
| 4 (**current**) | G per opponent: separate LLM and bot gain tables, mixed by w, the chance that seat plays like an LLM, learned from when it solves | tied v3: 37.8% vs 37.9%, gap −0.05 (−0.65 to +0.55), 2,004 games. Ian adopted it as "no worse" (bar changed after the result; recorded in the spec) because its case rests on LLM opponents, which self-play can't seat |

Against Sol, v4 judged Sol LLM-like (median w 0.87); against the hybrid, bot-like (0.31). Whether v4 beats v3 against LLMs is untested; rerunning lineup 2 with v3 bots (about $6) would show it.

### How it plays compared with people (40 v4 bot-only games against lineup 1 and older logs)

- **Fixed since v1:** the alphabetical B opening (v1 opened round 4 with B in 218 games).
- **Still inhuman:** keeps spinning once it knows (about 1.5 rounds a game reach 95%, then a median 1 more consonant, Bankrupt in 16% of those rounds); solves late and certain (62% of the board showing, median confidence 1.00, 0.07 wrong solves a game); about one vowel a game; flipped 14 of 14 Mysteries; near-fixed bonus picks.
- **Shared with LLMs now:** Sol hoards the Wild Card more than the bot does (kept 188, used 11) and rode every Express it got (17 of 17); Haiku solves as late as the bot (68%).
- **Why the bot solves late (lineup 2 logs):** in rounds Sol took, the bot was under 50% confident 40% of the time, never got a turn 44% of the time, and already knew the answer only 3% of the time. Of the ~15-point gap in solve timing (bot 67% vs Sol 52%), about 4 points is milking and about 10 is slower reading.

## 6. The other seats

- **LLM seat:** moves are tool calls (`spin`, `buy_vowel`, `solve`, `call_consonant`, `call_letter`, `keep`/`flip`, `pass`/`play`, `use_wild`, `bonus_picks`, `bonus_solve`). Rules once in the system prompt; each turn the view plus a recap of opponents' moves. History resets each round and at the bonus. Every model plays at its own default reasoning; `tools = "all"` keeps the prompt cacheable. 300 s per request, one retry. Invalid moves are logged by category; a wrong solve that doesn't fit the board is logged as a misfit.
- **Hybrid seat (`hybrid:<slug>`):** the bot plays every move. On each new board it acts on, it asks the model "is this solvable, and if so what's the answer?" (board, category, used letters, refuted answers; no money). A fitting answer joins the reader's samples with trust t from the model's trust curve (`[hybrid.trust]`), and steal odds use the model's steal curve (`[hybrid.steal]`). Luna (`openai/gpt-6-luna`) and DeepSeek have curves. The bonus picks are the reader's; the bonus solve uses the merged candidates.
- **Decision seat:** a decision model (`openai/gpt-6-luna-decisions` or Jev) makes every choice from probabilities; Luna writes the solves. An early trial found decision models pick letters by plain English frequency and lose the wheel about twice as often; likely a negative result.

## 7. Puzzles

- `puzzles/dev.json` (committed, development only), `puzzles/private.json` (400 main + 100 bonus aired puzzles, gitignored, scoring only), the ktebbe CSV (22,934 aired puzzles 2013–2025, gitignored).
- **Generated decks** (`puzzles/generated/`, gitignored): `grading-505` (prompt v6, 400 main + 100 bonus, hand-fixed in four passes; **the grid's deck**), `grading-202/303/404` (older prompts; 202 is the self-play check deck), `tuning-101` (tuning), `trial-v7-bonus` (100 bonus under prompt v7, hand-fixed). `seen.txt` keeps every generated answer from ever coming back.
- **Generator:** MiniMax M3 writes, code checks (board fit, length, hidden share after R S T L N E + C D M A, structure rules, near-repeats, spelling against the word data), GLM 4.7 judges (fits the category, natural wording rated 4 of 5 or more; sourced categories judged twice).
- **Prompt v7 (2026-10-31, bonus only):** a bonus Phrase is everyday talk, not an idiom, and bonus words needn't be the commonest. Why: 32% of grading-505's bonus answers were stock phrases in the bot's data, against 12% aired, and the bot solves every stock phrase.
- **Open:** the near-repeat check misses contraction and one-word variants.

## 8. Results

All grid lineups: grading-505, seed 707, 60 sets (360 games), bot v4, the new round 4 rule (except lineup 1, played under the old rule). A fair share is 33%.

### Lineup 1: Sol, DeepSeek, Haiku (W = Sol)

| | Sol | DeepSeek V4.1 Flash | Claude Haiku 5.5 |
|---|---|---|---|
| Win rate | **66%** (61–70%) | 25% (21–29%) | 9% (6–13%) |
| Rounds won per game | 1.92 | 1.54 | 0.55 |
| Solves right | 96% | 89% | 91% |
| Board showing at a correct solve | 48% | 46% | 67% |
| Bonus | 236 / 237 | 84 / 89 | 28 / 34 |
| Invalid moves per game | 0.02 | 0.39 | 0.20 |

$12.46. Every gap clears zero. MiMo was dropped (runaway thinking, timeouts; its partial run scrubbed), Haiku replaced it.

### Lineup 2: Sol, bot, bot

| | Sol | Each bot |
|---|---|---|
| Win rate | **58%** (51–64%) | 21% (17–25%) |
| Rounds won per game | 2.26 | 0.87 |
| Median bank when winning a round (rounds 1–3) | $3,350–3,975 | $5,300–7,000 |
| Solves right | 96% | 90% |
| Board showing at a correct solve | 52% | 65% |
| Bonus | 205 / 209 | 129 / 151 (both) |

$6.35. Sol leads each bot by 37–38 points. Set by set, Sol wins 7.8 points less than in lineup 1 (−15.0 to −0.6): two bots are tougher than DeepSeek and Haiku. Sol takes 56% of rounds, but the bots bank about 1.6 times as much per round won, and a bot took round 4 in 125 of Sol's 151 non-wins.

### Lineup 3: hybrid (bot + Luna), bot, bot

| | Hybrid | Each bot | Sol, lineup 2 |
|---|---|---|---|
| Win rate | **45%** (40–51%) | 27–28% | 58% |
| Rounds won per game | 1.74 | 1.13 | 2.26 |
| Solves right | 97.5% | 92.5% | 96% |
| Board showing at a correct solve | 65% | 66% | 52% |
| Bonus | 147 / 163 | 169 / 197 (both) | 205 / 209 |

$1.93. The hybrid leads each bot by 17–19 points, but set by set wins 12.8 points less than Sol did against the same bots (−20.0 to −5.6). It asked Luna 5,817 times (16 a game, about 6 s each, why these games are slow); Luna gave 3,333 answers, 84% right. Luna's reads raised accuracy and rounds won, not solve timing: the bot's strategy keeps choosing to milk against slow bot opponents.

**Reading so far:** strategy plus a weak reader beats pure strategy (the bot) but loses to a strong reader without strategy (Sol).

### Lineup 3b: Luna alone, bot, bot (running)

Started 2026-10-31 on the server (`logs/grid-3b.txt`, folder `seed707-e71dd1af`), about 0.2¢ and 70 s a game, roughly 40 minutes in all. Purpose: hybrid minus Luna-alone, set by set, is what the bot's strategy adds to Luna's reading. If Luna alone wins about 45%, strategy added nothing; clearly less means strategy matters.

### Bonus test (each player alone on every bonus puzzle in a file; `rstlne.bonustest`)

| | Aired (`private.json`) | grading-505 (v6) | trial-v7-bonus |
|---|---|---|---|
| Sol | 99% | 99% | 98% |
| DeepSeek | 90% (89/99) | 95% | 89% |
| Haiku | 53% | 67% | 57% |
| Bot | 67% | 88% | 86% |

- The bot solves 79% of a 500-puzzle sample of the aired archive outside `private.json`; the private 100 are harder than average.
- Prompt v7 made generated bonus puzzles as hard as aired ones for the LLMs but not for the bot. What makes aired puzzles hard for the bot (ranking rare words and unseen pairings) differs from what makes them hard for LLMs; memory may also help the LLMs on aired puzzles (untested; a blank-board probe would cost about $1).
- Haiku's misses are mostly misfits (solves that don't fit the board). Real contestants solve about 38% of bonus puzzles, with a 10-second clock.

### Self-play results

- **v3 check:** v3 43% vs two v1 bots 28% each (+15).
- **v4 check:** see the versions table.
- **Round 4 rule check** (100 sets, v4/v3/eager): no player's win rate moved by more than a point; the seat edge moved from seat 1 (42/29/30%) to seat 3 (31/31/38%), and halved. `logs/selfplay/v4-check-newstart`.

### Older findings (before the grid, bot v1 era; different decks)

- Recognition decides most rounds; once players recognize equally fast, patience wins.
- DeepSeek won about 39% against Luna's 22% at a mixed table.
- The hybrid (Luna) beat DeepSeek and the v1 bot by about 9 points over 100 sets.
- Express: the bot boards only when sure (0.97 confidence) and never busted on a letter.

## 9. Decisions made this session (2026-10-31)

1. Lineup 1 finished; W is Sol.
2. Built the bonus test; ran it on aired, grading-505 and the v7 trial.
3. Fitted, froze and checked bot v4; adopted it on Ian's "no worse" bar. Found and fixed the games-summary bug (ab4dcc4).
4. Puzzle prompt v7 for bonus puzzles; trial deck hand-fixed (4 corrected, 7 dropped and topped up). grading-505 stays unchanged for the grid.
5. **Round start rule:** from round 4 the previous round's solver starts; seeded draw if nobody solved (0ed8654). Lineup 1 not rerun (the rule moves win rates by under a point).
6. **Toss-ups excluded on purpose:** a recognition race, already measured elsewhere, no real speed in a turn-based game, and a call per model per letter.
7. **Every lineup is 60 sets** (matching lineup 1, so any two pair up set by set). To extend a close comparison, extend both lineups to 100 together.
8. **The hybrid uses Luna, not Sol, on purpose.** A Sol hybrid would answer "is Sol plus the bot better than Sol" (the "if you can't beat 'em, be 'em" trap Ian rejected). The Luna hybrid asks whether strategy can make up for weaker reading. Claims must stay scoped to a Luna-level reader.
9. Lineup 6 held back by Ian for now.
10. Wrote `WHEEL.md` with `wheel.png` and `wheel.svg`, drawn from the engine's layout. The drawing script is not in the repo (it was in a session scratchpad); offer to add it as a command if the wheel changes.

## 10. What's next

1. **Luna alone (running):** copy `seed707-e71dd1af` back, report it, and compare set by set with lineup 3 (hybrid) and lineup 2 (Sol).
2. **Remaining grid:** lineup 6 (bot, Sol, Sol) when Ian wants it; lineups 4 (Sol, hybrid, bot) and 5 (Sol, hybrid, hybrid), all 60 sets. Commands are in `GRADING_PLAN.md`. Lineups 4 and 5 show whether the hybrid solves earlier against a fast opponent like Sol.
3. **Optional checks:** lineup 2 rerun with v3 bots (does v4 help against LLMs?); the blank-board memory probe on aired bonus puzzles; habits measured on lineup 2 logs (the bot against a real stealer).
4. **Later:** bot v5 (refit the win table and stealer's gain under the new start rule); tighten the near-repeat check.
5. **Publicizing (Ian declined a draft for now):** a blog post framed by the four questions, a `--live` game video, a cleaned README. Never publish aired puzzles; publishing grading-505 would burn it for future scoring; use the show's name only in text, with a no-affiliation line; report intervals and date the models.

## 11. Commands

```
~/.local/bin/uv run pytest                                    # 758 tests at last count
uv run python -m rstlne.cli --live --seats human,llm:openai/gpt-6.1-sol,bot
uv run python -m rstlne.tournament --seats <seat>,<seat>,<seat> --sets 60 --parallel 12 --max-cost N \
    --puzzles puzzles/generated/grading-505.json --seed 707 2>&1 | tee -a logs/grid-N.txt
uv run python -m rstlne.bonustest --players llm:<slug>,bot --puzzles <file> --seed 707
uv run python -m rstlne.selfplay games --entrant ... --puzzles puzzles/generated/grading-202.json --sets N --seed 808 --out logs/selfplay/<name> --workers 4
uv run python -m rstlne.selfplay games-summary logs/selfplay/<name>
uv run python -m rstlne.puzzlegen --main 0 --bonus 100 --seed <s> --out puzzles/generated/<name>.json
```

Model slugs: Sol `openai/gpt-6.1-sol`, Terra `openai/gpt-6.1-terra`, Luna `openai/gpt-6-luna`, DeepSeek `deepseek/deepseek-v4.1-flash-1017`, Haiku `anthropic/claude-haiku-5.5`. Seat forms: `llm:<slug>`, `bot`, `hybrid:<slug>`, `decision[:<model>]`, `human`.
