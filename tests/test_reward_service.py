"""
tests/test_reward_service.py — Reward Service Integration Tests
================================================================
Covers F-009: Service-level tests for reward_service.process_event(),
including idempotency, user creation, XP/Star application, and season stats.

Uses an in-memory SQLite database via the shared conftest fixtures.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from synapse.database.models import (
    ActivityLog,
    Base,
    InteractionType,
    Season,
    User,
    UserStats,
)
from synapse.engine.cache import ConfigCache
from synapse.engine.events import SynapseEvent
from synapse.services import reward_service


@pytest.fixture
def engine(db_engine):
    """Re-use the shared conftest db_engine (SQLite, StaticPool)."""
    return db_engine


@pytest.fixture
def cache():
    """A mock ConfigCache with sensible defaults."""
    mock_cache = MagicMock(spec=ConfigCache)
    mock_cache.resolve_multipliers.return_value = (1.0, 1.0)
    mock_cache.get_active_achievements.return_value = []
    mock_cache.get_int.return_value = 0
    mock_cache.get_float.return_value = 0.0
    mock_cache.get_setting.return_value = None
    return mock_cache


def _make_event(
    user_id: int = 1000,
    event_type: InteractionType = InteractionType.MESSAGE,
    channel_id: int = 500,
    guild_id: int = 100,
    source_event_id: str | None = "msg-001",
    metadata: dict | None = None,
) -> SynapseEvent:
    return SynapseEvent(
        user_id=user_id,
        event_type=event_type,
        channel_id=channel_id,
        guild_id=guild_id,
        source_event_id=source_event_id,
        metadata=metadata or {"length": 50},
        timestamp=datetime(2026, 1, 15, 12, 0, 0),
    )


def _seed_season(engine, guild_id: int = 100) -> int:
    """Insert an active season and return its ID."""
    with Session(engine) as session:
        season = Season(
            guild_id=guild_id,
            name="S1",
            active=True,
            starts_at=datetime(2026, 1, 1),
            ends_at=datetime(2026, 12, 31),
        )
        session.add(season)
        session.commit()
        session.refresh(season)
        return season.id


class TestProcessEvent:
    """Test the full process_event pipeline."""

    def test_creates_user_on_first_event(self, engine, cache):
        """First event for an unknown user should create a User row."""
        event = _make_event()
        result, was_dup = reward_service.process_event(
            engine, cache, event, "Alice"
        )
        assert not was_dup
        assert result.xp > 0

        with Session(engine) as session:
            user = session.get(User, 1000)
            assert user is not None
            assert user.discord_name == "Alice"
            assert user.xp > 0

    def test_xp_is_applied_to_user(self, engine, cache):
        """process_event should increment the user's XP."""
        event = _make_event()
        result, _ = reward_service.process_event(
            engine, cache, event, "Bob"
        )

        with Session(engine) as session:
            user = session.get(User, 1000)
            assert user.xp == result.xp

    def test_activity_log_created(self, engine, cache):
        """An ActivityLog row should be created for the event."""
        event = _make_event()
        reward_service.process_event(engine, cache, event, "Charlie")

        with Session(engine) as session:
            logs = session.query(ActivityLog).all()
            assert len(logs) >= 1
            msg_logs = [
                entry for entry in logs
                if entry.event_type == InteractionType.MESSAGE.value
            ]
            assert len(msg_logs) == 1
            assert msg_logs[0].source_event_id == "msg-001"

    def test_idempotent_duplicate_event(self, engine, cache):
        """Processing the same source_event_id twice should be idempotent."""
        event = _make_event(source_event_id="msg-dup")

        result1, dup1 = reward_service.process_event(
            engine, cache, event, "Dave"
        )
        assert not dup1

        result2, dup2 = reward_service.process_event(
            engine, cache, event, "Dave"
        )
        assert dup2  # second call is a duplicate

        # User XP should only contain the first event's XP
        with Session(engine) as session:
            user = session.get(User, 1000)
            assert user.xp == result1.xp

    def test_events_without_source_id_always_insert(self, engine, cache):
        """Events with source_event_id=None should always insert (e.g. voice ticks)."""
        event1 = _make_event(source_event_id=None, event_type=InteractionType.VOICE_TICK)
        event2 = _make_event(source_event_id=None, event_type=InteractionType.VOICE_TICK)

        _, dup1 = reward_service.process_event(engine, cache, event1, "Eve")
        _, dup2 = reward_service.process_event(engine, cache, event2, "Eve")

        assert not dup1
        assert not dup2

        with Session(engine) as session:
            logs = session.query(ActivityLog).filter_by(
                event_type=InteractionType.VOICE_TICK.value
            ).all()
            assert len(logs) == 2

    def test_season_stats_updated(self, engine, cache):
        """When an active season exists, UserStats should be updated."""
        _seed_season(engine, guild_id=100)
        event = _make_event()

        result, _ = reward_service.process_event(engine, cache, event, "Frank")

        with Session(engine) as session:
            stats_list = session.query(UserStats).all()
            assert len(stats_list) == 1
            stats = stats_list[0]
            assert stats.season_stars == result.stars
            assert stats.messages_sent == 1

    def test_different_events_create_separate_logs(self, engine, cache):
        """Two different events should produce two separate activity logs."""
        e1 = _make_event(source_event_id="msg-a")
        e2 = _make_event(source_event_id="msg-b")

        reward_service.process_event(engine, cache, e1, "Grace")
        reward_service.process_event(engine, cache, e2, "Grace")

        with Session(engine) as session:
            logs = session.query(ActivityLog).filter_by(
                event_type=InteractionType.MESSAGE.value
            ).all()
            assert len(logs) == 2


class TestAwardManual:
    """Test the manual award path."""

    def test_award_creates_user_if_needed(self, engine):
        user = reward_service.award_manual(
            engine,
            user_id=2000,
            display_name="NewUser",
            guild_id=100,
            xp=50,
            gold=10,
            reason="welcome bonus",
            admin_id=1,
        )
        assert user.xp == 50
        assert user.gold == 10

    def test_award_increments_existing_user(self, engine):
        # Create user first
        with Session(engine) as session:
            session.add(User(id=3000, discord_name="Existing", xp=100, gold=20))
            session.commit()

        user = reward_service.award_manual(
            engine,
            user_id=3000,
            display_name="Existing",
            guild_id=100,
            xp=25,
            gold=5,
            reason="bonus",
            admin_id=1,
        )
        assert user.xp == 125
        assert user.gold == 25

    def test_award_creates_activity_log(self, engine):
        reward_service.award_manual(
            engine,
            user_id=4000,
            display_name="Logged",
            guild_id=100,
            xp=10,
            gold=0,
            reason="test",
            admin_id=1,
        )

        with Session(engine) as session:
            logs = session.query(ActivityLog).filter_by(
                event_type=InteractionType.MANUAL_AWARD.value
            ).all()
            assert len(logs) == 1
            assert logs[0].metadata_.get("reason") == "test"
