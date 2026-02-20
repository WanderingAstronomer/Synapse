"""
synapse.engine.anti_gaming — Anti-gaming checks & sliding window tracker
=========================================================================

Per D05 §5.7: prevents star/XP farming via pair-capping, diminishing
returns, self-reaction filters, and velocity caps.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from collections.abc import Callable
from threading import Lock

from synapse.database.models import InteractionType
from synapse.engine.events import SynapseEvent

logger = logging.getLogger(__name__)


class AntiGamingTracker:
    """Tracks per-user per-target reaction caps and sliding windows.

    Thread-safe. Entries expire after 24 hours.
    """

    def __init__(self, time_provider: Callable[[], float] | None = None) -> None:
        self._lock = Lock()
        # (reactor_id, target_user_id) → list of timestamps
        self._pair_reactions: dict[tuple[int, int], list[float]] = defaultdict(list)
        self._last_cleanup = (time_provider or time.time)()
        self._time = time_provider or time.time

    def is_pair_capped(self, reactor_id: int, target_user_id: int, max_per_day: int = 3) -> bool:
        """Check if reactor has hit the per-user per-target cap (§5.7.2).

        Returns True if capped (no rewards).
        """
        now = self._time()
        cutoff = now - 86400  # 24 hours

        with self._lock:
            self._maybe_cleanup(now)
            key = (reactor_id, target_user_id)
            self._pair_reactions[key] = [t for t in self._pair_reactions[key] if t > cutoff]
            if len(self._pair_reactions[key]) >= max_per_day:
                return True
            self._pair_reactions[key].append(now)
            return False

    def _maybe_cleanup(self, now: float) -> None:
        """Periodically clean up expired entries."""
        if now - self._last_cleanup < 3600:
            return
        self._last_cleanup = now
        cutoff = now - 86400
        to_delete = [k for k, v in self._pair_reactions.items() if all(t <= cutoff for t in v)]
        for k in to_delete:
            del self._pair_reactions[k]

    def reset(self) -> None:
        """Clear all tracked state. Use in test fixtures to prevent cross-test pollution."""
        with self._lock:
            self._pair_reactions.clear()
            self._last_cleanup = self._time()

    def get_diminishing_factor(self, reactor_id: int, target_user_id: int) -> float:
        """Return a diminishing factor (0.0–1.0) for repeated user-pair interactions.

        Each call records an interaction.  The factor decreases as the same pair
        interacts more within the 24-hour window.  Formula: 1 / (1 + count).
        """
        now = self._time()
        cutoff = now - 86400

        with self._lock:
            self._maybe_cleanup(now)
            key = (reactor_id, target_user_id)
            self._pair_reactions[key] = [t for t in self._pair_reactions[key] if t > cutoff]
            count = len(self._pair_reactions[key])
            self._pair_reactions[key].append(now)
            return 1.0 / (1.0 + count)


# Module-level default instance used by functions that accept an optional tracker.
# Production code uses this singleton for its sliding-window state.
# Tests should always pass an explicit AntiGamingTracker() to avoid cross-test
# state pollution; the reset() method is available for fixture teardown.
_default_anti_gaming = AntiGamingTracker()


# ---------------------------------------------------------------------------
# Anti-gaming stage functions
# ---------------------------------------------------------------------------


def apply_anti_gaming_xp(event: SynapseEvent, base_xp: int) -> int:
    """Adjust XP for anti-gaming: self-reaction filter."""
    if event.event_type == InteractionType.REACTION_RECEIVED:
        m = event.metadata
        if m.get("reactor_id") == event.user_id:
            return 0
    return base_xp


def apply_xp_caps(event: SynapseEvent, xp: int) -> int:
    """Apply XP caps (reaction velocity cap, etc.)."""
    if event.event_type == InteractionType.REACTION_RECEIVED:
        unique = event.metadata.get("unique_reactor_count", 1)
        message_age = event.metadata.get("message_age_seconds", 9999)
        if unique > 10 and message_age < 300:
            xp = min(xp, 5)
    return xp
