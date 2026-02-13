"""
tests/test_bootstrap.py — Unit Tests for First-Run Bootstrap
==============================================================

Tests the setup_service module: guild snapshot round-tripping,
bootstrap_guild logic, get_setup_status, save_guild_snapshot, and
idempotency guarantees.

All tests are pure unit tests using an in-memory SQLite database;
no Discord connection or Docker stack required.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from synapse.database.models import (
    Base,
    Season,
    Setting,
    Zone,
    ZoneChannel,
    ZoneMultiplier,
)
from synapse.services.setup_service import (
    BOOTSTRAP_VERSION,
    GUILD_SNAPSHOT_KEY,
    SETUP_INITIALIZED_KEY,
    ChannelInfo,
    GuildSnapshot,
    _default_settings,
    bootstrap_guild,
    get_setup_status,
    save_guild_snapshot,
)

GUILD_ID = 111222333


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def engine():
    """Create an in-memory SQLite database with only the tables bootstrap needs.

    We can't call ``Base.metadata.create_all()`` because some models (e.g.
    ``AdminLog``) use PostgreSQL-specific ``JSONB`` columns that SQLite
    cannot render.  Instead, create only the tables the setup service touches.
    """
    eng = create_engine("sqlite:///:memory:")
    tables = [
        Setting.__table__,
        Zone.__table__,
        ZoneChannel.__table__,
        ZoneMultiplier.__table__,
        Season.__table__,
    ]
    Base.metadata.create_all(eng, tables=tables)
    return eng


@pytest.fixture
def sample_snapshot() -> GuildSnapshot:
    """A realistic guild snapshot with 2 categories + assorted channels."""
    return GuildSnapshot(
        guild_id=GUILD_ID,
        guild_name="Test Server",
        afk_channel_id=900,
        captured_at=datetime.now(UTC).isoformat(),
        channels=[
            ChannelInfo(id=10, name="General", type="category"),
            ChannelInfo(id=11, name="general-chat", type="text", category_id=10, category_name="General"),
            ChannelInfo(id=12, name="bot-commands", type="text", category_id=10, category_name="General"),
            ChannelInfo(id=20, name="Development", type="category"),
            ChannelInfo(id=21, name="python-help", type="text", category_id=20, category_name="Development"),
            ChannelInfo(id=22, name="dev-voice", type="voice", category_id=20, category_name="Development"),
            ChannelInfo(id=23, name="dev-forum", type="forum", category_id=20, category_name="Development"),
            ChannelInfo(id=900, name="AFK", type="voice", category_id=None, category_name=None),
        ],
    )


@pytest.fixture
def sparse_snapshot() -> GuildSnapshot:
    """A guild with NO categories — just loose channels."""
    return GuildSnapshot(
        guild_id=GUILD_ID,
        guild_name="Barebones Server",
        channels=[
            ChannelInfo(id=50, name="general", type="text"),
            ChannelInfo(id=51, name="voice-lounge", type="voice"),
        ],
    )


# ---------------------------------------------------------------------------
# GuildSnapshot serialization
# ---------------------------------------------------------------------------
class TestGuildSnapshotSerialization:
    def test_round_trip(self, sample_snapshot: GuildSnapshot):
        """to_json() → from_json() should reconstruct an equivalent snapshot."""
        raw = sample_snapshot.to_json()
        restored = GuildSnapshot.from_json(raw)

        assert restored.guild_id == sample_snapshot.guild_id
        assert restored.guild_name == sample_snapshot.guild_name
        assert restored.afk_channel_id == sample_snapshot.afk_channel_id
        assert len(restored.channels) == len(sample_snapshot.channels)

    def test_channel_fields_preserved(self, sample_snapshot: GuildSnapshot):
        """Every channel field should survive the round-trip."""
        restored = GuildSnapshot.from_json(sample_snapshot.to_json())
        dev_voice = next(ch for ch in restored.channels if ch.name == "dev-voice")

        assert dev_voice.id == 22
        assert dev_voice.type == "voice"
        assert dev_voice.category_id == 20
        assert dev_voice.category_name == "Development"

    def test_empty_channels(self):
        """Snapshot with no channels should round-trip without error."""
        snap = GuildSnapshot(guild_id=1, guild_name="empty")
        restored = GuildSnapshot.from_json(snap.to_json())
        assert restored.channels == []

    def test_corrupt_json_raises(self):
        """from_json should raise on malformed input."""
        with pytest.raises((json.JSONDecodeError, KeyError)):
            GuildSnapshot.from_json("{bad json")


# ---------------------------------------------------------------------------
# save_guild_snapshot
# ---------------------------------------------------------------------------
class TestSaveGuildSnapshot:
    def test_persists_to_setting_table(self, engine, sample_snapshot: GuildSnapshot):
        """Snapshot should land in the Setting table under the correct key."""
        save_guild_snapshot(engine, sample_snapshot)

        with Session(engine) as session:
            row = session.get(Setting, GUILD_SNAPSHOT_KEY)
            assert row is not None
            assert row.category == "setup"
            data = json.loads(row.value_json)
            assert data["guild_id"] == GUILD_ID
            assert len(data["channels"]) == 8

    def test_overwrites_on_second_call(self, engine, sample_snapshot: GuildSnapshot):
        """A second save should overwrite the previous snapshot."""
        save_guild_snapshot(engine, sample_snapshot)

        updated = GuildSnapshot(guild_id=GUILD_ID, guild_name="Updated Name", channels=[])
        save_guild_snapshot(engine, updated)

        with Session(engine) as session:
            row = session.get(Setting, GUILD_SNAPSHOT_KEY)
            data = json.loads(row.value_json)
            assert data["guild_name"] == "Updated Name"
            assert data["channels"] == []


# ---------------------------------------------------------------------------
# get_setup_status
# ---------------------------------------------------------------------------
class TestGetSetupStatus:
    def test_uninitialized_state(self, engine):
        """Fresh DB should report not initialized, no snapshot."""
        status = get_setup_status(engine)

        assert status["initialized"] is False
        assert status["has_guild_snapshot"] is False
        assert status["guild_snapshot"] is None
        assert status["has_zones"] is False
        assert status["bootstrap_version"] is None

    def test_with_snapshot_only(self, engine, sample_snapshot: GuildSnapshot):
        """After bot writes a snapshot but before bootstrap, status reflects it."""
        save_guild_snapshot(engine, sample_snapshot)
        status = get_setup_status(engine)

        assert status["initialized"] is False
        assert status["has_guild_snapshot"] is True
        assert status["guild_snapshot"]["guild_name"] == "Test Server"
        assert status["guild_snapshot"]["channel_count"] == 8

    def test_after_bootstrap(self, engine, sample_snapshot: GuildSnapshot):
        """After a successful bootstrap, initialized should be True."""
        save_guild_snapshot(engine, sample_snapshot)
        bootstrap_guild(engine, GUILD_ID)

        status = get_setup_status(engine)
        assert status["initialized"] is True
        assert status["has_zones"] is True
        assert status["bootstrap_version"] == BOOTSTRAP_VERSION


# ---------------------------------------------------------------------------
# bootstrap_guild — happy path
# ---------------------------------------------------------------------------
class TestBootstrapGuild:
    def test_creates_zones_from_categories(self, engine, sample_snapshot: GuildSnapshot):
        """Bootstrap should create one zone per Discord category."""
        save_guild_snapshot(engine, sample_snapshot)
        result = bootstrap_guild(engine, GUILD_ID)

        assert result.success is True
        assert result.zones_created == 2  # "General" + "Development"
        assert result.zones_existing == 0

        with Session(engine) as session:
            zones = session.scalars(select(Zone)).all()
            zone_names = {z.name for z in zones}
            assert zone_names == {"General", "Development"}

    def test_maps_channels_to_zones(self, engine, sample_snapshot: GuildSnapshot):
        """Non-category channels should be mapped to their parent zone."""
        save_guild_snapshot(engine, sample_snapshot)
        result = bootstrap_guild(engine, GUILD_ID)

        # 8 channels total, 2 are categories → 6 should be mapped
        assert result.channels_mapped == 6
        assert result.channels_existing == 0

        with Session(engine) as session:
            mappings = session.scalars(select(ZoneChannel)).all()
            assert len(mappings) == 6

    def test_creates_zone_multipliers(self, engine, sample_snapshot: GuildSnapshot):
        """Each new zone should get default multipliers for all 4 interaction types."""
        save_guild_snapshot(engine, sample_snapshot)
        bootstrap_guild(engine, GUILD_ID)

        with Session(engine) as session:
            mults = session.scalars(select(ZoneMultiplier)).all()
            # 2 zones × 4 interaction types = 8 multipliers
            assert len(mults) == 8

    def test_creates_default_season(self, engine, sample_snapshot: GuildSnapshot):
        """Bootstrap should create Season 1 if none exists."""
        save_guild_snapshot(engine, sample_snapshot)
        result = bootstrap_guild(engine, GUILD_ID)

        assert result.season_created is True

        with Session(engine) as session:
            season = session.scalar(select(Season).where(Season.guild_id == GUILD_ID))
            assert season is not None
            assert season.name == "Season 1"
            assert season.active is True

    def test_writes_default_settings(self, engine, sample_snapshot: GuildSnapshot):
        """Bootstrap should write all baseline settings."""
        save_guild_snapshot(engine, sample_snapshot)
        result = bootstrap_guild(engine, GUILD_ID)

        expected = len(_default_settings())
        # +3 for setup.initialized, bootstrap_version, bootstrap_timestamp
        # +1 for guild.snapshot (written by save_guild_snapshot)
        assert result.settings_written == expected

        with Session(engine) as session:
            all_settings = session.scalars(select(Setting)).all()
            keys = {s.key for s in all_settings}
            assert "economy.xp_per_message" in keys
            assert "anti_gaming.min_message_length" in keys
            assert SETUP_INITIALIZED_KEY in keys

    def test_marks_initialized(self, engine, sample_snapshot: GuildSnapshot):
        """After bootstrap, setup.initialized should be True."""
        save_guild_snapshot(engine, sample_snapshot)
        bootstrap_guild(engine, GUILD_ID)

        with Session(engine) as session:
            row = session.get(Setting, SETUP_INITIALIZED_KEY)
            assert row is not None
            assert json.loads(row.value_json) is True


# ---------------------------------------------------------------------------
# bootstrap_guild — edge cases
# ---------------------------------------------------------------------------
class TestBootstrapEdgeCases:
    def test_no_snapshot_returns_failure(self, engine):
        """Calling bootstrap without a guild snapshot should fail gracefully."""
        result = bootstrap_guild(engine, GUILD_ID)

        assert result.success is False
        assert any("No guild snapshot" in w for w in result.warnings)
        assert result.zones_created == 0

    def test_sparse_guild_creates_fallback_zone(self, engine, sparse_snapshot: GuildSnapshot):
        """Guild with no categories should get a 'General' fallback zone."""
        save_guild_snapshot(engine, sparse_snapshot)
        result = bootstrap_guild(engine, GUILD_ID)

        assert result.success is True
        assert result.zones_created == 1
        assert any("no categories" in w for w in result.warnings)

        with Session(engine) as session:
            zone = session.scalar(select(Zone).where(Zone.guild_id == GUILD_ID))
            assert zone.name == "General"

    def test_sparse_guild_maps_channels_to_fallback(self, engine, sparse_snapshot: GuildSnapshot):
        """Loose channels should map to the General fallback zone."""
        save_guild_snapshot(engine, sparse_snapshot)
        result = bootstrap_guild(engine, GUILD_ID)

        assert result.channels_mapped == 2

        with Session(engine) as session:
            mappings = session.scalars(select(ZoneChannel)).all()
            assert len(mappings) == 2

    def test_guild_id_mismatch_produces_warning(self, engine, sample_snapshot: GuildSnapshot):
        """If config guild_id doesn't match snapshot, bootstrap should warn but continue."""
        save_guild_snapshot(engine, sample_snapshot)
        different_guild = 999888777
        result = bootstrap_guild(engine, different_guild)

        assert result.success is True
        assert any("differs from config" in w for w in result.warnings)

    def test_corrupt_snapshot_returns_failure(self, engine):
        """Corrupt JSON in the snapshot setting should fail gracefully."""
        with Session(engine) as session:
            session.add(Setting(
                key=GUILD_SNAPSHOT_KEY,
                value_json="{not valid json!!!",
                category="setup",
            ))
            session.commit()

        result = bootstrap_guild(engine, GUILD_ID)
        assert result.success is False
        assert any("corrupt" in w.lower() for w in result.warnings)


