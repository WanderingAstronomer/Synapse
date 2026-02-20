from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, select

# Hack to fix JSONB -> TEXT compilation for SQLite (since we are not running conftest.py)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from synapse.database.models import (
    AchievementCategory,
    AchievementRarity,
    AchievementTemplate,
    Base,
    InteractionType,
    Season,
    TriggerType,
    User,
    UserAchievement,
)
from synapse.engine.cache import ConfigCache
from synapse.engine.events import SynapseEvent
from synapse.engine.reward import RewardResult
from synapse.services.reward_service import process_event


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(element, compiler, **kw):  # type: ignore[misc]
    return "TEXT"

@pytest.fixture
def db_engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine

@pytest.fixture
def db_session_factory(db_engine):
    session_local = sessionmaker(bind=db_engine)
    return session_local

def test_max_earners_enforced(db_engine):
    """
    Test that an achievement with max_earners set cannot be awarded
    to more users than the limit.
    """
    session_local = sessionmaker(bind=db_engine)
    session = session_local()

    # 1. Setup Data
    # Fixed kw args: no description for category, no value for rarity
    category = AchievementCategory(guild_id=1, name="General")
    rarity = AchievementRarity(guild_id=1, name="Common", color="#ffffff")
    session.add_all([category, rarity])
    session.flush()

    template = AchievementTemplate(
        guild_id=1,
        name="Limited Edition",
        description="Only for the first.",
        badge_image="/foo.png",
        category_id=category.id,
        rarity_id=rarity.id,
        trigger_type=TriggerType.STAT_THRESHOLD,
        trigger_config={"field": "messages_sent", "value": 1},
        xp_reward=100,
        gold_reward=10,
        max_earners=1  # <--- The limit is 1
    )
    session.add(template)

    # Create Users
    user1 = User(id=101, discord_name="User1", xp=0, level=1)
    user2 = User(id=102, discord_name="User2", xp=0, level=1)

    # Season needed for event processing
    season = Season(
        guild_id=1,
        name="S1",
        starts_at=datetime.utcnow(),
        ends_at=datetime.utcnow(),
        active=True,
    )

    session.add_all([user1, user2, season])
    session.commit()

    # User 1 already has it (simulate previous award)
    ua1 = UserAchievement(user_id=101, achievement_id=template.id, earned_at=datetime.utcnow())
    session.add(ua1)
    session.commit()

    # Refresh and expunge to keep it usable after session close
    session.refresh(template)
    session.expunge(template)
    template_id = template.id

    session.close()

    # 2. Setup Mocks for process_event
    # We need a ConfigCache mock that returns the achievement template
    mock_cache = MagicMock(spec=ConfigCache)
    mock_cache.get_bool.return_value = False # firewall disabled
    mock_cache.get_int.return_value = 10
    mock_cache.get_active_achievements.return_value = [template]

    # Minimal dummy event for User 2
    event = SynapseEvent(
        user_id=102,
        guild_id=1,
        channel_id=999,
        event_type=InteractionType.MESSAGE,
        source_event_id="msg_UNIQUE_ID",
        metadata={},
        context={},
        timestamp=datetime.utcnow()
    )

    # 3. Simulate Logic
    # We patch check_achievements to SAY "User 2 qualifies" (returns the template ID)
    # The fix should prevent it being awarded because max_earners=1 is met by User 1.
    with patch("synapse.services.reward_service.check_achievements", return_value=[template_id]):
        # CALL THE SERVICE
        process_event(db_engine, mock_cache, event, "User2")

    # 4. Verify Result
    session = session_local()
    # Check if User 2 actually got the achievement
    ua2 = session.execute(select(UserAchievement).where(UserAchievement.user_id == 102)).scalar()

    session.close()

    # Should be None if fix works. If bug exists, this will contain data.
    assert ua2 is None, (
        "Achievement was awarded to User 2 despite max_earners=1 "
        "limit being reached!"
    )
