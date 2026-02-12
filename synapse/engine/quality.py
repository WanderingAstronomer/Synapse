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

    # Read thresholds from settings (fall back to defaults)
    if cache is not None:
        long_threshold = cache.get_int("quality_long_message_chars", 500)
        long_bonus = cache.get_float("quality_long_message_bonus", 1.5)
        medium_threshold = cache.get_int("quality_medium_message_chars", 200)
        medium_bonus = cache.get_float("quality_medium_message_bonus", 1.2)
        code_bonus = cache.get_float("quality_code_block_bonus", 1.4)
        link_bonus = cache.get_float("quality_link_bonus", 1.25)
        attachment_bonus = cache.get_float("quality_attachment_bonus", 1.1)
        emoji_threshold = cache.get_int("quality_emoji_spam_threshold", 5)
        emoji_penalty = cache.get_float("quality_emoji_spam_penalty", 0.5)
    else:
        long_threshold, long_bonus = 500, 1.5
        medium_threshold, medium_bonus = 200, 1.2
        code_bonus = 1.4
        link_bonus = 1.25
        attachment_bonus = 1.1
        emoji_threshold, emoji_penalty = 5, 0.5

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


def llm_quality_modifier(event: SynapseEvent) -> float:
    """Placeholder for LLM quality assessment (§5.9 — DEFERRED per D05-02).

    Currently always returns 1.0 (no effect).
    """
    return 1.0
