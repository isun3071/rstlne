# How bot v6 plays

This describes bot v6's whole strategy, from the spec (`documentation.md`, Bot) and the code (`rstlne/players/bot/`). It's the draft of the paper's bot appendix. The numbers on how it plays in practice come from the v6 grid.

The bot has no language model inside it. It reads the board with word data and counting. It turns every choice into one number, either expected dollars or the chance of winning the game, and takes the largest.

## 1. What it plays for

- **Rounds 1 and 2:** the most money. Every move is scored in expected dollars.
- **Round 3 on:** the chance of finishing first after the last main round. Every move is scored by how it changes that chance. Winning by $100 counts the same as winning by $10,000. A lead still helps, because it raises the chance of finishing first.
- **The win chance** comes from a formula, P = Φ(lead / (σ √rounds left)), with σ = $6,000. The lead is the bot's total minus the highest opponent's.
- **What an opponent adds before it solves.** When the bot weighs an opponent taking the round, it counts the opponent's current bank plus a spread of what it typically adds before solving. That spread is 20 equally likely amounts (from version 3), read by how many letter squares are still hidden. It's fit separately for opponents that play like LLMs and like bots, and mixed by how LLM-like each seat has played this game (from version 4).
- **Close calls.** From round 3, when every option's win chance is within 0.5 points of the best, the bot chooses by dollars instead, with held cards at their dollar values. A bot that has already won or lost a game still plays out the round for money.
- **The bonus round counts lightly.** The Wild Card and the Million card are valued by what they'd add in the bonus round. In rounds 1 and 2 that value counts as dollars. From round 3, it only breaks ties.

## 2. What it knows: the reader

- The reader splits the board into word slots and samples **400 whole answers** that fit, using word frequency, category fit (word vectors), and word pair and triple counts from Wikipedia. It also uses known phrases and names from Wiktionary and Wikidata, and special handling for categories like Before & After, Rhyme Time, What Are You Doing?, and Same Name.
- From those 400 answers it gets:
  - every letter's chance of appearing, and its expected number of copies
  - the top answers with their shares of the sample
  - the share that needed a word outside its lists
- **Calibration.** The raw share of the top answer passes through a curve fit on practice boards, which maps it to how often answers at that share were actually right. Every decision uses the calibrated number.
- A wrong solve by any seat rules that answer out for the rest of the round.

## 3. What it fears: steal odds

- For each opponent, the bot estimates the chance that seat solves correctly during its next turn. That chance depends on how much of the board shows and how sure the bot itself is.
- There are two base curves, both fit per turn in version 6. One is fit on LLM play and one on bot play. Each opponent's curve mixes the two by w, the bot's estimate of how LLM-like that seat plays. w starts at ½ each game and moves with every turn where the seat could have solved: early solvers climb toward 1, patient seats fall toward 0.
- Each seat's estimate is then scaled by its actual solves against expected solves this game, shrunk toward the base curve by a pseudo-count of 2.
- The chance of losing the round when the wheel passes is p_steal = q_next + (1 − q_next) × q_after: the next seat solves, or the one after it does.
- The bot uses no names and no memory across games. Everything resets every game.

## 4. How it scores a move

On every turn the bot scores each legal move with one formula and takes the best:

V(move) = what it gains now + P(keep the wheel) × V(play on) + P(lose the wheel) × (1 − p_steal) × V(play on later)

- **Spin:** an average over every wedge on the wheel as it stands.
  - A dollar wedge pays the best consonant's chance × wedge value × expected copies, and keeps the wheel if the letter hits.
  - Bankrupt wipes the round bank and the held cards, and passes the wheel.
  - Lose a Turn passes the wheel.
  - Free Play, the Mystery and the Express follow their own rules (section 6).
- **Buy a vowel:** −$250 plus what the vowel's information is worth. It keeps the wheel if the vowel is in the puzzle.
- **Solve:** c × the value of banking the round (at least $1,000) + (1 − c) × the value of the wheel passing, where c is the calibrated confidence. With no candidate answer at all, it never guesses unless solving is its only legal move.
- **Information has a dollar value:** how much a letter raises the bot's chance of solving before the opponents, times what the round is worth.
- **Losing the wheel costs the whole round** if an opponent then solves: the bot gets nothing from it, not even the $1,000 minimum. From round 3 the opponent's gain also counts against the bot's win chance.

## 5. Through a round

### Opening and middle: reading, and letters for money and information

