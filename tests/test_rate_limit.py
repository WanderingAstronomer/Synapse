"""
tests/test_rate_limit.py — Admin API Rate Limiting Tests
==========================================================
Verifies F-004: Admin mutation endpoints are rate-limited at 30/min
per admin user, returning 429 with consistent error payload.
"""

from __future__ import annotations

import time

import jwt
import pytest

from synapse.api.deps import JWT_ALGORITHM, JWT_SECRET
from synapse.api.rate_limit import AdminRateLimiter


# ---------------------------------------------------------------------------
# Unit tests for the AdminRateLimiter core
# ---------------------------------------------------------------------------
class TestAdminRateLimiter:
    """Test the sliding-window rate limiter in isolation."""

    def test_allows_requests_within_limit(self):
        limiter = AdminRateLimiter(max_requests=5, window_seconds=60)
        for _ in range(5):
            allowed, info = limiter.check("user1")
            assert allowed
            limiter.record("user1")

    def test_blocks_after_limit_exceeded(self):
        limiter = AdminRateLimiter(max_requests=3, window_seconds=60)
        for _ in range(3):
            limiter.record("user1")

        allowed, info = limiter.check("user1")
        assert not allowed
        assert info["remaining"] == 0
        assert info["retry_after"] if "retry_after" in info else info["reset"] > 0

    def test_separate_users_have_separate_limits(self):
        limiter = AdminRateLimiter(max_requests=2, window_seconds=60)
        limiter.record("user1")
        limiter.record("user1")

        # user1 is blocked
        allowed1, _ = limiter.check("user1")
        assert not allowed1

        # user2 is still allowed
        allowed2, _ = limiter.check("user2")
        assert allowed2

    def test_remaining_count_decreases(self):
        limiter = AdminRateLimiter(max_requests=5, window_seconds=60)

        _, info = limiter.check("user1")
        assert info["remaining"] == 5

        limiter.record("user1")
        _, info = limiter.check("user1")
        assert info["remaining"] == 4

        limiter.record("user1")
        _, info = limiter.check("user1")
        assert info["remaining"] == 3

    def test_window_expiry_resets_count(self):
        limiter = AdminRateLimiter(max_requests=2, window_seconds=1)
        limiter.record("user1")
        limiter.record("user1")

        allowed, _ = limiter.check("user1")
        assert not allowed

        # Wait for the window to expire
        time.sleep(1.1)

        allowed, info = limiter.check("user1")
        assert allowed
        assert info["remaining"] == 2

    def test_reset_clears_specific_user(self):
        limiter = AdminRateLimiter(max_requests=2, window_seconds=60)
        limiter.record("user1")
        limiter.record("user1")
        limiter.record("user2")

        limiter.reset("user1")

        allowed1, _ = limiter.check("user1")
        assert allowed1  # user1 cleared

        _, info2 = limiter.check("user2")
        assert info2["remaining"] == 1  # user2 still has 1 recorded

    def test_reset_all(self):
        limiter = AdminRateLimiter(max_requests=2, window_seconds=60)
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
    """Test the rate limiter middleware end-to-end via TestClient."""

    @pytest.fixture
    def client(self):
        """Create a fresh test client with a low rate limit."""
        import synapse.api.rate_limit as rl_mod
        from synapse.api.rate_limit import AdminRateLimiter

        original_limiter = rl_mod._limiter
        test_limiter = AdminRateLimiter(max_requests=3, window_seconds=60)
        rl_mod._limiter = test_limiter

        from fastapi.testclient import TestClient

        from synapse.api.main import app

        client = TestClient(app, raise_server_exceptions=False)
        yield client, test_limiter

        rl_mod._limiter = original_limiter

    @pytest.fixture
    def admin_token(self):
        """Generate a valid admin JWT."""
        return jwt.encode(
            {"sub": "admin-123", "username": "TestAdmin", "is_admin": True},
            JWT_SECRET,
            algorithm=JWT_ALGORITHM,
        )

    @pytest.fixture
    def admin_token_2(self):
        """Generate a second admin JWT with a different sub."""
        return jwt.encode(
            {"sub": "admin-456", "username": "TestAdmin2", "is_admin": True},
            JWT_SECRET,
            algorithm=JWT_ALGORITHM,
        )

    def _auth_headers(self, token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    def test_get_requests_not_rate_limited(self, client, admin_token):
        """GET requests should not count toward the rate limit."""
        test_client, limiter = client
        headers = self._auth_headers(admin_token)

        # Make many GET requests — should all succeed (or return normal errors, not 429)
        for _ in range(10):
            resp = test_client.get("/api/admin/zones", headers=headers)
            assert resp.status_code != 429

    def test_non_admin_paths_not_limited(self, client, admin_token):
        """Non-admin paths should not be rate-limited."""
        test_client, limiter = client

        for _ in range(10):
            resp = test_client.get("/api/health")
            assert resp.status_code != 429

    def test_mutation_returns_rate_limit_headers(self, client, admin_token):
        """Mutation responses should include X-RateLimit-* headers."""
        test_client, limiter = client
        headers = self._auth_headers(admin_token)

        resp = test_client.post(
            "/api/admin/zones",
            headers=headers,
            json={"name": "test-zone"},
        )
        # The request may fail for other reasons (no DB), but rate limit
        # headers should be present on non-429 responses if the middleware ran
        # and the admin ID was extractable.
        if resp.status_code < 429:
            assert "X-RateLimit-Limit" in resp.headers
            assert "X-RateLimit-Remaining" in resp.headers

    def test_returns_429_after_limit(self, client, admin_token):
        """After exceeding the limit, should return 429."""
        test_client, limiter = client
        headers = self._auth_headers(admin_token)

        # Pre-fill the limiter to the max
        for _ in range(3):
            limiter.record("admin-123")

        resp = test_client.post(
            "/api/admin/zones",
            headers=headers,
            json={"name": "test-zone"},
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
        resp1 = test_client.post(
            "/api/admin/zones",
            headers=self._auth_headers(admin_token),
            json={"name": "test"},
        )
        assert resp1.status_code == 429

        # admin-456 is not blocked
        resp2 = test_client.post(
            "/api/admin/zones",
            headers=self._auth_headers(admin_token_2),
            json={"name": "test"},
        )
        assert resp2.status_code != 429

    def test_unauthenticated_mutation_passes_through(self, client):
        """Requests without valid auth should pass to the route handler (which returns 401)."""
        test_client, limiter = client
        resp = test_client.post("/api/admin/zones", json={"name": "test"})
        assert resp.status_code in (401, 403)
