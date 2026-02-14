"""
tests/test_event_lake.py — Event Lake Unit & Integration Tests
===============================================================

Tests for:
- EventLakeWriter: event creation, idempotency, counter updates
- Message metadata extraction (privacy: no raw text stored)
- Voice session tracking (join/leave/move, AFK detection)
- All event types: message, reaction, thread, voice, member
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from synapse.services.event_lake_writer import (
    EventLakeWriter,
    EventType,
    VoiceSessionTracker,
    extract_message_metadata,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def voice_tracker():
    """Fresh VoiceSessionTracker."""
    return VoiceSessionTracker()


# ---------------------------------------------------------------------------
# Message Metadata Extraction Tests (Privacy)
# ---------------------------------------------------------------------------
class TestMessageMetadata:
    """Verify privacy-safe metadata extraction from message content."""

    def test_basic_text(self):
        meta = extract_message_metadata("Hello world!", 0, False)
        assert meta["length"] == 12
        assert meta["has_code_block"] is False
        assert meta["has_link"] is False
        assert meta["has_attachment"] is False
        assert meta["is_reply"] is False
        assert meta["reply_to_user_id"] is None

    def test_code_block_detected(self):
        content = "Look at this:\n```python\nprint('hi')\n```"
        meta = extract_message_metadata(content, 0, False)
        assert meta["has_code_block"] is True

    def test_link_detected_https(self):
        meta = extract_message_metadata("Check https://example.com", 0, False)
        assert meta["has_link"] is True

    def test_link_detected_http(self):
        meta = extract_message_metadata("Check http://example.com", 0, False)
        assert meta["has_link"] is True

    def test_no_link_in_plain_text(self):
        meta = extract_message_metadata("No links here", 0, False)
        assert meta["has_link"] is False

    def test_attachment_flag(self):
        meta = extract_message_metadata("Image:", 2, False)
        assert meta["has_attachment"] is True

    def test_reply_metadata(self):
        meta = extract_message_metadata("Yes!", 0, True, reply_to_user_id=999)
        assert meta["is_reply"] is True
        assert meta["reply_to_user_id"] == 999

    def test_emoji_count(self):
        meta = extract_message_metadata("Hello :smile: :wave:", 0, False)
        assert meta["emoji_count"] == 2

    def test_no_raw_text_in_output(self):
        """CRITICAL: verify that raw message content is NEVER in the output."""
        secret = "This is a private message that should never be stored"
        meta = extract_message_metadata(secret, 0, False)
        # The metadata dict should not contain the raw text
        for value in meta.values():
            if isinstance(value, str):
                assert secret not in value
            elif isinstance(value, dict):
                assert secret not in str(value)


# ---------------------------------------------------------------------------
# VoiceSessionTracker Tests
# ---------------------------------------------------------------------------
class TestVoiceSessionTracker:
    """Test in-memory voice session state management."""

    def test_join_and_leave(self, voice_tracker: VoiceSessionTracker):
        voice_tracker.join(1001, 100, 555, "sess-1", False, False)
        info = voice_tracker.leave(1001, 100)
        assert info is not None
        join_time, channel_id, session_id, mute, deaf = info
        assert channel_id == 555
        assert session_id == "sess-1"
        assert mute is False
        assert deaf is False

    def test_leave_without_join_returns_none(self, voice_tracker: VoiceSessionTracker):
        result = voice_tracker.leave(9999, 100)
        assert result is None

    def test_get_session(self, voice_tracker: VoiceSessionTracker):
        voice_tracker.join(1001, 100, 555, "sess-1", True, True)
        info = voice_tracker.get(1001, 100)
        assert info is not None
        assert info[1] == 555  # channel_id
        assert info[3] is True  # self_mute
        assert info[4] is True  # self_deaf

    def test_get_nonexistent(self, voice_tracker: VoiceSessionTracker):
        assert voice_tracker.get(9999, 100) is None

    def test_update_state(self, voice_tracker: VoiceSessionTracker):
        voice_tracker.join(1001, 100, 555, "sess-1", False, False)
        voice_tracker.update_state(1001, 100, True, True)
        info = voice_tracker.get(1001, 100)
        assert info is not None
        assert info[3] is True   # self_mute updated
        assert info[4] is True   # self_deaf updated

    def test_multiple_guilds(self, voice_tracker: VoiceSessionTracker):
        voice_tracker.join(1001, 100, 555, "sess-g1", False, False)
        voice_tracker.join(1001, 200, 666, "sess-g2", True, False)
        g1 = voice_tracker.get(1001, 100)
        g2 = voice_tracker.get(1001, 200)
        assert g1 is not None and g1[1] == 555
        assert g2 is not None and g2[1] == 666


# ---------------------------------------------------------------------------
# EventType Constants Tests
# ---------------------------------------------------------------------------
class TestEventTypeConstants:
    """Verify event type string constants match design doc."""

    def test_all_event_types_defined(self):
        expected = {
            "message_create", "reaction_add", "reaction_remove",
            "thread_create", "voice_join", "voice_leave", "voice_move",
            "member_join", "member_leave",
        }
        actual = {
            EventType.MESSAGE_CREATE, EventType.REACTION_ADD,
            EventType.REACTION_REMOVE, EventType.THREAD_CREATE,
            EventType.VOICE_JOIN, EventType.VOICE_LEAVE,
            EventType.VOICE_MOVE, EventType.MEMBER_JOIN,
            EventType.MEMBER_LEAVE,
        }
        assert actual == expected


# ---------------------------------------------------------------------------
# EventLakeWriter Unit Tests (with mocked DB)
# ---------------------------------------------------------------------------
class TestEventLakeWriter:
    """Test EventLakeWriter logic with mocked database sessions."""

    @pytest.fixture
    def mock_engine(self):
        return MagicMock()

    @pytest.fixture
    def writer(self, mock_engine):
        return EventLakeWriter(mock_engine, afk_channel_ids={777, 888})

    def test_afk_channel_detection(self, writer: EventLakeWriter):
        """AFK channels should be correctly tracked."""
        assert 777 in writer.afk_channel_ids
        assert 888 in writer.afk_channel_ids
        assert 999 not in writer.afk_channel_ids

    def test_set_afk_channels(self, writer: EventLakeWriter):
        writer.set_afk_channels({111, 222})
        assert writer.afk_channel_ids == {111, 222}

    @patch("synapse.services.event_lake_writer.get_session")
    def test_write_event_success(self, mock_get_session, writer: EventLakeWriter):
        """A normal event write should return True."""
        mock_session = MagicMock()
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        result = writer.write_event(
            guild_id=100,
            user_id=1001,
            event_type=EventType.MESSAGE_CREATE,
            channel_id=555,
            source_id="test-123",
        )
        assert result is True
        mock_session.add.assert_called_once()
        mock_session.flush.assert_called_once()

    @patch("synapse.services.event_lake_writer.get_session")
    def test_write_event_duplicate(self, mock_get_session, writer: EventLakeWriter):
        """Duplicate source_id should return False (idempotent)."""
        from sqlalchemy.exc import IntegrityError

        mock_session = MagicMock()
        mock_session.flush.side_effect = IntegrityError("dup", {}, None)
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        result = writer.write_event(
            guild_id=100,
            user_id=1001,
            event_type=EventType.MESSAGE_CREATE,
            source_id="duplicate-123",
        )
        assert result is False
        mock_session.rollback.assert_called_once()

    def test_voice_join_afk_channel(self, writer: EventLakeWriter):
        """Voice join to AFK channel should be tagged is_afk=True in payload."""
        with patch("synapse.services.event_lake_writer.get_session") as mock_gs:
            mock_session = MagicMock()
            mock_gs.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_gs.return_value.__exit__ = MagicMock(return_value=False)

            writer.write_voice_join(
                guild_id=100,
                user_id=1001,
                channel_id=777,  # AFK channel
                session_id="sess-afk",
            )

            # Check the EventLake object that was added
            added = mock_session.add.call_args[0][0]
            assert added.payload["is_afk"] is True

    def test_voice_join_normal_channel(self, writer: EventLakeWriter):
        """Voice join to normal channel should be tagged is_afk=False."""
        with patch("synapse.services.event_lake_writer.get_session") as mock_gs:
            mock_session = MagicMock()
            mock_gs.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_gs.return_value.__exit__ = MagicMock(return_value=False)

            writer.write_voice_join(
                guild_id=100,
                user_id=1001,
                channel_id=555,  # Normal channel
                session_id="sess-normal",
            )

            added = mock_session.add.call_args[0][0]
            assert added.payload["is_afk"] is False

    def test_voice_leave_computes_duration(self, writer: EventLakeWriter):
        """Voice leave should compute duration from tracked join."""
        with patch("synapse.services.event_lake_writer.get_session") as mock_gs:
            mock_session = MagicMock()
            mock_gs.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_gs.return_value.__exit__ = MagicMock(return_value=False)

            # First join
            writer.write_voice_join(
                guild_id=100,
                user_id=1001,
                channel_id=555,
                session_id="sess-dur",
            )

            # Then leave
            writer.write_voice_leave(
                guild_id=100,
                user_id=1001,
                channel_id=555,
                session_id="sess-dur",
            )

            # The leave event should have a duration
            leave_call = mock_session.add.call_args_list[-1]
            leave_event = leave_call[0][0]
            assert "duration_seconds" in leave_event.payload
            assert leave_event.payload["duration_seconds"] >= 0

    def test_voice_leave_idle_entire_session_is_afk(self, writer: EventLakeWriter):
        """If muted+deafed entire session, voice_leave should be tagged is_afk=True."""
        with patch("synapse.services.event_lake_writer.get_session") as mock_gs:
            mock_session = MagicMock()
            mock_gs.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_gs.return_value.__exit__ = MagicMock(return_value=False)

            writer.write_voice_join(
                guild_id=100,
                user_id=1001,
                channel_id=555,
                session_id="sess-idle",
                self_mute=True,
                self_deaf=True,
            )

            writer.write_voice_leave(
                guild_id=100,
                user_id=1001,
                channel_id=555,
                session_id="sess-idle",
                self_mute=True,
                self_deaf=True,
            )

            leave_event = mock_session.add.call_args_list[-1][0][0]
            assert leave_event.payload["is_afk"] is True

    @patch("synapse.services.event_lake_writer.get_session")
    def test_write_message_create_source_id(self, mock_gs, writer: EventLakeWriter):
        """Message source_id should be the message snowflake."""
        mock_session = MagicMock()
        mock_gs.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_gs.return_value.__exit__ = MagicMock(return_value=False)

        writer.write_message_create(
            guild_id=100,
            user_id=1001,
            channel_id=555,
            message_id=123456789,
            content="Hello world",
        )

        added = mock_session.add.call_args[0][0]
        assert added.source_id == "123456789"
        assert added.event_type == EventType.MESSAGE_CREATE
        # Verify content is NOT in the payload
        assert "Hello world" not in str(added.payload)

    @patch("synapse.services.event_lake_writer.get_session")
    def test_write_reaction_add_source_id(self, mock_gs, writer: EventLakeWriter):
        """Reaction source_id should follow the {user}-{msg}-{emoji} scheme."""
        mock_session = MagicMock()
        mock_gs.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_gs.return_value.__exit__ = MagicMock(return_value=False)

        writer.write_reaction_add(
            guild_id=100,
            user_id=1001,
            channel_id=555,
            message_id=999,
            emoji_name="👍",
        )

        added = mock_session.add.call_args[0][0]
        assert added.source_id == "1001-999-👍"

    @patch("synapse.services.event_lake_writer.get_session")
    def test_write_reaction_remove_no_source_id(self, mock_gs, writer: EventLakeWriter):
        """Reaction remove events should have no source_id (per §3B.4)."""
        mock_session = MagicMock()
        mock_gs.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_gs.return_value.__exit__ = MagicMock(return_value=False)

        writer.write_reaction_remove(
            guild_id=100,
            user_id=1001,
            channel_id=555,
            message_id=999,
            emoji_name="👍",
        )

        added = mock_session.add.call_args[0][0]
        assert added.source_id is None

    @patch("synapse.services.event_lake_writer.get_session")
    def test_write_thread_create(self, mock_gs, writer: EventLakeWriter):
        """Thread create should use thread ID as source_id."""
        mock_session = MagicMock()
        mock_gs.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_gs.return_value.__exit__ = MagicMock(return_value=False)

        writer.write_thread_create(
            guild_id=100,
            user_id=1001,
            thread_id=777888,
            parent_channel_id=555,
            thread_name="help-docker",
        )

        added = mock_session.add.call_args[0][0]
        assert added.source_id == "777888"
        assert added.payload["name"] == "help-docker"

    @patch("synapse.services.event_lake_writer.get_session")
    def test_write_member_join(self, mock_gs, writer: EventLakeWriter):
        """Member join should include joined_at in payload."""
        mock_session = MagicMock()
        mock_gs.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_gs.return_value.__exit__ = MagicMock(return_value=False)

        joined = datetime(2026, 2, 12, 14, 30, 0, tzinfo=UTC)
        writer.write_member_join(
            guild_id=100,
            user_id=1001,
            joined_at=joined,
        )

        added = mock_session.add.call_args[0][0]
        assert added.event_type == EventType.MEMBER_JOIN
        assert "joined_at" in added.payload

    @patch("synapse.services.event_lake_writer.get_session")
    def test_write_member_leave(self, mock_gs, writer: EventLakeWriter):
        """Member leave should have empty payload."""
        mock_session = MagicMock()
        mock_gs.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_gs.return_value.__exit__ = MagicMock(return_value=False)

        writer.write_member_leave(guild_id=100, user_id=1001)

        added = mock_session.add.call_args[0][0]
        assert added.event_type == EventType.MEMBER_LEAVE
        assert added.payload == {}


# ---------------------------------------------------------------------------
# Data Source Toggle Enforcement Tests
# ---------------------------------------------------------------------------
class TestDataSourceToggle:
    """Verify that disabled data sources prevent event writes."""

    @patch("synapse.services.event_lake_writer.get_session")
    def test_disabled_source_skips_write(self, mock_gs):
        """When a source is disabled, write_event should return False without writing."""
        engine = MagicMock()
        writer = EventLakeWriter(engine)

        # Simulate disabled source by directly setting the cache
        writer._disabled_sources = {"message_create"}
        writer._disabled_sources_ts = 9999999999.0  # far future — cache won't expire

        result = writer.write_event(
            guild_id=100, user_id=1, event_type=EventType.MESSAGE_CREATE,
        )

        assert result is False
        # Session should never have been opened
        mock_gs.assert_not_called()

    @patch("synapse.services.event_lake_writer.get_session")
    def test_enabled_source_allows_write(self, mock_gs):
        """When a source is enabled (not in disabled set), write should proceed."""
        mock_session = MagicMock()
        mock_gs.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_gs.return_value.__exit__ = MagicMock(return_value=False)

        engine = MagicMock()
        writer = EventLakeWriter(engine)

        # Only reaction_add is disabled; message_create should still work
        writer._disabled_sources = {"reaction_add"}
        writer._disabled_sources_ts = 9999999999.0

        result = writer.write_event(
            guild_id=100, user_id=1, event_type=EventType.MESSAGE_CREATE,
        )

        assert result is True
        mock_session.add.assert_called_once()

    def test_is_source_enabled_defaults_to_true(self):
        """With no disabled sources, all types should be enabled."""
        engine = MagicMock()
        writer = EventLakeWriter(engine)
        writer._disabled_sources = set()
        writer._disabled_sources_ts = 9999999999.0

        assert writer.is_source_enabled(EventType.MESSAGE_CREATE) is True
        assert writer.is_source_enabled(EventType.VOICE_JOIN) is True
        assert writer.is_source_enabled(EventType.MEMBER_LEAVE) is True

    def test_is_source_enabled_respects_disabled(self):
        """Disabled sources should return False."""
        engine = MagicMock()
        writer = EventLakeWriter(engine)
        writer._disabled_sources = {"voice_join", "member_leave"}
        writer._disabled_sources_ts = 9999999999.0

        assert writer.is_source_enabled(EventType.VOICE_JOIN) is False
        assert writer.is_source_enabled(EventType.MEMBER_LEAVE) is False
        assert writer.is_source_enabled(EventType.MESSAGE_CREATE) is True

    def test_emoji_count_regex_improvements(self):
        """Test improved regex logic for custom emojis and edge cases."""
        # Custom emoji
        assert extract_message_metadata("Hi <:custom:123>", 0, False)["emoji_count"] == 1
        # Animated custom emoji
        assert extract_message_metadata("Wow <a:anim:456>", 0, False)["emoji_count"] == 1
        # Mixed standard (shortcode) and custom
        assert extract_message_metadata(":smile: <a:anim:456>", 0, False)["emoji_count"] == 2
        # Edge case: raw colons shouldn't count
        assert extract_message_metadata("Time: 12:00:30", 0, False)["emoji_count"] == 0
        # Edge case: triple colon
        assert extract_message_metadata(":::", 0, False)["emoji_count"] == 0
