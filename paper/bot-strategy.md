# How bot v6 plays

This is bot v6's whole strategy, taken from the spec (`documentation.md`, Bot) and the code (`rstlne/players/bot/`). It's the draft of the paper's bot appendix. The numbers on how it plays in practice come from the v6 grid.

The bot has no language model inside it. It reads the board with word data and counting, turns every choice into one number, either expected dollars or the chance of winning the game, and takes the largest.

## 1. What it plays for

In rounds 1 and 2 the bot plays for money, scoring every move in expected dollars. From round 3 it plays for the chance of finishing first after the last main round, and scores every move by how it changes that chance. Winning by $100 then counts the same as winning by $10,000. A lead still matters, because it raises the chance of finishing first.

The win chance comes from a formula, P = Φ(lead / (σ √rounds left)), with σ = $6,000 and the lead measured from the bot's total to the highest opponent's. When the bot weighs an opponent taking the round, it counts that opponent's bank plus what it typically adds before solving. Since version 3 that spread is 20 equally likely amounts, read by how many letter squares are still hidden. Since version 4 it's fit separately for opponents that play like LLMs and like bots, and mixed by how LLM-like each seat has played this game.

From round 3, when every option's win chance is within 0.5 points of the best, the bot chooses by dollars instead, with held cards at their dollar values. So a bot that has already won or lost still plays the round out for money. The bonus round counts lightly. The Wild Card and the Million card are valued at what they'd add in the bonus round, as dollars in rounds 1 and 2 and only as a tiebreaker from round 3.

## 2. What it knows: the reader

The reader splits the board into word slots and samples 400 whole answers that fit. It weighs word frequency, category fit from word vectors, word pair and triple counts from Wikipedia, and known phrases and names from Wiktionary and Wikidata. Categories like Before & After, Rhyme Time, What Are You Doing? and Same Name get their own handling.

From those 400 answers it gets each letter's chance of appearing and its expected number of copies, the top answers with their shares of the sample, and the share that needed a word outside its lists. The top answer's raw share then goes through a calibration curve, fit on practice boards, that maps it to how often answers at that share were actually right. Decisions use the calibrated number. And a wrong solve by any seat rules that answer out for the rest of the round.

## 3. What it fears: steal odds

For each opponent the bot estimates the chance that seat solves correctly during its next turn, from how much of the board shows and how sure the bot itself is. Version 6 fits two base curves per turn, one on LLM play and one on bot play. Each opponent's curve mixes them by w, the bot's estimate of how LLM-like that seat plays. w starts at ½ each game. Seats that solve early push it toward 1, and seats that pass up boards they could read push it toward 0.

Each seat's estimate is then scaled by its actual solves against its expected solves this game, shrunk toward the base curve by a pseudo-count of 2. The chance of losing the round when the wheel passes is p_steal = q_next + (1 − q_next) × q_after: either the next seat solves, or the one after it does. The bot uses no names and no memory across games. All of it resets every game.

## 4. How it scores a move

On every turn the bot scores each legal move with one formula and takes the best:

V(move) = what it gains now + P(keep the wheel) × V(play on) + P(lose the wheel) × (1 − p_steal) × V(play on later)

A spin is averaged over every wedge on the wheel as it stands. A dollar wedge pays the best consonant's chance × wedge value × expected copies and keeps the wheel if the letter hits. Bankrupt wipes the round bank and the held cards and passes the wheel, and Lose a Turn passes it. Free Play, the Mystery and the Express follow their own rules (section 6).

Buying a vowel costs $250 and earns what the vowel's information is worth, keeping the wheel if the vowel is there. Solving is worth c × the value of banking the round (at least $1,000) plus (1 − c) × the value of the wheel passing, where c is the calibrated confidence. With no candidate answer at all, the bot never guesses unless solving is its only legal move.

Information has a dollar value: how much a letter raises the bot's chance of solving before the opponents, times what the round is worth. Losing the wheel costs the whole round if an opponent then solves. The bot gets nothing from it, not even the $1,000 minimum, and from round 3 the opponent's gain counts against the bot's win chance too.

## 5. Through a round

### Opening and middle: letters for money and information

