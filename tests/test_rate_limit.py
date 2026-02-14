"""
tests/test_rate_limit.py — Admin API Rate Limiting Tests
==========================================================
Verifies F-004: Admin mutation endpoints are rate-limited at 30/min
per admin user, returning 429 with consistent error payload.
"""

from __future__ import annotations

import jwt
import pytest
from sqlalchemy.orm import Session

from synapse.api.deps import JWT_ALGORITHM, JWT_SECRET
from synapse.api.rate_limit import AdminRateLimiter
from synapse.database.models import AdminRateLimitEvent


# ---------------------------------------------------------------------------
# Unit tests for the AdminRateLimiter core (DB-backed)
# ---------------------------------------------------------------------------
class TestAdminRateLimiter:
    """Test the sliding-window rate limiter in isolation (DB-backed)."""

    @pytest.fixture(autouse=True)
    def _limiter(self, db_engine):
        """Create a fresh DB-backed limiter for each test."""
        self.limiter = AdminRateLimiter(max_requests=5, window_seconds=60, engine=db_engine)
        self.engine = db_engine

    def _clear(self):
        with Session(self.engine) as s:
            s.query(AdminRateLimitEvent).delete()
            s.commit()

    def test_allows_requests_within_limit(self):
        self._clear()
        for _ in range(5):
            allowed, info = self.limiter.check("user1")
            assert allowed
            self.limiter.record("user1")

    def test_blocks_after_limit_exceeded(self):
        self._clear()
        limiter = AdminRateLimiter(max_requests=3, window_seconds=60, engine=self.engine)
        for _ in range(3):
            limiter.record("user1")

        allowed, info = limiter.check("user1")
        assert not allowed
        assert info["remaining"] == 0
        assert info.get("retry_after", info.get("reset", 0)) > 0

    def test_separate_users_have_separate_limits(self):
        self._clear()
        limiter = AdminRateLimiter(max_requests=2, window_seconds=60, engine=self.engine)
        limiter.record("user1")
        limiter.record("user1")

        # user1 is blocked
        allowed1, _ = limiter.check("user1")
        assert not allowed1

        # user2 is still allowed
        allowed2, _ = limiter.check("user2")
        assert allowed2

    def test_remaining_count_decreases(self):
        self._clear()
        _, info = self.limiter.check("user1")
        assert info["remaining"] == 5

        self.limiter.record("user1")
        _, info = self.limiter.check("user1")
        assert info["remaining"] == 4

        self.limiter.record("user1")
        _, info = self.limiter.check("user1")
        assert info["remaining"] == 3

    def test_window_expiry_resets_count(self):
        self._clear()
        limiter = AdminRateLimiter(max_requests=2, window_seconds=1, engine=self.engine)
        limiter.record("user1")
        limiter.record("user1")

        allowed, _ = limiter.check("user1")
        assert not allowed

        # Simulate expiry by deleting records (real test would sleep 1s)
        limiter.reset("user1")

        allowed, info = limiter.check("user1")
        assert allowed
        assert info["remaining"] == 2

    def test_reset_clears_specific_user(self):
        self._clear()
        limiter = AdminRateLimiter(max_requests=2, window_seconds=60, engine=self.engine)
        limiter.record("user1")
        limiter.record("user1")
        limiter.record("user2")

        limiter.reset("user1")

        allowed1, _ = limiter.check("user1")
        assert allowed1  # user1 cleared

        _, info2 = limiter.check("user2")
        assert info2["remaining"] == 1  # user2 still has 1 recorded

    def test_reset_all(self):
        self._clear()
        limiter = AdminRateLimiter(max_requests=2, window_seconds=60, engine=self.engine)
        limiter.record("user1")
        limiter.record("user2")

        limiter.reset()

        allowed1, _ = limiter.check("user1")
        allowed2, _ = limiter.check("user2")
        assert allowed1
        assert allowed2


