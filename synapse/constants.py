"""
synapse.constants — Shared Constants & Helpers
================================================

Single source of truth for presentation constants and the leveling formula.
Import from here instead of duplicating in cogs, services, and dashboard.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from synapse.engine.cache import ConfigCache

# ---------------------------------------------------------------------------
# Rarity presentation (used by bot embeds, announcement service)
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# Layout Service Allow Lists
# ---------------------------------------------------------------------------
ALLOWED_CARD_FIELDS: set[str] = {
    "card_type", "position", "grid_span", "title",
    "subtitle", "config_json", "visible",
}


# ---------------------------------------------------------------------------
# Text processing helpers
# ---------------------------------------------------------------------------
_EMOJI_REGEX = re.compile(r"<a?:[a-zA-Z0-9_]+:[0-9]+>|(?<!\d):[a-zA-Z0-9_]+:(?!\d)")

def count_emojis(text: str) -> int:
    """Count custom emojis (<:name:id>) and shortcodes (:smile:) in text.

    This is a heuristic for spam detection (quality.py) and lake metadata.
    It does NOT count raw unicode emojis (requires heavy dependencies).
    """
    return len(_EMOJI_REGEX.findall(text))
