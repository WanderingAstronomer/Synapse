"""
synapse.engine.reward — Reward Calculation Pipeline
=====================================================

Pure calculation pipeline using the channel-first reward system.
No Discord I/O, no DB I/O inside the engine.

Pipeline stages:
  SynapseEvent → Multiplier Resolve → Quality → Anti-Gaming → Cap → RewardResult
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from synapse.constants import xp_for_level
from synapse.database.models import InteractionType
from synapse.engine.anti_gaming import (
    AntiGamingTracker,
    apply_anti_gaming_stars,
    apply_anti_gaming_xp,
    apply_xp_caps,
)
from synapse.engine.events import BASE_STARS, BASE_XP, SynapseEvent
from synapse.engine.quality import calculate_quality_modifier

if TYPE_CHECKING:
    from synapse.engine.cache import ConfigCache

logger = logging.getLogger(__name__)

__all__ = [
    "RewardResult",
    "calculate_reward",
]


# ---------------------------------------------------------------------------
# RewardResult — output of the pipeline
# ---------------------------------------------------------------------------
@dataclass
class RewardResult:
    """Final reward calculation output."""

    xp: int = 0
    stars: int = 0
    leveled_up: bool = False
    new_level: int | None = None
    gold_bonus: int = 0
    achievements_earned: list[int] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Full calculation pipeline
# ---------------------------------------------------------------------------
def calculate_reward(
    event: SynapseEvent,
    cache: ConfigCache,
    *,
    user_xp: int = 0,
    user_level: int = 1,
    anti_gaming_tracker: AntiGamingTracker | None = None,
) -> RewardResult:
    """Run the full reward pipeline on a SynapseEvent.

    This is a PURE function — no DB or Discord I/O.
    All tuning parameters are read from the cache (settings table).
    """
    # Read tuning params from cache (settings table)
    _gold_per_level = cache.get_int("gold_per_level_up", 50)

    # 1. Multiplier resolution (channel-first)
    xp_mult, star_mult = cache.resolve_multipliers(
        event.channel_id, event.event_type.value,
    )

    # 2. Quality modifier (messages only, XP only) — reads thresholds from cache
    quality = calculate_quality_modifier(event, cache)

    # 3. Base values
    base_xp = BASE_XP.get(event.event_type, 0)
    base_stars = BASE_STARS.get(event.event_type, 0)

    # 4. Anti-gaming adjustments
    base_xp = apply_anti_gaming_xp(event, base_xp)
    adjusted_stars = apply_anti_gaming_stars(
        event, base_stars, tracker=anti_gaming_tracker
    )

    # 5. Calculate final values
    final_xp = int(base_xp * xp_mult * quality)
    final_stars = int(adjusted_stars * star_mult)

    # 6. Apply XP caps
    final_xp = apply_xp_caps(event, final_xp)

    # 7. Level-up check — uses canonical formula from constants
    new_xp = user_xp + final_xp
    required = xp_for_level(user_level, cache)
    leveled_up = new_xp >= required and final_xp > 0
    new_level = user_level + 1 if leveled_up else None
    gold_bonus = _gold_per_level if leveled_up else 0

    return RewardResult(
        xp=final_xp,
        stars=final_stars,
        leveled_up=leveled_up,
        new_level=new_level,
        gold_bonus=gold_bonus,
        achievements_earned=[],  # Filled by achievement checker
    )
