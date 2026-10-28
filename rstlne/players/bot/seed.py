"""Seeds for the bot's sampling, so the same game seed and the same moves replay the same game."""

from __future__ import annotations

import hashlib

from rstlne.engine.state import PublicView


def view_seed(view: PublicView) -> int:
    """A 64-bit seed from everything in the view. blake2b, since Python's hash() changes per process."""
    return int.from_bytes(hashlib.blake2b(repr(view).encode(), digest_size=8).digest(), "big")
