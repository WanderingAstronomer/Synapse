"""
synapse.engine.achievements — Achievement Check Pipeline v2
=============================================================

Handler-registry implementation for achievement trigger evaluation.
Each TriggerType maps to a pure handler function that receives an
AchievementContext and the template's trigger_config JSONB.

This module is pure calculation — no database I/O, no Discord I/O.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from synapse.database.models import InteractionType, TriggerType

if TYPE_CHECKING:
    from synapse.engine.cache import ConfigCache

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Valid stat fields for stat_threshold triggers
# ---------------------------------------------------------------------------
VALID_STAT_FIELDS: set[str] = {
    "messages_sent",
    "reactions_given",
    "reactions_received",
    "threads_created",
    "voice_minutes",
}

# Map InteractionType → UserStats field to increment
EVENT_TO_STAT: dict[InteractionType, str] = {
    InteractionType.MESSAGE: "messages_sent",
    InteractionType.REACTION_GIVEN: "reactions_given",
    InteractionType.REACTION_RECEIVED: "reactions_received",
    InteractionType.THREAD_CREATE: "threads_created",
}


# ---------------------------------------------------------------------------
# Achievement Context — passed to every trigger handler
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class AchievementContext:
    """Snapshot of user state passed to trigger handlers.

    Parameters
    ----------
    user_xp : Total accumulated XP (after this event's delta).
    user_level : Current level (after any level-up).
    old_level : Level before this event (None if not a level-up event).
    stats : Dict of UserStats column values (e.g. {"messages_sent": 105}).
    event_type : The InteractionType that triggered this check (or None).
    event_counts : Mapping of event_type string → total occurrences for
        this user.  Populated from activity_log when needed.
    member_since : When the user first appeared (User.created_at).
        Used by the ``member_tenure`` trigger handler.
    """

    user_xp: int = 0
    user_level: int = 1
    old_level: int | None = None
    stats: dict[str, int] = field(default_factory=dict)
    event_type: InteractionType | None = None
    event_counts: dict[str, int] = field(default_factory=dict)
    member_since: datetime | None = None


# ---------------------------------------------------------------------------
# Trigger handlers — pure functions (config, ctx) → bool
# ---------------------------------------------------------------------------


def _check_stat_threshold(config: dict, ctx: AchievementContext) -> bool:
    """Fires when a UserStats field reaches a threshold value.

    Config: {"field": "messages_sent", "value": 100}
    """
    field_name = config.get("field", "")
    if field_name not in VALID_STAT_FIELDS:
        return False
    value = config.get("value")
    if value is None:
        return False
    return ctx.stats.get(field_name, 0) >= value


def _check_xp_milestone(config: dict, ctx: AchievementContext) -> bool:
    """Fires when total XP reaches a threshold.

    Config: {"value": 5000}
    """
    value = config.get("value")
    if value is None:
        return False
    return ctx.user_xp >= value


def _check_level_reached(config: dict, ctx: AchievementContext) -> bool:
    """Fires when the user reaches (or surpasses) a specific level.

    Config: {"value": 10}
    """
    value = config.get("value")
    if value is None:
        return False
    return ctx.user_level >= value


def _check_level_interval(config: dict, ctx: AchievementContext) -> bool:
    """Fires when the user's level is a multiple of an interval.

    Only triggers on level-up events (old_level must differ from user_level).
    Config: {"interval": 10}
    """
    interval = config.get("interval")
    if interval is None or interval <= 0:
        return False
    # Only fire on an actual level-up
    if ctx.old_level is None or ctx.old_level == ctx.user_level:
        return False
    # Check if the new level crosses an interval boundary
    return ctx.user_level % interval == 0


def _check_event_count(config: dict, ctx: AchievementContext) -> bool:
    """Fires when the total count of a specific event type reaches N.

    Uses activity_log counts passed in ctx.event_counts.
    Config: {"event_type": "MESSAGE", "count": 50}
    """
    event_type = config.get("event_type", "")
    count = config.get("count")
    if count is None or not event_type:
        return False
    return ctx.event_counts.get(event_type, 0) >= count


def _check_first_event(config: dict, ctx: AchievementContext) -> bool:
    """Fires on the first occurrence of a specific event type.

    Config: {"event_type": "MESSAGE"}
    """
    event_type = config.get("event_type", "")
    if not event_type:
        return False
    return ctx.event_counts.get(event_type, 0) >= 1


def _check_member_tenure(config: dict, ctx: AchievementContext) -> bool:
    """Fires when a member has been in the server for N days.

    Config: {"days": 365}

    Uses ``ctx.member_since`` (populated from ``User.created_at`` which
    records the first time Synapse observed the member).
    """
    if ctx.member_since is None:
        return False
    days_required = config.get("days")
    if days_required is None:
        return False
    now = datetime.now(UTC)
    # Ensure member_since is timezone-aware for comparison
    member_since = ctx.member_since
    if member_since.tzinfo is None:
        member_since = member_since.replace(tzinfo=UTC)
    elapsed = (now - member_since).days
    return elapsed >= int(days_required)


def _check_invite_count(config: dict, ctx: AchievementContext) -> bool:
    """Fires when a member has successfully invited N users.

    Config: {"count": 10}

    Deferred — requires Discord invite tracking infrastructure that is not
    yet implemented.  Invite data is not available through the Gateway
    without privileged intents and periodic polling.
    """
    logger.warning(
        "invite_count trigger evaluated but invite tracking is not yet implemented "
        "— achievement will never fire (config=%s)",
        config,
    )
    return False


# ---------------------------------------------------------------------------
# Handler registry
# ---------------------------------------------------------------------------
TRIGGER_HANDLERS: dict[str, Callable[[dict, AchievementContext], bool]] = {
    TriggerType.STAT_THRESHOLD: _check_stat_threshold,
    TriggerType.XP_MILESTONE: _check_xp_milestone,
    TriggerType.LEVEL_REACHED: _check_level_reached,
    TriggerType.LEVEL_INTERVAL: _check_level_interval,
    TriggerType.EVENT_COUNT: _check_event_count,
    TriggerType.FIRST_EVENT: _check_first_event,
    TriggerType.MEMBER_TENURE: _check_member_tenure,
    TriggerType.INVITE_COUNT: _check_invite_count,
    # TriggerType.MANUAL intentionally omitted — never auto-triggered
}


# ---------------------------------------------------------------------------
# Main check function
# ---------------------------------------------------------------------------
def check_achievements(
    guild_id: int,
    cache: ConfigCache,
    ctx: AchievementContext,
    already_earned: set[int],
) -> list[int]:
    """Check which achievements the user has newly earned.

    Parameters
    ----------
    guild_id : Discord guild ID.
    cache : ConfigCache instance.
    ctx : AchievementContext with current user state.
    already_earned : Set of achievement template IDs the user already has.

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

        # Series gating: if in a series, previous tier must be earned
        if (
            template.series_id is not None
            and template.series_order is not None
            and template.series_order > 1
        ):
            predecessor = cache.get_series_predecessor(
                template.series_id,
                template.series_order,
            )
            if predecessor is not None and predecessor.id not in already_earned:
                continue

        # Look up the handler for this trigger type
        handler = TRIGGER_HANDLERS.get(template.trigger_type)
        if handler is None:
            # Unknown or MANUAL type — skip
            continue

        config = template.trigger_config or {}
        if handler(config, ctx):
            newly_earned.append(template.id)
            logger.info(
                "Achievement triggered: %s (id=%d) for guild %d",
                template.name,
                template.id,
                guild_id,
            )

    return newly_earned