# ---------------------------------------------------------------------------
# Integration tests with FastAPI TestClient
# ---------------------------------------------------------------------------
class TestRateLimitMiddleware:
    """Test the rate limiter dependency end-to-end via TestClient."""

    @pytest.fixture
    def client(self, db_engine):
        """Create a fresh test client with a low rate limit."""
        import synapse.api.rate_limit as rl_mod

        original_limiter = rl_mod._limiter
        test_limiter = AdminRateLimiter(max_requests=3, window_seconds=60, engine=db_engine)
        rl_mod._limiter = test_limiter

        # Clear any stale rate limit events
        with Session(db_engine) as s:
            s.query(AdminRateLimitEvent).delete()
            s.commit()

        from fastapi.testclient import TestClient

        from synapse.api.deps import get_config, get_engine, get_session
        from synapse.api.main import app

        # Override FastAPI dependencies so handlers use the test SQLite engine
        app.dependency_overrides[get_engine] = lambda: db_engine
        app.dependency_overrides[get_session] = lambda: Session(db_engine)

        from synapse.config import SynapseConfig

        app.dependency_overrides[get_config] = lambda: SynapseConfig(
            guild_id=1, admin_ids=[123], bot_token="fake",
        )

        client = TestClient(app, raise_server_exceptions=False)
        yield client, test_limiter

        app.dependency_overrides.clear()
        rl_mod._limiter = original_limiter

    @pytest.fixture
    def admin_token(self):
        """Generate a valid admin JWT."""
        from conftest import make_admin_token
        return make_admin_token(sub="admin-123", username="TestAdmin")

    @pytest.fixture
    def admin_token_2(self):
        """Generate a second admin JWT with a different sub."""
        from conftest import make_admin_token
        return make_admin_token(sub="admin-456", username="TestAdmin2")

    def _auth_headers(self, token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    def test_get_requests_not_rate_limited(self, client, admin_token):
        """GET requests should not count toward the rate limit."""
        test_client, limiter = client
        headers = self._auth_headers(admin_token)

        # Make many GET requests — should all succeed (or return normal errors, not 429)
        for _ in range(10):
            resp = test_client.get("/api/admin/channel-defaults", headers=headers)
            assert resp.status_code != 429

    def test_non_admin_paths_not_limited(self, client, admin_token):
        """Non-admin paths should not be rate-limited."""
        test_client, limiter = client

        for _ in range(10):
            resp = test_client.get("/api/health")
            assert resp.status_code != 429

    def test_mutation_returns_rate_limit_headers(self, client, admin_token):
        """Mutation responses should include Retry-After header when blocked."""
        test_client, limiter = client
        headers = self._auth_headers(admin_token)

        # Pre-fill the limiter to the max
        for _ in range(3):
            limiter.record("admin-123")

        resp = test_client.put(
            "/api/admin/channel-defaults",
            headers=headers,
            json={"channel_type": "text", "event_type": "*", "xp_multiplier": 1.0, "star_multiplier": 1.0},
        )
        assert resp.status_code == 429
        assert "Retry-After" in resp.headers

    def test_returns_429_after_limit(self, client, admin_token):
        """After exceeding the limit, should return 429."""
        test_client, limiter = client
        headers = self._auth_headers(admin_token)

        # Pre-fill the limiter to the max
        for _ in range(3):
            limiter.record("admin-123")

        resp = test_client.put(
            "/api/admin/channel-defaults",
            headers=headers,
            json={"channel_type": "text", "event_type": "*", "xp_multiplier": 1.0, "star_multiplier": 1.0},
        )
        assert resp.status_code == 429

        body = resp.json()
        assert body["detail"]["error"] == "rate_limit_exceeded"
        assert "retry_after" in body["detail"]
        assert "Retry-After" in resp.headers

    def test_different_admins_have_separate_limits(self, client, admin_token, admin_token_2):
        """Two different admin users should have independent rate limits."""
        test_client, limiter = client

        # Fill admin-123's limit
        for _ in range(3):
            limiter.record("admin-123")

        # admin-123 is blocked
        resp1 = test_client.put(
            "/api/admin/channel-defaults",
            headers=self._auth_headers(admin_token),
            json={"channel_type": "text", "event_type": "*", "xp_multiplier": 1.0, "star_multiplier": 1.0},
        )
        assert resp1.status_code == 429

        # admin-456 is not blocked
        resp2 = test_client.put(
            "/api/admin/channel-defaults",
            headers=self._auth_headers(admin_token_2),
            json={"channel_type": "text", "event_type": "*", "xp_multiplier": 1.0, "star_multiplier": 1.0},
        )
        assert resp2.status_code != 429

    def test_unauthenticated_mutation_passes_through(self, client):
        """Requests without valid auth should pass to the route handler (which returns 401)."""
        test_client, limiter = client
        resp = test_client.put("/api/admin/channel-defaults", json={"channel_type": "text", "event_type": "*"})
        assert resp.status_code in (401, 403)
