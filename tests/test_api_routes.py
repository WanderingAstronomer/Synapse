"""
tests/test_api_routes.py — FastAPI Route Integration Tests
============================================================
Covers F-009: Integration tests for critical public and admin API routes
using the FastAPI TestClient.

These tests verify:
- Auth guards on admin endpoints
- Basic response structure of public endpoints
- Health endpoint availability
"""

from __future__ import annotations

import jwt
import pytest
from fastapi.testclient import TestClient

from synapse.api.deps import JWT_ALGORITHM, JWT_SECRET


@pytest.fixture
def client():
    """Create a FastAPI TestClient."""
    from synapse.api.main import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def admin_token():
    return jwt.encode(
        {"sub": "12345", "username": "TestAdmin", "is_admin": True},
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )


@pytest.fixture
def non_admin_token():
    return jwt.encode(
        {"sub": "67890", "username": "RegularUser", "is_admin": False},
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ===========================================================================
# Health endpoint
# ===========================================================================
class TestHealthEndpoint:
    def test_health_returns_ok(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


# ===========================================================================
# Auth guards — admin endpoints should reject unauthenticated/non-admin users
# ===========================================================================
class TestAdminAuthGuards:
    """All admin endpoints must return 401/403 for missing/invalid/non-admin tokens."""

    ADMIN_GET_ENDPOINTS = [
        "/api/admin/zones",
        "/api/admin/achievements",
        "/api/admin/settings",
        "/api/admin/audit",
        "/api/admin/setup/status",
    ]

    ADMIN_POST_ENDPOINTS = [
        "/api/admin/zones",
        "/api/admin/achievements",
    ]

    @pytest.mark.parametrize("endpoint", ADMIN_GET_ENDPOINTS)
    def test_get_rejects_no_auth(self, client, endpoint):
        resp = client.get(endpoint)
        assert resp.status_code in (401, 403)

    @pytest.mark.parametrize("endpoint", ADMIN_POST_ENDPOINTS)
    def test_post_rejects_no_auth(self, client, endpoint):
        resp = client.post(endpoint, json={})
        assert resp.status_code in (401, 403, 422)

    @pytest.mark.parametrize("endpoint", ADMIN_GET_ENDPOINTS)
    def test_get_rejects_invalid_token(self, client, endpoint):
        resp = client.get(endpoint, headers={"Authorization": "Bearer invalid"})
        assert resp.status_code == 401

    @pytest.mark.parametrize("endpoint", ADMIN_GET_ENDPOINTS)
    def test_get_rejects_non_admin(self, client, non_admin_token, endpoint):
        resp = client.get(endpoint, headers=_auth(non_admin_token))
        assert resp.status_code == 403


# ===========================================================================
# Public endpoints — should not require auth
# ===========================================================================
class TestPublicEndpoints:
    """Public endpoints should be accessible without auth.

    Note: These will fail to produce data without a real DB, but should
    return a proper HTTP status (not 401/500 from auth failures).
    """

    def test_health_no_auth(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200

    def test_public_settings_responds(self, client):
        """Public settings should be accessible (may return 500 w/o DB, not 401)."""
        resp = client.get("/api/settings/public")
        # Without a real DB, the endpoint might fail, but it should NOT be 401/403.
        assert resp.status_code != 401
        assert resp.status_code != 403

    def test_achievements_public_responds(self, client):
        resp = client.get("/api/achievements")
        assert resp.status_code != 401
        assert resp.status_code != 403

    def test_leaderboard_responds(self, client):
        resp = client.get("/api/leaderboard/xp")
        assert resp.status_code != 401
        assert resp.status_code != 403


# ===========================================================================
# Auth /me endpoint
# ===========================================================================
class TestAuthMe:
    def test_me_returns_admin_info(self, client, admin_token):
        resp = client.get("/api/auth/me", headers=_auth(admin_token))
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == "12345"
        assert body["username"] == "TestAdmin"
        assert body["is_admin"] is True

    def test_me_rejects_no_auth(self, client):
        resp = client.get("/api/auth/me")
        assert resp.status_code == 401

    def test_me_rejects_non_admin(self, client, non_admin_token):
        resp = client.get("/api/auth/me", headers=_auth(non_admin_token))
        assert resp.status_code == 403
