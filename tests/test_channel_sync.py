"""
tests/test_channel_sync.py — Channel Sync Service Tests
=========================================================
Tests for ``sync_channels_from_snapshot`` which upserts Discord channel
metadata into the ``channels`` table.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from synapse.database.models import Channel
from synapse.services.channel_service import sync_channels_from_snapshot

GUILD_ID = 111222333


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ch(id: int, name: str, type: str = "text", category_id=None, category_name=None, position=0):
    return {
        "id": id,
        "name": name,
        "type": type,
        "category_id": category_id,
        "category_name": category_name,
        "position": position,
    }


def _get_channels(engine, guild_id=GUILD_ID) -> list[Channel]:
    with Session(engine) as s:
        return list(s.scalars(
            select(Channel).where(Channel.guild_id == guild_id).order_by(Channel.id)
        ).all())


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSyncChannelsFromSnapshot:
    """Test channel upsert logic."""

    def test_inserts_new_channels(self, db_engine):
        channels = [
            _ch(1, "general"),
            _ch(2, "voice-chat", "voice"),
            _ch(3, "announcements", "announcement"),
        ]
        result = sync_channels_from_snapshot(db_engine, GUILD_ID, channels)

        assert result["upserted"] == 3
        assert result["removed"] == 0

        rows = _get_channels(db_engine)
        assert len(rows) == 3
        assert rows[0].name == "general"
        assert rows[1].name == "voice-chat"
        assert rows[1].type == "voice"
        assert rows[2].name == "announcements"

    def test_upserts_existing_channels(self, db_engine):
        # Insert initial data
        sync_channels_from_snapshot(db_engine, GUILD_ID, [
            _ch(1, "general"),
            _ch(2, "voice-chat", "voice"),
        ])

        # Update: rename channel 1, keep channel 2
        result = sync_channels_from_snapshot(db_engine, GUILD_ID, [
            _ch(1, "main-chat"),
            _ch(2, "voice-chat", "voice"),
        ])

        assert result["upserted"] == 2
        assert result["removed"] == 0

        rows = _get_channels(db_engine)
        assert len(rows) == 2
        assert rows[0].name == "main-chat"  # Updated
        assert rows[1].name == "voice-chat"  # Unchanged

    def test_removes_stale_channels(self, db_engine):
        # Insert 3 channels
        sync_channels_from_snapshot(db_engine, GUILD_ID, [
            _ch(1, "general"),
            _ch(2, "voice-chat", "voice"),
            _ch(3, "random"),
        ])

        # Sync with only 2 — channel 3 should be removed
        result = sync_channels_from_snapshot(db_engine, GUILD_ID, [
            _ch(1, "general"),
            _ch(2, "voice-chat", "voice"),
        ])

        assert result["removed"] == 1
        rows = _get_channels(db_engine)
        assert len(rows) == 2
        assert all(ch.id != 3 for ch in rows)

    def test_empty_snapshot_removes_all(self, db_engine):
        sync_channels_from_snapshot(db_engine, GUILD_ID, [
            _ch(1, "general"),
            _ch(2, "voice-chat", "voice"),
        ])

        result = sync_channels_from_snapshot(db_engine, GUILD_ID, [])
        assert result["upserted"] == 0
        assert result["removed"] == 2
        assert _get_channels(db_engine) == []

    def test_preserves_discord_category_metadata(self, db_engine):
        sync_channels_from_snapshot(db_engine, GUILD_ID, [
            _ch(10, "help", "text", category_id=99, category_name="Support"),
            _ch(11, "stage-talk", "stage", category_id=99, category_name="Support"),
        ])

        rows = _get_channels(db_engine)
        assert rows[0].discord_category_id == 99
        assert rows[0].discord_category_name == "Support"
        assert rows[1].type == "stage"

    def test_different_guilds_are_isolated(self, db_engine):
        sync_channels_from_snapshot(db_engine, GUILD_ID, [_ch(1, "general")])
        sync_channels_from_snapshot(db_engine, 999888777, [_ch(2, "other-server")])

        g1 = _get_channels(db_engine, GUILD_ID)
        g2 = _get_channels(db_engine, 999888777)
        assert len(g1) == 1
        assert len(g2) == 1
        assert g1[0].name == "general"
        assert g2[0].name == "other-server"

    def test_idempotent_on_identical_data(self, db_engine):
        channels = [_ch(1, "general"), _ch(2, "voice", "voice")]

        r1 = sync_channels_from_snapshot(db_engine, GUILD_ID, channels)
        r2 = sync_channels_from_snapshot(db_engine, GUILD_ID, channels)

        assert r1["upserted"] == r2["upserted"] == 2
        assert r1["removed"] == r2["removed"] == 0
        assert len(_get_channels(db_engine)) == 2

    def test_defaults_unknown_name_and_text_type(self, db_engine):
        """Channels with missing name/type get sensible defaults."""
        sync_channels_from_snapshot(db_engine, GUILD_ID, [{"id": 42}])

        rows = _get_channels(db_engine)
        assert len(rows) == 1
        assert rows[0].name == "unknown"
        assert rows[0].type == "text"
