from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from synapse.api.deps import get_session
from synapse.api.main import app
from synapse.database.models import (
    AchievementRarity,
    AchievementTemplate,
    ActivityLog,
    User,
    UserAchievement,
)

client = TestClient(app)

@pytest.fixture
def mock_session():
    ms = MagicMock()
    app.dependency_overrides[get_session] = lambda: ms
    yield ms
    app.dependency_overrides.clear()

@pytest.fixture
def mock_jwt():
    with patch("synapse.api.routes.public.jwt.decode") as mock_decode:
        yield mock_decode

def test_activity_privacy_unauthenticated(mock_session):
    # Setup data
    user = User(id=123, discord_name="Real Name", discord_avatar_hash="hash123")
    log = ActivityLog(
        id=1,
        user_id=123,
        event_type="test",
        xp_delta=10,
        timestamp=datetime.now(UTC),
        metadata_={},
    )

    mock_session.scalars.return_value.all.return_value = [log]
    # For user loop - we use a side_effect that returns objects with an .all() method
    mock_session.scalars.side_effect = [
        MagicMock(all=lambda: [log]), # logs
        MagicMock(all=lambda: [user]) # users
    ]
    # Daily aggregation
    mock_session.execute.return_value.all.return_value = []

    response = client.get("/api/activity")

    assert response.status_code == 200
    data = response.json()
    assert len(data["events"]) == 1
    event = data["events"][0]
    assert event["user_name"] == "Anonymous Member"
    assert "Real Name" not in event["user_name"]
    assert "hash123" not in event["avatar_url"]

def test_activity_privacy_authenticated(mock_session, mock_jwt):
    # Setup data
    user = User(id=123, discord_name="Real Name", discord_avatar_hash="hash123")
    log = ActivityLog(
        id=1,
        user_id=123,
        event_type="test",
        xp_delta=10,
        timestamp=datetime.now(UTC),
        metadata_={},
    )

    # Mock JWT decode for valid user
    mock_jwt.return_value = {"sub": "999"} # Caller ID doesn't matter, just needs to be valid dict

    # Mock session side effects is tricky with multiple calls.
    # The route calls:
    # 1. session.scalars(activity_query) -> [log]
    # 2. session.execute(daily_query) -> []
    # 3. session.scalars(user_query) -> [user]

    def side_effect(*args, **kwargs):
        # Extremely simplified matching based on query string or object type
        return MagicMock(all=lambda: [log] if "ActivityLog" in str(args) else [user])

    mock_session.scalars.side_effect = [
        MagicMock(all=lambda: [log]), # logs
        MagicMock(all=lambda: [user]) # users
    ]
    mock_session.execute.return_value.all.return_value = []

    response = client.get("/api/activity", headers={"Authorization": "Bearer valid_token"})

    assert response.status_code == 200
    data = response.json()
    assert len(data["events"]) == 1
    event = data["events"][0]
    assert event["user_name"] == "Real Name"
    assert "hash123" in event["avatar_url"]

def test_recent_achievements_privacy(mock_session, mock_jwt):
    # Setup data
    user = User(id=123, discord_name="Real Name", discord_avatar_hash="hash123")
    tmpl = AchievementTemplate(id=1, name="Test Ach", rarity_id=1)
    ua = UserAchievement(user_id=123, achievement_id=1, earned_at=datetime.now(UTC))
    rarity = AchievementRarity(id=1, name="Common", color="#fff")

    # The route executes a join query returning tuples (UserAchievement, AchievementTemplate, User)
    row = (ua, tmpl, user)
    mock_session.execute.return_value.all.return_value = [row]
    # Rarities lookup
    mock_session.scalars.return_value.all.return_value = [rarity]

    # Test Unauthenticated
    response = client.get("/api/achievements/recent")

    assert response.status_code == 200
    item = response.json()["recent"][0]
    assert item["user_name"] == "Anonymous Member"
    assert "hash123" not in item["avatar_url"]

    # Test Authenticated
    mock_jwt.return_value = {"sub": "999"}
    # Reset mock iterators if needed (here side_effect not used for execute, just return_value)

    response = client.get(
        "/api/achievements/recent", headers={"Authorization": "Bearer valid_token"}
    )

    assert response.status_code == 200
    item = response.json()["recent"][0]
    assert item["user_name"] == "Real Name"
    assert "hash123" in item["avatar_url"]
