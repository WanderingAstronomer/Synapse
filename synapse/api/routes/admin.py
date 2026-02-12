"""
synapse.api.routes.admin — Admin CRUD endpoints (JWT‑protected)
================================================================
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from synapse.api.deps import get_config, get_current_admin, get_engine, get_session
from synapse.config import SynapseConfig
from synapse.database.models import (
    AchievementTemplate,
    AdminLog,
    User,
    Zone,
    ZoneChannel,
    ZoneMultiplier,
)
from synapse.services import admin_service, reward_service, settings_service

router = APIRouter(prefix="/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------
class ZoneCreate(BaseModel):
    name: str
    description: str | None = None
    channel_ids: list[int] = Field(default_factory=list)
    multipliers: dict[str, list[float]] | None = None  # {"MESSAGE": [1.5, 1.0]}


class ZoneUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    active: bool | None = None
    channel_ids: list[int] | None = None
    multipliers: dict[str, list[float]] | None = None


class AchievementCreate(BaseModel):
    name: str
    description: str | None = None
    category: str = "social"
    requirement_type: str = "custom"
    requirement_scope: str = "season"
    requirement_field: str | None = None
    requirement_value: int | None = None
    xp_reward: int = 0
    gold_reward: int = 0
    badge_image_url: str | None = None
    rarity: str = "common"
    announce_channel_id: int | None = None


class AchievementUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    category: str | None = None
    requirement_type: str | None = None
    requirement_scope: str | None = None
    requirement_field: str | None = None
    requirement_value: int | None = None
    xp_reward: int | None = None
    gold_reward: int | None = None
    badge_image_url: str | None = None
    rarity: str | None = None
    announce_channel_id: int | None = None
    active: bool | None = None


class ManualAward(BaseModel):
    user_id: int
    display_name: str = "Unknown"
    xp: int = 0
    gold: int = 0
    reason: str = ""


class GrantAchievement(BaseModel):
    user_id: int
    display_name: str = "Unknown"
    achievement_id: int


class SettingUpdate(BaseModel):
    key: str
    value: Any
    category: str | None = None
    description: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _parse_multipliers(
    data: dict[str, list[float]] | None,
) -> dict[str, tuple[float, float]] | None:
    """Convert JSON multiplier format to service tuple format."""
    if data is None:
        return None
    return {k: (v[0], v[1] if len(v) > 1 else 1.0) for k, v in data.items()}


def _zone_dict(z: Zone, session: Session) -> dict:
    """Serialize a zone with its channels and multipliers."""
    channels = session.scalars(
        select(ZoneChannel).where(ZoneChannel.zone_id == z.id)
    ).all()
    multipliers = session.scalars(
        select(ZoneMultiplier).where(ZoneMultiplier.zone_id == z.id)
    ).all()
    return {
        "id": z.id,
        "guild_id": str(z.guild_id),
        "name": z.name,
        "description": z.description,
        "active": z.active,
        "created_by": str(z.created_by) if z.created_by else None,
        "created_at": z.created_at.isoformat() if z.created_at else None,
        "channel_ids": [str(ch.channel_id) for ch in channels],
        "multipliers": {
            m.interaction_type: {
                "xp": m.xp_multiplier,
                "star": m.star_multiplier,
            }
            for m in multipliers
        },
    }


# ---------------------------------------------------------------------------
# Zones
# ---------------------------------------------------------------------------
@router.get("/zones")
def list_zones(
    admin: dict = Depends(get_current_admin),
    session: Session = Depends(get_session),
):
    zones = session.scalars(select(Zone).order_by(Zone.name)).all()
    return {"zones": [_zone_dict(z, session) for z in zones]}


@router.post("/zones", status_code=201)
def create_zone(
    body: ZoneCreate,
    admin: dict = Depends(get_current_admin),
    engine=Depends(get_engine),
    cfg: SynapseConfig = Depends(get_config),
):
    zone = admin_service.create_zone(
        engine,
        guild_id=cfg.guild_id,
        name=body.name,
        description=body.description,
        channel_ids=body.channel_ids or None,
        multipliers=_parse_multipliers(body.multipliers),
        actor_id=int(admin["sub"]),
    )
    return {"id": zone.id, "name": zone.name}


@router.patch("/zones/{zone_id}")
def update_zone(
    zone_id: int,
    body: ZoneUpdate,
    admin: dict = Depends(get_current_admin),
    engine=Depends(get_engine),
):
    zone = admin_service.update_zone(
        engine,
        zone_id=zone_id,
        name=body.name,
        description=body.description,
        active=body.active,
        channel_ids=body.channel_ids,
        multipliers=_parse_multipliers(body.multipliers),
        actor_id=int(admin["sub"]),
    )
    if not zone:
        raise HTTPException(404, "Zone not found")
    return {"id": zone.id, "name": zone.name, "active": zone.active}


# ---------------------------------------------------------------------------
# Achievements
# ---------------------------------------------------------------------------
@router.get("/achievements")
def list_achievements(
    admin: dict = Depends(get_current_admin),
    session: Session = Depends(get_session),
):
    templates = session.scalars(
        select(AchievementTemplate).order_by(
            AchievementTemplate.category, AchievementTemplate.name
        )
    ).all()
    return {
        "achievements": [
            {
                "id": t.id,
                "name": t.name,
                "description": t.description,
                "category": t.category,
                "requirement_type": t.requirement_type,
                "requirement_scope": t.requirement_scope,
                "requirement_field": t.requirement_field,
                "requirement_value": t.requirement_value,
                "xp_reward": t.xp_reward,
                "gold_reward": t.gold_reward,
                "badge_image_url": t.badge_image_url,
                "rarity": t.rarity,
                "announce_channel_id": (
                    str(t.announce_channel_id) if t.announce_channel_id else None
                ),
                "active": t.active,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in templates
        ],
    }


@router.post("/achievements", status_code=201)
def create_achievement(
    body: AchievementCreate,
    admin: dict = Depends(get_current_admin),
    engine=Depends(get_engine),
    cfg: SynapseConfig = Depends(get_config),
):
    tmpl = admin_service.create_achievement(
        engine,
        guild_id=cfg.guild_id,
        name=body.name,
        description=body.description,
        category=body.category,
        requirement_type=body.requirement_type,
        requirement_scope=body.requirement_scope,
        requirement_field=body.requirement_field,
        requirement_value=body.requirement_value,
        xp_reward=body.xp_reward,
        gold_reward=body.gold_reward,
        badge_image_url=body.badge_image_url,
        rarity=body.rarity,
        announce_channel_id=body.announce_channel_id,
        actor_id=int(admin["sub"]),
    )
    return {"id": tmpl.id, "name": tmpl.name}


@router.patch("/achievements/{achievement_id}")
def update_achievement(
    achievement_id: int,
    body: AchievementUpdate,
    admin: dict = Depends(get_current_admin),
    engine=Depends(get_engine),
):
    kwargs = body.model_dump(exclude_none=True)
    if not kwargs:
        raise HTTPException(400, "No fields to update")
    tmpl = admin_service.update_achievement(
        engine,
        achievement_id=achievement_id,
        actor_id=int(admin["sub"]),
        **kwargs,
    )
    if not tmpl:
        raise HTTPException(404, "Achievement not found")
    return {"id": tmpl.id, "name": tmpl.name, "active": tmpl.active}


# ---------------------------------------------------------------------------
# Manual Awards
# ---------------------------------------------------------------------------
@router.post("/awards/xp-gold")
def award_xp_gold(
    body: ManualAward,
    admin: dict = Depends(get_current_admin),
    engine=Depends(get_engine),
    cfg: SynapseConfig = Depends(get_config),
):
    user = reward_service.award_manual(
        engine,
        user_id=body.user_id,
        display_name=body.display_name,
        guild_id=cfg.guild_id,
        xp=body.xp,
        gold=body.gold,
        reason=body.reason,
        admin_id=int(admin["sub"]),
    )
    return {
        "user_id": str(user.id),
        "xp": user.xp,
        "gold": user.gold,
        "level": user.level,
    }


@router.post("/awards/achievement")
def grant_achievement(
    body: GrantAchievement,
    admin: dict = Depends(get_current_admin),
    engine=Depends(get_engine),
    cfg: SynapseConfig = Depends(get_config),
):
    success, msg = reward_service.grant_achievement(
        engine,
        user_id=body.user_id,
        display_name=body.display_name,
        guild_id=cfg.guild_id,
        achievement_id=body.achievement_id,
        admin_id=int(admin["sub"]),
    )
    if not success:
        raise HTTPException(400, msg)
    return {"message": msg}


# ---------------------------------------------------------------------------
# Users lookup (for admin award forms)
# ---------------------------------------------------------------------------
@router.get("/users")
def search_users(
    q: str = Query("", min_length=0),
    limit: int = Query(20, ge=1, le=100),
    admin: dict = Depends(get_current_admin),
    session: Session = Depends(get_session),
):
    """Search users by name for award dropdowns."""
    query = select(User).order_by(User.discord_name).limit(limit)
    if q:
        query = query.where(User.discord_name.ilike(f"%{q}%"))
    users = session.scalars(query).all()
    return {
        "users": [
            {
                "id": str(u.id),
                "discord_name": u.discord_name,
                "level": u.level,
                "xp": u.xp,
            }
            for u in users
        ],
    }


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
@router.get("/settings")
def get_all_settings(
    admin: dict = Depends(get_current_admin),
    engine=Depends(get_engine),
):
    rows = settings_service.get_all_settings(engine)
    return {
        "settings": [
            {
                "key": r.key,
                "value": json.loads(r.value_json) if r.value_json else None,
                "category": r.category,
                "description": r.description,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            }
            for r in rows
        ],
    }


@router.put("/settings")
def update_settings(
    body: list[SettingUpdate],
    admin: dict = Depends(get_current_admin),
    engine=Depends(get_engine),
):
    items = [
        {
            "key": s.key,
            "value": s.value,
            **({"category": s.category} if s.category else {}),
            **({"description": s.description} if s.description else {}),
        }
        for s in body
    ]
    count = settings_service.bulk_upsert(engine, items)
    return {"updated": count}


# ---------------------------------------------------------------------------
# Audit Log
# ---------------------------------------------------------------------------
@router.get("/audit")
def get_audit_log(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    admin: dict = Depends(get_current_admin),
    session: Session = Depends(get_session),
):
    """Paginated admin audit log."""
    from sqlalchemy import func as sqlfunc

    total = session.scalar(
        select(sqlfunc.count()).select_from(AdminLog)
    ) or 0
    offset = (page - 1) * page_size

    rows = session.scalars(
        select(AdminLog)
        .order_by(AdminLog.timestamp.desc())
        .offset(offset)
        .limit(page_size)
    ).all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "entries": [
            {
                "id": r.id,
                "actor_id": str(r.actor_id),
                "action_type": r.action_type,
                "target_table": r.target_table,
                "target_id": r.target_id,
                "before_snapshot": r.before_snapshot,
                "after_snapshot": r.after_snapshot,
                "reason": r.reason,
                "timestamp": r.timestamp.isoformat() if r.timestamp else None,
            }
            for r in rows
        ],
    }
