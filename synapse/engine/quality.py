"""
synapse.engine.quality — Message quality modifiers
====================================================

Per D05 §5.6: multiplicative quality modifier applied only to XP for
MESSAGE events.  Thresholds are read from ConfigCache settings when
available, falling back to sensible defaults.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from synapse.database.models import InteractionType
from synapse.engine.events import SynapseEvent

if TYPE_CHECKING:
    from synapse.engine.cache import ConfigCache

# ---------------------------------------------------------------------------
# Default quality thresholds (single source of truth)
# ---------------------------------------------------------------------------
_LONG_MSG_CHARS = 500
_LONG_MSG_BONUS = 1.5
_MEDIUM_MSG_CHARS = 200
_MEDIUM_MSG_BONUS = 1.2
_CODE_BLOCK_BONUS = 1.4
_LINK_BONUS = 1.25
_ATTACHMENT_BONUS = 1.1
_EMOJI_SPAM_THRESHOLD = 5
_EMOJI_SPAM_PENALTY = 0.5


def calculate_quality_modifier(
    event: SynapseEvent,
    cache: ConfigCache | None = None,
) -> float:
    """Multiplicative quality modifier for MESSAGE events.

    Returns 1.0 for non-MESSAGE events.  Quality modifiers apply ONLY to XP.
    When *cache* is provided, thresholds are read from the settings table.
    """
    if event.event_type != InteractionType.MESSAGE:
        return 1.0

    m = event.metadata
    modifier = 1.0
    length = m.get("length", 0)

    # Read thresholds from settings (fall back to module-level defaults)
    long_threshold = cache.get_int("quality_long_message_chars", _LONG_MSG_CHARS) if cache else _LONG_MSG_CHARS
    long_bonus = cache.get_float("quality_long_message_bonus", _LONG_MSG_BONUS) if cache else _LONG_MSG_BONUS
    medium_threshold = cache.get_int("quality_medium_message_chars", _MEDIUM_MSG_CHARS) if cache else _MEDIUM_MSG_CHARS
    medium_bonus = cache.get_float("quality_medium_message_bonus", _MEDIUM_MSG_BONUS) if cache else _MEDIUM_MSG_BONUS
    code_bonus = cache.get_float("quality_code_block_bonus", _CODE_BLOCK_BONUS) if cache else _CODE_BLOCK_BONUS
    link_bonus = cache.get_float("quality_link_bonus", _LINK_BONUS) if cache else _LINK_BONUS
    attachment_bonus = cache.get_float("quality_attachment_bonus", _ATTACHMENT_BONUS) if cache else _ATTACHMENT_BONUS
    emoji_threshold = cache.get_int("quality_emoji_spam_threshold", _EMOJI_SPAM_THRESHOLD) if cache else _EMOJI_SPAM_THRESHOLD
    emoji_penalty = cache.get_float("quality_emoji_spam_penalty", _EMOJI_SPAM_PENALTY) if cache else _EMOJI_SPAM_PENALTY

    # Length bonus (mutually exclusive tiers)
    if length > long_threshold:
        modifier *= long_bonus
    elif length > medium_threshold:
        modifier *= medium_bonus

    # Code block bonus
    if m.get("has_code_block"):
        modifier *= code_bonus

    # Link enrichment
    if m.get("has_link"):
        modifier *= link_bonus

    # Attachment bonus
    if m.get("has_attachment"):
        modifier *= attachment_bonus

    # Emoji spam penalty
    if m.get("emoji_count", 0) > emoji_threshold:
        modifier *= emoji_penalty

    # Floor to prevent zero-XP
    return max(modifier, 0.1)
