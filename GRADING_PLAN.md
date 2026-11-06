# Grading plan: six lineups

> **The v4 checkpoint (2026-11-01).** Every lineup here ran with bot version 4, and these results are the checkpoint the findings are frozen on. Bot v5 work is the next phase; its runs go in their own section, marked v5, and leave these untouched.

Six tournaments that pit every kind of player against every other: LLMs, the bot, and the hybrid (the bot plus Luna reading the board).

## The rules for every run

- **Same deck:** `puzzles/generated/grading-505.json`, the realistic v6 puzzles (400 main, 100 bonus).
- **Same seed:** `707`. Set 17 has the same spins and puzzles in every lineup, so differences between lineups come from the players, not luck.
- **Bot v4**, adopted on 2026-10-31: in its self-play check it tied v3 (−0.05 points, −0.65 to +0.55), and Ian adopted it as no worse. Lineup 3 first ran on v3 and was scrubbed, so every bot lineup runs on v4.
- **W** is the winner of lineup 1 (the highest win rate). W fills every LLM seat in lineups 2 to 6.

## The six lineups

| # | Seats | What it tells us | Sets |
|---|---|---|---|
| 1 | Sol, DeepSeek, Haiku | Which LLM is best, with no bot around: three labs (OpenAI, DeepSeek, Anthropic) | 60 |
| 2 | W, bot, bot | Can a good LLM beat the bot? | 60 |
| 3 | hybrid, bot, bot | How much does Luna's reading add to the bot? | 60 |
| 3b | Luna, bot, bot | What does the bot's strategy add to Luna? (added 2026-10-31) | 60 |
| 4 | W, hybrid, bot | All three player types at one table | 60 |
| 5 | W, hybrid, hybrid | Can an LLM beat the strongest seats? | 60 |
| 6 | bot, W, W | Can the bot beat two good LLMs? Optional now (see below) | 60 |
| 6a | bot, Luna, Luna | Can the bot beat a pair of reckless guessers? | 60 |
| 6b | bot, Haiku, Haiku | `seed707-345192e8` | done | bot **65.8%** (61–71%), Haikus 19.2% and 15.0%; +47 and +51 points (+38 to +58) | $4.92 |
| 6c | bot, DeepSeek, DeepSeek | ...a pair of eager readers? | 60 |

**Lineup 6 against weaker pairs (Ian, 2026-10-31).** One Sol beat two bots 58% to 21% each, so against two Sols the bot would be a massive underdog: in betting terms, a long shot, likely winning 10% or less. That makes lineup 6 a predictable answer for about $12. Lineup 6 keeps its format, the bot against two copies of one model, but against weaker models from three labs (6a to 6c). Each mirrors that model's solo run against two bots, so the matchup is seen from both sides. Lineup 6 with Sol stays optional; if run, 20 sets (about $4) would do, since its first 20 sets pair with every lineup's first 20.

**Spreading across labs (2026-10-31).** After lineup 1 every LLM seat was OpenAI's (Sol, and Luna in the hybrid and alone). To keep this from becoming a test of one lab's models, the same yardstick, a model alone against two bots, also runs for DeepSeek and Haiku, and a DeepSeek hybrid repeats the hybrid's lift on a second lab. MiniMax and Z.ai can't sit, since they write and judge the puzzles.

| # | Seats | Question | Sets |
|---|---|---|---|
| 3c | DeepSeek, bot, bot | DeepSeek's solo yardstick | 60 |
| 3d | Haiku, bot, bot | Haiku's solo yardstick | 60 |
| 3e | hybrid:DeepSeek, bot, bot | does wrapping DeepSeek lift it too? Stopped after 9 games (runaway thinking made it slow and costly) | 60 |
| 3f | hybrid:Haiku, bot, bot | the hybrid's lift on a second lab, in place of 3e | 60 |
| 2t | Terra, bot, bot | the mid-range model's yardstick, between Sol and Luna (added 2026-11-06, on v6 only) | 60 |
| d1 | decision:d1-ultra, bot, bot | a decision model deciding everything, Luna solving | 60 |
| d2 | decision:Luna Decisions, bot, bot | the same, with the solver's own family deciding | 60 |

**Sets:** 60 for every lineup, matching lineup 1, so any two lineups pair up set by set (Ian, 2026-10-31; lineup 3 was planned at 100 until its early gap proved large). **More sets if needed:** if a result is too close to call, rerun the commands of both lineups being compared with `--sets 100`, so the extra sets still pair; a rerun picks up where its folder stopped.

**Lineup 1 was cut to 50 sets on 2026-10-31, at 10 games at a time:** Sol won its first 19 games outright, and 24 at a time made MiMo's host time out. Second place goes on rounds won, money, and second-place finishes, since DeepSeek and MiMo barely win.

**MiMo was dropped from lineup 1 on 2026-10-31.**
- **Why:** about 1 call in 4 ran away into 6,000 to 58,000 tokens of thinking. Those calls timed out games and made up two thirds of MiMo's spend, so it cost more per game than Sol and DeepSeek combined.
- **The record:** its partial run (23 games, all won by Sol) was scrubbed at Ian's request.
- **The replacement:** Claude Haiku 5.5, for Anthropic.

## Reruns on bot v6 and grading-606b (from 2026-11-05)

