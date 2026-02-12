"""
synapse.constants — Shared Constants & Helpers
================================================

Single source of truth for presentation constants and the leveling formula.
Import from here instead of duplicating in cogs, services, and dashboard.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from synapse.engine.cache import ConfigCache

# ---------------------------------------------------------------------------
# Rarity presentation (used by bot embeds, dashboard, announcement service)
# ---------------------------------------------------------------------------
RARITY_COLORS_HEX: dict[str, str] = {
    "common": "#9e9e9e",
    "uncommon": "#4caf50",
    "rare": "#2196f3",
    "epic": "#9c27b0",
    "legendary": "#ff9800",
}

RARITY_LABELS: dict[str, str] = {
    "common": "Common",
    "uncommon": "Uncommon",
    "rare": "Rare",
    "epic": "Epic",
    "legendary": "Legendary",
}

RARITY_EMOJI: dict[str, str] = {
    "common": "\u26aa",        # ⚪
    "uncommon": "\U0001f7e2",  # 🟢
    "rare": "\U0001f535",      # 🔵
    "epic": "\U0001f7e3",      # 🟣
    "legendary": "\U0001f7e1", # 🟡
}

RANK_BADGES: list[str] = ["\U0001f947", "\U0001f948", "\U0001f949"]  # 🥇🥈🥉


# ---------------------------------------------------------------------------
# Leveling formula — THE single canonical implementation
# ---------------------------------------------------------------------------
def xp_for_level(level: int, cache: ConfigCache | None = None) -> int:
    """XP required to reach *level*.

    Uses the exponential formula::

        required = level_base * (level_factor ** level)

    Parameters are read from the ``settings`` table via *cache*.
    Falls back to defaults (100, 1.25) if cache is unavailable.
    """
    if cache is not None:
        base = cache.get_int("level_base", 100)
        factor = cache.get_float("level_factor", 1.25)
    else:
        base = 100
        factor = 1.25
    return int(base * (factor ** level))
