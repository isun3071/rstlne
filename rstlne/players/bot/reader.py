"""Readers turn the board and category into a Belief.

FrequencyReader knows only English letter frequency: the fallback when nothing else fits.
WordListReader samples whole answers, one word per slot from a word list weighted by frequency,
with an unknown word in every slot whose letters come from letter frequency. Unknown words become
the Belief's out of vocabulary share. Word n-grams, multiword entries, and category priors come later.
"""

from __future__ import annotations

import math
import random
from collections import Counter, defaultdict
from collections.abc import Mapping
from typing import Protocol

from rstlne.engine.puzzle import LETTERS
from rstlne.engine.state import PublicView
from rstlne.players.bot.belief import Belief, LetterStats
from rstlne.players.bot.seed import view_seed
from rstlne.players.bot.versions import Knobs

# Percent of letters in English text
FREQUENCY = {
    "E": 12.70, "T": 9.06, "A": 8.17, "O": 7.51, "I": 6.97, "N": 6.75, "S": 6.33, "H": 6.09, "R": 5.99,
    "D": 4.25, "L": 4.03, "C": 2.78, "U": 2.76, "M": 2.41, "W": 2.36, "F": 2.23, "G": 2.02, "Y": 1.97,
    "P": 1.93, "B": 1.29, "V": 0.98, "K": 0.77, "J": 0.15, "X": 0.15, "Q": 0.10, "Z": 0.07,
}
_SHARE = {c: f / sum(FREQUENCY.values()) for c, f in FREQUENCY.items()}
_UNKNOWN = None  # marks an unknown word in a slot


class Reader(Protocol):
    def read(self, view: PublicView) -> Belief: ...


def board_text(board: str) -> str:
    """`W _ _ _ L   O F` -> `W___L OF`: words split by single spaces, `_` for hidden squares."""
    return " ".join(word.replace(" ", "") for word in board.split("   "))


def _entropy(counts: Counter, total: int) -> float:
    return -sum(n / total * math.log2(n / total) for n in counts.values() if n)


class FrequencyReader:
    name = "frequency"

    def read(self, view: PublicView) -> Belief:
        text = board_text(view.board)
        hidden = text.count("_")
        if hidden == 0:
            return Belief(letters={}, answers=((text, 1.0),), oov=0.0)
        pool = LETTERS - set(view.used_letters)
        total = sum(FREQUENCY[c] for c in pool)
        letters = {}
        for c in pool:
            f = FREQUENCY[c] / total
            p_hit = 1 - (1 - f) ** hidden
            bits = -(f * math.log2(f) + (1 - f) * math.log2(1 - f)) if 0 < f < 1 else 0.0
            letters[c] = LetterStats(p_hit=p_hit, count=hidden * f / p_hit, entropy=hidden * bits)
        return Belief(letters=letters, answers=(), oov=1.0)


class WordListReader:
    name = "word list"

    def __init__(self, lexicon: Mapping[str, float], knobs: Knobs):
        self.knobs = knobs
        self.by_length: dict[int, list[tuple[str, float]]] = defaultdict(list)
        mass = sum(lexicon.values())
        length_mass: Counter = Counter()
        for word, weight in lexicon.items():
            word = word.upper()
            self.by_length[len(word)].append((word, weight / mass))
            length_mass[len(word)] += weight / mass
        lengths = range(1, max(self.by_length, default=1) + 2)
        smoothed = {n: length_mass[n] + 1e-4 for n in lengths}  # every length can hold an unknown word
        total = sum(smoothed.values())
        self.length_share = {n: m / total for n, m in smoothed.items()}

    def read(self, view: PublicView) -> Belief:
        text = board_text(view.board)
        if "_" not in text:
            return Belief(letters={}, answers=((text, 1.0),), oov=0.0)
        used = set(view.used_letters)
        pool = sorted(LETTERS - used)
        pool_weights = [_SHARE[c] for c in pool]
        open_square = sum(_SHARE[c] for c in pool)  # chance an unknown word's hidden square avoids used letters
        slots = [self._slot(pattern, used, open_square) for pattern in text.split(" ")]
        rng = random.Random(view_seed(view))
        n = self.knobs.samples
        samples, unknown = [], []
        for _ in range(n):
            words, oov = [], False
            for pattern, (options, weights) in zip(text.split(" "), slots):
                word = rng.choices(options, weights)[0] if options else _UNKNOWN
                if word is _UNKNOWN:
                    oov = True
                    word = "".join(rng.choices(pool, pool_weights)[0] if c == "_" else c for c in pattern)
                words.append(word)
            samples.append(" ".join(words))
            unknown.append(oov)
        return summarize(samples, unknown, text, pool, self.knobs)

    def _slot(self, pattern: str, used: set[str], open_square: float) -> tuple[list, list[float]]:
        """One word slot's candidates and weights, the unknown word included."""
        options, weights = [], []
        for word, share in self.by_length.get(len(pattern), ()):
            if all((p == "_" and w in LETTERS and w not in used) or p == w for w, p in zip(word, pattern)):
                options.append(word)
                weights.append(share * (1 - self.knobs.unknown_word))
        if self.knobs.unknown_word > 0 or not options:
            fit = self.length_share.get(len(pattern), 1e-4)
            for p in pattern:
                fit *= open_square if p == "_" else _SHARE.get(p, 1.0)
            options.append(_UNKNOWN)
            weights.append(self.knobs.unknown_word * fit if options[:-1] else 1.0)
        return options, weights


def summarize(samples: list[str], unknown: list[bool], text: str, pool: list[str], knobs: Knobs) -> Belief:
    """A Belief from sampled whole answers. Answers with an unknown word count toward the oov share only."""
    n = len(samples)
    answers = Counter(a for a, oov in zip(samples, unknown) if not oov)
    top = sorted(answers.items(), key=lambda a: (-a[1], a[0]))[: knobs.top_answers]
    hidden = [i for i, c in enumerate(text) if c == "_"]
    letters = {}
    for c in pool:
        patterns = Counter(tuple(i for i in hidden if s[i] == c) for s in samples)
        hits = [s for s in samples if any(s[i] == c for i in hidden)]
        if not hits:
            continue
        count = sum(sum(s[i] == c for i in hidden) for s in hits) / len(hits)
        letters[c] = LetterStats(p_hit=len(hits) / n, count=count, entropy=_entropy(patterns, n))
    return Belief(letters=letters, answers=tuple((a, k / n) for a, k in top), oov=sum(unknown) / n)
