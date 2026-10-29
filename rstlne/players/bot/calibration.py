"""Calibration: correcting the reader's confidence so that "70% sure" means right 70% of the time.

The curve is a short list of (raw confidence, how often that confidence was actually right) points,
fit as a never-decreasing function and interpolated between points. No points means no change.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import numpy as np


def calibration_curve(points: Sequence[tuple[float, bool]]) -> list[tuple[float, float, float, int]]:
    """Accuracy as a never-decreasing function of a stated probability, fit by pooling adjacent violators.
    Each block is (lowest probability, highest probability, accuracy, boards). Decision model thresholds
    and the bot's confidence curve both use it."""
    blocks: list[list] = []  # [correct, boards, lowest P, highest P]
    for p, correct in sorted(points):
        blocks.append([float(correct), 1, p, p])
        while len(blocks) > 1 and blocks[-2][0] / blocks[-2][1] > blocks[-1][0] / blocks[-1][1]:
            right, n, _, high = blocks.pop()
            blocks[-1][0] += right
            blocks[-1][1] += n
            blocks[-1][3] = high
    return [(low, high, right / n, n) for right, n, low, high in blocks]


Points = tuple[tuple[float, float], ...]
KNOTS = 21  # points kept: every 0.05 of raw confidence


def curve(points: Points) -> Callable[[float], float]:
    if not points:
        return lambda c: c
    xs = np.array([x for x, _ in points])
    ys = np.array([y for _, y in points])
    return lambda c: float(np.interp(c, xs, ys))


def fit(pairs: Sequence[tuple[float, bool]], knots: int = KNOTS) -> Points:
    """Accuracy as a never-decreasing function of raw confidence (pooled adjacent violators), read off
    at evenly spaced confidences so the curve stays short enough to freeze into a bot version."""
    blocks = calibration_curve(pairs)
    mids = [(low + high) / 2 for low, high, _, _ in blocks]
    accuracy = [a for _, _, a, _ in blocks]
    grid = np.linspace(0, 1, knots)
    values = np.interp(grid, mids, accuracy)
    return tuple((round(float(x), 4), round(float(y), 4)) for x, y in zip(grid, values))


def error(pairs: Sequence[tuple[float, bool]], correct: Callable[[float], float], bins: int = 10) -> float:
    """Expected calibration error: across bands of stated confidence, how far stated sits from actual,
    weighted by how many boards fall in each band."""
    stated = np.array([correct(c) for c, _ in pairs])
    right = np.array([float(r) for _, r in pairs])
    band = np.minimum((stated * bins).astype(int), bins - 1)
    total = 0.0
    for b in range(bins):
        inside = band == b
        if inside.any():
            total += inside.sum() * abs(stated[inside].mean() - right[inside].mean())
    return float(total / len(pairs))


def brier(pairs: Sequence[tuple[float, bool]], correct: Callable[[float], float]) -> float:
    """Mean squared gap between stated confidence and what happened: lower is better."""
    return float(np.mean([(correct(c) - float(r)) ** 2 for c, r in pairs]))
