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
    AchievementTemplate,
    AdminLog,
    Season,
    Zone,
    ZoneChannel,
    ZoneMultiplier,
)
from synapse.engine.cache import send_notify

logger = logging.getLogger(__name__)


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


# ---------------------------------------------------------------------------
# Zone CRUD
# ---------------------------------------------------------------------------
def create_zone(
    engine,
    *,
    guild_id: int,
    name: str,
    description: str | None = None,
    channel_ids: list[int] | None = None,
    multipliers: dict[str, tuple[float, float]] | None = None,
    actor_id: int,
    ip_address: str | None = None,
) -> Zone:
    """Create a new zone with optional channels and multipliers."""
    with Session(engine) as session:
        zone = Zone(
            guild_id=guild_id,
            name=name,
            description=description,
            created_by=actor_id,
        )
        session.add(zone)
        session.flush()  # Get zone.id

        # Add channels
        if channel_ids:
            for ch_id in channel_ids:
                session.add(ZoneChannel(zone_id=zone.id, channel_id=ch_id))

        # Add multipliers
        if multipliers:
            for itype, (xp_m, star_m) in multipliers.items():
                session.add(ZoneMultiplier(
                    zone_id=zone.id,
                    interaction_type=itype,
                    xp_multiplier=xp_m,
                    star_multiplier=star_m,
                ))

        session.flush()
        after = _row_to_dict(zone)
        _log_admin_action(
            session,
            actor_id=actor_id,
            action_type="CREATE",
            target_table="zones",
            target_id=str(zone.id),
            before=None,
            after=after,
            ip_address=ip_address,
        )
        session.commit()

        # NOTIFY after commit
        send_notify(engine, "zones")
        send_notify(engine, "zone_channels")
        if multipliers:
            send_notify(engine, "zone_multipliers")

        session.refresh(zone)
        session.expunge(zone)
        return zone


def update_zone(
    engine,
    *,
    zone_id: int,
    name: str | None = None,
    description: str | None = None,
    active: bool | None = None,
    channel_ids: list[int] | None = None,
    multipliers: dict[str, tuple[float, float]] | None = None,
    actor_id: int,
    ip_address: str | None = None,
) -> Zone | None:
    """Update an existing zone."""
    with Session(engine) as session:
        zone = session.get(Zone, zone_id)
        if not zone:
            return None

        before = _row_to_dict(zone)

        if name is not None:
            zone.name = name
        if description is not None:
            zone.description = description
        if active is not None:
            zone.active = active

        # Replace channels if provided
        if channel_ids is not None:
            # Delete existing
            for ch in list(zone.channels):
                session.delete(ch)
            session.flush()
            for ch_id in channel_ids:
                session.add(ZoneChannel(zone_id=zone.id, channel_id=ch_id))

        # Replace multipliers if provided
        if multipliers is not None:
            for m in list(zone.multipliers):
                session.delete(m)
            session.flush()
            for itype, (xp_m, star_m) in multipliers.items():
                session.add(ZoneMultiplier(
                    zone_id=zone.id,
                    interaction_type=itype,
                    xp_multiplier=xp_m,
                    star_multiplier=star_m,
                ))

        session.flush()
        after = _row_to_dict(zone)
        _log_admin_action(
            session,
            actor_id=actor_id,
            action_type="UPDATE",
            target_table="zones",
            target_id=str(zone.id),
            before=before,
            after=after,
            ip_address=ip_address,
        )
        session.commit()

        send_notify(engine, "zones")
        if channel_ids is not None:
            send_notify(engine, "zone_channels")
        if multipliers is not None:
            send_notify(engine, "zone_multipliers")

        session.refresh(zone)
        session.expunge(zone)
        return zone


def deactivate_zone(
    engine,
    *,
    zone_id: int,
    actor_id: int,
    ip_address: str | None = None,
) -> bool:
    """Soft-delete a zone."""
    return update_zone(
        engine,
        zone_id=zone_id,
        active=False,
        actor_id=actor_id,
        ip_address=ip_address,
    ) is not None


# ---------------------------------------------------------------------------
# Achievement Template CRUD
# ---------------------------------------------------------------------------
def create_achievement(
    engine,
    *,
    guild_id: int,
    name: str,
    description: str | None = None,
    category: str = "social",
    requirement_type: str = "custom",
    requirement_scope: str = "season",
    requirement_field: str | None = None,
    requirement_value: int | None = None,
    xp_reward: int = 0,
    gold_reward: int = 0,
    badge_image_url: str | None = None,
    rarity: str = "common",
    announce_channel_id: int | None = None,
    actor_id: int,
    ip_address: str | None = None,
) -> AchievementTemplate:
    """Create a new achievement template."""
    with Session(engine) as session:
        tmpl = AchievementTemplate(
            guild_id=guild_id,
            name=name,
            description=description,
            category=category,
            requirement_type=requirement_type,
            requirement_scope=requirement_scope,
            requirement_field=requirement_field,
            requirement_value=requirement_value,
            xp_reward=xp_reward,
            gold_reward=gold_reward,
            badge_image_url=badge_image_url,
            rarity=rarity,
            announce_channel_id=announce_channel_id,
        )
        session.add(tmpl)
        session.flush()
        after = _row_to_dict(tmpl)
        _log_admin_action(
            session,
            actor_id=actor_id,
            action_type="CREATE",
            target_table="achievement_templates",
            target_id=str(tmpl.id),
            before=None,
            after=after,
            ip_address=ip_address,
        )
        session.commit()

        send_notify(engine, "achievement_templates")

        session.refresh(tmpl)
        session.expunge(tmpl)
        return tmpl


def update_achievement(
    engine,
    *,
    achievement_id: int,
    actor_id: int,
    ip_address: str | None = None,
    **kwargs,
) -> AchievementTemplate | None:
    """Update an existing achievement template."""
    with Session(engine) as session:
        tmpl = session.get(AchievementTemplate, achievement_id)
        if not tmpl:
            return None

        before = _row_to_dict(tmpl)
        for key, value in kwargs.items():
            if hasattr(tmpl, key) and key not in ("id", "guild_id", "created_at"):
                setattr(tmpl, key, value)

        session.flush()
        after = _row_to_dict(tmpl)
        _log_admin_action(
            session,
            actor_id=actor_id,
            action_type="UPDATE",
            target_table="achievement_templates",
            target_id=str(tmpl.id),
            before=before,
            after=after,
            ip_address=ip_address,
        )
        session.commit()

        send_notify(engine, "achievement_templates")

        session.refresh(tmpl)
        session.expunge(tmpl)
        return tmpl


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
    with Session(engine) as session:
        if activate:
            # Deactivate current active season
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
