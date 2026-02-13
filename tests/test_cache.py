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

    @patch.object(ConfigCache, "_load_zones")
    @patch.object(ConfigCache, "_load_multipliers")
    @patch.object(ConfigCache, "_load_achievements")
    def test_zones_notify(self, mock_ach, mock_mult, mock_zones):
        """NOTIFY payload 'zones' should reload zones."""
        engine = MagicMock()
        cache = ConfigCache.__new__(ConfigCache)
        cache._engine = engine
        cache._zones = {}
        cache._channel_zone_map = {}
        cache._multipliers = {}
        cache._achievements = []
        cache._lock = __import__("threading").Lock()

        cache.handle_notify("zones")
        mock_zones.assert_called_once()

    @patch.object(ConfigCache, "_load_zones")
    @patch.object(ConfigCache, "_load_multipliers")
    @patch.object(ConfigCache, "_load_achievements")
    def test_multipliers_notify(self, mock_ach, mock_mult, mock_zones):
        """NOTIFY payload 'zone_multipliers' should reload multipliers."""
        engine = MagicMock()
        cache = ConfigCache.__new__(ConfigCache)
        cache._engine = engine
        cache._zones = {}
        cache._channel_zone_map = {}
        cache._multipliers = {}
        cache._achievements = []
        cache._lock = __import__("threading").Lock()

        cache.handle_notify("zone_multipliers")
        mock_mult.assert_called_once()

    @patch.object(ConfigCache, "_load_zones")
    @patch.object(ConfigCache, "_load_multipliers")
    @patch.object(ConfigCache, "_load_achievements")
    def test_achievements_notify(self, mock_ach, mock_mult, mock_zones):
        """NOTIFY payload 'achievement_templates' should reload achievements."""
        engine = MagicMock()
        cache = ConfigCache.__new__(ConfigCache)
        cache._engine = engine
        cache._zones = {}
        cache._channel_zone_map = {}
        cache._multipliers = {}
        cache._achievements = []
        cache._lock = __import__("threading").Lock()

        cache.handle_notify("achievement_templates")
        mock_ach.assert_called_once()

    @patch.object(ConfigCache, "_load_zones")
    @patch.object(ConfigCache, "_load_multipliers")
    @patch.object(ConfigCache, "_load_achievements")
    def test_unknown_notify_ignored(self, mock_ach, mock_mult, mock_zones):
        """Unknown table name should not trigger any reload."""
        engine = MagicMock()
        cache = ConfigCache.__new__(ConfigCache)
        cache._engine = engine
        cache._zones = {}
        cache._channel_zone_map = {}
        cache._multipliers = {}
        cache._achievements = []
        cache._lock = __import__("threading").Lock()

        cache.handle_notify("unknown_table")
        mock_zones.assert_not_called()
        mock_mult.assert_not_called()
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
            send_notify(engine, "zones'; DROP TABLE users; --")

    def test_rejects_empty_string(self):
        engine = MagicMock()
        with pytest.raises(ValueError, match="Invalid table name"):
            send_notify(engine, "")

    def test_allowlist_is_frozen(self):
        """The allowlist should be immutable."""
        assert isinstance(ALLOWED_NOTIFY_TABLES, frozenset)

    def test_allowlist_matches_handle_notify_branches(self):
        """Every table in the allowlist should be handled (or handled via alias)."""
        # All tables referenced in handle_notify should be in the allowlist
        for table in ("zones", "zone_channels", "zone_multipliers",
                      "achievement_templates", "settings"):
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
