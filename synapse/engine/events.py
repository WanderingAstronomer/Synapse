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
from enum import StrEnum

from synapse.database.models import InteractionType

__all__ = ["SynapseEvent", "EventType"]


# ---------------------------------------------------------------------------
# Event Lake event type constants (match 03B_DATA_LAKE.md §3B.4)
# ---------------------------------------------------------------------------
class EventType(StrEnum):
    """Canonical event type identifiers for the Event Lake.

    All event writes and counter lookups should reference these constants
    rather than bare strings to ensure rename-safety.
    """

    MESSAGE_CREATE = "message_create"
    REACTION_ADD = "reaction_add"
    REACTION_REMOVE = "reaction_remove"
    THREAD_CREATE = "thread_create"
    VOICE_JOIN = "voice_join"
    VOICE_LEAVE = "voice_leave"
    VOICE_MOVE = "voice_move"
    MEMBER_JOIN = "member_join"
    MEMBER_LEAVE = "member_leave"
    POLL_VOTE = "poll_vote"


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
    # The 'Context' bucket: holds state needed for scaling (e.g. daily message counts, user level).
    # Populated by the service layer before pipeline entry.
    context: dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