# ---------------------------------------------------------------------------
# bootstrap_guild — idempotency
# ---------------------------------------------------------------------------
class TestBootstrapIdempotency:
    def test_second_run_creates_no_duplicates(self, engine, sample_snapshot: GuildSnapshot):
        """Running bootstrap twice should not duplicate zones or channels."""
        save_guild_snapshot(engine, sample_snapshot)

        result1 = bootstrap_guild(engine, GUILD_ID)
        assert result1.zones_created == 2
        assert result1.channels_mapped == 6
        assert result1.season_created is True

        result2 = bootstrap_guild(engine, GUILD_ID)
        assert result2.zones_created == 0
        assert result2.zones_existing == 2
        assert result2.channels_mapped == 0
        assert result2.channels_existing == 6
        assert result2.season_created is False

    def test_idempotent_settings(self, engine, sample_snapshot: GuildSnapshot):
        """Second run should not re-write settings that already exist."""
        save_guild_snapshot(engine, sample_snapshot)

        result1 = bootstrap_guild(engine, GUILD_ID)
        result2 = bootstrap_guild(engine, GUILD_ID)

        assert result2.settings_written == 0

    def test_zone_count_stable_after_rerun(self, engine, sample_snapshot: GuildSnapshot):
        """Total zone count shouldn't change across multiple runs."""
        save_guild_snapshot(engine, sample_snapshot)

        bootstrap_guild(engine, GUILD_ID)
        bootstrap_guild(engine, GUILD_ID)
        bootstrap_guild(engine, GUILD_ID)

        with Session(engine) as session:
            zones = session.scalars(
                select(Zone).where(Zone.guild_id == GUILD_ID)
            ).all()
            assert len(zones) == 2


# ---------------------------------------------------------------------------
# _default_settings sanity
# ---------------------------------------------------------------------------
class TestDefaultSettings:
    def test_all_keys_have_three_tuple(self):
        """Every default setting should be a (value, category, description) tuple."""
        for key, val in _default_settings().items():
            assert isinstance(val, tuple), f"{key} is not a tuple"
            assert len(val) == 3, f"{key} tuple length is {len(val)}, expected 3"

    def test_categories_are_known(self):
        """Setting categories should be from a known set."""
        known = {"economy", "anti_gaming", "quality", "announcements", "display"}
        for key, (_, category, _) in _default_settings().items():
            assert category in known, f"{key} has unknown category '{category}'"

    def test_minimum_setting_count(self):
        """We should have at least 15 default settings (currently 16)."""
        assert len(_default_settings()) >= 15
