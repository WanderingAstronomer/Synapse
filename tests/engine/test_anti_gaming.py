from __future__ import annotations

from typing import Any

import pytest

from synapse.database.models import InteractionType
from synapse.engine.anti_gaming import (
    AntiGamingTracker,
    apply_anti_gaming_xp,
    apply_xp_caps,
)
from synapse.engine.events import SynapseEvent


class MockTime:
    def __init__(self, initial: float = 1000000.0) -> None:
        self._now = initial

    def __call__(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


@pytest.fixture
def mock_clock() -> MockTime:
    return MockTime()


@pytest.fixture
def tracker(mock_clock: MockTime) -> AntiGamingTracker:
    return AntiGamingTracker(time_provider=mock_clock)


class TestAntiGamingTracker:
    def test_pair_capping_under_limit(self, tracker: AntiGamingTracker) -> None:
        # 3 interactions allowed per day
        assert not tracker.is_pair_capped(1, 2, max_per_day=3)
        assert not tracker.is_pair_capped(1, 2, max_per_day=3)
        assert not tracker.is_pair_capped(1, 2, max_per_day=3)

    def test_pair_capping_exceeded(self, tracker: AntiGamingTracker) -> None:
        assert not tracker.is_pair_capped(1, 2, max_per_day=2)
        assert not tracker.is_pair_capped(1, 2, max_per_day=2)
        assert tracker.is_pair_capped(1, 2, max_per_day=2)  # 3rd attempt is capped

    def test_pair_capping_resets_after_24h(
        self, tracker: AntiGamingTracker, mock_clock: MockTime
    ) -> None:
        max_per_day = 1
        assert not tracker.is_pair_capped(1, 2, max_per_day=max_per_day)
        assert tracker.is_pair_capped(1, 2, max_per_day=max_per_day)

        # Advance 24 hours + 1 second
        mock_clock.advance(86401)
        assert not tracker.is_pair_capped(1, 2, max_per_day=max_per_day)

    def test_pair_capping_distinct_pairs(self, tracker: AntiGamingTracker) -> None:
        max_per_day = 1
        # User 1 -> User 2
        assert not tracker.is_pair_capped(1, 2, max_per_day=max_per_day)
        assert tracker.is_pair_capped(1, 2, max_per_day=max_per_day)

        # User 1 -> User 3 (should be independent)
        assert not tracker.is_pair_capped(1, 3, max_per_day=max_per_day)

        # User 2 -> User 1 (should be independent)
        assert not tracker.is_pair_capped(2, 1, max_per_day=max_per_day)

    def test_diminishing_returns_sequence(self, tracker: AntiGamingTracker) -> None:
        # Formula: 1 / (1 + previous_count)
        # 1st call: count=0 -> 1.0
        assert tracker.get_diminishing_factor(1, 2) == 1.0
        # 2nd call: count=1 -> 0.5
        assert tracker.get_diminishing_factor(1, 2) == 0.5
        # 3rd call: count=2 -> 0.333...
        assert abs(tracker.get_diminishing_factor(1, 2) - 0.3333333333) < 0.0001

    def test_diminishing_returns_resets_after_24h(
        self, tracker: AntiGamingTracker, mock_clock: MockTime
    ) -> None:
        tracker.get_diminishing_factor(1, 2)  # 1.0
        tracker.get_diminishing_factor(1, 2)  # 0.5

        mock_clock.advance(86401)
        assert tracker.get_diminishing_factor(1, 2) == 1.0

    def test_cleanup_removes_expired_entries(
        self, tracker: AntiGamingTracker, mock_clock: MockTime
    ) -> None:
        # Add entry at t=0
        tracker.is_pair_capped(1, 2, max_per_day=5)

        # Access internal state to verify existence
        assert (1, 2) in tracker._pair_reactions

        # Advance 25 hours. Next write operation should clean up.
        mock_clock.advance(3600 * 25)

        # Trigger cleanup via write
        tracker.is_pair_capped(3, 4, max_per_day=5)

        # Verify (1, 2) is gone
        assert (1, 2) not in tracker._pair_reactions
        assert (3, 4) in tracker._pair_reactions


class TestApplyAntiGamingXP:
    def test_self_reaction_returns_zero(self) -> None:
        event = SynapseEvent(
            event_type=InteractionType.REACTION_RECEIVED,
            user_id=100,
            channel_id=200,
            guild_id=300,
            metadata={"reactor_id": 100},
        )
        assert apply_anti_gaming_xp(event, base_xp=100) == 0

    def test_normal_reaction_returns_base(self) -> None:
        event = SynapseEvent(
            event_type=InteractionType.REACTION_RECEIVED,
            user_id=100,
            channel_id=200,
            guild_id=300,
            metadata={"reactor_id": 999},
        )
        assert apply_anti_gaming_xp(event, base_xp=100) == 100


class TestApplyXPCaps:
    def test_velocity_cap(self) -> None:
        # unique > 10 and message_age < 300 -> Cap at 5 XP
        event = SynapseEvent(
            event_type=InteractionType.REACTION_RECEIVED,
            user_id=100,
            channel_id=200,
            guild_id=300,
            metadata={
                "unique_reactor_count": 11,
                "message_age_seconds": 299,
            },
        )
        assert apply_xp_caps(event, xp=50) == 5

    def test_velocity_cap_not_applied_if_old_enough(self) -> None:
        event = SynapseEvent(
            event_type=InteractionType.REACTION_RECEIVED,
            user_id=100,
            channel_id=200,
            guild_id=300,
            metadata={
                "unique_reactor_count": 11,
                "message_age_seconds": 301,
            },
        )
        assert apply_xp_caps(event, xp=50) == 50

    def test_velocity_cap_not_applied_if_low_unique(self) -> None:
        event = SynapseEvent(
            event_type=InteractionType.REACTION_RECEIVED,
            user_id=100,
            channel_id=200,
            guild_id=300,
            metadata={
                "unique_reactor_count": 10,
                "message_age_seconds": 100,
            },
        )
        assert apply_xp_caps(event, xp=50) == 50
