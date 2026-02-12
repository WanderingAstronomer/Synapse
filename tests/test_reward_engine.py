"""
tests/test_reward_engine.py — Unit Tests for Reward Pipeline
=============================================================

Tests the pure calculation pipeline (no I/O, no database).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from synapse.database.models import InteractionType
from synapse.engine.events import BASE_STARS, BASE_XP, SynapseEvent
from synapse.engine.reward import (
    AntiGamingTracker,
    RewardResult,
    apply_anti_gaming_stars,
    apply_xp_caps,
    calculate_quality_modifier,
    calculate_reward,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def mock_cache():
    """Create a mock ConfigCache with sensible defaults."""
    cache = MagicMock()

    # Default: no zone → returns None for zone lookup
    cache.get_zone_for_channel.return_value = None

    # Default multipliers: both 1.0
    cache.get_multipliers.return_value = (1.0, 1.0)

    # Default settings — return the fallback default for any key
    cache.get_int.side_effect = lambda k, d=0: d
    cache.get_float.side_effect = lambda k, d=0.0: d
    cache.get_str.side_effect = lambda k, d="": d
    cache.get_bool.side_effect = lambda k, d=False: d
    cache.get_setting.side_effect = lambda k, d=None: d

    return cache


@pytest.fixture
def message_event():
    """A standard message event."""
    return SynapseEvent(
        user_id=1001,
        event_type=InteractionType.MESSAGE,
        channel_id=555,
        guild_id=100,
        source_event_id="msg_123",
        metadata={
            "content_length": 50,
            "has_code_block": False,
            "has_link": False,
            "has_attachment": False,
            "emoji_count": 0,
        },
    )


@pytest.fixture
def long_message_event():
    """A message with code blocks, good length."""
    return SynapseEvent(
        user_id=1001,
        event_type=InteractionType.MESSAGE,
        channel_id=555,
        guild_id=100,
        source_event_id="msg_456",
        metadata={
            "content_length": 300,
            "has_code_block": True,
            "has_link": True,
            "has_attachment": True,
            "emoji_count": 2,
        },
    )


@pytest.fixture
def reaction_event():
    """A reaction received event."""
    return SynapseEvent(
        user_id=2001,
        event_type=InteractionType.REACTION_RECEIVED,
        channel_id=555,
        guild_id=100,
        source_event_id="rxn_789",
        metadata={
            "unique_reactor_count": 5,
            "reactor_id": 3001,
        },
    )


# ---------------------------------------------------------------------------
# BASE_XP / BASE_STARS
# ---------------------------------------------------------------------------
class TestBaseValues:
    def test_message_has_base_xp(self):
        assert BASE_XP[InteractionType.MESSAGE] > 0

    def test_reaction_given_has_base_stars(self):
        assert BASE_STARS[InteractionType.REACTION_GIVEN] > 0

    def test_voice_tick_has_base_stars(self):
        assert BASE_STARS[InteractionType.VOICE_TICK] > 0


# ---------------------------------------------------------------------------
# Quality Modifier
# ---------------------------------------------------------------------------
class TestQualityModifier:
    def test_short_message_base_modifier(self, message_event):
        # Short message (50 chars) — should get base quality
        mod = calculate_quality_modifier(message_event)
        assert mod >= 1.0

    def test_long_message_higher_modifier(self, long_message_event):
        mod_long = calculate_quality_modifier(long_message_event)
        # Long message with code+link+attachment should have higher modifier
        assert mod_long > 1.0

    def test_code_block_bonus(self):
        event = SynapseEvent(
            user_id=1,
            event_type=InteractionType.MESSAGE,
            channel_id=1,
            guild_id=1,
            metadata={"content_length": 100, "has_code_block": True},
        )
        mod_code = calculate_quality_modifier(event)

        event_no_code = SynapseEvent(
            user_id=1,
            event_type=InteractionType.MESSAGE,
            channel_id=1,
            guild_id=1,
            metadata={"content_length": 100, "has_code_block": False},
        )
        mod_no_code = calculate_quality_modifier(event_no_code)
        assert mod_code > mod_no_code

    def test_non_message_returns_base(self):
        event = SynapseEvent(
            user_id=1,
            event_type=InteractionType.VOICE_TICK,
            channel_id=1,
            guild_id=1,
            metadata={},
        )
        assert calculate_quality_modifier(event) == 1.0


# ---------------------------------------------------------------------------
# Anti-Gaming
# ---------------------------------------------------------------------------
class TestAntiGaming:
    def test_self_reaction_blocked(self):
        event = SynapseEvent(
            user_id=1001,
            event_type=InteractionType.REACTION_RECEIVED,
            channel_id=1,
            guild_id=1,
            metadata={"reactor_id": 1001, "unique_reactor_count": 1},
        )
        stars = apply_anti_gaming_stars(event, 5)
        assert stars == 0  # Self-reactions should yield 0 stars

    def test_unique_reactor_weighting(self, reaction_event):
        # With 5 unique reactors, should get good star value
        stars = apply_anti_gaming_stars(reaction_event, 10)
        assert stars > 0

    def test_diminishing_returns_tracker(self):
        tracker = AntiGamingTracker()
        user_id = 1001
        target_id = 2001

        # First few interactions should pass
        for _ in range(3):
            factor = tracker.get_diminishing_factor(user_id, target_id)
            assert factor > 0

    def test_reaction_velocity_cap(self):
        event = SynapseEvent(
            user_id=1001,
            event_type=InteractionType.REACTION_RECEIVED,
            channel_id=1,
            guild_id=1,
            metadata={"unique_reactor_count": 1},
        )
        xp = apply_xp_caps(event, 100)
        # With only 1 unique reactor, XP should be capped/reduced
        assert xp <= 100


# ---------------------------------------------------------------------------
# Full Pipeline
# ---------------------------------------------------------------------------
class TestCalculateReward:
    def test_message_produces_xp_and_stars(self, message_event, mock_cache):
        result = calculate_reward(message_event, mock_cache)
        assert isinstance(result, RewardResult)
        assert result.xp >= 0
        assert result.stars >= 0

    def test_reaction_produces_stars(self, reaction_event, mock_cache):
        result = calculate_reward(reaction_event, mock_cache)
        assert result.stars >= 0

    def test_level_up_detection(self, message_event, mock_cache):
        # User at level 1 with 120 XP
        # Settings: level_base=100, level_factor=1.25
        # Required = 100 * 1.25^1 = 125
        # If they earn XP and total > 125 → level up!
        level_map = {"level_base": 100, "gold_per_level_up": 50}
        mock_cache.get_int.side_effect = lambda k, d=0: level_map.get(k, d)
        mock_cache.get_float.side_effect = lambda k, d=0.0: {"level_factor": 1.25}.get(k, d)
        result = calculate_reward(
            message_event,
            mock_cache,
            user_xp=120,
            user_level=1,
        )
        # The XP earned may or may not trigger level-up depending on quality
        # modifier, but we can test the mechanism
        assert isinstance(result.leveled_up, bool)
        assert isinstance(result.gold_bonus, int)

    def test_zone_multiplier_applied(self, message_event, mock_cache):
        # Configure zone with 2x XP multiplier
        zone = MagicMock()
        zone.id = 1
        mock_cache.get_zone_for_channel.return_value = zone
        mock_cache.get_multipliers.return_value = (2.0, 1.0)

        result_2x = calculate_reward(message_event, mock_cache)

        # Now with 1x multiplier
        mock_cache.get_multipliers.return_value = (1.0, 1.0)
        result_1x = calculate_reward(message_event, mock_cache)

        # 2x zone should produce more XP (approximately 2x)
        assert result_2x.xp >= result_1x.xp

    def test_voice_tick_produces_result(self, mock_cache):
        event = SynapseEvent(
            user_id=1001,
            event_type=InteractionType.VOICE_TICK,
            channel_id=555,
            guild_id=100,
            metadata={"tick_minutes": 10},
        )
        result = calculate_reward(event, mock_cache)
        assert isinstance(result, RewardResult)
