"""
synapse.services.reward_service — Event Persistence & Reward Application
=========================================================================

Shared service module callable by both bot and dashboard.
Handles idempotent event persistence, XP/Star/Gold application,
stat counter updates, and achievement awarding.

Per D02-06: inserts use ON CONFLICT DO NOTHING on (source_system, source_event_id).
"""

from __future__ import annotations

import dataclasses
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from synapse.constants import xp_for_level
from synapse.database.models import (
    AchievementTemplate,
    ActivityLog,
    EventCounter,
    EventLake,
    InteractionType,
    RewardRule,
    RuleEvaluation,
    RuleSnapshot,
    Season,
    User,
    UserAchievement,
    UserStats,
)
from synapse.engine.achievements import EVENT_TO_STAT, AchievementContext, check_achievements
from synapse.engine.events import EventType, SynapseEvent
from synapse.engine.reward import RewardResult
from synapse.engine.rule_engine import RuleEngine, RuleEvaluationResult

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
        select(UserAchievement.achievement_id).where(UserAchievement.user_id == user_id)
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


# ---------------------------------------------------------------------------
# Context injection
# ---------------------------------------------------------------------------


def _build_event_context(session: Session, user_id: int, user: User) -> dict:
    """Build the context bucket for rule evaluation from event_counters.

    Queries the pre-computed ``event_counters`` table to populate scaling
    variables (daily/lifetime counts) and attaches the current user state.
    Called once per ``process_event`` invocation.
    """
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    day_key = f"day:{today}"

    rows = session.execute(
        select(
            EventCounter.event_type,
            EventCounter.period,
            EventCounter.count,
        ).where(
            EventCounter.user_id == user_id,
            EventCounter.event_type.in_(
                [
                    EventType.MESSAGE_CREATE,
                    EventType.REACTION_ADD,
                    EventType.VOICE_LEAVE,
                ]
            ),
        )
    ).all()

    counter_map: dict[tuple[str, str], int] = {
        (row.event_type, row.period): row.count for row in rows
    }

    return {
        "messages_today": counter_map.get((EventType.MESSAGE_CREATE, day_key), 0),
        "messages_lifetime": counter_map.get((EventType.MESSAGE_CREATE, "lifetime"), 0),
        "reactions_today": counter_map.get((EventType.REACTION_ADD, day_key), 0),
        "voice_minutes_today": counter_map.get((EventType.VOICE_LEAVE, day_key), 0),
        "user_level": user.level,
        "user_xp": user.xp,
    }


# ---------------------------------------------------------------------------
# Shadow rule evaluation
# ---------------------------------------------------------------------------


