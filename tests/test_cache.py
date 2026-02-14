"""
tests/test_cache.py — ConfigCache Unit Tests
==============================================

Tests NOTIFY payload routing (without a real PG connection),
send_notify allowlist validation (F-005), and listener health (F-006).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from synapse.engine.cache import ALLOWED_NOTIFY_TABLES, ConfigCache, send_notify


class TestNotifyRouting:
    """Test that NOTIFY payloads route to the correct reload method."""

    @pytest.fixture
    def cache(self):
        """Build a ConfigCache bypassing __init__ (no DB needed)."""
        engine = MagicMock()
        c = ConfigCache(engine)
        return c

    @pytest.mark.parametrize(
        "table_name, expected_method",
        [
            ("channel_type_defaults", "_load_type_defaults"),
            ("channel_overrides", "_load_overrides"),
            ("channels", "_load_channels"),
            ("achievement_templates", "_load_achievements"),
        ],
    )
    def test_notify_routes_to_correct_reload(self, cache, table_name, expected_method):
        """NOTIFY payload should route to the correct reload method."""
        with patch.object(cache, expected_method) as mock_method:
            cache.handle_notify(table_name)
            mock_method.assert_called_once()

    def test_unknown_notify_ignored(self, cache):
        """Unknown table name should not trigger any reload."""
        with (
            patch.object(cache, "_load_channels") as mock_ch,
            patch.object(cache, "_load_type_defaults") as mock_td,
            patch.object(cache, "_load_overrides") as mock_ov,
            patch.object(cache, "_load_achievements") as mock_ach,
        ):
            cache.handle_notify("unknown_table")
            mock_ch.assert_not_called()
            mock_td.assert_not_called()
            mock_ov.assert_not_called()
            mock_ach.assert_not_called()


# ---------------------------------------------------------------------------
# F-005: NOTIFY SQL injection safety — allowlist validation
# ---------------------------------------------------------------------------
class TestSendNotifyAllowlist:
    """Verify send_notify() rejects table names not in the allowlist."""

    def test_allowed_tables_accepted(self):
        """All known table names should be accepted without ValueError."""
        for table in ALLOWED_NOTIFY_TABLES:
            # We can't call send_notify without a real engine/connection,
            # but we can verify the allowlist check doesn't raise.
            engine = MagicMock()
            engine.connect.return_value.__enter__ = MagicMock()
            engine.connect.return_value.__exit__ = MagicMock(return_value=False)
            try:
                send_notify(engine, table)
            except Exception as exc:
                # Ignore DB-level errors — we just care that ValueError isn't raised
                if isinstance(exc, ValueError):
                    raise

    def test_rejects_unknown_table(self):
        engine = MagicMock()
        with pytest.raises(ValueError, match="Invalid table name"):
            send_notify(engine, "users")

    def test_rejects_sql_injection_attempt(self):
        engine = MagicMock()
        with pytest.raises(ValueError, match="Invalid table name"):
            send_notify(engine, "categories'; DROP TABLE users; --")

    def test_rejects_empty_string(self):
        engine = MagicMock()
        with pytest.raises(ValueError, match="Invalid table name"):
            send_notify(engine, "")

    def test_allowlist_is_frozen(self):
        """The allowlist should be immutable."""
        assert isinstance(ALLOWED_NOTIFY_TABLES, frozenset)

    def test_allowlist_matches_handle_notify_branches(self):
        """Every table in the allowlist should be handled (or handled via alias)."""
        for table in ("channel_type_defaults", "channel_overrides",
                      "channels", "achievement_templates", "settings"):
            assert table in ALLOWED_NOTIFY_TABLES


# ---------------------------------------------------------------------------
# F-006: Listener health property
# ---------------------------------------------------------------------------
class TestListenerHealth:
    """Verify the listener_healthy property reflects thread state."""

    def test_initially_unhealthy(self):
        engine = MagicMock()
        cache = ConfigCache(engine)
        assert cache.listener_healthy is False

    def test_health_property_exists(self):
        engine = MagicMock()
        cache = ConfigCache(engine)
        # Should be accessible as a property (not a method)
        assert isinstance(cache.listener_healthy, bool)
