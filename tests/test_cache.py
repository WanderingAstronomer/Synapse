"""
tests/test_cache.py — ConfigCache Unit Tests
==============================================

Tests NOTIFY payload routing (without a real PG connection).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from synapse.engine.cache import ConfigCache


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
