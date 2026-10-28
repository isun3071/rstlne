"""Bot versions. A version fixes the bot's code, data files, and knobs; tournaments never mix them."""

from __future__ import annotations

VERSIONS = (1,)  # v1 is in development until self-play freezes it


def current(config: dict) -> int:
    """The version `[bot] version` in config.toml picks."""
    version = config.get("bot", {}).get("version")
    if version is None:
        raise ValueError("config.toml needs [bot] version")
    if version not in VERSIONS:
        raise ValueError(f"bot version {version} doesn't exist. Known versions: {', '.join(map(str, VERSIONS))}")
    return version