def _evaluate_rules(
    session: Session,
    event: SynapseEvent,
    guild_id: int,
) -> tuple[RuleEvaluationResult, int] | None:
    """Run the RuleEngine and persist the evaluation trace.

    Returns (RuleEvaluationResult, rule_evaluation_id) or None.
    the outcomes to drive rewards (when ``flags.firewall_enabled`` is True).
    Returns ``None`` when no active rules exist for the guild.

    Must be called inside a ``session.begin_nested()`` SAVEPOINT when
    operating in shadow mode so failures are isolated.

    Parameters
    ----------
    session : Session
        The active SQLAlchemy session.
    event : SynapseEvent
        The enriched event (with context injected).
    guild_id : int
        The guild for which to load active rules.
    """
    active_rules = session.scalars(
        select(RewardRule)
        .where(
            RewardRule.guild_id == guild_id,
            RewardRule.is_active.is_(True),
        )
        .order_by(RewardRule.priority.desc())
    ).all()

    if not active_rules:
        return None  # No rules seeded yet — skip silently

    rules_data = [
        {
            "id": r.id,
            "name": r.name,
            "priority": r.priority,
            "predicates": r.predicates if isinstance(r.predicates, list) else [],
            "outcomes": r.outcomes if isinstance(r.outcomes, list) else [],
        }
        for r in active_rules
    ]

    eval_result = RuleEngine().evaluate(event, rules_data, event.context)

    # Resolve event_lake_id via the idempotency source_id (nullable)
    event_lake_id: int | None = None
    if event.source_event_id is not None:
        event_lake_id = session.scalar(
            select(EventLake.id).where(EventLake.source_id == event.source_event_id)
        )

    # Resolve active snapshot for this guild (may be None if never published)
    snapshot_id: int | None = session.scalar(
        select(RuleSnapshot.id).where(
            RuleSnapshot.guild_id == guild_id,
            RuleSnapshot.is_active.is_(True),
        )
    )

    eval_obj = RuleEvaluation(
        guild_id=guild_id,
        user_id=event.user_id,
        event_lake_id=event_lake_id,
        snapshot_id=snapshot_id,
        matched_rules=eval_result.matched_rules,
        outcomes_applied=eval_result.outcomes_applied,
        context_snapshot=eval_result.context_snapshot,
    )
    session.add(eval_obj)
    session.flush()

    return eval_result, eval_obj.id


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

        # Context injection (Phase 3): populate event.context for RuleEngine
        ctx = _build_event_context(session, event.user_id, user)
        enriched_event = dataclasses.replace(event, context=ctx)

        rule_eval_id: int | None = None

        # -----------------------------------------------------------
        # Reward calculation — Rule Engine (The Firewall)
        # -----------------------------------------------------------
        # RuleEngine is the authoritative and ONLY reward path.
        # If no rules match, the result is zero (pure intent-based auto-OS).
        res_tuple = _evaluate_rules(session, enriched_event, event.guild_id)
        if res_tuple is not None:
            eval_result, rule_eval_id = res_tuple
            oa = eval_result.outcomes_applied
            fw_xp = int(oa.get("xp", 0))
            fw_gold = int(oa.get("gold", 0))

            # Level-up check
            new_xp = user.xp + fw_xp
            required = xp_for_level(user.level + 1, cache)
            leveled_up = new_xp >= required and fw_xp > 0
            new_level = user.level + 1 if leveled_up else None
            gold_per_level = cache.get_int("gold_per_level_up", 50)
            gold_bonus = (fw_gold + gold_per_level) if leveled_up else fw_gold

            result = RewardResult(
                xp=fw_xp,
                leveled_up=leveled_up,
                new_level=new_level,
                gold_bonus=gold_bonus,
            )
        else:
            # No active rules — reward nothing (pure intent-based).
            result = RewardResult(xp=0)

        # Idempotent insert into activity_log
        if event.source_event_id is not None:
            # Use SAVEPOINT + IntegrityError to handle the partial unique
            # index (ix_activity_log_idempotent).
            log = ActivityLog(
                user_id=event.user_id,
                event_type=event.event_type.value,
                season_id=season_id,
                source_system="discord",
                source_event_id=event.source_event_id,
                xp_delta=result.xp,
                metadata_=event.metadata,
                timestamp=event.timestamp,
                rule_evaluation_id=rule_eval_id,
            )
            try:
                with session.begin_nested():  # SAVEPOINT
                    session.add(log)
                    session.flush()
            except IntegrityError:
                # Duplicate event — partial index caught it.
                # Rolled back by begin_nested(), but we must not commit the orphan RuleEvaluation
                # that happened before the savepoint.
                session.rollback()
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
                metadata_=event.metadata,
                timestamp=event.timestamp,
                rule_evaluation_id=rule_eval_id,
            )
            session.add(log)

        # Update user XP, level, gold
        old_level = user.level
        user.xp += result.xp
        if result.leveled_up and result.new_level is not None:
            user.level = result.new_level
            user.gold += result.gold_bonus

            # Log level-up event
            session.add(
                ActivityLog(
                    user_id=user.id,
                    event_type=InteractionType.LEVEL_UP.value,
                    season_id=season_id,
                    source_system="discord",
                    xp_delta=0,
                    metadata_={"old_level": old_level, "new_level": user.level},
                )
            )

        # Update season stats
        if season_id is not None:
            stats = get_or_create_stats(session, event.user_id, season_id)

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
                stats=stats_dict,
                event_type=event.event_type,
                event_counts=event_counts,
                member_since=user.created_at,
            )

            new_achievements = check_achievements(
                event.guild_id,
                cache,
                ctx,
                earned_ids,
            )

            validated_achievements = []
            for tmpl_id in new_achievements:
                # Get template for bonus rewards AND check max_earners constraint
                # Use with_for_update=True to lock the row and prevent race conditions
                tmpl = session.get(AchievementTemplate, tmpl_id, with_for_update=True)
                if not tmpl:
                    continue

                # Enforce max_earners (Phase 7 deferred fix P07-02)
                if tmpl.max_earners is not None:
                    from sqlalchemy import func as sa_func

                    current_count = session.scalar(
                        select(sa_func.count()).where(
                            UserAchievement.achievement_id == tmpl_id
                        )
                    )
                    # current_count might be None if no rows? No, count() returns 0.
                    if (current_count or 0) >= tmpl.max_earners:
                        logger.info(
                            "Achievement %s (id=%d) skipped for user %d: "
                            "max_earners limit reached (%d/%d)",
                            tmpl.name,
                            tmpl.id,
                            event.user_id,
                            current_count,
                            tmpl.max_earners,
                        )
                        continue

                # Award the achievement
                session.add(
                    UserAchievement(
                        user_id=event.user_id,
                        achievement_id=tmpl_id,
                    )
                )
                validated_achievements.append(tmpl_id)

                user.xp += tmpl.xp_reward
                user.gold += tmpl.gold_reward

                # Log achievement earned
                session.add(
                    ActivityLog(
                        user_id=event.user_id,
                        event_type=InteractionType.ACHIEVEMENT_EARNED.value,
                        season_id=season_id,
                        source_system="discord",
                        xp_delta=tmpl.xp_reward,
                        metadata_={
                            "achievement_id": tmpl.id,
                            "achievement_name": tmpl.name,
                        },
                    )
                )

            result.achievements_earned = validated_achievements

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

        session.add(
            ActivityLog(
                user_id=user_id,
                event_type=InteractionType.MANUAL_AWARD.value,
                season_id=season_id,
                source_system="admin",
                xp_delta=xp,
                metadata_={"admin_id": admin_id, "reason": reason},
            )
        )

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
        session.add(
            UserAchievement(
                user_id=user_id,
                achievement_id=achievement_id,
                granted_by=admin_id,
            )
        )

        user.xp += template.xp_reward
        user.gold += template.gold_reward

        session.add(
            ActivityLog(
                user_id=user_id,
                event_type=InteractionType.ACHIEVEMENT_EARNED.value,
                season_id=season_id,
                source_system="admin",
                xp_delta=template.xp_reward,
                metadata_={
                    "achievement_id": template.id,
                    "achievement_name": template.name,
                    "admin_id": admin_id,
                },
            )
        )

        session.commit()
        return True, f"Achievement '{template.name}' granted."
