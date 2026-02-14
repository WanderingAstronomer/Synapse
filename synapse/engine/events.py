"""
synapse.engine.events — SynapseEvent and InteractionType
=========================================================

The universal event envelope (originally per 05_REWARD_ENGINE.md §5.2,
now documented in 05_RULES_ENGINE.md §5.2).
Every Discord interaction is normalized into a SynapseEvent before
the reward pipeline processes it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from synapse.database.models import InteractionType

__all__ = ["SynapseEvent", "BASE_XP", "BASE_STARS"]

# ---------------------------------------------------------------------------
# Base XP and Stars per interaction type (05 §5.2)
# ---------------------------------------------------------------------------
BASE_XP: dict[InteractionType, int] = {
    InteractionType.MESSAGE: 15,
    InteractionType.REACTION_GIVEN: 2,
    InteractionType.REACTION_RECEIVED: 3,
    InteractionType.THREAD_CREATE: 20,
    InteractionType.VOICE_TICK: 0,
    InteractionType.MANUAL_AWARD: 0,  # varies
    InteractionType.LEVEL_UP: 0,
    InteractionType.ACHIEVEMENT_EARNED: 0,
    InteractionType.VOICE_JOIN: 0,
    InteractionType.VOICE_LEAVE: 0,
}

BASE_STARS: dict[InteractionType, int] = {
    InteractionType.MESSAGE: 1,
    InteractionType.REACTION_GIVEN: 1,
    InteractionType.REACTION_RECEIVED: 1,
    InteractionType.THREAD_CREATE: 2,
    InteractionType.VOICE_TICK: 1,
    InteractionType.MANUAL_AWARD: 0,
    InteractionType.LEVEL_UP: 0,
    InteractionType.ACHIEVEMENT_EARNED: 0,
    InteractionType.VOICE_JOIN: 0,
    InteractionType.VOICE_LEAVE: 0,
}


# ---------------------------------------------------------------------------
# SynapseEvent — the universal event envelope
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class SynapseEvent:
    """Normalized event from any source (Discord, GitHub, admin, etc.).

    This is the sole input to the reward pipeline. All source-specific
    details are captured in ``metadata``.
    """

    user_id: int
    event_type: InteractionType
    channel_id: int
    guild_id: int
    source_event_id: str | None = None
    metadata: dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
