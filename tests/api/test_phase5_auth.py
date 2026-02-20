"""
tests.test_phase5_auth — Phase 5: Three-Tier Authentication Tests
==================================================================

Tests profile_service, auth._read_bool_setting, and dep guards:
- upsert_profile: INSERT / UPDATE paths
- anonymize_on_leave: anonymization + no-op when missing
- sync_member_roles: atomic role replacement
- _check_member_sync: membership lookup logic
- get_member_context: JWT decode + membership gate
- get_admin_context: JWT decode + is_admin gate

No real database, no Discord, no Docker required.
"""

from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import jwt
import pytest

from synapse.api.deps import (
    _MEMBER_CACHE_TTL,
    JWT_ALGORITHM,
    JWT_SECRET,
    _check_member_sync,
    _member_cache,
    get_admin_context,
    get_member_context,
)
from synapse.services.profile_service import (
    anonymize_on_leave,
    sync_member_roles,
    upsert_profile,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_token(sub: str = "42", is_admin: bool = False, **extra) -> str:
    payload = {"sub": sub, "is_admin": is_admin, **extra}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _auth(token: str) -> str:
    return f"Bearer {token}"


# ---------------------------------------------------------------------------
# upsert_profile
# ---------------------------------------------------------------------------


class TestUpsertProfile:
    def _mock_session(self, existing=None):
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_session.get.return_value = existing
        return mock_session

    def test_creates_new_profile_when_absent(self):
        mock_engine = MagicMock()
        session = self._mock_session(existing=None)

        with patch("synapse.services.profile_service.Session", return_value=session):
            upsert_profile(mock_engine, 1001, 9999, "alice", "https://cdn/alice.png")

        session.add.assert_called_once()
        added = session.add.call_args[0][0]
        assert added.discord_id == 1001
        assert added.guild_id == 9999
        assert added.username == "alice"
        assert added.avatar_url == "https://cdn/alice.png"
        assert added.left_at is None
        session.commit.assert_called_once()

    def test_updates_existing_profile(self):
        mock_engine = MagicMock()
        existing = SimpleNamespace(
            discord_id=1001,
            guild_id=9999,
            username="old_alice",
            avatar_url="https://old",
            last_seen=None,
            left_at=None,
        )
        session = self._mock_session(existing=existing)

        with patch("synapse.services.profile_service.Session", return_value=session):
            upsert_profile(mock_engine, 1001, 9999, "new_alice", "https://new")

        assert existing.username == "new_alice"
        assert existing.avatar_url == "https://new"
        assert existing.last_seen is not None
        session.add.assert_not_called()
        session.commit.assert_called_once()

    def test_clears_left_at_on_active_upsert(self):
        """An upsert on an active event should clear a stale left_at."""
        from datetime import UTC, datetime, timedelta

        mock_engine = MagicMock()
        existing = SimpleNamespace(
            discord_id=1001,
            guild_id=9999,
            username="alice",
            avatar_url=None,
            last_seen=None,
            left_at=datetime.now(UTC) - timedelta(days=7),
        )
        session = self._mock_session(existing=existing)

        with patch("synapse.services.profile_service.Session", return_value=session):
            upsert_profile(mock_engine, 1001, 9999, "alice", None)

        assert existing.left_at is None

    def test_avatar_url_may_be_none(self):
        mock_engine = MagicMock()
        session = self._mock_session(existing=None)

        with patch("synapse.services.profile_service.Session", return_value=session):
            upsert_profile(mock_engine, 1002, 9999, "bob", None)

        added = session.add.call_args[0][0]
        assert added.avatar_url is None


# ---------------------------------------------------------------------------
# anonymize_on_leave
# ---------------------------------------------------------------------------


class TestAnonymizeOnLeave:
    def _mock_session(self, existing=None):
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_session.get.return_value = existing
        return mock_session

    def test_anonymizes_existing_profile(self):
        mock_engine = MagicMock()
        profile = SimpleNamespace(
            discord_id=1001,
            guild_id=9999,
            username="alice",
            avatar_url="https://cdn/alice.png",
            left_at=None,
        )
        session = self._mock_session(existing=profile)

        with patch("synapse.services.profile_service.Session", return_value=session):
            anonymize_on_leave(mock_engine, 1001, 9999)

        assert profile.username == "Former Member"
        assert profile.avatar_url is None
        assert profile.left_at is not None
        session.commit.assert_called_once()

    def test_noop_when_no_profile(self):
        """anonymize_on_leave is a no-op when the user has no profile row."""
        mock_engine = MagicMock()
        session = self._mock_session(existing=None)

        with patch("synapse.services.profile_service.Session", return_value=session):
            anonymize_on_leave(mock_engine, 9999, 9999)  # unknown user

        session.commit.assert_not_called()

    def test_deletes_roles(self):
        """anonymize_on_leave must execute a DELETE on user_guild_roles."""
        mock_engine = MagicMock()
        profile = SimpleNamespace(
            discord_id=1001,
            guild_id=9999,
            username="alice",
            avatar_url=None,
            left_at=None,
        )
        session = self._mock_session(existing=profile)

        with patch("synapse.services.profile_service.Session", return_value=session):
            anonymize_on_leave(mock_engine, 1001, 9999)

        session.execute.assert_called_once()


# ---------------------------------------------------------------------------
# sync_member_roles
# ---------------------------------------------------------------------------


class TestSyncMemberRoles:
    def _mock_session(self):
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        return mock_session

    def test_deletes_old_roles_and_inserts_new(self):
        mock_engine = MagicMock()
        session = self._mock_session()

        with patch("synapse.services.profile_service.Session", return_value=session):
            sync_member_roles(mock_engine, 1001, 9999, [(111, "Member"), (222, "VIP")])

        # DELETE executed once
        session.execute.assert_called_once()
        # Two new role rows added
        assert session.add.call_count == 2
        session.commit.assert_called_once()

    def test_empty_roles_clears_all(self):
        mock_engine = MagicMock()
        session = self._mock_session()

        with patch("synapse.services.profile_service.Session", return_value=session):
            sync_member_roles(mock_engine, 1001, 9999, [])

        session.execute.assert_called_once()  # DELETE still runs
        session.add.assert_not_called()
        session.commit.assert_called_once()


# ---------------------------------------------------------------------------
# _check_member_sync
# ---------------------------------------------------------------------------


class TestCheckMemberSync:
    def test_active_member_returns_true(self):
        engine = MagicMock()
        profile = SimpleNamespace(discord_id=42, left_at=None)
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_session.get.return_value = profile

        with patch("synapse.api.deps.Session", return_value=mock_session):
            result = _check_member_sync(engine, 42)

        assert result is True

    def test_former_member_returns_false(self):
        from datetime import UTC, datetime

        engine = MagicMock()
        profile = SimpleNamespace(discord_id=42, left_at=datetime.now(UTC))
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_session.get.return_value = profile

        with patch("synapse.api.deps.Session", return_value=mock_session):
            result = _check_member_sync(engine, 42)

        assert result is False

    def test_unknown_user_returns_false(self):
        engine = MagicMock()
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_session.get.return_value = None

        with patch("synapse.api.deps.Session", return_value=mock_session):
            result = _check_member_sync(engine, 999)

        assert result is False


# ---------------------------------------------------------------------------
# get_member_context
# ---------------------------------------------------------------------------


class TestGetMemberContext:
    def setup_method(self):
        _member_cache.clear()

    def _active_engine(self):
        engine = MagicMock()
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_session.get.return_value = SimpleNamespace(discord_id=42, left_at=None)
        with patch("synapse.api.deps.Session", return_value=mock_session):
            engine._mock_session = mock_session
        return engine

    def test_valid_token_active_member_succeeds(self):
        _member_cache.clear()
        token = _make_token(sub="42")
        engine = MagicMock()

        with patch("synapse.api.deps._check_member_sync", return_value=True):
            payload = get_member_context(_auth(token), engine)

        assert payload["sub"] == "42"

    def test_missing_token_raises_401(self):
        from fastapi import HTTPException

        engine = MagicMock()
        with pytest.raises(HTTPException) as exc:
            get_member_context(None, engine)
        assert exc.value.status_code == 401

    def test_invalid_token_raises_401(self):
        from fastapi import HTTPException

        engine = MagicMock()
        with pytest.raises(HTTPException) as exc:
            get_member_context("Bearer invalid.jwt.value", engine)
        assert exc.value.status_code == 401

    def test_former_member_raises_403(self):
        from fastapi import HTTPException

        _member_cache.clear()
        token = _make_token(sub="77")
        engine = MagicMock()

        with patch("synapse.api.deps._check_member_sync", return_value=False):
            with pytest.raises(HTTPException) as exc:
                get_member_context(_auth(token), engine)
        assert exc.value.status_code == 403

    def test_cache_hit_skips_db(self):
        """A cache-warm result must not call _check_member_sync again."""
        _member_cache.clear()
        token = _make_token(sub="55")
        engine = MagicMock()

        # Prime the cache
        _member_cache[55] = (True, time.monotonic() + _MEMBER_CACHE_TTL)

        with patch(
            "synapse.api.deps._check_member_sync", side_effect=AssertionError("should not call DB")
        ):
            payload = get_member_context(_auth(token), engine)

        assert payload["sub"] == "55"

    def test_expired_cache_entry_triggers_db(self):
        """An expired cache entry must re-query the DB."""
        _member_cache.clear()
        token = _make_token(sub="66")
        engine = MagicMock()

        # Plant an expired entry
        _member_cache[66] = (True, time.monotonic() - 1)

        with patch("synapse.api.deps._check_member_sync", return_value=True) as mock_check:
            get_member_context(_auth(token), engine)

        mock_check.assert_called_once()


# ---------------------------------------------------------------------------
# get_admin_context
# ---------------------------------------------------------------------------


class TestGetAdminContext:
    def test_valid_admin_token_succeeds(self):
        token = _make_token(sub="99", is_admin=True)
        payload = get_admin_context(_auth(token))
        assert payload["is_admin"] is True
        assert payload["sub"] == "99"

    def test_non_admin_token_raises_403(self):
        from fastapi import HTTPException

        token = _make_token(sub="88", is_admin=False)
        with pytest.raises(HTTPException) as exc:
            get_admin_context(_auth(token))
        assert exc.value.status_code == 403

    def test_missing_token_raises_401(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            get_admin_context(None)
        assert exc.value.status_code == 401

    def test_invalid_token_raises_401(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            get_admin_context("Bearer garbage")
        assert exc.value.status_code == 401
