"""
synapse.engine.envelope — InteractionEnvelope
=============================================

The typed schema contract for every event entering the Event Lake.

Every Discord interaction that the bot captures must be representable as an
``InteractionEnvelope`` before being written to ``event_lake``.  The
envelope formalizes the minimum required fields and provides a canonical
``source_category`` classification for audit and Rules Engine routing.

Relationship to ``SynapseEvent``
---------------------------------
- ``InteractionEnvelope`` is the *capture* layer: everything Discord sends us.
- ``SynapseEvent`` is the *reward pipeline* layer: what the engine processes.
- Both are pure value objects with no I/O.

Source categories
-----------------
``GATEWAY``   — Event received via the Discord real-time Gateway (WebSocket
                DISPATCH).  The vast majority of events fall here.
``REST``      — Event obtained via a Discord REST API call, typically an
                on-demand fetch or scheduled poll for data not pushed over
                the Gateway.
``SYNTHETIC`` — Event generated internally by Synapse (e.g. ``MANUAL_AWARD``,
                ``LEVEL_UP``, ``ACHIEVEMENT_EARNED``).  No corresponding
                external Discord event exists.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from synapse.database.models import SourceCategory
from synapse.engine.events import EventType

__all__ = ["InteractionEnvelope", "EVENT_SOURCE_CATEGORY"]

# ---------------------------------------------------------------------------
# Canonical source-category map  (EventType → SourceCategory)
# ---------------------------------------------------------------------------
# All gateway-pushed events that have a dedicated write_* method today.
# SYNTHETIC events (MANUAL_AWARD, LEVEL_UP, ACHIEVEMENT_EARNED) are written
# directly by the reward service and do not pass through the Event Lake writer.
EVENT_SOURCE_CATEGORY: dict[str, SourceCategory] = {
    EventType.MESSAGE_CREATE: SourceCategory.GATEWAY,
    EventType.REACTION_ADD: SourceCategory.GATEWAY,
    EventType.REACTION_REMOVE: SourceCategory.GATEWAY,
    EventType.THREAD_CREATE: SourceCategory.GATEWAY,
    EventType.VOICE_JOIN: SourceCategory.GATEWAY,
    EventType.VOICE_LEAVE: SourceCategory.GATEWAY,
    EventType.VOICE_MOVE: SourceCategory.GATEWAY,
    EventType.MEMBER_JOIN: SourceCategory.GATEWAY,
    EventType.MEMBER_LEAVE: SourceCategory.GATEWAY,
    EventType.POLL_VOTE: SourceCategory.GATEWAY,
}


# ---------------------------------------------------------------------------
# InteractionEnvelope — the capture-layer event contract
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class InteractionEnvelope:
    """Minimum required fields for any event written to the Event Lake.

    Parameters
    ----------
    guild_id : int
        The Discord guild (server) in which the event occurred.
    user_id : int
        The Discord user who triggered the event.
    event_type : str
        String identifier for the event kind.  Should be one of
        :class:`~synapse.engine.events.EventType` values.
    source_category : SourceCategory
        Origin of the event: ``GATEWAY``, ``REST``, or ``SYNTHETIC``.
    channel_id : int | None
        The channel in which the event occurred, if applicable.
    target_id : int | None
        Secondary actor or object (e.g. message author on a reaction).
    payload : dict
        Event-specific JSONB metadata.  Content is event-type-dependent
        and must never include raw message content (Decision D03B-07).
    source_id : str | None
        Idempotency key.  If provided, duplicate inserts with the same
        ``source_id`` are silently ignored via DB UNIQUE constraint.
    timestamp : datetime | None
        UTC timestamp of the event.  Defaults to ``datetime.now(UTC)`` at
        write time if ``None``.
    """

    guild_id: int
    user_id: int
    event_type: str
    source_category: SourceCategory
    channel_id: int | None = None
    target_id: int | None = None
    payload: dict = field(default_factory=dict)
    source_id: str | None = None
    timestamp: datetime | None = None
