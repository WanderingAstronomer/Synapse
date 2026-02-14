"""
synapse.api.routes.achievements — Achievement CRUD, awards & user search
==========================================================================
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from synapse.api.deps import get_config, get_engine, get_session
from synapse.api.rate_limit import rate_limited_admin
from synapse.config import SynapseConfig
from synapse.database.models import (
    AchievementCategory,
    AchievementRarity,
    AchievementSeries,
    AchievementTemplate,
    TriggerType,
    User,
)
from synapse.engine.cache import send_event_notify
from synapse.services import admin_service, reward_service

router = APIRouter(prefix="/admin", tags=["admin"])
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------
class AchievementCreate(BaseModel):
    name: str
    description: str | None = None
    category_id: int | None = None
    rarity_id: int | None = None
    trigger_type: str = "manual"
    trigger_config: dict | None = None
    series_id: int | None = None
    series_order: int | None = None
    xp_reward: int = 0
    gold_reward: int = 0
    badge_image: str | None = None
    announce_channel_id: int | None = None
    is_hidden: bool = False
    max_earners: int | None = None


class AchievementUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    category_id: int | None = None
    rarity_id: int | None = None
    trigger_type: str | None = None
    trigger_config: dict | None = None
    series_id: int | None = None
    series_order: int | None = None
    xp_reward: int | None = None
    gold_reward: int | None = None
    badge_image: str | None = None
    announce_channel_id: int | None = None
    is_hidden: bool | None = None
    max_earners: int | None = None
    active: bool | None = None


class CategoryCreate(BaseModel):
    name: str
    icon: str | None = None
    sort_order: int = 0


class CategoryUpdate(BaseModel):
    name: str | None = None
    icon: str | None = None
    sort_order: int | None = None


class RarityCreate(BaseModel):
    name: str
    color: str = "#9e9e9e"
    emoji: str | None = None
    sort_order: int = 0


class RarityUpdate(BaseModel):
    name: str | None = None
    color: str | None = None
    emoji: str | None = None
    sort_order: int | None = None


class SeriesCreate(BaseModel):
    name: str
    description: str | None = None


class SeriesUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


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


# ---------------------------------------------------------------------------
# Achievement Categories
# ---------------------------------------------------------------------------
@router.get("/achievement-categories")
def list_achievement_categories(
    admin: dict = Depends(rate_limited_admin),
    session: Session = Depends(get_session),
    cfg: SynapseConfig = Depends(get_config),
):
    rows = session.scalars(
        select(AchievementCategory)
        .where(AchievementCategory.guild_id == cfg.guild_id)
        .order_by(AchievementCategory.sort_order)
    ).all()
    return {
        "categories": [
            {"id": c.id, "name": c.name, "icon": c.icon, "sort_order": c.sort_order}
            for c in rows
        ]
    }


@router.post("/achievement-categories", status_code=201)
def create_achievement_category(
    body: CategoryCreate,
    admin: dict = Depends(rate_limited_admin),
    engine=Depends(get_engine),
    cfg: SynapseConfig = Depends(get_config),
):
    cat = admin_service.create_achievement_category(
        engine, guild_id=cfg.guild_id,
        name=body.name, icon=body.icon, sort_order=body.sort_order,
        actor_id=int(admin["sub"]),
    )
    return {"id": cat.id, "name": cat.name}


@router.patch("/achievement-categories/{category_id}")
def update_achievement_category(
    category_id: int,
    body: CategoryUpdate,
    admin: dict = Depends(rate_limited_admin),
    engine=Depends(get_engine),
):
    kwargs = body.model_dump(exclude_none=True)
    if not kwargs:
        raise HTTPException(400, "No fields to update")
    cat = admin_service.update_achievement_category(
        engine, category_id=category_id, actor_id=int(admin["sub"]), **kwargs,
    )
    if not cat:
        raise HTTPException(404, "Category not found")
    return {"id": cat.id, "name": cat.name}


@router.delete("/achievement-categories/{category_id}", status_code=204)
def delete_achievement_category(
    category_id: int,
    admin: dict = Depends(rate_limited_admin),
    engine=Depends(get_engine),
):
    if not admin_service.delete_achievement_category(
        engine, category_id=category_id, actor_id=int(admin["sub"]),
    ):
        raise HTTPException(404, "Category not found")
    return None


# ---------------------------------------------------------------------------
# Achievement Rarities
# ---------------------------------------------------------------------------
@router.get("/achievement-rarities")
def list_achievement_rarities(
    admin: dict = Depends(rate_limited_admin),
    session: Session = Depends(get_session),
    cfg: SynapseConfig = Depends(get_config),
):
    rows = session.scalars(
        select(AchievementRarity)
        .where(AchievementRarity.guild_id == cfg.guild_id)
        .order_by(AchievementRarity.sort_order)
    ).all()
    return {
        "rarities": [
            {"id": r.id, "name": r.name, "color": r.color, "sort_order": r.sort_order}
            for r in rows
        ]
    }


@router.post("/achievement-rarities", status_code=201)
def create_achievement_rarity(
    body: RarityCreate,
    admin: dict = Depends(rate_limited_admin),
    engine=Depends(get_engine),
    cfg: SynapseConfig = Depends(get_config),
):
    rar = admin_service.create_achievement_rarity(
        engine, guild_id=cfg.guild_id,
        name=body.name, color=body.color, sort_order=body.sort_order,
        actor_id=int(admin["sub"]),
    )
    return {"id": rar.id, "name": rar.name}


@router.patch("/achievement-rarities/{rarity_id}")
def update_achievement_rarity(
    rarity_id: int,
    body: RarityUpdate,
    admin: dict = Depends(rate_limited_admin),
    engine=Depends(get_engine),
):
    kwargs = body.model_dump(exclude_none=True)
    if not kwargs:
        raise HTTPException(400, "No fields to update")
    rar = admin_service.update_achievement_rarity(
        engine, rarity_id=rarity_id, actor_id=int(admin["sub"]), **kwargs,
    )
    if not rar:
        raise HTTPException(404, "Rarity not found")
    return {"id": rar.id, "name": rar.name}


@router.delete("/achievement-rarities/{rarity_id}", status_code=204)
def delete_achievement_rarity(
    rarity_id: int,
    admin: dict = Depends(rate_limited_admin),
    engine=Depends(get_engine),
):
    if not admin_service.delete_achievement_rarity(
        engine, rarity_id=rarity_id, actor_id=int(admin["sub"]),
    ):
        raise HTTPException(404, "Rarity not found")
    return None


# ---------------------------------------------------------------------------
# Achievement Series
# ---------------------------------------------------------------------------
@router.get("/achievement-series")
def list_achievement_series(
    admin: dict = Depends(rate_limited_admin),
    session: Session = Depends(get_session),
    cfg: SynapseConfig = Depends(get_config),
):
    rows = session.scalars(
        select(AchievementSeries)
        .where(AchievementSeries.guild_id == cfg.guild_id)
        .order_by(AchievementSeries.name)
    ).all()
    return {
        "series": [
            {"id": s.id, "name": s.name, "description": s.description}
            for s in rows
        ]
    }


@router.post("/achievement-series", status_code=201)
def create_achievement_series(
    body: SeriesCreate,
    admin: dict = Depends(rate_limited_admin),
    engine=Depends(get_engine),
    cfg: SynapseConfig = Depends(get_config),
):
    series = admin_service.create_achievement_series(
        engine, guild_id=cfg.guild_id,
        name=body.name, description=body.description,
        actor_id=int(admin["sub"]),
    )
    return {"id": series.id, "name": series.name}


@router.patch("/achievement-series/{series_id}")
def update_achievement_series(
    series_id: int,
    body: SeriesUpdate,
    admin: dict = Depends(rate_limited_admin),
    engine=Depends(get_engine),
):
    kwargs = body.model_dump(exclude_none=True)
    if not kwargs:
        raise HTTPException(400, "No fields to update")
    series = admin_service.update_achievement_series(
        engine, series_id=series_id, actor_id=int(admin["sub"]), **kwargs,
    )
    if not series:
        raise HTTPException(404, "Series not found")
    return {"id": series.id, "name": series.name}


@router.delete("/achievement-series/{series_id}", status_code=204)
def delete_achievement_series(
    series_id: int,
    admin: dict = Depends(rate_limited_admin),
    engine=Depends(get_engine),
):
    if not admin_service.delete_achievement_series(
        engine, series_id=series_id, actor_id=int(admin["sub"]),
    ):
        raise HTTPException(404, "Series not found")
    return None


# ---------------------------------------------------------------------------
# Achievements
# ---------------------------------------------------------------------------
@router.get("/achievements")
def list_achievements(
    admin: dict = Depends(rate_limited_admin),
    session: Session = Depends(get_session),
):
    templates = session.scalars(
        select(AchievementTemplate).order_by(
            AchievementTemplate.name
        )
    ).all()
    return {
        "achievements": [
            {
                "id": t.id,
                "name": t.name,
                "description": t.description,
                "category_id": t.category_id,
                "rarity_id": t.rarity_id,
                "trigger_type": t.trigger_type,
                "trigger_config": t.trigger_config,
                "series_id": t.series_id,
                "series_order": t.series_order,
                "xp_reward": t.xp_reward,
                "gold_reward": t.gold_reward,
                "badge_image": t.badge_image,
                "announce_channel_id": (
                    str(t.announce_channel_id) if t.announce_channel_id else None
                ),
                "is_hidden": t.is_hidden,
                "max_earners": t.max_earners,
                "active": t.active,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in templates
        ],
    }


@router.post("/achievements", status_code=201)
def create_achievement(
    body: AchievementCreate,
    admin: dict = Depends(rate_limited_admin),
    engine=Depends(get_engine),
    cfg: SynapseConfig = Depends(get_config),
):
    # Validate trigger_type
    valid_triggers = {t.value for t in TriggerType}
    if body.trigger_type not in valid_triggers:
        raise HTTPException(
            400, f"Invalid trigger_type. Must be one of: {sorted(valid_triggers)}"
        )
    tmpl = admin_service.create_achievement(
        engine,
        guild_id=cfg.guild_id,
        name=body.name,
        description=body.description,
        category_id=body.category_id,
        rarity_id=body.rarity_id,
        trigger_type=body.trigger_type,
        trigger_config=body.trigger_config,
        series_id=body.series_id,
        series_order=body.series_order,
        xp_reward=body.xp_reward,
        gold_reward=body.gold_reward,
        badge_image=body.badge_image,
        announce_channel_id=body.announce_channel_id,
        is_hidden=body.is_hidden,
        max_earners=body.max_earners,
        actor_id=int(admin["sub"]),
    )
    return {"id": tmpl.id, "name": tmpl.name}


@router.patch("/achievements/{achievement_id}")
def update_achievement(
    achievement_id: int,
    body: AchievementUpdate,
    admin: dict = Depends(rate_limited_admin),
    engine=Depends(get_engine),
):
    kwargs = body.model_dump(exclude_none=True)
    if not kwargs:
        raise HTTPException(400, "No fields to update")
    # Validate trigger_type if being updated
    if "trigger_type" in kwargs:
        valid_triggers = {t.value for t in TriggerType}
        if kwargs["trigger_type"] not in valid_triggers:
            raise HTTPException(
                400, f"Invalid trigger_type. Must be one of: {sorted(valid_triggers)}"
            )
    tmpl = admin_service.update_achievement(
        engine,
        achievement_id=achievement_id,
        actor_id=int(admin["sub"]),
        **kwargs,
    )
    if not tmpl:
        raise HTTPException(404, "Achievement not found")
    return {"id": tmpl.id, "name": tmpl.name, "active": tmpl.active}


@router.delete("/achievements/{achievement_id}", status_code=204)
def delete_achievement(
    achievement_id: int,
    admin: dict = Depends(rate_limited_admin),
    engine=Depends(get_engine),
):
    if not admin_service.delete_achievement(
        engine, achievement_id=achievement_id, actor_id=int(admin["sub"]),
    ):
        raise HTTPException(404, "Achievement not found")
    return None


# ---------------------------------------------------------------------------
# Manual Awards
# ---------------------------------------------------------------------------
@router.post("/awards/xp-gold")
def award_xp_gold(
    body: ManualAward,
    admin: dict = Depends(rate_limited_admin),
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
    admin: dict = Depends(rate_limited_admin),
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

    # Notify the bot to announce the achievement via Discord
    try:
        send_event_notify(engine, {
            "type": "achievement_granted",
            "recipient_id": str(body.user_id),
            "display_name": body.display_name,
            "achievement_id": body.achievement_id,
            "admin_name": admin.get("username", "Admin"),
        })
    except Exception:
        logger.warning("Failed to send achievement grant notification", exc_info=True)

    return {"message": msg}


# ---------------------------------------------------------------------------
# Users lookup (for admin award forms)
# ---------------------------------------------------------------------------
@router.get("/users")
def search_users(
    q: str = Query("", min_length=0),
    limit: int = Query(20, ge=1, le=100),
    admin: dict = Depends(rate_limited_admin),
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
