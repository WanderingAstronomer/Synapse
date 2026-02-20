from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from synapse.api.deps import get_member_context, get_session
from synapse.api.main import app
from synapse.database.models import (
    ActivityLog,
    User,
    UserProfile,
)

client = TestClient(app)

@pytest.fixture
def mock_session():
    ms = MagicMock()
    app.dependency_overrides[get_session] = lambda: ms
    yield ms
    app.dependency_overrides.clear()

@pytest.fixture
def member_auth():
    """Overrides get_member_context to simulate a logged-in member."""
    mock_ctx = {
        "sub": "123",
        "username": "Test User",
        "avatar_url": "http://cdn/123",
        "roles": [],
        "is_admin": False
    }
    app.dependency_overrides[get_member_context] = lambda: mock_ctx
    yield mock_ctx
    app.dependency_overrides.pop(get_member_context, None)

def test_get_member_profile(mock_session, member_auth):
    # Setup data
    user = User(
        id=123,
        discord_name="Test User",
        discord_avatar_hash="hash123",
        xp=1000,
        level=5,
        gold=50,
        created_at=datetime.now(UTC)
    )
    profile = UserProfile(
        discord_id=123,
        guild_id=1,
        username="Test User",
        avatar_url="http://cdn/123"
    )

    # Mock calls in order:
    # 1. session.get(User, 123)
    # 2. session.get(UserProfile, 123)

    def side_effect_get(model, pk):
        if model == User and pk == 123:
            return user
        if model == UserProfile and pk == 123:
            return profile
        return None
    mock_session.get.side_effect = side_effect_get

    # 3. Rank queries: session.execute(...).scalar_one_or_none()
    # Called twice: XP rank, Gold rank
    mock_rank_xp = MagicMock()
    mock_rank_xp.scalar_one_or_none.return_value = 10

    mock_rank_gold = MagicMock()
    mock_rank_gold.scalar_one_or_none.return_value = 5

    # Configure execute side effect
    # The first two executes are for ranks
    # Achievement/total counts use session.scalar, not session.execute.

    # wait, session.scalar(stmt) -> session.execute(stmt).scalar()
    # If session.execute is mocked, session.scalar might depend on it in some implementations.
    # But usually MagicMock mocks scalar separately if accessed as attribute.
    # In my previous analysis, session.scalar() calls were separate.

    # Let's set execute side_effect for the 2 explicit execute calls
    # And scalar side_effect for the 2 explicit scalar calls
    mock_session.execute.side_effect = [mock_rank_xp, mock_rank_gold]
    mock_session.scalar.side_effect = [2, 100]

    response = client.get("/api/member/profile")
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["user"]["id"] == "123"
    assert data["user"]["xp"] == 1000
    assert data["ranks"]["xp"] == 10
    assert data["achievement_count"] == 2

def test_get_member_activity_with_why_trace(mock_session, member_auth):
    # Use fixed timestamp for reliable matching
    # Needs to match formatting in code: %Y-%m-%dT%H:%M
    ts = datetime(2023, 10, 27, 12, 0, 0, tzinfo=UTC)

    log = ActivityLog(
        id=1,
        user_id=123,
        event_type="MESSAGE_CREATE",
        xp_delta=10,
        star_delta=1,
        metadata_={"content": "hello"},
        timestamp=ts,
        rule_evaluation_id=555
    )

    # Matching evaluation
    # Code matches on key = ev.evaluated_at.strftime("%Y-%m-%dT%H:%M")
    eval_rec = MagicMock()
    eval_rec.matched_rules = [{"id": 10, "name": "Test Rule"}]
    eval_rec.outcomes_applied = {"xp": 10}
    eval_rec.context_snapshot = {}
    eval_rec.evaluated_at = ts

    # logs = session.scalars(ActivityLog...).all()
    # evals = session.execute(RuleEvaluation...).scalars().all()

    # mock logs
    mock_logs_scalar = MagicMock()
    mock_logs_scalar.all.return_value = [log]

    # mock evals
    mock_evals_scalar = MagicMock()
    mock_evals_scalar.all.return_value = [eval_rec]
    mock_evals_execute = MagicMock()
    mock_evals_execute.scalars.return_value = mock_evals_scalar

    # session.scalars(logs) is called FIRST.
    mock_session.scalars.side_effect = [mock_logs_scalar]

    # session.execute(evals) is called SECOND.
    mock_session.execute.side_effect = [mock_evals_execute]

    response = client.get("/api/member/activity")
    assert response.status_code == 200, response.text
    data = response.json()

    # Should be wrapped in "events"
    assert "events" in data
    assert len(data["events"]) == 1
    event = data["events"][0]

    assert event["xp_delta"] == 10

    # Check trace
    trace = event["why_trace"]
    assert trace is not None
    assert trace["matched_rules"][0]["id"] == 10

def test_get_member_achievements(mock_session, member_auth):
    # Setup data
    tmpl = MagicMock()
    tmpl.id = 1
    tmpl.name = "First Post"
    tmpl.description = "Post once"
    tmpl.category_id = 1
    tmpl.rarity_id = 1
    tmpl.xp_reward = 10
    tmpl.gold_reward = 5
    tmpl.badge_image = "img"
    tmpl.series_id = None
    tmpl.series_order = 1

    ua = MagicMock()
    ua.user_id = 123
    ua.achievement_id = 1
    ua.earned_at = datetime.now(UTC)

    cat = MagicMock()
    cat.id = 1
    cat.name = "General"

    rarity = MagicMock()
    rarity.id = 1
    rarity.name = "Common"
    rarity.color = "#fff"

    # 1. rows = session.execute(join query).all()
    mock_main_result = MagicMock()
    mock_main_result.all.return_value = [(ua, tmpl)]
    mock_session.execute.return_value = mock_main_result

    # 2. categories = session.scalars(Category).all()
    mock_cat_scalars = MagicMock()
    mock_cat_scalars.all.return_value = [cat]

    # 3. rarities = session.scalars(Rarity).all()
    mock_rarity_scalars = MagicMock()
    mock_rarity_scalars.all.return_value = [rarity]

    mock_session.scalars.side_effect = [mock_cat_scalars, mock_rarity_scalars]

    response = client.get("/api/member/achievements")
    assert response.status_code == 200, response.text
    data = response.json()

    assert "achievements" in data
    assert len(data["achievements"]) == 1
    ach = data["achievements"][0]
    assert ach["name"] == "First Post"
    assert ach["category"] == "General"

def test_leaderboard_anonymity_unauth(mock_session):
    # Ensure NO auth override
    app.dependency_overrides.pop(get_member_context, None)

    # Setup data
    u1 = User(id=1, discord_name="Public Name", discord_avatar_hash="h1", xp=100, level=2, gold=10)
    u2 = User(id=2, discord_name="Private User", xp=50, level=1, gold=5)

    # Mock:
    # 1. total = session.scalar()
    # 2. rows = session.scalars(User...).all()

    mock_session.scalar.return_value = 2 # total

    mock_users_result = MagicMock()
    mock_users_result.all.return_value = [u1, u2]
    mock_session.scalars.return_value = mock_users_result

    # Using public route
    response = client.get("/api/leaderboard/xp")
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["authenticated"] is False
    assert len(data["users"]) == 2

    # Verify anonymity
    user_item = data["users"][0]
    assert "discord_name" not in user_item
    assert "username" not in user_item
    assert user_item["xp"] == 100
    assert user_item["rank"] == 1
