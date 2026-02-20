from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, select

# JSONB -> TEXT shim for SQLite test
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from synapse.database.models import (
    ActivityLog,
    Base,
    InteractionType,
    RewardRule,
    RuleEvaluation,
)
from synapse.engine.cache import ConfigCache
from synapse.engine.events import SynapseEvent
from synapse.services.reward_service import process_event


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(element, compiler, **kw):
    return "TEXT"

@pytest.fixture
def db_engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine

@pytest.fixture
def session(db_engine):
    with Session(db_engine) as session:
        yield session

def test_rule_evaluation_linked_in_firewall_mode(db_engine):
    """
    Verify that in firewall mode, an ActivityLog entry is linked
    to its corresponding RuleEvaluation record via FK.
    """
    # Setup
    mock_cache = MagicMock(spec=ConfigCache)
    mock_cache.get_bool.side_effect = (
        lambda key, default=False: (
            True if key == "flags.firewall_enabled" else default
        )
    )
    mock_cache.get_int.return_value = 50  # gold per level
    mock_cache.resolve_multipliers.return_value = (1.0, 1.0)

    # Create dummy rule to ensure evaluation runs
    rule = RewardRule(
        guild_id=123,
        name="Test Rule",
        predicates=[{"field": "event_type", "op": "==", "value": "MESSAGE"}],
        outcomes=[{"type": "xp", "base_value": 10}],
        priority=100,
        is_active=True,
    )

    with Session(db_engine) as s:
        s.add(rule)
        s.commit()

    # Create event
    event = SynapseEvent(
        user_id=101,
        event_type=InteractionType.MESSAGE,
        source_event_id="msg_001",
        guild_id=123,
        channel_id=456,
        metadata={"content": "hello"},
        timestamp=datetime.now(),
    )

    # Act
    # process_event opens its own session using engine
    result, duplicate = process_event(db_engine, mock_cache, event, "TestUser")

    # Assert
    assert not duplicate
    assert result.xp == 10  # From rule

    with Session(db_engine) as s:
        log = s.scalar(select(ActivityLog).where(ActivityLog.source_event_id == "msg_001"))
        assert log is not None
        assert log.rule_evaluation_id is not None

        evaluation = s.get(RuleEvaluation, log.rule_evaluation_id)
        assert evaluation is not None
        assert evaluation.user_id == 101

def test_rule_evaluation_linked_in_shadow_mode(db_engine):
    """
    Verify that in shadow mode (firewall=False), an ActivityLog entry is
    linked to a RuleEvaluation record created by shadow evaluation.
    """
    # Setup
    mock_cache = MagicMock(spec=ConfigCache)
    # firewall_enabled = False
    mock_cache.get_bool.return_value = False
    mock_cache.get_int.return_value = 50
    mock_cache.resolve_multipliers.return_value = (1.0, 1.0)
    # Also need multiplier config mocks?
    # RuleEngine uses cache.get_float/int for multipliers if rules say so.
    mock_cache.get_float.return_value = 1.0

    # Create dummy rule
    rule = RewardRule(
        guild_id=123,
        name="Test Rule",
        predicates=[{"field": "event_type", "op": "==", "value": "MESSAGE"}],
        outcomes=[{"type": "xp", "base_value": 10}],
        priority=100,
        is_active=True,
    )

    with Session(db_engine) as s:
        s.add(rule)
        s.commit()

    # Create event
    event = SynapseEvent(
        user_id=102,
        event_type=InteractionType.MESSAGE,
        source_event_id="msg_002",
        guild_id=123,
        channel_id=456,
        metadata={"content": "hello shadow"},
        timestamp=datetime.now(),
    )

    # Act
    result, duplicate = process_event(db_engine, mock_cache, event, "TestUserShadow")

    # Assert
    assert not duplicate
    # In shadow mode, legacy calculation runs. Without specific config, maybe 0 XP?
    # Or default base XP? Message base XP is usually configured.
    # We don't care about result values, just linkage.

    with Session(db_engine) as s:
        log = s.scalar(select(ActivityLog).where(ActivityLog.source_event_id == "msg_002"))
        assert log is not None
        assert log.rule_evaluation_id is not None  # Should be set by shadow eval

        evaluation = s.get(RuleEvaluation, log.rule_evaluation_id)
        assert evaluation is not None
        assert evaluation.user_id == 102

def test_duplicate_event_handling(db_engine):
    """
    Verify duplicates are handled correctly (no new ActivityLog, but count as dupes).
    """
    mock_cache = MagicMock(spec=ConfigCache)
    mock_cache.get_bool.return_value = True # Firewall mode
    mock_cache.resolve_multipliers.return_value = (1.0, 1.0)
    mock_cache.get_int.return_value = 50

    # Run once
    event = SynapseEvent(
        user_id=103,
        event_type=InteractionType.MESSAGE,
        source_event_id="msg_003",
        guild_id=123,
        channel_id=456,
        metadata={},
        timestamp=datetime.now(),
    )

    process_event(db_engine, mock_cache, event, "TestUserDupe")

    # Run twice
    result, duplicate = process_event(db_engine, mock_cache, event, "TestUserDupe")

    assert duplicate is True

    with Session(db_engine) as s:
        logs = s.scalars(select(ActivityLog).where(ActivityLog.source_event_id == "msg_003")).all()
        assert len(logs) == 1
