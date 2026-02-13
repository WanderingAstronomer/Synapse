"""
synapse.api.routes.public — Read-only public endpoints
=========================================================
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from synapse.api.deps import get_session
from synapse.constants import RARITY_COLORS_HEX, RARITY_LABELS, xp_for_level
from synapse.database.models import (
    AchievementTemplate,
    ActivityLog,
    Setting,
    User,
    UserAchievement,
)

router = APIRouter(tags=["public"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _avatar_url(user_id: int, avatar_hash: str | None) -> str:
    """Construct a Discord CDN avatar URL."""
    if avatar_hash:
        ext = "gif" if avatar_hash.startswith("a_") else "png"
        return f"https://cdn.discordapp.com/avatars/{user_id}/{avatar_hash}.{ext}"
    # Default avatar (index based on user id)
    return f"https://cdn.discordapp.com/embed/avatars/{(user_id >> 22) % 6}.png"


def _user_dict(u: User) -> dict:
    return {
        "id": str(u.id),
        "discord_name": u.discord_name,
        "avatar_url": _avatar_url(u.id, u.discord_avatar_hash),
        "xp": u.xp,
        "level": u.level,
        "gold": u.gold,
        "xp_for_next": xp_for_level(u.level + 1),
        "xp_progress": u.xp / max(xp_for_level(u.level + 1), 1),
        "created_at": u.created_at.isoformat() if u.created_at else None,
    }


def _setting_val(row: Setting | None, default=None):
    if row is None:
        return default
    try:
        return json.loads(row.value_json)
    except (json.JSONDecodeError, TypeError):
        return row.value_json


# ---------------------------------------------------------------------------
# GET /metrics
# ---------------------------------------------------------------------------
@router.get("/metrics")
def get_metrics(session: Session = Depends(get_session)):
    """Overview metrics for the dashboard hero section."""
    total_users = session.scalar(select(func.count()).select_from(User)) or 0
    total_xp = session.scalar(select(func.coalesce(func.sum(User.xp), 0))) or 0

    week_ago = datetime.now(UTC) - timedelta(days=7)
    active_users = session.scalar(
        select(func.count(distinct(ActivityLog.user_id)))
        .where(ActivityLog.timestamp >= week_ago)
    ) or 0

    top_level = session.scalar(
        select(func.coalesce(func.max(User.level), 1))
    ) or 1

    total_achievements_earned = session.scalar(
        select(func.count()).select_from(UserAchievement)
    ) or 0

    return {
        "total_users": total_users,
        "total_xp": total_xp,
        "active_users_7d": active_users,
        "top_level": top_level,
        "total_achievements_earned": total_achievements_earned,
    }


# ---------------------------------------------------------------------------
# GET /leaderboard/{currency}
# ---------------------------------------------------------------------------
@router.get("/leaderboard/{currency}")
def get_leaderboard(
    currency: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: Session = Depends(get_session),
):
    """Paginated leaderboard by xp, gold, or level."""
    order_col = {"xp": User.xp, "gold": User.gold, "level": User.level}.get(currency)
    if order_col is None:
        order_col = User.xp

    total = session.scalar(select(func.count()).select_from(User)) or 0
    offset = (page - 1) * page_size

    rows = session.scalars(
        select(User).order_by(order_col.desc(), User.id).offset(offset).limit(page_size)
    ).all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "users": [
            {**_user_dict(u), "rank": offset + i + 1}
            for i, u in enumerate(rows)
        ],
    }


# ---------------------------------------------------------------------------
# GET /activity
# ---------------------------------------------------------------------------
@router.get("/activity")
def get_activity(
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(100, ge=1, le=500),
    event_type: str | None = Query(None),
    session: Session = Depends(get_session),
):
    """Recent activity feed + daily aggregation for charts."""
    since = datetime.now(UTC) - timedelta(days=days)
    query = (
        select(ActivityLog)
        .where(ActivityLog.timestamp >= since)
        .order_by(ActivityLog.timestamp.desc())
    )
    if event_type:
        query = query.where(ActivityLog.event_type == event_type)
    query = query.limit(limit)

    logs = session.scalars(query).all()

    # Build daily aggregation
    daily_query = (
        select(
            func.date_trunc("day", ActivityLog.timestamp).label("day"),
            ActivityLog.event_type,
            func.count().label("cnt"),
        )
        .where(ActivityLog.timestamp >= since)
    )
    if event_type:
        daily_query = daily_query.where(ActivityLog.event_type == event_type)
    daily_query = (
        daily_query
        .group_by("day", ActivityLog.event_type)
        .order_by("day")
    )
    daily_rows = session.execute(daily_query).all()

    # Build user lookup for activity entries
    user_ids = {log.user_id for log in logs}
    users = {
        u.id: u for u in session.scalars(
            select(User).where(User.id.in_(user_ids))
        ).all()
    } if user_ids else {}

    events = []
    for log in logs:
        u = users.get(log.user_id)
        events.append({
            "id": log.id,
            "user_id": str(log.user_id),
            "user_name": u.discord_name if u else "Unknown",
            "avatar_url": _avatar_url(log.user_id, u.discord_avatar_hash if u else None),
            "event_type": log.event_type,
            "xp_delta": log.xp_delta,
            "star_delta": log.star_delta,
            "timestamp": log.timestamp.isoformat() if log.timestamp else None,
            "metadata": log.metadata_,
        })

    daily: dict[str, dict[str, int]] = {}
    for row in daily_rows:
        day_str = row.day.strftime("%Y-%m-%d") if row.day else "unknown"
        if day_str not in daily:
            daily[day_str] = {}
        daily[day_str][row.event_type] = row.cnt

    return {
        "events": events,
        "daily": daily,
    }


# ---------------------------------------------------------------------------
# GET /achievements
# ---------------------------------------------------------------------------
@router.get("/achievements")
def get_achievements(session: Session = Depends(get_session)):
    """All active achievement templates with earn counts."""
    templates = session.scalars(
        select(AchievementTemplate)
        .where(AchievementTemplate.active.is_(True))
        .order_by(AchievementTemplate.category, AchievementTemplate.name)
    ).all()

    # Count earners per achievement
    earn_counts_q = (
        select(
            UserAchievement.achievement_id,
            func.count().label("cnt"),
        )
        .group_by(UserAchievement.achievement_id)
    )
    earn_counts = {row.achievement_id: row.cnt for row in session.execute(earn_counts_q).all()}

    total_users = session.scalar(select(func.count()).select_from(User)) or 1

    return {
        "achievements": [
            {
                "id": t.id,
                "name": t.name,
                "description": t.description,
                "category": t.category,
                "rarity": t.rarity,
                "rarity_label": RARITY_LABELS.get(t.rarity, t.rarity),
                "rarity_color": RARITY_COLORS_HEX.get(t.rarity, "#9e9e9e"),
                "xp_reward": t.xp_reward,
                "gold_reward": t.gold_reward,
                "badge_image_url": t.badge_image_url,
                "earner_count": earn_counts.get(t.id, 0),
                "earn_pct": round(earn_counts.get(t.id, 0) / total_users * 100, 1),
            }
            for t in templates
        ],
    }


# ---------------------------------------------------------------------------
# GET /achievements/recent
# ---------------------------------------------------------------------------
@router.get("/achievements/recent")
def get_recent_achievements(
    limit: int = Query(10, ge=1, le=50),
    session: Session = Depends(get_session),
):
    """Recently earned achievements."""
    rows = session.execute(
        select(UserAchievement, AchievementTemplate, User)
        .join(AchievementTemplate, UserAchievement.achievement_id == AchievementTemplate.id)
        .join(User, UserAchievement.user_id == User.id)
        .order_by(UserAchievement.earned_at.desc())
        .limit(limit)
    ).all()

    return {
        "recent": [
            {
                "user_id": str(ua.user_id),
                "user_name": u.discord_name,
                "avatar_url": _avatar_url(u.id, u.discord_avatar_hash),
                "achievement_name": t.name,
                "achievement_rarity": t.rarity,
                "rarity_color": RARITY_COLORS_HEX.get(t.rarity, "#9e9e9e"),
                "earned_at": ua.earned_at.isoformat() if ua.earned_at else None,
            }
            for ua, t, u in rows
        ],
    }


# ---------------------------------------------------------------------------
# GET /settings/public
# ---------------------------------------------------------------------------
@router.get("/settings/public")
def get_public_settings(session: Session = Depends(get_session)):
    """Return public-facing dashboard settings (branding, display)."""
    public_keys = [
        "dashboard_title",
        "dashboard_subtitle",
        "dashboard_leaderboard_page_size",
        "dashboard_activity_default_days",
        "dashboard_cta_label",
        "dashboard_cta_url",
        "dashboard_hero_emoji",
        "economy.primary_currency_name",
        "economy.secondary_currency_name",
    ]
    rows = session.scalars(
        select(Setting).where(Setting.key.in_(public_keys))
    ).all()

    result = {}
    for r in rows:
        result[r.key] = _setting_val(r)

    # Defaults
    result.setdefault("dashboard_title", "Synapse Community Dashboard")
    result.setdefault("dashboard_subtitle", "Community engagement at a glance")
    result.setdefault("dashboard_leaderboard_page_size", 20)
    result.setdefault("dashboard_activity_default_days", 30)
    result.setdefault("economy.primary_currency_name", "XP")
    result.setdefault("economy.secondary_currency_name", "Gold")

    return result
