"""
synapse.engine.reward — Reward Calculation Pipeline
=====================================================

Pure calculation pipeline per 05_REWARD_ENGINE.md.
No Discord I/O, no DB I/O inside the engine.

Pipeline stages:
  SynapseEvent → Zone Classify → Multiply → Quality → Anti-Gaming → Cap → RewardResult
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
    get_default_tracker,
)
from synapse.engine.events import BASE_STARS, BASE_XP, SynapseEvent
from synapse.engine.quality import calculate_quality_modifier, llm_quality_modifier

if TYPE_CHECKING:
    from synapse.engine.cache import ConfigCache

logger = logging.getLogger(__name__)

# Re-export so existing consumers continue to work
__all__ = [
    "AntiGamingTracker",
    "RewardResult",
    "apply_anti_gaming_stars",
    "apply_anti_gaming_xp",
    "apply_xp_caps",
    "calculate_quality_modifier",
    "calculate_reward",
    "classify_zone",
    "get_default_tracker",
    "get_multipliers",
]


# ---------------------------------------------------------------------------
# RewardResult — output of the pipeline (05 §5.10)
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
    zone_name: str | None = None


# ---------------------------------------------------------------------------
# Stage 1: Zone Classification (§5.4)
# ---------------------------------------------------------------------------
def classify_zone(
    event: SynapseEvent, cache: ConfigCache
) -> tuple[int | None, str | None]:
    """Returns (zone_id, zone_name) for the event's channel."""
    zone = cache.get_zone_for_channel(event.channel_id)
    if zone is not None:
        return zone.id, zone.name
    return None, "default"


# ---------------------------------------------------------------------------
# Stage 2: Multiplier Lookup (§5.5)
# ---------------------------------------------------------------------------
def get_multipliers(
    zone_id: int | None, event_type: InteractionType, cache: ConfigCache
) -> tuple[float, float]:
    """Returns (xp_multiplier, star_multiplier)."""
    return cache.get_multipliers(zone_id, event_type.value)


# ---------------------------------------------------------------------------
# Full calculation pipeline (§5.11)
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

    Parameters
    ----------
    event : SynapseEvent
    cache : ConfigCache for zone/multiplier/setting lookups
    user_xp : current user XP (for level-up check)
    user_level : current user level
    anti_gaming_tracker : optional tracker instance (for testing)
    """
    # Read tuning params from cache (settings table)
    _gold_per_level = cache.get_int("gold_per_level_up", 50)

    # 1. Zone classification
    zone_id, zone_name = classify_zone(event, cache)

    # 2. Multiplier lookup
    xp_mult, star_mult = get_multipliers(zone_id, event.event_type, cache)

    # 3. Quality modifier (messages only, XP only) — reads thresholds from cache
    quality = calculate_quality_modifier(event, cache)

    # LLM slot (deferred)
    _llm = llm_quality_modifier(event)

    # 4. Base values
    base_xp = BASE_XP.get(event.event_type, 0)
    base_stars = BASE_STARS.get(event.event_type, 0)

    # 5. Anti-gaming adjustments
    base_xp = apply_anti_gaming_xp(event, base_xp)
    adjusted_stars = apply_anti_gaming_stars(
        event, base_stars, tracker=anti_gaming_tracker
    )

    # 6. Calculate final values
    final_xp = int(base_xp * xp_mult * quality * _llm)
    final_stars = int(adjusted_stars * star_mult)

    # 7. Apply XP caps
    final_xp = apply_xp_caps(event, final_xp)

    # 8. Level-up check — uses canonical formula from constants
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
        zone_name=zone_name,
    )