- **Consonants.** On a dollar wedge it calls the consonant with the best chance × value × copies plus information value. A consonant at 99% or more is "safe" and gets called whatever the bot thinks of the full answer.
- **Version 6 changed letter choice.** It expects a miss to lose the round more often than not, so it leans toward the letter likeliest to hit. In a check on tuning puzzles, where versions 5 and 6 called different consonants, version 6's hit 91.9% of the time and version 5's 75.8%.
- **Vowels** are bought only when the information is worth more than the $250. So the bot buys most vowels late, when a vowel separates two candidate answers. In the v6 grid only 26% of its vowel buys came while less than a quarter of the board showed, against 73% of Sol's and Terra's.
- **Solving.** It rarely solves before half the board shows. Against Sol, 76% of the bots' solve attempts came after 50% showed, and 99% of their solves at 25–50% were right.
- **Free Play.** A miss keeps the wheel, so it calls the letter with the best money ($500 per consonant copy) plus information.

### Endgame: once it knows the answer, milking

- When calibrated confidence reaches **95%**, a planner takes over. It looks ahead through the answer's hidden consonants, most copies first, up to 8. At each step it compares solving now with spinning again.
- Spinning again risks:
  - Bankrupt, which loses the bank and passes the wheel
  - Lose a Turn, which passes the wheel
  - a miss, if the answer is wrong after all
- Each hit makes it surer, and the first miss means the answer it was sure of is ruled out. Every way of losing the wheel is priced with the opponents' steal odds. So against an opponent likely to steal, the planner solves sooner.
- It doesn't buy vowels while milking: a vowel earns nothing.
- **In practice (v6 grid):** across the six lineups with one model against two bots, the bots milked 472 to 767 rounds per 360 games and won 63–69% of the rounds they milked, adding a median $2,000–2,525 each. Better opponents leave them fewer rounds to milk: 1.3 a game against Sol and Terra, 2.1 against Haiku.

## 6. Special wedges

- **Mystery (round 2):** keep k copies × $1,000, or flip for half a chance at $10,000 (keeping the wheel) and half a chance at Bankrupt. With one or two copies, flipping's average beats keeping, so the bot nearly always flips.
- **Express (round 3):** it boards only when the value function, counting the chance that the final solve is right, favours riding over passing. Then it calls safe consonants, and once they run out it weighs buying a safe vowel against solving (from version 5). Any miss on the Express is Bankrupt, so it rides only when it's nearly sure.
- **Wild Card:** it spends the card on an extra consonant only when that's worth more than the card's saved value: its lift to the bonus round (assumed +10 points of solve chance) times the chance of reaching the bonus.
- **Million wedge:** the middle third plays as $500 and claims the card, and the outer thirds are Bankrupt. The card is valued at its expected bonus-round worth, so the bot holds it into the bonus. In the earlier grid, bots and hybrids won 37 of the 38 $1,000,000 envelopes.

## 7. The bonus round

- **Picks:** it tries every legal set of three consonants and a vowel (four consonants with the Wild Card), and scores each set by the chance its best guess is right after the reveal. In practice it picks D, H, C and A on most puzzles. Those leave about 55% of the answer showing, where Sol's own picks leave 77%.
- **Solve:** its best guess. With no candidate, it fills the blanks with the most common unused letter.
- On grading-606b's 100 bonus puzzles it solved 95.

## 8. What it doesn't do

- It doesn't remember opponents across games or use their names. It learns each seat's style from scratch every game.
- It doesn't use an LLM or any neural model besides fixed word vectors.
- It never reads Wheel of Fortune puzzle archives as data. Grading, dev and private puzzles are never used for tuning.

## 9. How it fares (v6 grid)

- **Against one model and another bot,** each bot wins:
  - 27% with Sol at the table
  - 38–39% with DeepSeek
  - 41–45% with Luna or Qwen 3.8 Flash
  - 43–49% with Haiku
- **Against two copies of one player** it wins 58.6% (Lunas), 65.8% (Haikus), 83.3% (Luna Decisions seats) and 88.3% (d1-ultra seats).
- **Its edge** is bigger rounds: a median of $4,600–5,400 per round won, against $1,350–3,350 for the models alone.
- **Its weakness** is reading late. It solves at a median 62–68% of the board showing, so an opponent that's right with half the board up takes rounds before milking can start.
- **It underrates strong readers.** Against Sol and Terra, it rated its chance of losing the round when passing the wheel unsure at 64–65%, and the real rate was 75–77%. Against Luna the estimate held (64% against 66%). Its LLM steal curve was fit on earlier games of other chat models on practice puzzles, and one game is too little play for the per-seat adjustment to learn how much stronger Sol is.
