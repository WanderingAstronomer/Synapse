"""
synapse.services.admin_service — Admin Mutation Service Layer
==============================================================

Shared service module for all admin config mutations per 07 §7.9.
Every write follows the pattern:
  1. Begin transaction
  2. Read "before" snapshot
  3. Apply change
  4. Write admin_log with before/after JSONB
  5. NOTIFY config_changed, '<table>'
  6. Commit
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from synapse.database.models import (
    AchievementCategory,
    AchievementRarity,
    AchievementSeries,
    AchievementTemplate,
    AdminLog,
    ChannelOverride,
    ChannelTypeDefault,
    Season,
)
from synapse.engine.cache import notify_before_commit

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Generic audit helpers
# ---------------------------------------------------------------------------

def _row_to_dict(obj: Any) -> dict | None:
    """Convert a SQLAlchemy model instance to a JSON-serializable dict."""
    if obj is None:
        return None
    result = {}
    for col in obj.__table__.columns:
        val = getattr(obj, col.key if col.key != "metadata" else "metadata_", None)
        if isinstance(val, datetime):
            val = val.isoformat()
        result[col.name] = val
    return result


def _log_admin_action(
    session: Session,
    *,
    actor_id: int,
    action_type: str,
    target_table: str,
    target_id: str | None,
    before: dict | None,
    after: dict | None,
    ip_address: str | None = None,
    reason: str | None = None,
) -> None:
    """Insert a row into admin_log within the current transaction."""
    session.add(AdminLog(
        actor_id=actor_id,
        action_type=action_type,
        target_table=target_table,
        target_id=target_id,
        before_snapshot=before,
        after_snapshot=after,
        ip_address=ip_address,
        reason=reason,
    ))


def _audited_create(
    engine,
    row: Any,
    *,
    table_name: str,
    actor_id: int,
    ip_address: str | None = None,
) -> Any:
    """Generic audited CREATE: add -> flush -> log -> notify -> commit -> return.

    Parameters
    ----------
    row : ORM instance (already constructed, not yet added to a session).
    """
    with Session(engine, expire_on_commit=False) as session:
        session.add(row)
        session.flush()
        _log_admin_action(
            session,
            actor_id=actor_id,
            action_type="CREATE",
            target_table=table_name,
            target_id=str(row.id),
            before=None,
            after=_row_to_dict(row),
            ip_address=ip_address,
        )
        notify_before_commit(session, table_name)
        session.commit()
        session.refresh(row)
        session.expunge(row)
        return row


def _audited_update(
    engine,
    model_cls: type,
    pk: int,
    *,
    table_name: str,
    actor_id: int,
    frozen_keys: tuple[str, ...] = ("id", "guild_id"),
    ip_address: str | None = None,
    **kwargs: Any,
) -> Any | None:
    """Generic audited UPDATE: get -> before -> apply kwargs -> log -> commit.

    Returns the updated (expunged) object, or ``None`` if not found.
    """
    with Session(engine, expire_on_commit=False) as session:
        obj = session.get(model_cls, pk)
        if obj is None:
            return None
        before = _row_to_dict(obj)
        for key, value in kwargs.items():
            if hasattr(obj, key) and key not in frozen_keys:
                setattr(obj, key, value)
        session.flush()
        _log_admin_action(
            session,
            actor_id=actor_id,
            action_type="UPDATE",
            target_table=table_name,
            target_id=str(obj.id),
            before=before,
            after=_row_to_dict(obj),
            ip_address=ip_address,
        )
        notify_before_commit(session, table_name)
        session.commit()
        session.refresh(obj)
        session.expunge(obj)
        return obj


def _audited_delete(
    engine,
    model_cls: type,
    pk: int,
    *,
    table_name: str,
    actor_id: int,
    ip_address: str | None = None,
) -> bool:
    """Generic audited DELETE: get -> log -> delete -> commit -> notify.

    Returns ``True`` if the row existed and was deleted.
    """
    with Session(engine) as session:
        obj = session.get(model_cls, pk)
        if obj is None:
            return False
        _log_admin_action(
            session,
            actor_id=actor_id,
            action_type="DELETE",
            target_table=table_name,
            target_id=str(obj.id),
            before=_row_to_dict(obj),
            after=None,
            ip_address=ip_address,
        )
        session.delete(obj)
        notify_before_commit(session, table_name)
        session.commit()
        return True


# ---------------------------------------------------------------------------
# Channel Type Default CRUD
# ---------------------------------------------------------------------------

def upsert_type_default(
    engine,
    *,
    guild_id: int,
    channel_type: str,
    event_type: str,
    xp_multiplier: float = 1.0,
    star_multiplier: float = 1.0,
    actor_id: int,
) -> ChannelTypeDefault:
    """Create or update a channel type default rule."""
    with Session(engine, expire_on_commit=False) as session:
        existing = session.scalar(
            select(ChannelTypeDefault).where(
                ChannelTypeDefault.guild_id == guild_id,
                ChannelTypeDefault.channel_type == channel_type,
                ChannelTypeDefault.event_type == event_type,
            )
        )
        before = _row_to_dict(existing)

        if existing:
            existing.xp_multiplier = xp_multiplier
            existing.star_multiplier = star_multiplier
            action = "UPDATE"
            obj = existing
        else:
            obj = ChannelTypeDefault(
                guild_id=guild_id,
                channel_type=channel_type,
                event_type=event_type,
                xp_multiplier=xp_multiplier,
                star_multiplier=star_multiplier,
            )
            session.add(obj)
            before = None
            action = "CREATE"

        session.flush()
        _log_admin_action(
            session,
            actor_id=actor_id,
            action_type=action,
            target_table="channel_type_defaults",
            target_id=str(obj.id),
            before=before,
            after=_row_to_dict(obj),
        )
        notify_before_commit(session, "channel_type_defaults")
        session.commit()
        session.refresh(obj)
        session.expunge(obj)
        return obj


def delete_type_default(engine, *, default_id: int, actor_id: int) -> bool:
    """Delete a channel type default. Returns True if found and deleted."""
    return _audited_delete(
        engine, ChannelTypeDefault, default_id,
        table_name="channel_type_defaults", actor_id=actor_id,
    )


# ---------------------------------------------------------------------------
# Channel Override CRUD
# ---------------------------------------------------------------------------

def upsert_channel_override(
    engine,
    *,
    guild_id: int,
    channel_id: int,
    event_type: str,
    xp_multiplier: float = 1.0,
    star_multiplier: float = 1.0,
    reason: str | None = None,
    actor_id: int,
) -> ChannelOverride:
    """Create or update a per-channel override."""
    with Session(engine, expire_on_commit=False) as session:
        existing = session.scalar(
            select(ChannelOverride).where(
                ChannelOverride.guild_id == guild_id,
                ChannelOverride.channel_id == channel_id,
                ChannelOverride.event_type == event_type,
            )
        )
        before = _row_to_dict(existing)

        if existing:
            existing.xp_multiplier = xp_multiplier
            existing.star_multiplier = star_multiplier
            existing.reason = reason
            action = "UPDATE"
            obj = existing
        else:
            obj = ChannelOverride(
                guild_id=guild_id,
                channel_id=channel_id,
                event_type=event_type,
                xp_multiplier=xp_multiplier,
                star_multiplier=star_multiplier,
                reason=reason,
            )
            session.add(obj)
            before = None
            action = "CREATE"

        session.flush()
        _log_admin_action(
            session,
            actor_id=actor_id,
            action_type=action,
            target_table="channel_overrides",
            target_id=str(obj.id),
            before=before,
            after=_row_to_dict(obj),
        )
        notify_before_commit(session, "channel_overrides")
        session.commit()
        session.refresh(obj)
        session.expunge(obj)
        return obj


def delete_channel_override(engine, *, override_id: int, actor_id: int) -> bool:
    """Delete a channel override. Returns True if found and deleted."""
    return _audited_delete(
        engine, ChannelOverride, override_id,
        table_name="channel_overrides", actor_id=actor_id,
    )


# ---------------------------------------------------------------------------
# Achievement Template CRUD
# ---------------------------------------------------------------------------

def create_achievement(
    engine,
    *,
    guild_id: int,
    name: str,
    description: str | None = None,
    category_id: int | None = None,
    rarity_id: int | None = None,
    trigger_type: str = "manual",
    trigger_config: dict | None = None,
    series_id: int | None = None,
    series_order: int | None = None,
    xp_reward: int = 0,
    gold_reward: int = 0,
    badge_image: str | None = None,
    announce_channel_id: int | None = None,
    is_hidden: bool = False,
    max_earners: int | None = None,
    actor_id: int,
    ip_address: str | None = None,
) -> AchievementTemplate:
    """Create a new achievement template."""
    return _audited_create(
        engine,
        AchievementTemplate(
            guild_id=guild_id,
            name=name,
            description=description,
            category_id=category_id,
            rarity_id=rarity_id,
            trigger_type=trigger_type,
            trigger_config=trigger_config or {},
            series_id=series_id,
            series_order=series_order,
            xp_reward=xp_reward,
            gold_reward=gold_reward,
            badge_image=badge_image,
            announce_channel_id=announce_channel_id,
            is_hidden=is_hidden,
            max_earners=max_earners,
        ),
        table_name="achievement_templates",
        actor_id=actor_id,
        ip_address=ip_address,
    )


def update_achievement(
    engine,
    *,
    achievement_id: int,
    actor_id: int,
    ip_address: str | None = None,
    **kwargs,
) -> AchievementTemplate | None:
    """Update an existing achievement template."""
    return _audited_update(
        engine, AchievementTemplate, achievement_id,
        table_name="achievement_templates",
        actor_id=actor_id,
        frozen_keys=("id", "guild_id", "created_at"),
        ip_address=ip_address,
        **kwargs,
    )


def delete_achievement(
    engine,
    *,
    achievement_id: int,
    actor_id: int,
    ip_address: str | None = None,
) -> bool:
    """Delete an achievement template."""
    return _audited_delete(
        engine, AchievementTemplate, achievement_id,
        table_name="achievement_templates",
        actor_id=actor_id,
        ip_address=ip_address,
    )


# ---------------------------------------------------------------------------
# Achievement Category CRUD
# ---------------------------------------------------------------------------

def create_achievement_category(
    engine,
    *,
    guild_id: int,
    name: str,
    icon: str | None = None,
    sort_order: int = 0,
    actor_id: int,
    ip_address: str | None = None,
) -> AchievementCategory:
    """Create a new achievement category."""
    return _audited_create(
        engine,
        AchievementCategory(guild_id=guild_id, name=name, icon=icon, sort_order=sort_order),
        table_name="achievement_categories",
        actor_id=actor_id,
        ip_address=ip_address,
    )


def update_achievement_category(
    engine, *, category_id: int, actor_id: int, ip_address: str | None = None, **kwargs,
) -> AchievementCategory | None:
    """Update an existing achievement category."""
    return _audited_update(
        engine, AchievementCategory, category_id,
        table_name="achievement_categories",
        actor_id=actor_id,
        ip_address=ip_address,
        **kwargs,
    )


def delete_achievement_category(
    engine, *, category_id: int, actor_id: int, ip_address: str | None = None,
) -> bool:
    """Delete an achievement category."""
    return _audited_delete(
        engine, AchievementCategory, category_id,
        table_name="achievement_categories",
        actor_id=actor_id,
        ip_address=ip_address,
    )


# ---------------------------------------------------------------------------
# Achievement Rarity CRUD
# ---------------------------------------------------------------------------

def create_achievement_rarity(
    engine,
    *,
    guild_id: int,
    name: str,
    color: str = "#9e9e9e",
    sort_order: int = 0,
    actor_id: int,
    ip_address: str | None = None,
) -> AchievementRarity:
    """Create a new achievement rarity tier."""
    return _audited_create(
        engine,
        AchievementRarity(guild_id=guild_id, name=name, color=color, sort_order=sort_order),
        table_name="achievement_rarities",
        actor_id=actor_id,
        ip_address=ip_address,
    )


def update_achievement_rarity(
    engine, *, rarity_id: int, actor_id: int, ip_address: str | None = None, **kwargs,
) -> AchievementRarity | None:
    """Update an existing achievement rarity tier."""
    return _audited_update(
        engine, AchievementRarity, rarity_id,
        table_name="achievement_rarities",
        actor_id=actor_id,
        ip_address=ip_address,
        **kwargs,
    )


def delete_achievement_rarity(
    engine, *, rarity_id: int, actor_id: int, ip_address: str | None = None,
) -> bool:
    """Delete an achievement rarity tier."""
    return _audited_delete(
        engine, AchievementRarity, rarity_id,
        table_name="achievement_rarities",
        actor_id=actor_id,
        ip_address=ip_address,
    )


# ---------------------------------------------------------------------------
# Achievement Series CRUD
# ---------------------------------------------------------------------------

def create_achievement_series(
    engine,
    *,
    guild_id: int,
    name: str,
    description: str | None = None,
    actor_id: int,
    ip_address: str | None = None,
) -> AchievementSeries:
    """Create a new achievement series."""
    return _audited_create(
        engine,
        AchievementSeries(guild_id=guild_id, name=name, description=description),
        table_name="achievement_series",
        actor_id=actor_id,
        ip_address=ip_address,
    )


def update_achievement_series(
    engine, *, series_id: int, actor_id: int, ip_address: str | None = None, **kwargs,
) -> AchievementSeries | None:
    """Update an existing achievement series."""
    return _audited_update(
        engine, AchievementSeries, series_id,
        table_name="achievement_series",
        actor_id=actor_id,
        ip_address=ip_address,
        **kwargs,
    )


def delete_achievement_series(
    engine, *, series_id: int, actor_id: int, ip_address: str | None = None,
) -> bool:
    """Delete an achievement series."""
    return _audited_delete(
        engine, AchievementSeries, series_id,
        table_name="achievement_series",
        actor_id=actor_id,
        ip_address=ip_address,
    )


# ---------------------------------------------------------------------------
# Season Management
# ---------------------------------------------------------------------------

def create_season(
    engine,
    *,
    guild_id: int,
    name: str,
    starts_at: datetime,
    ends_at: datetime,
    actor_id: int,
    ip_address: str | None = None,
    activate: bool = True,
) -> Season:
    """Create a new season, optionally deactivating the current one."""
    with Session(engine, expire_on_commit=False) as session:
        if activate:
            current = session.scalar(
                select(Season).where(
                    Season.guild_id == guild_id, Season.active.is_(True)
                )
            )
            if current:
                before_curr = _row_to_dict(current)
                current.active = False
                _log_admin_action(
                    session,
                    actor_id=actor_id,
                    action_type="SEASON_ROLL",
                    target_table="seasons",
                    target_id=str(current.id),
                    before=before_curr,
                    after=_row_to_dict(current),
                    ip_address=ip_address,
                )

        season = Season(
            guild_id=guild_id,
            name=name,
            starts_at=starts_at,
            ends_at=ends_at,
            active=activate,
        )
        session.add(season)
        session.flush()
        _log_admin_action(
            session,
            actor_id=actor_id,
            action_type="CREATE",
            target_table="seasons",
            target_id=str(season.id),
            before=None,
            after=_row_to_dict(season),
            ip_address=ip_address,
        )
        session.commit()

        session.refresh(season)
        session.expunge(season)
        return season