On a dollar wedge the bot calls the consonant with the best chance × value × copies plus information value. A consonant at 99% or more is "safe" and gets called whatever the bot thinks of the full answer. Version 6 expects a miss to lose the round more often than not, so it leans toward the letter likeliest to hit. In a check on tuning puzzles, on the calls where versions 5 and 6 picked different consonants, version 6's hit 91.9% of the time and version 5's 75.8%.

Vowels get bought only when their information is worth more than the $250, which usually means late, when a vowel separates two candidate answers. In the v6 grid only 26% of the bots' vowel buys came while less than a quarter of the board showed. For Sol and Terra it was 73%.

The bot rarely solves before half the board shows. Against Sol, 76% of the bots' solve attempts came after that point, and 99% of their solves at 25–50% showing were right. On Free Play a miss keeps the wheel, so it calls the letter with the best money ($500 per consonant copy) plus information.

### Endgame: once it knows the answer, milking

When calibrated confidence reaches 95%, a planner takes over. It looks ahead through the answer's hidden consonants, most copies first and up to 8, and at each step compares solving now with spinning again. Another spin risks Bankrupt, which loses the bank and the wheel, Lose a Turn, and a miss if the answer turns out wrong. Each hit makes the bot surer, and the first miss rules out the answer it was sure of. Every way of losing the wheel is priced with the opponents' steal odds, so against an opponent likely to steal, the planner solves sooner. No vowels while milking. A vowel earns nothing.

In the v6 grid, across the six lineups of one model against two bots, the bots milked 472 to 767 rounds per 360 games. They won 63–69% of the rounds they milked and added a median $2,000–2,525 in each. Better opponents leave fewer rounds to milk: 1.3 a game against Sol and Terra, 2.1 against Haiku.

## 6. Special wedges

On the Mystery (round 2) the bot can keep k copies × $1,000 or flip: half the time $10,000 and the wheel, half the time Bankrupt. With one or two copies, flipping's average beats keeping. It nearly always flips.

It boards the Express (round 3) only when the value function, counting the chance that the final solve is right, favours riding over passing. Then it calls safe consonants, and once those run out it weighs buying a safe vowel against solving (from version 5). Any miss on the Express is Bankrupt. It rides only when nearly sure.

It spends the Wild Card on an extra consonant only when that's worth more than the card's saved value. The saved value is the card's lift to the bonus round, assumed to be +10 points of solve chance, times the chance of reaching the bonus.

The Million wedge's middle third plays as $500 and claims the card, and its outer thirds are Bankrupt. The bot values the card at its expected bonus-round worth and holds it into the bonus. In the earlier grid, bots and hybrids won 37 of the 38 $1,000,000 envelopes.

## 7. The bonus round

For its picks the bot tries every legal set of three consonants and a vowel (four consonants with the Wild Card), and keeps the set that gives its best guess the highest chance of being right after the reveal. In practice that's D, H, C and A on most puzzles, which leave about 55% of the answer showing, where Sol's own picks leave 77%. It then answers with its best guess, or with no candidate fills the blanks with the most common unused letter. On grading-606b's 100 bonus puzzles it solved 95.

## 8. What it doesn't do

It doesn't remember opponents across games or use their names, so it learns each seat's style from scratch every game. It has no neural model besides fixed word vectors. It never reads Wheel of Fortune puzzle archives as data, and grading, dev and private puzzles are never used for tuning.

## 9. How it fares (v6 grid)

Playing against one model and another bot, each bot wins 27% with Sol at the table, 38–39% with DeepSeek, 41–45% with Luna or Qwen 3.8 Flash, and 43–49% with Haiku. Against two copies of one player it wins 58.6% against Lunas, 65.8% against Haikus, 83.3% against Luna Decisions seats and 88.3% against d1-ultra seats.

Its edge is bigger rounds. It banks a median of $4,600–5,400 per round won, against $1,350–3,350 for the models playing alone. Its weakness is reading late: it solves at a median 62–68% of the board showing, so an opponent that's right with half the board up takes rounds before milking can start.

It also underrates strong readers. Against Sol and Terra it put its chance of losing the round, when passing the wheel unsure, at 64–65%. It was really 75–77%. Against Luna the estimate held, 64% against 66%. Its LLM steal curve was fit on earlier games of other chat models on practice puzzles, and one game is too little play for the per-seat adjustment to learn how much stronger Sol is.
