"""
synapse.engine.achievements — Achievement Check Pipeline
==========================================================

Implements the achievement check pipeline per 06_ACHIEVEMENTS.md §6.5.
After the reward engine calculates XP and Stars, this module checks
whether any achievement templates have been triggered.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from synapse.database.models import InteractionType

if TYPE_CHECKING:
    from synapse.engine.cache import ConfigCache

logger = logging.getLogger(__name__)

# Stat fields that can be used in counter_threshold achievements
VALID_STAT_FIELDS = {
    "messages_sent",
    "reactions_given",
    "reactions_received",
    "threads_created",
    "voice_minutes",
}

# Map InteractionType → stat field to increment
EVENT_TO_STAT: dict[InteractionType, str] = {
    InteractionType.MESSAGE: "messages_sent",
    InteractionType.REACTION_GIVEN: "reactions_given",
    InteractionType.REACTION_RECEIVED: "reactions_received",
    InteractionType.THREAD_CREATE: "threads_created",
}


def check_achievements(
    guild_id: int,
    cache: ConfigCache,
    *,
    user_xp: int,
    season_stars: int,
    lifetime_stars: int,
    stats: dict[str, int],
    already_earned: set[int],
) -> list[int]:
    """Check which achievements the user has newly earned.

    Parameters
    ----------
    guild_id : Discord guild ID
    cache : ConfigCache instance
    user_xp : User's total XP (after this event's delta)
    season_stars : Current season stars
    lifetime_stars : Lifetime stars
    stats : Dict of user_stats column values (e.g. {"messages_sent": 105})
    already_earned : Set of achievement template IDs the user already has

    Returns
    -------
    List of achievement template IDs that were newly triggered.
    """
    templates = cache.get_active_achievements(guild_id)
    newly_earned: list[int] = []

    for template in templates:
        # Skip if already earned
        if template.id in already_earned:
            continue

        # Skip custom achievements (manual only, §6.3)
        if template.requirement_type == "custom":
            continue

        triggered = False

        if template.requirement_type == "counter_threshold":
            field_name = template.requirement_field
            if field_name and field_name in VALID_STAT_FIELDS:
                current = stats.get(field_name, 0)
                if (
                    template.requirement_value is not None
                    and current >= template.requirement_value
                ):
                    triggered = True

        elif template.requirement_type == "star_threshold":
            # Check against appropriate scope
            if template.requirement_scope == "season":
                check_value = season_stars
            else:
                check_value = lifetime_stars
            if (
                template.requirement_value is not None
                and check_value >= template.requirement_value
            ):
                triggered = True

        elif template.requirement_type == "xp_milestone":
            if template.requirement_value is not None and user_xp >= template.requirement_value:
                triggered = True

        if triggered:
            newly_earned.append(template.id)
            logger.info(
                "Achievement triggered: %s (id=%d) for guild %d",
                template.name, template.id, guild_id,
            )

    return newly_earned