The paper uses one bot version and one deck, so the grid reruns with bot v6 on grading-606b: four rounds of 100 main puzzles matching aired rounds 1 to 4 in category and length, dealt by round. Seed 707 and 60 sets as before, so the reruns pair set by set with each other (not with the v4 grid, whose deck differs). Hybrid seats use the per-turn steal curves (`[hybrid.steal_turn.v5]`). Lineup 1 isn't rerun: it only picked W (Sol), and has no bot seat. No DeepSeek or Sol hybrid (Ian). The v4 results below stay as the earlier record. Commands are under Commands, with `--puzzles puzzles/generated/grading-606b.json --seed 707`; stats so far: `uv run python -m rstlne.analysis.progress 2 3 …` (lineup ids from `lineups.toml`, which maps each to its folder; add each new lineup's folder there when it starts).

| # | Seats | Folder | Status | Result (95%) | Cost |
|---|---|---|---|---|---|
| 2 | Sol, bot, bot | `seed707-b511deec` | done | Sol **46.1%** (40–52%), bots 26.9% each; +19.2 points over each (+10 to +28) | $5.83 |
| 3 | Luna hybrid, bot, bot | `seed707-c18bccd7` | done | hybrid **40.6%** (35–46%), bots 30.6% and 28.9%; +10.0 and +11.7 (+2 to +20) | $1.67 |
| 3b | Luna, bot, bot | `seed707-4bac0081` | done | Luna **14.4%** (10–19%), bots 40.6% and 45.0%; −26.1 and −30.6 | $1.13 |
| 3d | Haiku, bot, bot | `seed707-21904e0d` | done | Haiku **7.5%** (5–10%), bots 43.3% and 49.2%; −35.8 and −41.7 | $2.14 |
| 2t | Terra, bot, bot | `seed707-aba71d75` | done | Terra **45.3%** (39–52%), bots 27.5% and 27.2%; +17.8 and +18.1 (+8 to +28) | $3.27 |
| 3c | DeepSeek, bot, bot | `seed707-47cfbb61` | done (5 games failed on API errors and were replayed) | DeepSeek **23.6%** (19–29%), bots 37.8% and 38.6%; −14.2 and −15.0 (−23 to −6) | $4.98 |
| 3f | Haiku hybrid, bot, bot | `seed707-d0d90cd5` | done | hybrid **36.1%** (32–41%), bots 31.1% and 32.8%; +5.0 and +3.3 (−4 to +12) | $3.87 |
| 6a | bot, Luna, Luna | `seed707-0724ada8` | done | bot **58.6%** (52–65%), Lunas 20.6% and 20.8%; +38 points over each (+28 to +48) | $2.39 |
| 6b | bot, Haiku, Haiku | `seed707-345192e8` | running (46 of 60 sets on 2026-11-06) | | |
| d1 | d1-ultra decision seat, bot, bot | `seed707-f06fd2a1` | done | d1-ultra **1.9%** (0–4%), bots 49.2% and 48.9%; −47 points | $0.31 |
| d2 | Luna Decisions seat, bot, bot | `seed707-5a806f9e` | done | Luna Decisions **3.9%** (2–6%), bots 47.5% and 48.6%; −44 to −45 points | $0.86 |

**Lineup 2 on v6:** Sol won 1.94 rounds a game to the bots' 1.03, solving right 97% of the time at a median 50% of the board showing against their 62%; the bots banked more when they won a round (median $5,175 to $5,275 at the solve, against Sol's $3,350). By seat Sol won 39%, 52%, 47%. Bonus: Sol 166 of 166, the bots 89 of 97 and 90 of 97. For reference only (other bots and decks): Sol won 58% against v4 on grading-505, 49% against v5 on grading-505, and 42% against v5 on unedited grading-606.

**Lineups 3b and 3d on v6:** Luna alone won 1.54 rounds a game, more than either bot (1.21, 1.24), but at a median bank of $1,350 at its solves against the bots' $5,050–5,150, solving at 48% showing with 71% right and 0.64 wrong solves a game. Haiku alone won 0.87 rounds a game, solving late (70% showing) at a median $2,300, 93% right. Both did worse than against v4 bots (17.5% and 14%). **The hybrid's lift holds:** Luna hybrid minus Luna alone, set by set, **+26.1 points (+19.4 to +33.1)**, against +27.8 on v4.

**Lineups d1 and d2 on v6:** the decision seats did worse than on v4 (4% and 8%), and worse than Luna alone (14.4%). d1-ultra won 0.43 rounds a game, solving late (76% showing, 85% right) for a median $1,400, and missed 1.94 consonants a game. Luna Decisions won 0.84 rounds a game at a median bank of $700, solving early (47% showing) and often wrongly (58% right, 0.62 wrong solves a game); it bought 0.08 vowels a game, as on v4.

**Lineup 2t on v6:** Terra ties Sol. Set by set, Terra minus Sol is **−0.8 points (−6.9 to +5.0)**, at 56% of Sol's cost ($3.27 against $5.83). Terra won 2.05 rounds a game to the bots' 0.97 and 0.98, solving at a median 48% showing with 94% right (Sol: 50%, 97%) and 0.13 wrong solves a game (Sol 0.07), at a median bank of $3,100 at its solves (Sol $3,350). By seat Terra won 42%, 44%, 49%. Bonus: Terra 160 of 163, the bots 91 of 99 and 88 of 98. Against the Luna hybrid, set by set: +4.7 points (−2.5 to +12.5).

**Lineup 3c on v6:** DeepSeek won 1.78 rounds a game, more than either bot (1.13, 1.09), at a median bank of $1,500 at its solves against the bots' $5,200–5,400, solving at 45% showing with 87% right and 0.26 wrong solves a game. Set by set it leads Luna alone by +9.2 points (+1.9 to +15.8). On v4 and grading-505 it won 36.7% and tied the bots.

