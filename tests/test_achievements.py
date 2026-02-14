"""
tests/test_achievements.py — Unit Tests for Achievement Check Pipeline v2
==========================================================================

Tests the handler-registry achievement engine with AchievementContext,
trigger types, trigger configs, and series gating.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from synapse.database.models import TriggerType
from synapse.engine.achievements import AchievementContext, check_achievements


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _tmpl(
    id: int,
    trigger_type: str,
    trigger_config: dict | None = None,
    *,
    guild_id: int = 100,
    active: bool = True,
    series_id: int | None = None,
    series_order: int | None = None,
    name: str | None = None,
) -> MagicMock:
    """Create a mock AchievementTemplate with v2 schema."""
    t = MagicMock()
    t.id = id
    t.guild_id = guild_id
    t.active = active
    t.trigger_type = trigger_type
    t.trigger_config = trigger_config or {}
    t.series_id = series_id
    t.series_order = series_order
    t.name = name or f"achievement_{id}"
    return t


def _ctx(**kwargs) -> AchievementContext:
    """Build an AchievementContext with sensible defaults."""
    return AchievementContext(**kwargs)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def mock_cache():
    """Cache returning sample achievement templates."""
    cache = MagicMock()

    templates = [
        _tmpl(1, TriggerType.XP_MILESTONE, {"value": 100}),
        _tmpl(2, TriggerType.STAR_MILESTONE, {"scope": "season", "value": 50}),
        _tmpl(3, TriggerType.STAT_THRESHOLD, {"field": "messages_sent", "value": 100}),
        _tmpl(4, TriggerType.MANUAL),  # Manual — never auto-triggered
        _tmpl(5, TriggerType.LEVEL_REACHED, {"value": 10}),
        _tmpl(6, TriggerType.LEVEL_INTERVAL, {"interval": 5}),
        _tmpl(7, TriggerType.EVENT_COUNT, {"event_type": "MESSAGE", "count": 50}),
        _tmpl(8, TriggerType.FIRST_EVENT, {"event_type": "THREAD_CREATE"}),
    ]

    cache.get_active_achievements.return_value = templates
    cache.get_series_predecessor.return_value = None
    return cache


# ---------------------------------------------------------------------------
# Tests — Individual trigger types
# ---------------------------------------------------------------------------
class TestTriggerTypes:
    def test_xp_milestone_earned(self, mock_cache):
        ctx = _ctx(user_xp=150)
        earned = check_achievements(100, mock_cache, ctx, set())
        assert 1 in earned

    def test_xp_milestone_not_reached(self, mock_cache):
        ctx = _ctx(user_xp=50)
        earned = check_achievements(100, mock_cache, ctx, set())
        assert 1 not in earned

    def test_star_milestone_season(self, mock_cache):
        ctx = _ctx(season_stars=60)
        earned = check_achievements(100, mock_cache, ctx, set())
        assert 2 in earned

    def test_star_milestone_below(self, mock_cache):
        ctx = _ctx(season_stars=10)
        earned = check_achievements(100, mock_cache, ctx, set())
        assert 2 not in earned

    def test_stat_threshold_earned(self, mock_cache):
        ctx = _ctx(stats={"messages_sent": 150})
        earned = check_achievements(100, mock_cache, ctx, set())
        assert 3 in earned

    def test_stat_threshold_below(self, mock_cache):
        ctx = _ctx(stats={"messages_sent": 50})
        earned = check_achievements(100, mock_cache, ctx, set())
        assert 3 not in earned

    def test_manual_never_auto_triggered(self, mock_cache):
        ctx = _ctx(user_xp=999999, season_stars=999999, stats={"messages_sent": 999999})
        earned = check_achievements(100, mock_cache, ctx, set())
        assert 4 not in earned

    def test_level_reached(self, mock_cache):
        ctx = _ctx(user_level=12)
        earned = check_achievements(100, mock_cache, ctx, set())
        assert 5 in earned

    def test_level_reached_below(self, mock_cache):
        ctx = _ctx(user_level=8)
        earned = check_achievements(100, mock_cache, ctx, set())
        assert 5 not in earned

    def test_level_interval_fires(self, mock_cache):
        """Level interval fires on a level-up that crosses a multiple."""
        ctx = _ctx(user_level=10, old_level=9)
        earned = check_achievements(100, mock_cache, ctx, set())
        assert 6 in earned

    def test_level_interval_no_level_up(self, mock_cache):
        """Level interval does NOT fire without an actual level-up."""
        ctx = _ctx(user_level=10, old_level=None)
        earned = check_achievements(100, mock_cache, ctx, set())
        assert 6 not in earned

    def test_level_interval_no_match(self, mock_cache):
        """Level interval does NOT fire on non-multiple levels."""
        ctx = _ctx(user_level=11, old_level=10)
        earned = check_achievements(100, mock_cache, ctx, set())
        assert 6 not in earned

    def test_event_count(self, mock_cache):
        ctx = _ctx(event_counts={"MESSAGE": 60})
        earned = check_achievements(100, mock_cache, ctx, set())
        assert 7 in earned

    def test_event_count_below(self, mock_cache):
        ctx = _ctx(event_counts={"MESSAGE": 30})
        earned = check_achievements(100, mock_cache, ctx, set())
        assert 7 not in earned

    def test_first_event(self, mock_cache):
        ctx = _ctx(event_counts={"THREAD_CREATE": 1})
        earned = check_achievements(100, mock_cache, ctx, set())
        assert 8 in earned

    def test_first_event_zero(self, mock_cache):
        ctx = _ctx(event_counts={})
        earned = check_achievements(100, mock_cache, ctx, set())
        assert 8 not in earned


# ---------------------------------------------------------------------------
# Tests — Already earned & multiple
# ---------------------------------------------------------------------------
class TestEarnedFiltering:
    def test_already_earned_skipped(self, mock_cache):
        ctx = _ctx(
            user_xp=999, season_stars=999,
            stats={"messages_sent": 999},
            event_counts={"MESSAGE": 999, "THREAD_CREATE": 999},
            user_level=99, old_level=98,
        )
        already = {1, 2, 3, 5, 6, 7, 8}
        earned = check_achievements(100, mock_cache, ctx, already)
        for aid in already:
            assert aid not in earned

    def test_multiple_achievements_at_once(self, mock_cache):
        ctx = _ctx(
            user_xp=200, season_stars=100,
            stats={"messages_sent": 200},
            event_counts={"MESSAGE": 100, "THREAD_CREATE": 5},
            user_level=10, old_level=9,
        )
        earned = check_achievements(100, mock_cache, ctx, set())
        # XP milestone, star milestone, stat threshold, level reached,
        # level interval (10 % 5 == 0), event count, first event
        assert 1 in earned
        assert 2 in earned
        assert 3 in earned
        assert 4 not in earned  # manual
        assert 5 in earned
        assert 6 in earned
        assert 7 in earned
        assert 8 in earned


# ---------------------------------------------------------------------------
# Tests — Series gating
# ---------------------------------------------------------------------------
class TestSeriesGating:
    def test_second_tier_blocked_without_first(self):
        """Tier 2 in a series should not trigger if tier 1 not earned."""
        tier1 = _tmpl(10, TriggerType.XP_MILESTONE, {"value": 100},
                       series_id=1, series_order=1)
        tier2 = _tmpl(11, TriggerType.XP_MILESTONE, {"value": 200},
                       series_id=1, series_order=2)

        cache = MagicMock()
        cache.get_active_achievements.return_value = [tier1, tier2]
        cache.get_series_predecessor.return_value = tier1  # tier1 is predecessor

        ctx = _ctx(user_xp=500)
        earned = check_achievements(100, cache, ctx, set())

        # Tier 1 should earn, but tier 2 blocked because tier1 not in already_earned
        assert 10 in earned
        assert 11 not in earned

    def test_second_tier_unlocks_with_first_earned(self):
        """Tier 2 should trigger when tier 1 is already earned."""
        tier1 = _tmpl(10, TriggerType.XP_MILESTONE, {"value": 100},
                       series_id=1, series_order=1)
        tier2 = _tmpl(11, TriggerType.XP_MILESTONE, {"value": 200},
                       series_id=1, series_order=2)

        cache = MagicMock()
        cache.get_active_achievements.return_value = [tier1, tier2]
        cache.get_series_predecessor.return_value = tier1

        ctx = _ctx(user_xp=500)
        # Tier 1 already earned
        earned = check_achievements(100, cache, ctx, {10})
        assert 10 not in earned  # already earned
        assert 11 in earned  # unlocked

    def test_first_tier_no_gating(self):
        """Tier 1 (series_order=1) has no predecessor — always eligible."""
        tier1 = _tmpl(10, TriggerType.STAT_THRESHOLD,
                       {"field": "messages_sent", "value": 5},
                       series_id=1, series_order=1)

        cache = MagicMock()
        cache.get_active_achievements.return_value = [tier1]
        cache.get_series_predecessor.return_value = None  # order=1 has no predecessor

        ctx = _ctx(stats={"messages_sent": 10})
        earned = check_achievements(100, cache, ctx, set())
        assert 10 in earned


# ---------------------------------------------------------------------------
# Tests — Edge cases
# ---------------------------------------------------------------------------
class TestEdgeCases:
    def test_missing_config_value(self):
        """Threshold triggers with missing value should not fire."""
        cache = MagicMock()
        cache.get_active_achievements.return_value = [
            _tmpl(20, TriggerType.XP_MILESTONE, {}),  # no "value" key
        ]
        cache.get_series_predecessor.return_value = None

        ctx = _ctx(user_xp=999999)
        earned = check_achievements(100, cache, ctx, set())
        assert 20 not in earned

    def test_invalid_stat_field(self):
        """stat_threshold with an invalid field should not fire."""
        cache = MagicMock()
        cache.get_active_achievements.return_value = [
            _tmpl(21, TriggerType.STAT_THRESHOLD,
                   {"field": "nonexistent_field", "value": 1}),
        ]
        cache.get_series_predecessor.return_value = None

        ctx = _ctx(stats={"nonexistent_field": 999})
        earned = check_achievements(100, cache, ctx, set())
        assert 21 not in earned

    def test_star_milestone_lifetime_scope(self):
        """Star milestone with lifetime scope uses lifetime_stars."""
        cache = MagicMock()
        cache.get_active_achievements.return_value = [
            _tmpl(22, TriggerType.STAR_MILESTONE,
                   {"scope": "lifetime", "value": 100}),
        ]
        cache.get_series_predecessor.return_value = None

        ctx = _ctx(season_stars=10, lifetime_stars=200)
        earned = check_achievements(100, cache, ctx, set())
        assert 22 in earned

    def test_null_trigger_config_treated_as_empty(self):
        """Templates with trigger_config=None should not crash."""
        cache = MagicMock()
        tmpl = _tmpl(23, TriggerType.STAT_THRESHOLD, None)
        cache.get_active_achievements.return_value = [tmpl]
        cache.get_series_predecessor.return_value = None

        ctx = _ctx(stats={"messages_sent": 999})
        earned = check_achievements(100, cache, ctx, set())
        assert 23 not in earned  # no field/value in config
