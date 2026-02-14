"""
synapse.services.reward_service — Event Persistence & Reward Application
=========================================================================

Shared service module callable by both bot and dashboard.
Handles idempotent event persistence, XP/Star/Gold application,
stat counter updates, and achievement awarding.

Per D02-06: inserts use ON CONFLICT DO NOTHING on (source_system, source_event_id).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from synapse.database.models import (
    AchievementTemplate,
    ActivityLog,
    InteractionType,
    Season,
    User,
    UserAchievement,
    UserStats,
)
from synapse.engine.achievements import EVENT_TO_STAT, AchievementContext, check_achievements
from synapse.engine.events import SynapseEvent
from synapse.engine.reward import RewardResult, calculate_reward

if TYPE_CHECKING:
    from sqlalchemy import Engine

    from synapse.engine.cache import ConfigCache

logger = logging.getLogger(__name__)


def get_or_create_user(session: Session, user_id: int, display_name: str) -> User:
    """Fetch or insert a User row."""
    user = session.get(User, user_id)
    if user is None:
        user = User(id=user_id, discord_name=display_name)
        session.add(user)
        session.flush()
    else:
        user.discord_name = display_name
    return user


def get_active_season(session: Session, guild_id: int) -> Season | None:
    """Get the currently active season for a guild."""
    return session.scalar(
        select(Season).where(Season.guild_id == guild_id, Season.active.is_(True))
    )


def get_or_create_stats(session: Session, user_id: int, season_id: int) -> UserStats:
    """Fetch or create the UserStats row for user+season."""
    stats = session.get(UserStats, (user_id, season_id))
    if stats is None:
        stats = UserStats(user_id=user_id, season_id=season_id)
        session.add(stats)
        session.flush()
    return stats


def get_earned_achievement_ids(session: Session, user_id: int) -> set[int]:
    """Get set of achievement template IDs the user has already earned."""
    rows = session.scalars(
        select(UserAchievement.achievement_id).where(
            UserAchievement.user_id == user_id
        )
    ).all()
    return set(rows)


def _get_event_counts(session: Session, user_id: int) -> dict[str, int]:
    """Build a mapping of event_type → total count from activity_log.

    Used by event_count and first_event achievement triggers.
    """
    from sqlalchemy import func as sa_func

    rows = session.execute(
        select(
            ActivityLog.event_type,
            sa_func.count().label("cnt"),
        )
        .where(ActivityLog.user_id == user_id)
        .group_by(ActivityLog.event_type)
    ).all()
    return {row.event_type: row.cnt for row in rows}


def process_event(
    engine: Engine,
    cache: ConfigCache,
    event: SynapseEvent,
    display_name: str,
) -> tuple[RewardResult, bool]:
    """Process a SynapseEvent through the full pipeline.

    1. Calculate rewards via engine
    2. Persist idempotently
    3. Update user XP/level/gold
    4. Update season stats
    5. Check and award achievements

    Returns (RewardResult, was_duplicate).
    If was_duplicate is True, the event was already processed (no changes made).
    """
    with Session(engine) as session:
        # Get user and season context
        user = get_or_create_user(session, event.user_id, display_name)
        season = get_active_season(session, event.guild_id)
        season_id = season.id if season else None

        # Calculate reward
        result = calculate_reward(
            event,
            cache,
            user_xp=user.xp,
            user_level=user.level,
        )

        # Idempotent insert into activity_log
        if event.source_event_id is not None:
            # Use SAVEPOINT + IntegrityError to handle the partial unique
            # index (ix_activity_log_idempotent).  SQLAlchemy's
            # on_conflict_do_nothing cannot reliably match partial indexes,
            # so we let the DB enforce uniqueness directly.
            log = ActivityLog(
                user_id=event.user_id,
                event_type=event.event_type.value,
                season_id=season_id,
                source_system="discord",
                source_event_id=event.source_event_id,
                xp_delta=result.xp,
                star_delta=result.stars,
                metadata_=event.metadata,
                timestamp=event.timestamp,
            )
            try:
                with session.begin_nested():   # SAVEPOINT
                    session.add(log)
                    session.flush()
            except IntegrityError:
                # Duplicate event — partial index caught it.
                # The SAVEPOINT was rolled back; the outer txn is still alive.
                session.commit()
                return result, True
        else:
            # Events without natural keys (e.g., voice ticks) — always insert
            log = ActivityLog(
                user_id=event.user_id,
                event_type=event.event_type.value,
                season_id=season_id,
                source_system="discord",
                source_event_id=None,
                xp_delta=result.xp,
                star_delta=result.stars,
                metadata_=event.metadata,
                timestamp=event.timestamp,
            )
            session.add(log)

        # Update user XP, level, gold
        old_level = user.level
        user.xp += result.xp
        if result.leveled_up and result.new_level is not None:
            user.level = result.new_level
            user.gold += result.gold_bonus

            # Log level-up event
            session.add(ActivityLog(
                user_id=user.id,
                event_type=InteractionType.LEVEL_UP.value,
                season_id=season_id,
                source_system="discord",
                xp_delta=0,
                star_delta=0,
                metadata_={"old_level": old_level, "new_level": user.level},
            ))

        # Update season stats
        if season_id is not None:
            stats = get_or_create_stats(session, event.user_id, season_id)
            stats.season_stars += result.stars
            stats.lifetime_stars += result.stars

            # Increment the appropriate counter
            stat_field = EVENT_TO_STAT.get(event.event_type)
            if stat_field:
                current = getattr(stats, stat_field, 0)
                setattr(stats, stat_field, current + 1)

            if event.event_type == InteractionType.VOICE_TICK:
                tick_minutes = cache.get_int("voice_tick_minutes", 10)
                stats.voice_minutes += tick_minutes

            # Build achievement context
            earned_ids = get_earned_achievement_ids(session, event.user_id)
            stats_dict = {
                "messages_sent": stats.messages_sent,
                "reactions_given": stats.reactions_given,
                "reactions_received": stats.reactions_received,
                "threads_created": stats.threads_created,
                "voice_minutes": stats.voice_minutes,
            }
            event_counts = _get_event_counts(session, event.user_id)

            ctx = AchievementContext(
                user_xp=user.xp,
                user_level=user.level,
                old_level=old_level if result.leveled_up else None,
                season_stars=stats.season_stars,
                lifetime_stars=stats.lifetime_stars,
                stats=stats_dict,
                event_type=event.event_type,
                event_counts=event_counts,
            )

            new_achievements = check_achievements(
                event.guild_id,
                cache,
                ctx,
                earned_ids,
            )

            for tmpl_id in new_achievements:
                # Award the achievement
                session.add(UserAchievement(
                    user_id=event.user_id,
                    achievement_id=tmpl_id,
                ))

                # Get template for bonus rewards
                tmpl = session.get(AchievementTemplate, tmpl_id)
                if tmpl:
                    user.xp += tmpl.xp_reward
                    user.gold += tmpl.gold_reward

                    # Log achievement earned
                    session.add(ActivityLog(
                        user_id=event.user_id,
                        event_type=InteractionType.ACHIEVEMENT_EARNED.value,
                        season_id=season_id,
                        source_system="discord",
                        xp_delta=tmpl.xp_reward,
                        star_delta=0,
                        metadata_={
                            "achievement_id": tmpl.id,
                            "achievement_name": tmpl.name,
                        },
                    ))

            result.achievements_earned = new_achievements

        session.commit()
        return result, False


def award_manual(
    engine: Engine,
    *,
    user_id: int,
    display_name: str,
    guild_id: int,
    xp: int = 0,
    gold: int = 0,
    reason: str = "",
    admin_id: int,
) -> User:
    """Award XP and/or Gold manually (admin command or dashboard)."""
    with Session(engine, expire_on_commit=False) as session:
        user = get_or_create_user(session, user_id, display_name)
        season = get_active_season(session, guild_id)
        season_id = season.id if season else None

        user.xp += xp
        user.gold += gold

        session.add(ActivityLog(
            user_id=user_id,
            event_type=InteractionType.MANUAL_AWARD.value,
            season_id=season_id,
            source_system="admin",
            xp_delta=xp,
            star_delta=0,
            metadata_={"admin_id": admin_id, "reason": reason},
        ))

        session.commit()
        session.refresh(user)
        session.expunge(user)
        return user


def grant_achievement(
    engine: Engine,
    *,
    user_id: int,
    display_name: str,
    guild_id: int,
    achievement_id: int,
    admin_id: int,
) -> tuple[bool, str]:
    """Grant a specific achievement to a user.

    Returns (success, message).
    """
    with Session(engine) as session:
        user = get_or_create_user(session, user_id, display_name)
        season = get_active_season(session, guild_id)
        season_id = season.id if season else None

        # Check if already earned
        existing = session.get(UserAchievement, (user_id, achievement_id))
        if existing:
            return False, "User has already earned this achievement."

        # Get template
        template = session.get(AchievementTemplate, achievement_id)
        if not template:
            return False, "Achievement template not found."

        # Award
        session.add(UserAchievement(
            user_id=user_id,
            achievement_id=achievement_id,
            granted_by=admin_id,
        ))

        user.xp += template.xp_reward
        user.gold += template.gold_reward

        session.add(ActivityLog(
            user_id=user_id,
            event_type=InteractionType.ACHIEVEMENT_EARNED.value,
            season_id=season_id,
            source_system="admin",
            xp_delta=template.xp_reward,
            star_delta=0,
            metadata_={
                "achievement_id": template.id,
                "achievement_name": template.name,
                "admin_id": admin_id,
            },
        ))

        session.commit()
        return True, f"Achievement '{template.name}' granted."
