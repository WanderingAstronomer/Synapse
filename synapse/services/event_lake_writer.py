"""
synapse.services.event_lake_writer — Event Lake Write Service
==============================================================

Central write path for the Event Lake (03B_DATA_LAKE.md).

Responsibilities:
1. Insert events into ``event_lake`` with idempotency (source_id UNIQUE).
2. Transactionally update ``event_counters`` with each insert.
3. Provide helpers for extracting message quality metadata (privacy-safe).
4. Manage voice session state for join/leave/move derivation.

**Hot-path safety:** All public methods are synchronous and designed to
be called via ``await run_db(writer.write_event, ...)``.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Engine, select, text
from sqlalchemy.exc import IntegrityError

from synapse.database.engine import get_session
from synapse.database.models import EventLake, Setting

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Event type constants (match 03B_DATA_LAKE.md §3B.4)
# ---------------------------------------------------------------------------
class EventType:
    """Event type string constants for the Event Lake."""
    MESSAGE_CREATE = "message_create"
    REACTION_ADD = "reaction_add"
    REACTION_REMOVE = "reaction_remove"
    THREAD_CREATE = "thread_create"
    VOICE_JOIN = "voice_join"
    VOICE_LEAVE = "voice_leave"
    VOICE_MOVE = "voice_move"
    MEMBER_JOIN = "member_join"
    MEMBER_LEAVE = "member_leave"


# ---------------------------------------------------------------------------
# Message quality metadata extraction (privacy-safe)
# ---------------------------------------------------------------------------
def extract_message_metadata(content: str, attachments: int, is_reply: bool,
                             reply_to_user_id: int | None = None) -> dict[str, Any]:
    """Extract quality metadata from message content, then discard text.

    Per Decision D03B-07: message content is NEVER persisted.
    Only numerical/boolean metadata is returned.
    """
    return {
        "length": len(content),
        "has_code_block": "```" in content,
        "has_link": "http://" in content or "https://" in content,
        "has_attachment": attachments > 0,
        "emoji_count": content.count(":") // 2,  # rough paired-colon estimate
        "is_reply": is_reply,
        "reply_to_user_id": reply_to_user_id,
    }


# ---------------------------------------------------------------------------
# Voice Session Tracker (in-memory)
# ---------------------------------------------------------------------------
class VoiceSessionTracker:
    """In-memory tracker for voice join timestamps and session IDs.

    Used to derive voice_leave duration and detect AFK sessions.
    """

    def __init__(self) -> None:
        # {user_id: {guild_id: (join_time, channel_id, session_id, self_mute, self_deaf)}}
        self._sessions: dict[int, dict[int, tuple[float, int, str, bool, bool]]] = {}

    def join(
        self,
        user_id: int,
        guild_id: int,
        channel_id: int,
        session_id: str,
        self_mute: bool,
        self_deaf: bool,
    ) -> None:
        """Record a voice join."""
        if user_id not in self._sessions:
            self._sessions[user_id] = {}
        self._sessions[user_id][guild_id] = (
            time.time(), channel_id, session_id, self_mute, self_deaf,
        )

    def leave(
        self, user_id: int, guild_id: int,
    ) -> tuple[float, int, str, bool, bool] | None:
        """Pop a voice session and return (join_time, channel_id, session_id, mute, deaf).

        Returns None if no active session.
        """
        if user_id in self._sessions:
            return self._sessions[user_id].pop(guild_id, None)
        return None

    def get(self, user_id: int, guild_id: int) -> tuple[float, int, str, bool, bool] | None:
        """Get current session info without removing it."""
        return self._sessions.get(user_id, {}).get(guild_id)

    def update_state(
        self, user_id: int, guild_id: int, self_mute: bool, self_deaf: bool,
    ) -> None:
        """Update mute/deaf state for idle detection on leave."""
        if user_id in self._sessions and guild_id in self._sessions[user_id]:
            join_time, channel_id, session_id, _, _ = self._sessions[user_id][guild_id]
            self._sessions[user_id][guild_id] = (
                join_time, channel_id, session_id, self_mute, self_deaf,
            )


# ---------------------------------------------------------------------------
# Counter update helper
# ---------------------------------------------------------------------------
def _update_counters(
    session,
    user_id: int,
    event_type: str,
    zone_id: int = 0,
    timestamp: datetime | None = None,
) -> None:
    """Increment event counters transactionally.

    Updates three periods: 'lifetime', 'season', and 'day:YYYY-MM-DD'.
    """
    ts = timestamp or datetime.now(UTC)
    day_key = f"day:{ts.strftime('%Y-%m-%d')}"

    for period in ("lifetime", "season", day_key):
        # Use raw SQL for UPSERT (ON CONFLICT … DO UPDATE) for atomicity
        session.execute(
            text("""
                INSERT INTO event_counters (user_id, event_type, zone_id, period, count)
                VALUES (:user_id, :event_type, :zone_id, :period, 1)
                ON CONFLICT (user_id, event_type, zone_id, period)
                DO UPDATE SET count = event_counters.count + 1
            """),
            {
                "user_id": user_id,
                "event_type": event_type,
                "zone_id": zone_id,
                "period": period,
            },
        )


# ---------------------------------------------------------------------------
# EventLakeWriter — main write service
# ---------------------------------------------------------------------------
class EventLakeWriter:
    """Service for writing events to the Event Lake.

    All methods are synchronous — call via ``await run_db(writer.method, ...)``.
    """

    def __init__(self, engine: Engine, afk_channel_ids: set[int] | None = None) -> None:
        self.engine = engine
        self.voice_tracker = VoiceSessionTracker()
        # Discord's built-in AFK channel + admin-designated non-tracked channels
        self.afk_channel_ids: set[int] = afk_channel_ids or set()
        # Data-source toggles: set of *disabled* event types, refreshed lazily
        self._disabled_sources: set[str] = set()
        self._disabled_sources_ts: float = 0.0  # last refresh epoch
        self._disabled_sources_ttl: float = 60.0  # seconds between refreshes

    def set_afk_channels(self, channel_ids: set[int]) -> None:
        """Update the set of AFK/non-tracked voice channel IDs."""
        self.afk_channel_ids = channel_ids

    def _refresh_disabled_sources(self) -> None:
        """Reload the set of disabled event types from the settings table.

        Cached for ``_disabled_sources_ttl`` seconds to avoid a DB hit
        on every single event write.
        """
        now = time.time()
        if now - self._disabled_sources_ts < self._disabled_sources_ttl:
            return  # cache still fresh

        try:
            with get_session(self.engine) as session:
                rows = session.scalars(
                    select(Setting).where(
                        Setting.key.like("event_lake.source.%.enabled")
                    )
                ).all()

            disabled: set[str] = set()
            for row in rows:
                try:
                    val = json.loads(row.value_json)
                except (json.JSONDecodeError, TypeError):
                    val = row.value_json
                # Extract event_type from key: event_lake.source.<type>.enabled
                parts = row.key.split(".")
                if len(parts) == 4:
                    event_type = parts[2]
                    if val is False or (isinstance(val, str) and val.lower() in ("false", "0", "no")):
                        disabled.add(event_type)

            self._disabled_sources = disabled
        except Exception:
            logger.debug("Failed to refresh disabled sources; using cached set")
        finally:
            self._disabled_sources_ts = now

    def is_source_enabled(self, event_type: str) -> bool:
        """Check whether a given event type is enabled for capture."""
        self._refresh_disabled_sources()
        return event_type not in self._disabled_sources

    # -------------------------------------------------------------------
    # Core write path
    # -------------------------------------------------------------------
    def write_event(
        self,
        *,
        guild_id: int,
        user_id: int,
        event_type: str,
        channel_id: int | None = None,
        target_id: int | None = None,
        payload: dict[str, Any] | None = None,
        source_id: str | None = None,
        timestamp: datetime | None = None,
        zone_id: int = 0,
    ) -> bool:
        """Write a single event to the Event Lake with counter update.

        Returns True if the event was inserted, False if it was a duplicate
        (idempotent insert via source_id UNIQUE constraint) or the source
        type is disabled via admin toggle.
        """
        # Check data-source toggle (§3B.8)
        if not self.is_source_enabled(event_type):
            logger.debug("Event source disabled, skipping: type=%s user=%s", event_type, user_id)
            return False

        ts = timestamp or datetime.now(UTC)
        event = EventLake(
            guild_id=guild_id,
            user_id=user_id,
            event_type=event_type,
            channel_id=channel_id,
            target_id=target_id,
            payload=payload or {},
            source_id=source_id,
            timestamp=ts,
        )

        with get_session(self.engine) as session:
            try:
                session.add(event)
                session.flush()  # Trigger UNIQUE constraint check before counters
                _update_counters(session, user_id, event_type, zone_id, ts)
                return True
            except IntegrityError:
                session.rollback()
                logger.debug(
                    "Duplicate event skipped: source_id=%s type=%s user=%s",
                    source_id, event_type, user_id,
                )
                return False

    # -------------------------------------------------------------------
    # High-level event writers (one per event type)
    # -------------------------------------------------------------------

    def write_message_create(
        self,
        *,
        guild_id: int,
        user_id: int,
        channel_id: int,
        message_id: int,
        content: str,
        attachment_count: int = 0,
        is_reply: bool = False,
        reply_to_user_id: int | None = None,
        zone_id: int = 0,
    ) -> bool:
        """Write a message_create event with privacy-safe metadata extraction."""
        payload = extract_message_metadata(
            content, attachment_count, is_reply, reply_to_user_id,
        )
        return self.write_event(
            guild_id=guild_id,
            user_id=user_id,
            event_type=EventType.MESSAGE_CREATE,
            channel_id=channel_id,
            target_id=reply_to_user_id,
            payload=payload,
            source_id=str(message_id),
            zone_id=zone_id,
        )

    def write_reaction_add(
        self,
        *,
        guild_id: int,
        user_id: int,
        channel_id: int,
        message_id: int,
        emoji_name: str,
        message_author_id: int | None = None,
    ) -> bool:
        """Write a reaction_add event."""
        source_id = f"{user_id}-{message_id}-{emoji_name}"
        return self.write_event(
            guild_id=guild_id,
            user_id=user_id,
            event_type=EventType.REACTION_ADD,
            channel_id=channel_id,
            target_id=message_author_id,
            payload={
                "emoji_name": emoji_name,
                "message_id": str(message_id),
            },
            source_id=source_id,
        )

    def write_reaction_remove(
        self,
        *,
        guild_id: int,
        user_id: int,
        channel_id: int,
        message_id: int,
        emoji_name: str,
        message_author_id: int | None = None,
    ) -> bool:
        """Write a reaction_remove event (no idempotency — removals have no unique ID)."""
        return self.write_event(
            guild_id=guild_id,
            user_id=user_id,
            event_type=EventType.REACTION_REMOVE,
            channel_id=channel_id,
            target_id=message_author_id,
            payload={
                "emoji_name": emoji_name,
                "message_id": str(message_id),
            },
            source_id=None,  # Removal events don't have unique IDs
        )

    def write_thread_create(
        self,
        *,
        guild_id: int,
        user_id: int,
        thread_id: int,
        parent_channel_id: int | None = None,
        thread_name: str = "",
    ) -> bool:
        """Write a thread_create event."""
        return self.write_event(
            guild_id=guild_id,
            user_id=user_id,
            event_type=EventType.THREAD_CREATE,
            channel_id=parent_channel_id,
            target_id=parent_channel_id,
            payload={
                "name": thread_name,
                "parent_channel_id": str(parent_channel_id) if parent_channel_id else None,
            },
            source_id=str(thread_id),
        )

    def write_voice_join(
        self,
        *,
        guild_id: int,
        user_id: int,
        channel_id: int,
        session_id: str,
        self_mute: bool = False,
        self_deaf: bool = False,
    ) -> bool:
        """Write a voice_join event and start tracking the session."""
        is_afk = channel_id in self.afk_channel_ids

        # Track session in memory for duration calculation on leave
        self.voice_tracker.join(
            user_id, guild_id, channel_id, session_id, self_mute, self_deaf,
        )

        return self.write_event(
            guild_id=guild_id,
            user_id=user_id,
            event_type=EventType.VOICE_JOIN,
            channel_id=channel_id,
            payload={
                "channel_id": str(channel_id),
                "self_mute": self_mute,
                "self_deaf": self_deaf,
                "is_afk": is_afk,
            },
            source_id=f"{user_id}-{session_id}-join",
        )

    def write_voice_leave(
        self,
        *,
        guild_id: int,
        user_id: int,
        channel_id: int,
        session_id: str,
        self_mute: bool = False,
        self_deaf: bool = False,
    ) -> bool:
        """Write a voice_leave event with computed duration."""
        session_info = self.voice_tracker.leave(user_id, guild_id)

        if session_info:
            join_time, join_channel, _, join_mute, join_deaf = session_info
            duration_seconds = int(time.time() - join_time)
            # AFK detection: was idle (mute+deaf) for entire session?
            was_idle_entire = (join_mute and join_deaf and self_mute and self_deaf)
        else:
            duration_seconds = 0
            was_idle_entire = self_mute and self_deaf

        is_afk = channel_id in self.afk_channel_ids or was_idle_entire

        return self.write_event(
            guild_id=guild_id,
            user_id=user_id,
            event_type=EventType.VOICE_LEAVE,
            channel_id=channel_id,
            payload={
                "channel_id": str(channel_id),
                "duration_seconds": duration_seconds,
                "self_mute": self_mute,
                "self_deaf": self_deaf,
                "is_afk": is_afk,
            },
            source_id=f"{user_id}-{session_id}-leave",
        )

    def write_voice_move(
        self,
        *,
        guild_id: int,
        user_id: int,
        from_channel_id: int,
        to_channel_id: int,
        session_id: str,
        self_mute: bool = False,
        self_deaf: bool = False,
    ) -> bool:
        """Write a voice_move event."""
        is_afk = to_channel_id in self.afk_channel_ids

        # Update tracker with new channel
        session_info = self.voice_tracker.get(user_id, guild_id)
        if session_info:
            join_time = session_info[0]
            self.voice_tracker._sessions[user_id][guild_id] = (
                join_time, to_channel_id, session_id, self_mute, self_deaf,
            )

        ts = datetime.now(UTC)
        return self.write_event(
            guild_id=guild_id,
            user_id=user_id,
            event_type=EventType.VOICE_MOVE,
            channel_id=to_channel_id,
            payload={
                "from_channel_id": str(from_channel_id),
                "to_channel_id": str(to_channel_id),
                "is_afk": is_afk,
            },
            source_id=f"{user_id}-{session_id}-move-{int(ts.timestamp())}",
            timestamp=ts,
        )

    def write_member_join(
        self,
        *,
        guild_id: int,
        user_id: int,
        joined_at: datetime | None = None,
    ) -> bool:
        """Write a member_join event."""
        ts = datetime.now(UTC)
        return self.write_event(
            guild_id=guild_id,
            user_id=user_id,
            event_type=EventType.MEMBER_JOIN,
            payload={
                "joined_at": joined_at.isoformat() if joined_at else ts.isoformat(),
            },
            source_id=f"{user_id}-join-{int(ts.timestamp())}",
            timestamp=ts,
        )

    def write_member_leave(
        self,
        *,
        guild_id: int,
        user_id: int,
    ) -> bool:
        """Write a member_leave event."""
        ts = datetime.now(UTC)
        return self.write_event(
            guild_id=guild_id,
            user_id=user_id,
            event_type=EventType.MEMBER_LEAVE,
            payload={},
            source_id=f"{user_id}-leave-{int(ts.timestamp())}",
            timestamp=ts,
        )
