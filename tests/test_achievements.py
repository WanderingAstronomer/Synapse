"""
tests/test_achievements.py — Unit Tests for Achievement Checking
=================================================================

Tests the achievement pipeline logic.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from synapse.engine.achievements import check_achievements


@pytest.fixture
def mock_cache():
    """Cache with sample achievement templates."""
    cache = MagicMock()

    # Simulate achievement templates
    templates = [
        MagicMock(
            id=1,
            guild_id=100,
            active=True,
            requirement_type="xp_milestone",
            requirement_scope="lifetime",
            requirement_field=None,
            requirement_value=100,
        ),
        MagicMock(
            id=2,
            guild_id=100,
            active=True,
            requirement_type="star_threshold",
            requirement_scope="season",
            requirement_field=None,
            requirement_value=50,
        ),
        MagicMock(
            id=3,
            guild_id=100,
            active=True,
            requirement_type="counter_threshold",
            requirement_scope="season",
            requirement_field="messages_sent",
            requirement_value=100,
        ),
        MagicMock(
            id=4,
            guild_id=100,
            active=True,
            requirement_type="custom",
            requirement_scope="lifetime",
            requirement_field=None,
            requirement_value=None,
        ),
    ]
    cache.get_active_achievements.return_value = templates
    return cache


class TestCheckAchievements:
    def test_xp_milestone_earned(self, mock_cache):
        """User with 150 XP should earn the 100 XP milestone."""
        earned = check_achievements(
            guild_id=100,
            cache=mock_cache,
            user_xp=150,
            season_stars=0,
            lifetime_stars=0,
            stats={"messages_sent": 0},
            already_earned=set(),
        )
        assert 1 in earned  # XP milestone achievement

    def test_xp_milestone_not_reached(self, mock_cache):
        """User with 50 XP should NOT earn the 100 XP milestone."""
        earned = check_achievements(
            guild_id=100,
            cache=mock_cache,
            user_xp=50,
            season_stars=0,
            lifetime_stars=0,
            stats={"messages_sent": 0},
            already_earned=set(),
        )
        assert 1 not in earned

    def test_already_earned_skipped(self, mock_cache):
        """Achievement already earned should not be re-awarded."""
        earned = check_achievements(
            guild_id=100,
            cache=mock_cache,
            user_xp=150,
            season_stars=100,
            lifetime_stars=100,
            stats={"messages_sent": 200},
            already_earned={1, 2, 3},
        )
        assert 1 not in earned
        assert 2 not in earned
        assert 3 not in earned

    def test_star_threshold_season_scope(self, mock_cache):
        """Star threshold with season scope checks season_stars."""
        earned = check_achievements(
            guild_id=100,
            cache=mock_cache,
            user_xp=0,
            season_stars=60,
            lifetime_stars=60,
            stats={"messages_sent": 0},
            already_earned=set(),
        )
        assert 2 in earned

    def test_counter_threshold(self, mock_cache):
        """Counter threshold checks the stat field."""
        earned = check_achievements(
            guild_id=100,
            cache=mock_cache,
            user_xp=0,
            season_stars=0,
            lifetime_stars=0,
            stats={"messages_sent": 150},
            already_earned=set(),
        )
        assert 3 in earned

    def test_custom_type_skipped(self, mock_cache):
        """Custom achievements cannot be auto-awarded."""
        earned = check_achievements(
            guild_id=100,
            cache=mock_cache,
            user_xp=999999,
            season_stars=999999,
            lifetime_stars=999999,
            stats={"messages_sent": 999999},
            already_earned=set(),
        )
        assert 4 not in earned

    def test_multiple_achievements_at_once(self, mock_cache):
        """User meeting all thresholds earns all eligible achievements."""
        earned = check_achievements(
            guild_id=100,
            cache=mock_cache,
            user_xp=200,
            season_stars=100,
            lifetime_stars=100,
            stats={"messages_sent": 200},
            already_earned=set(),
        )
        assert 1 in earned
        assert 2 in earned
        assert 3 in earned
        assert 4 not in earned  # Custom is never auto-earned
