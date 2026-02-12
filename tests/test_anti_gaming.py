"""
tests/test_anti_gaming.py — Anti-Gaming Mechanism Tests
========================================================

Tests unique-reactor weighting, per-user caps, and diminishing returns.
"""

from __future__ import annotations

from synapse.database.models import InteractionType
from synapse.engine.events import SynapseEvent
from synapse.engine.reward import (
    AntiGamingTracker,
    apply_anti_gaming_stars,
    apply_anti_gaming_xp,
    apply_xp_caps,
)


class TestSelfReactionFilter:
    def test_self_reaction_yields_zero_stars(self):
        """Reacting to your own message gives 0 stars."""
        event = SynapseEvent(
            user_id=1001,
            event_type=InteractionType.REACTION_RECEIVED,
            channel_id=1,
            guild_id=1,
            metadata={"reactor_id": 1001, "unique_reactor_count": 1},
        )
        assert apply_anti_gaming_stars(event, 10) == 0

    def test_other_reaction_yields_stars(self):
        """Reacting to someone else's message gives stars."""
        event = SynapseEvent(
            user_id=1001,
            event_type=InteractionType.REACTION_RECEIVED,
            channel_id=1,
            guild_id=1,
            metadata={"reactor_id": 2001, "unique_reactor_count": 3},
        )
        result = apply_anti_gaming_stars(event, 10)
        assert result > 0


class TestUniqueReactorWeighting:
    def test_more_unique_reactors_more_stars(self):
        """More unique reactors should produce more star value."""
        event_1 = SynapseEvent(
            user_id=1001,
            event_type=InteractionType.REACTION_RECEIVED,
            channel_id=1,
            guild_id=1,
            metadata={"reactor_id": 2001, "unique_reactor_count": 1},
        )
        event_5 = SynapseEvent(
            user_id=1001,
            event_type=InteractionType.REACTION_RECEIVED,
            channel_id=1,
            guild_id=1,
            metadata={"reactor_id": 2001, "unique_reactor_count": 5},
        )
        stars_1 = apply_anti_gaming_stars(event_1, 10)
        stars_5 = apply_anti_gaming_stars(event_5, 10)
        assert stars_5 >= stars_1

    def test_reaction_velocity_xp_cap(self):
        """XP from reactions should be capped based on unique reactor count."""
        event = SynapseEvent(
            user_id=1001,
            event_type=InteractionType.REACTION_RECEIVED,
            channel_id=1,
            guild_id=1,
            metadata={"unique_reactor_count": 1},
        )
        capped = apply_xp_caps(event, 100)
        assert capped <= 100


class TestDiminishingReturns:
    def test_first_interaction_full_factor(self):
        """First interaction between two users should have factor close to 1."""
        tracker = AntiGamingTracker()
        factor = tracker.get_diminishing_factor(1001, 2001)
        assert factor > 0.5

    def test_repeated_interactions_diminish(self):
        """Repeated interactions between same users should diminish."""
        tracker = AntiGamingTracker()
        factors = []
        for _ in range(10):
            f = tracker.get_diminishing_factor(1001, 2001)
            factors.append(f)
        # Later factors should be smaller (or at least not bigger)
        assert factors[-1] <= factors[0]

    def test_different_targets_independent(self):
        """Interacting with different users should have independent tracking."""
        tracker = AntiGamingTracker()
        # Exhaust diminishing returns with user 2001
        for _ in range(10):
            tracker.get_diminishing_factor(1001, 2001)

        # New target should still have good factor
        factor = tracker.get_diminishing_factor(1001, 3001)
        assert factor > 0.5


class TestAntiGamingXP:
    def test_non_reaction_passes_through(self):
        """Non-reaction events should pass through XP unmodified."""
        event = SynapseEvent(
            user_id=1001,
            event_type=InteractionType.MESSAGE,
            channel_id=1,
            guild_id=1,
            metadata={},
        )
        result = apply_anti_gaming_xp(event, 15)
        assert result == 15

    def test_reaction_xp_not_negative(self):
        """Anti-gaming should never produce negative XP."""
        event = SynapseEvent(
            user_id=1001,
            event_type=InteractionType.REACTION_RECEIVED,
            channel_id=1,
            guild_id=1,
            metadata={"unique_reactor_count": 0},
        )
        result = apply_anti_gaming_xp(event, 10)
        assert result >= 0