**Lineup 6a on v6:** the bot won 58.6% against two Lunas (v4: 50%). The Lunas won more rounds a game (1.38 and 1.36 to the bot's 1.25), at a median bank of $1,750 and $1,550 against the bot's $5,300, solving at 44–45% showing with 69% right and 0.62–0.63 wrong solves a game each. By seat the bot won 59%, 61%, 56%; bonus 197 of 211.

**Lineup 6b on v6:** the bot won 65.8% against two Haikus (v4: 56%), winning 1.91 rounds a game to their 1.13 and 0.95 at a median bank of $4,500 against $2,550 and $2,850. The Haikus solved late (71% and 73% showing, 92–94% right). By seat the bot won 62%, 68%, 68%; bonus 216 of 237, the Haikus 46 of 69 and 38 of 54.

**Lineup 3f on v6:** the Haiku hybrid ties the bots (+5.0 and +3.3 points, both intervals crossing zero; v4: 44%). It won 1.42 rounds a game to the bots' 1.30 and 1.29, solving at a median 62% showing (bots 63–64%) with 97% right, median bank $4,575 at its solves. Bonus 124 of 130. **The hybrid's lift holds on a second lab:** Haiku hybrid minus Haiku alone, set by set, **+28.6 points (+23.3 to +33.9)**, against Luna's +26.1 (+19.2 to +32.8). The Haiku hybrid trails the Luna hybrid by 4.4 points (−8.9 to −0.0). Haiku alone solves late (70% showing) and Luna early (48%); in the hybrid the bot drops Luna's answers that don't fit, so Luna's early reads reach the bot sooner than Haiku's.

**Lineup 3 on v6:** the Luna hybrid won 1.57 rounds a game to the bots' 1.21, 98% of its solves right at a median 60% showing, median bank $4,500 at its solves (bots about $5,000). Bonus 140 of 146. Against v4 bots it won 45%; v6's bots win more rounds, which leaves the hybrid less.

## Lineup 1 result (2026-10-31): W is Sol

**Rule change after lineup 1:** from 2026-10-31 the solver of round 3 starts round 4 (before, seat 1 always did). Lineup 1 played under the old rule and is not rerun: W is Sol either way, and in 100 self-play sets the change moved no player's win rate by more than a point (`logs/selfplay/v4-check-newstart`). Lineups 2 to 6 play under the new rule. Don't extend lineup 1's folder with more sets, since it would mix the two rules.

360 games in 60 sets, `logs/tournaments/seed707-d7589355`, $12.46 in all.

| | Sol | DeepSeek | Haiku |
|---|---|---|---|
| Win rate | **66%** (61–70%) | 25% (21–29%) | 9% (6–13%) |
| 1st / 2nd / 3rd | 237 / 75 / 48 | 89 / 186 / 85 | 34 / 99 / 227 |
| Rounds won per game | 1.92 | 1.54 | 0.55 |
| Solves right | 96% | 89% | 91% |
| Board showing at a correct solve | 48% | 46% | 67% |
| Bonus won | 236 / 237 | 84 / 89 | 28 / 34 |
| Invalid moves per game | 0.02 | 0.39 | 0.20 |
| Cost per game | $0.015 | $0.014 | $0.005 |

Every gap clears zero: Sol leads DeepSeek by 41 points (34 to 49), and DeepSeek leads Haiku by 15 (9 to 21). In Sol's 123 losses it won no round 40 times, won at least as many rounds as the winner 31 times, and made a wrong solve in only 12.

## Lineup 2 result (2026-10-31): Sol beats two bots, but less easily than two LLMs

360 games in 60 sets, `logs/tournaments/seed707-e250a942`, $6.35, bot v4, round 3's solver starting round 4.

| | Sol | Each bot |
|---|---|---|
| Win rate | **58%** (51–64%) | 21% (17–25%) |
| Rounds won per game | 2.26 | 0.87 |
| Median bank when winning a round (rounds 1–3) | $3,350–3,975 | $5,300–7,000 |
| Solves right | 96% | 90% |
| Board showing at a correct solve | 52% | 65% |
| Bonus won | 205 / 209 | 129 / 151 (both bots) |

Sol leads each bot by 37 to 38 points (27 to 47). Set by set, Sol wins 7.8 points less against two bots than against DeepSeek and Haiku in lineup 1 (−15.0 to −0.6), with the caveat that lineup 1 ran under the old round 4 rule (worth under a point in self-play). Sol takes 56% of rounds, but the bots bank half again as much when they win one, and in 125 of Sol's 151 losses a bot took round 4. The bots read Sol as LLM-like (median w 0.87 at game end), so v4's per-opponent gain was in use; only a rerun with v3 seats would show whether it helped.

## Lineup 2 with bot v5 (2026-11-02): Sol still wins, by less

A v5 addendum; the v4 result above stands. 360 games in 60 sets, `logs/tournaments/seed707-2858c353`, $5.86, bot v5, the same deck, seed, and sets as the v4 run, so every game replays its v4 counterpart's puzzles and spins.

| | Sol vs two v5 bots | Each v5 bot | Sol vs two v4 bots |
|---|---|---|---|
| Win rate | **49%** (42–55%) | 26% (21–30%) | 58% |
| Rounds won per game | 1.99 | 1.01 | 2.26 |
| Board showing at a correct solve | 51% | 61% | 53% (bots 65%) |
| Wrong solves, all games | 28 | 14 (both bots) | 34 (bots 69) |
| Bonus won | 174 / 175 | 172 / 185 (both bots) | 205 / 209 (bots 129 / 151) |
| Average total | $31,614 | $21,867 | $36,603 (bots $16,468) |

- Sol leads each v5 bot by 22 to 24 points (+12 to +34), against 37 to 38 with v4 bots. Game by game, Sol wins 9.4 points less often than against v4 (−16.1 to −3.1, resampling sets).
- The rounds Sol lost are the long ones, where the reading fixes aim. Sol took 56% of rounds with 27 or more letters (v4: 65%), 44% at 23–26 (v4: 54%), 50% at 18–22 (v4: 55%), and 48% at 17 or fewer (v4: 49%).
- The bots' wrong solves fell from 69 to 14, and they solved earlier (61% showing against 65%). Sol's play didn't change: it solved at 51–53% showing and missed one bonus.
- By seat, Sol won 58%, 37%, and 51% (v4: 55%, 53%, 66%). Only seat 1 held up (+3 points; seats 2 and 3 −17 and −15). With 120 games a seat this may be noise; nothing here explains it yet.
- Sets 0–36 cost Sol 13 points against v4, sets 37–59 only 4. Puzzle lengths match across the halves (median 23 letters both), so this reads as noise around the overall −9.
- **Why Sol still wins.** Each round Sol won was replayed through the bots' reader, on the board Sol solved and from the bots' own logs on their last turn (no API calls). Of Sol's 715 rounds (v4 run: 812): 34% the bot's best answer was wrong on Sol's board (v4: 47%), at a median 39% showing; 30% it was right but unsure (median calibrated 0.61; v4 25%); 28% it would have been sure on that board but Sol had the turn (v4 22%); and 8% it knew the answer, kept spinning for money, and hit Bankrupt (v4 6%). v5 took its rounds from the wrong-answer group (380 to 246). About 1.2 of Sol's 2 rounds a game still come from boards Sol reads and the bot can't, yet; that is recognition, which a word-count reader can approach but not match.

## Sol against two Luna hybrids on v5 (2026-11-02): the hybrids help a little, if at all

A v5 addendum. 360 games in 60 sets, `logs/tournaments/seed707-8e6d80ec`, $8.54 (Sol $5.82, the hybrids $2.72), the same deck, seed, and sets as both lineup 2 runs.

| | Sol vs two Luna hybrids | Each hybrid | Sol vs two v5 bots | Sol vs two v4 bots |
|---|---|---|---|---|
| Win rate | **45%** (40–50%) | 27.5% | 48.6% | 58.1% |
| Rounds won per game | 1.87 | 1.07 | 1.99 | 2.26 |
| Board showing at the opponents' correct solves | | 59% | 61.5% | 65% |
| Opponents' bonus won | | 192 / 198 (both) | 172 / 185 | 129 / 151 |

- Game by game, Sol wins 3.6 points less than against plain v5 bots (−9.4 to +2.5) and 13.1 less than against v4 bots (−19.4 to −6.7). Sol leads each hybrid by 16 to 19 points.
- Of Sol's 673 winning rounds: in 37% Sol solved before either hybrid had a turn, and in 39% Luna couldn't yet read the board on the hybrids' turns. Luna answered wrong in 5%, and was right but trusted too little (around 0.6) in 8%.
- In the other 11% (73 rounds), the hybrid had Luna's right answer at 90% or more and kept spinning for money; every one of those turns ended in Bankrupt (51), Lose a Turn (14), or a Mystery flipped to Bankrupt (8), and Sol solved. The plain v5 bots did the same in 59 rounds. Those are the visible cost of the bot's strategy, which is deliberate: it can't out-read an LLM, so it makes every round it wins count. Counted in full, a hybrid that knew the answer kept spinning in 696 rounds and still won 72% of them, adding $3,538 on average; it lost 13% to Sol and 15% to the other hybrid, giving up about $2,300 each (v5 bots: 604 rounds, 73% won, +$3,161). With a $2,500 bank, that is about $4,350 expected against $2,500 for solving at once, so milking pays even with Sol at the table. From round 3 the bot already weighs it by win chance, with Sol's steal odds.
- The hybrids are right on 99% of solves but not too cautious: when Luna had the answer, the median trust was 0.97. Sol's lead is reading speed, which Luna doesn't match either.

## Lineup 3 result (2026-10-31): the hybrid beats two bots, but Sol alone does better

360 games in 60 sets, `logs/tournaments/seed707-ca968604`, $1.93, bot v4, round 3's solver starting round 4.

| | Hybrid (bot + Luna) | Each bot | Sol in lineup 2, same bots |
|---|---|---|---|
| Win rate | **45%** (40–51%) | 27–28% | 58% |
| Rounds won per game | 1.74 | 1.13 | 2.26 |
| Median bank when winning a round (rounds 1–3) | $4,900–5,375 | $4,900–6,550 | $3,350–3,975 |
| Solves right | 97.5% | 92.5% | 96% |
| Board showing at a correct solve | 65% | 66% | 52% |
| Bonus won | 147 / 163 | 169 / 197 (both bots) | 205 / 209 |

The hybrid leads each bot by 17 to 19 points (9 to 27). Set by set, it wins 12.8 points less than Sol did against the same two bots (−20.0 to −5.6). It asked Luna 5,817 times (16 a game, about 6 seconds each): Luna called the board not solvable 2,484 times and gave an answer 3,333 times, 84% of them right. Luna's reads made the hybrid surer (median +0.20 confidence) and more accurate, but it still solved at the bots' 65% of the board, milking as they do. The bots read it as bot-like (median w 0.31). A Luna-alone lineup on the same sets would show what the bot's strategy adds to Luna.

## Lineup 3b result (2026-10-31): Luna alone loses to two bots; the bot's strategy adds 28 points to Luna

360 games in 60 sets, `logs/tournaments/seed707-e71dd1af`, $1.33. Luna, bot, bot: Luna playing every move itself, against the same two bots and sets as lineups 2 and 3.

| Against two bots | Luna alone | Hybrid (bot + Luna) | Sol alone |
|---|---|---|---|
| Win rate | **17.5%** (12–23%) | 45% | 58% |
| Rounds won per game | 1.79 | 1.74 | 2.26 |
| Main-round winnings per round won | about $2,460 | about $5,400 | about $4,270 |
| Wrong solves per game | 0.70 | 0.04 | 0.09 |
| Solves right | 72% | 97.5% | 96% |

Set by set: hybrid − Luna alone +27.8 points (+20.8 to +34.7), Sol − Luna alone +40.6 (+32.5 to +48.3), Sol − hybrid +12.8 (+5.6 to +20.0). Luna's losses are discipline: 219 solves that don't fit the board (it puts already-called letters in hidden squares, repeats refuted answers, guesses on near-empty boards) and 150 bad tool calls, almost all a consonant called without spinning first (every tool is offered on every move, for prompt caching). The hybrid's fit check, refuted-answer list, and the bot's choice of when to trust a read remove those faults. The two identical bots differed by 8 points (+0.6 to +16), most likely chance.

## Lineups 6a and 3d results (2026-10-31)

| | 6a: bot against two Lunas | 3d: Haiku alone against two bots |
|---|---|---|
| Win rate | bot **50%** (43–57%); Lunas 26% and 24% | Haiku **14%** (10–19%); bots 40% and 46% |
| Gap | bot over each Luna +25 to +26 (+13 to +36) | Haiku under each bot −25 to −31 |
| The LLM's solves | 70% right, at 47–48% of the board | 95% right, at 72% of the board |
| The LLM's wrong solves per game | about 0.7 each | 0.07 |
| Rounds won per game (the LLM) | | 1.22 (Luna alone: 1.79) |
| Cost | $2.58 | $2.61 |

Luna is reckless (early, often wrong) and Haiku passive (right, but too late): opposite faults, both well below a fair share. Sol, early and right, is the only one of the three that beats the bots. Folders `seed707-6496578d` (6a) and `seed707-4ef950be` (3d).

## Lineups 6b and 3c results (2026-10-31)

| | 6b: bot against two Haikus | 3c: DeepSeek alone against two bots |
|---|---|---|
| Win rate | bot **56%** (50–63%); Haikus 23% and 20% | DeepSeek **37%** (31–43%); bots 31% and 32% |
| Against the 33% null | rejected: the bot is better | **not rejected: DeepSeek ties the bot** |
| The LLM's solves | 93% right, at 71–74% of the board | 89% right, at 49% of the board |
| Rounds won per game (the LLM) | | 2.12, at a median bank of $1,300 per round |
| Cost | $5.55 | $6.20 |

DeepSeek is eager and mostly right: it wins more rounds than any model but Sol, at small banks, and the bots' bigger banks balance it out (main-round money about $6,100 each). Set by set: Sol − DeepSeek +21 (+14 to +28), hybrid − DeepSeek +8.6 (+2.8 to +14.4), DeepSeek − Luna +19, DeepSeek − Haiku +22. Measured from either side (a model alone against two bots, or the bot against two copies), Luna and Haiku lose by similar margins in the same order. The copies of each model passed their A/A test (gaps +1 and +3, intervals across zero).

## When decision models choose to solve (probe, 2026-10-31)

In choice mode, d1-ultra (first on Artificial Analysis's Decision Index) never solved in a one-set trial, so a probe asked three decision models, on 30 tuning puzzles revealed letter by letter (289 boards), which move they'd make, and separately whether the board was solvable; Luna tried one solve on every board. Script: `logs/solve-probe.py`.

| | First picks solve, on average | Luna right at 60–69% of the board | Model's P(solvable) there |
|---|---|---|---|
| Luna (the solver) | can solve from 30% of the board | 100% | |
| GPT-6 Luna Decisions (index rank 15) | 31% | | 0.56 |
| d1-ultra (rank 1) | 86% (26 of 30 puzzles) | | 0.17 |
| Jev 1.14 (rank 5) | 90% (20 of 30) | | 0.35 |

d1-ultra and Jev are strongly underconfident on this task: they seem to judge solvability by their own reading, though the seat hands the solve to Luna, who reads far better. Luna Decisions, the same family as its solver, picks solve about as often as Luna can succeed at every stage. The overconfidence the index found on knowledge questions doesn't carry over to reading a board. Expect d1-ultra's lineup near 0%: the bots usually solve by about 65% of the board.

## d1-ultra lineup, and finishing places (2026-10-31)

**d1-ultra decision seat (choice mode, Luna solving) alone against two bots:** 4% (2–7%), 35¢ for 360 games. It solved 243 times, 87% right, but at a median 75% of the board, after the bots' usual 63–65%, and often for the $1,000 minimum. The top model on Artificial Analysis's Decision Index is the weakest player tested.

**Finishing places** (ties share places; 2.00 is par). Contestants keep what they bank even without reaching the bonus, so placement matters as well as winning.

| Alone against two bots | Average place (95%) | 1st / 2nd / 3rd |
|---|---|---|
| Sol | 1.57 (1.48–1.67) | 58 / 27 / 15% |
| Hybrid (Luna) | 1.81 (1.72–1.91) | 45 / 28 / 27% |
| DeepSeek | 1.87 (1.76–1.98) | 37 / 40 / 23% |
| Luna | 2.12 (2.03–2.21) | 18 / 53 / 30% |
| Haiku | 2.33 (2.24–2.41) | 14 / 38 / 47% |
| Hybrid (Haiku) | 1.85 (1.77–1.94) | 44 / 28 / 29% |
| Luna Decisions seat | 2.42 (2.35–2.48) | 8 / 42 / 50% |
| d1-ultra seat | 2.63 (2.56–2.70) | 4 / 28 / 67% |

DeepSeek ties the bots on wins but beats them on place: it rarely finishes last. Luna wins only 18% but is second 53% of the time and last no more often than a bot, so its average place is near par. The bots are boom or bust: against two Lunas the bot won 50% and was last 32%. Chart: `figures/7-finishing-places.png`.

## Money, margins, leads, and risk (2026-10-31)

Each player alone against two bots, then the bot against two copies; main-round money is the total before the bonus. Charts 8–11 in `figures/`.

| | Main-round money: median (mean, sd) | $0 games | Led after round 3 / held | Trailed / came back | Bankrupts a game | Turns held | $1M won |
|---|---|---|---|---|---|---|---|
| Sol | $8.6k ($9.6k, $6.4k) | 9% | 53% / 89% | 47% / 23% | 0.92 | 38.5% | 0 |
| Hybrid (Luna) | $9.2k ($9.4k, $7.3k) | 14% | 43% / 78% | 57% / 20% | 1.32 | 35.5% | 2 |
| DeepSeek | $4.9k ($6.2k, $5.5k) | 8% | 32% / 81% | 68% / 16% | 0.73 | 31.4% | 0 |
| Luna | $3.5k ($4.4k, $3.8k) | 8% | 18% / 62% | 81% / 7% | 0.60 | 28.8% | 0 |
| Haiku | $3.0k ($4.4k, $4.9k) | 21% | 18% / 56% | 82% / 5% | 1.04 | 30.4% | 0 |
| Hybrid (Haiku) | $7.8k ($8.9k, $7.4k) | 18% | 38% / 80% | 62% / 21% | 1.33 | 34.5% | 2 |
| Luna Decisions seat | $2.0k ($2.8k, $3.1k) | 18% | 11% / 61% | 89% / 2% | 0.75 | 20.2% | 0 |
| d1-ultra seat | $0 ($2.1k, $3.5k) | 52% | 9% / 42% | 91% / 1% | 0.94 | 24.1% | 0 |
| Bot, against two Lunas | $5.3k ($6.9k, $7.4k) | 35% | 49% / 87% | 51% / 14% | 1.25 | 37.6% | 2 |
| Bot, against two Haikus | $7.3k ($8.9k, $8.1k) | 19% | 53% / 87% | 47% / 21% | 1.61 | 37.7% | 1 |

- **Take-home money** (with the bonus) is skewed by $40k+ bonus wins: Sol's median is $49.6k, everyone else's $0–16.5k. Report medians.
- **Gaps between places** (median main-round money, per lineup): 1st to 2nd about $4.5–6.6k, 2nd to 3rd about $2.5–5.0k. 9–19% of games are won by under $1,000.
- **Bot-based players won 37 of the 38 $1M envelopes** (2–6 per lineup, including in the bots' seats against Sol and DeepSeek). Against bots, no LLM ever did; the one LLM win was Haiku's, once, in lineup 1, with no bots at the table. It needs the Million card kept into the bonus, which the bot values and holds. (Corrected 2026-11-01: this first said no LLM ever won it, from the lineups against bots only.)
- **The bot is boom or bust:** against two Lunas it banked nothing in 35% of games and had the highest Bankrupt rate, yet won half. The LLMs bank something in about 92% of games.

## Lineups 3f and d2 results (2026-11-01): the hybrid lifts a second lab; a decision model doesn't

**3f, the Haiku hybrid** (the bot decides everything, Haiku reads the board), alone against two bots: **44%** (38–49%), the bots 28% and 29%. 360 games, $4.76 (1.3¢ a game), 2h34m. It replaces 3e, the DeepSeek hybrid, stopped after 9 games because DeepSeek's runaway thinking made it slow and costly. Haiku's trust and steal curves were measured on the tuning boards first (`calibrate trust`).

| Set by set | Gap (95%) |
|---|---|
| **Haiku hybrid − Haiku alone** | **+29.2 (+22.2 to +36.1)** |
| Haiku hybrid − Luna hybrid | −1.7 (−7.2 to +3.9) |
| Haiku hybrid − DeepSeek alone | +6.9 (+0.3 to +13.6) |
| Haiku hybrid − Sol alone | −14.4 (−20.0 to −8.6) |

- **The lift replicates across labs and across opposite faults:** +27.8 for Luna (OpenAI, reckless) and +29.2 for Haiku (Anthropic, passive). The bot fixes whichever fault the model has.
- **The two hybrids tie** on wins, place (1.81 and 1.85) and money. The bot's strategy sets the level; the reader matters only through accuracy, and both are accurate inside the hybrid (Haiku 95% of solves right, 0 invalid moves).
- Haiku's hybrid wins slightly fewer rounds (1.58 a game against 1.74), since Haiku says "solvable" later, at the same bank per round (median about $4,800).
- The two bots passed their A/A test: −1 point (−5 to +2).

**d2, the Luna Decisions seat** (choice mode: GPT-6 Luna Decisions makes every move and decides when to solve; Luna writes the answer), alone against two bots: **8%** (4–12%), the bots 45% and 47%. 360 games, 96¢.

- **Worse than Luna playing alone:** −9.4 points set by set (−15.8 to −3.6). Ahead of d1-ultra (4%).
- **It solves as early as Luna and as often wrongly:** 695 attempts (1.9 a game), 65% right, at 54% of the board; 0.67 wrong solves a game (Luna alone 0.70).
- **And it handles the wheel worse than Luna:** it misses consonants twice as often (1.56 a game against 0.75), almost never buys a vowel (0.08 a game against 2.67), and holds only 20% of turns (Luna alone 29%). Its rounds are cheap: median bank $1,000, the round minimum.
- 0.53 invalid answers a game, from the Decisions API.

**Who decides, holding the reader fixed** (alone against two bots):

| Who decides | Luna reading | Haiku reading |
|---|---|---|
| A decision model | 8% (Luna Decisions), 4% (d1-ultra) | |
| The model itself | 17.5% | 14% |
| **The bot (hybrid)** | **45%** | **44%** |

## Puzzle length (2026-11-01)

Share of solved main rounds each player won against two bots (a third is fair), by letters in the puzzle; 95% from resampling sets. Chart: `figures/12-puzzle-length.png`.

| Player | 16–17 | 18–19 | 20–22 | 23–26 | 27+ | 27+ minus 16–19 |
|---|---|---|---|---|---|---|
| Sol | 49% | 54% | 55% | 53% | 65% | +13.7 (+4.1 to +23.9) |
| Hybrid (Luna) | 40% | 39% | 46% | 41% | 47% | +7.8 (−1.1 to +16.8) |
| Hybrid (Haiku) | 36% | 38% | 39% | 40% | 41% | +4.4 (−4.0 to +13.3) |
| DeepSeek | 51% | 51% | 52% | 51% | 58% | +7.2 (−3.5 to +17.8) |
| Luna | 44% | 43% | 46% | 41% | 49% | +5.4 (−7.4 to +18.6) |
| Haiku | 28% | 22% | 31% | 31% | 34% | +8.4 (−1.4 to +18.6) |
| Luna Decisions seat | 29% | 31% | 28% | 27% | 40% | +10.2 (−2.2 to +22.2) |
| d1-ultra seat | 15% | 12% | 12% | 13% | 20% | +6.1 (−1.6 to +13.8) |
| All 8, averaged | | | | | | +7.9 (+0.3 to +15.6) |

Puzzles run 16 to 35 letters, median 23; solved rounds per band in Sol's lineup: 192, 138, 312, 402, 396. The bots' median board at their correct solves rises with length (59%, 67%, 65%, 68%, 68%), while Sol (50%, 53%, 50%, 52%, 48%), DeepSeek and Luna stay near 50%. On the shortest puzzles Sol beats the bots to the solve by about 6 points of board; on the longest, by about 20. Caveats: length goes with category, and the 8 lineups share the same bots and puzzles.

## Frontier and other labs: trials only, until there's a grant (2026-10-31)

Three more models had one-set trials (set 0, six games, alone against two bots, on the laptop):

| Model | Set 0 games won | Cost per game | Why it costs more than Sol (1.8¢) |
|---|---|---|---|
| Gemini 4 Argon (flex) | 5 of 6 | 9.6¢ | Google caches only prompts of 4,096 tokens or more; our rounds start at about 1,700 |
| Gemini 3.8 Flash (flex) | 5 of 6 | 6.9¢ | the same cache floor, and about 1,500 output tokens a move |
| GLM 5.3 (Morph FP8) | stopped | about 8–12¢ | about 1,500 output tokens a move and 11,500-token prompts; Morph was very slow (one game made one move in six minutes) |

On the same set, Sol won 3 of 6, the hybrid 3, and Luna 2. One set is too small to rank anyone. Ian set these models aside until he has a grant. Argon's and Flash's set 0 folders (`seed707-d589e90f`, `seed707-07858ca3`) are on the laptop; a later run that continues them skips set 0. GLM 5.3 would be a disclosed exception to the rule that puzzle labs don't play (Z.ai's GLM 4.7 judged the puzzles); if it ever plays, the bonus test on aired and generated puzzles would check whether the judge's taste helps it.

## Folders (resume or extend with `--out`)

On 2026-10-31 folder names stopped counting provider pins of models that don't play, and decision settings when no decision seat plays. Each change renamed tournaments once. To resume or extend a tournament started before that, pass its folder: `--out logs/tournaments/<folder>`.

| Lineup | Folder |
|---|---|
| 1 | `seed707-d7589355` |
| 2 | `seed707-e250a942` |
| 3 | `seed707-ca968604` |
| 3b | `seed707-e71dd1af` |
| 6a | `seed707-6496578d` |
| 3d | `seed707-4ef950be` |
| 6b | `seed707-261dfa12` |
| 3c | `seed707-6fa48eea` |
| 3e (stopped, 9 games, server only) | `seed707-df31ddd4` |
| 3f | `seed707-1a2b906a` |
| d1 | `seed707-5e5a8958` on the server; copied to `seed707-d1-server` on the laptop |
| d2 | `seed707-bd7e0c0b` on the server; copied to `seed707-lunadec-server` on the laptop (the laptop's `seed707-bd7e0c0b` is the one-set trial) |

## Order

1. **Now:** run lineup 1 (LLMs only, so the bot version doesn't matter). Alongside it, run v4's data run:
   ```
   uv run python -m rstlne.selfplay round-banks --puzzles puzzles/generated/tuning-101.json --sets 334 --seed 909 --out logs/selfplay/round-banks-v3 --workers 4
   ```
2. **Fit and freeze v4:** copy the data run back, run `selfplay v4-fit`, and freeze v4.
3. **Check v4:** in self-play, v4 against v3 against an eager v3, on grading-202, about 2,000 games.
4. **If v4 beats v3,** move `[bot] version` to 4. If not, stay on v3.
5. **Pick W** from lineup 1. If #1 and #2 are within each other's error bars, note that it's a close call.
6. **Run 3, 2, 4, 5, and 6.**

## Commands (on the server)

The same flags go at the end of every command:

```
--puzzles puzzles/generated/grading-505.json --seed 707
```

| # | Command |
|---|---|
| 1 | `uv run python -m rstlne.tournament --seats llm:openai/gpt-6.1-sol,llm:deepseek/deepseek-v4.1-flash-1017,llm:anthropic/claude-haiku-5.5 --sets 60 --parallel 16 --max-cost 20` |
| 3 | `uv run python -m rstlne.tournament --seats hybrid:openai/gpt-6-luna,bot,bot --sets 60 --parallel 10 --max-cost 5` |
| 2 | `uv run python -m rstlne.tournament --seats llm:W,bot,bot --sets 60 --parallel 5 --max-cost 10` |
| 4 | `uv run python -m rstlne.tournament --seats llm:W,hybrid:openai/gpt-6-luna,bot --sets 60 --parallel 5 --max-cost 10` |
| 5 | `uv run python -m rstlne.tournament --seats llm:W,hybrid:openai/gpt-6-luna,hybrid:openai/gpt-6-luna --sets 60 --parallel 5 --max-cost 10` |
| 6 | `uv run python -m rstlne.tournament --seats bot,llm:W,llm:W --sets 20 --parallel 5 --max-cost 5` (optional) |
| 6a | `uv run python -m rstlne.tournament --seats bot,llm:openai/gpt-6-luna,llm:openai/gpt-6-luna --sets 60 --parallel 8 --max-cost 4` |
| 6b | `uv run python -m rstlne.tournament --seats bot,llm:anthropic/claude-haiku-5.5,llm:anthropic/claude-haiku-5.5 --sets 60 --parallel 8 --max-cost 6` |
| 6c | `uv run python -m rstlne.tournament --seats bot,llm:deepseek/deepseek-v4.1-flash-1017,llm:deepseek/deepseek-v4.1-flash-1017 --sets 60 --parallel 8 --max-cost 14` |
| 3c | `uv run python -m rstlne.tournament --seats llm:deepseek/deepseek-v4.1-flash-1017,bot,bot --sets 60 --parallel 8 --max-cost 8` |
| 3d | `uv run python -m rstlne.tournament --seats llm:anthropic/claude-haiku-5.5,bot,bot --sets 60 --parallel 8 --max-cost 4` |
| 3e | `uv run python -m rstlne.tournament --seats hybrid:deepseek/deepseek-v4.1-flash-1017,bot,bot --sets 60 --parallel 8 --max-cost 5` |
| 3f | `uv run python -m rstlne.tournament --seats hybrid:anthropic/claude-haiku-5.5,bot,bot --sets 60 --parallel 12 --max-cost 6` |
| d1 | `uv run python -m rstlne.tournament --seats decision:liquid/d1-ultra,bot,bot --sets 60 --parallel 8 --max-cost 2` |
| d2 | `uv run python -m rstlne.tournament --seats decision:openai/gpt-6-luna-decisions,bot,bot --sets 60 --parallel 8 --max-cost 2` |

Replace `W` with the winner's model name, such as `openai/gpt-6.1-sol`.

- **Logs:** add `2>&1 | tee -a logs/grid-N.txt` to keep each run's output.
- **Hitting the cost cap:** a run that stops at its `--max-cost` resumes when you rerun it with a higher cap.

## Watch out for

- **Memory.** Every bot or hybrid seat loads about 420 MB per game process, and the server has 15 GB. Keep lineups 2 to 6 at `--parallel 5` each. Lineup 1 has no bots, so it can use `--parallel 24`.
- **Time.** Lineup 1 is the slow one: three thinking models play every move, about 4 to 5 hours. The rest take a few hours together.
- **Cost.** These estimates include OpenAI's flex tier for Terra and Sol, and the cache fix that sends every tool on every move (`tools = "all"`). Together they cut cost per game about 4×.
  - Lineup 1 is about $17.
  - Lineups 2 to 6 at 50 sets are about $26 if Sol wins, about $15 if Terra wins, and about $12 if DeepSeek wins.
  - Sol hasn't played our game yet, so its figure is a guess until its first games.

## Afterwards

Copy each tournament folder back:

```
rsync -av server:rstlne/logs/tournaments/ logs/tournaments/
```

The analysis compares the same sets across lineups.
