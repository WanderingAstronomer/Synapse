"""
synapse.api.routes.member — Authenticated member endpoints
=============================================================

Tier 2 (guild member) endpoints.  All require a valid JWT for a
current guild member via ``get_member_context``.

Endpoints
---------
- ``GET /member/profile``       — Own stats, rank, avatar
- ``GET /member/achievements``  — Own earned achievements
- ``GET /member/activity``      — Own activity timeline with "Why" trace
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from synapse.api.deps import get_member_context, get_session
from synapse.constants import xp_for_level
from synapse.database.models import (
    AchievementCategory,
    AchievementRarity,
    AchievementTemplate,
    ActivityLog,
    RuleEvaluation,
    User,
    UserAchievement,
    UserProfile,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/member", tags=["member"])

MAX_ACTIVITY_LIMIT = 200


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _avatar_url(user_id: int, avatar_hash: str | None) -> str:
    """Construct a Discord CDN avatar URL."""
    if avatar_hash:
        ext = "gif" if avatar_hash.startswith("a_") else "png"
        return f"https://cdn.discordapp.com/avatars/{user_id}/{avatar_hash}.{ext}"
    return f"https://cdn.discordapp.com/embed/avatars/{(user_id >> 22) % 6}.png"


def _rank_for_user(session: Session, user_id: int, order_col) -> int | None:
    """Return 1-based rank for a user in the given ordering, or None if not found."""
    # Use a window function subquery for correct rank
    sub = (
        select(
            User.id,
            func.row_number().over(order_by=[order_col.desc(), User.id]).label("rank"),
        )
    ).subquery()
    row = session.execute(
        select(sub.c.rank).where(sub.c.id == user_id)
    ).scalar_one_or_none()
    return int(row) if row is not None else None


# ---------------------------------------------------------------------------
# GET /member/profile
# ---------------------------------------------------------------------------
@router.get("/profile")
def get_member_profile(
    member: dict = Depends(get_member_context),
    session: Session = Depends(get_session),
):
    """Own stats, rank, and profile info for the authenticated member."""
    user_id = int(member["sub"])
    user = session.get(User, user_id)
    if user is None:
        return {"error": "User not found", "user": None}

    profile = session.get(UserProfile, user_id)

    xp_rank = _rank_for_user(session, user_id, User.xp)
    gold_rank = _rank_for_user(session, user_id, User.gold)

    achievement_count = (
        session.scalar(
            select(func.count()).select_from(UserAchievement).where(
                UserAchievement.user_id == user_id
            )
        )
        or 0
    )

    total_users = session.scalar(select(func.count()).select_from(User)) or 0

    return {
        "user": {
            "id": str(user.id),
            "discord_name": user.discord_name,
            "avatar_url": (
                profile.avatar_url
                if profile and profile.avatar_url
                else _avatar_url(user.id, user.discord_avatar_hash)
            ),
            "xp": user.xp,
            "level": user.level,
            "gold": user.gold,
            "xp_for_next": xp_for_level(user.level + 1),
            "xp_progress": user.xp / max(xp_for_level(user.level + 1), 1),
            "created_at": user.created_at.isoformat() if user.created_at else None,
        },
        "ranks": {
            "xp": xp_rank,
            "gold": gold_rank,
            "total_users": total_users,
        },
        "achievement_count": achievement_count,
    }


# ---------------------------------------------------------------------------
# GET /member/achievements
# ---------------------------------------------------------------------------
@router.get("/achievements")
def get_member_achievements(
    member: dict = Depends(get_member_context),
    session: Session = Depends(get_session),
):
    """Earned achievements for the authenticated member."""
    user_id = int(member["sub"])

    rows = session.execute(
        select(UserAchievement, AchievementTemplate)
        .join(AchievementTemplate, UserAchievement.achievement_id == AchievementTemplate.id)
        .where(UserAchievement.user_id == user_id)
        .order_by(UserAchievement.earned_at.desc())
    ).all()

    categories = {c.id: c for c in session.scalars(select(AchievementCategory)).all()}
    rarities = {r.id: r for r in session.scalars(select(AchievementRarity)).all()}

    return {
        "achievements": [
            {
                "id": t.id,
                "name": t.name,
                "description": t.description,
                "category": (
                    categories[t.category_id].name
                    if t.category_id and t.category_id in categories
                    else None
                ),
                "rarity": (
                    rarities[t.rarity_id].name
                    if t.rarity_id and t.rarity_id in rarities
                    else None
                ),
                "rarity_color": (
                    rarities[t.rarity_id].color
                    if t.rarity_id and t.rarity_id in rarities
                    else "#9e9e9e"
                ),
                "xp_reward": t.xp_reward,
                "gold_reward": t.gold_reward,
                "badge_image": t.badge_image,
                "earned_at": ua.earned_at.isoformat() if ua.earned_at else None,
            }
            for ua, t in rows
        ],
    }


# ---------------------------------------------------------------------------
# GET /member/activity
# ---------------------------------------------------------------------------
@router.get("/activity")
def get_member_activity(
    member: dict = Depends(get_member_context),
    session: Session = Depends(get_session),
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(50, ge=1, le=MAX_ACTIVITY_LIMIT),
):
    """Own activity timeline with 'Why was I rewarded?' trace.

    Each event is joined to its ``RuleEvaluation`` (if one exists) to
    surface the matched rules and applied outcomes.
    """
    user_id = int(member["sub"])
    since = datetime.now(UTC) - timedelta(days=days)

    logs = session.scalars(
        select(ActivityLog)
        .where(ActivityLog.user_id == user_id, ActivityLog.timestamp >= since)
        .order_by(ActivityLog.timestamp.desc())
        .limit(limit)
    ).all()

    # Batch-load rule evaluations for these events.
    # Match via (user_id, evaluated_at close to activity timestamp).
    # Fetch evaluations for this user in the time range
    evaluations_by_ts: dict[str, dict] = {}
    if logs:
        evals = session.execute(
            select(RuleEvaluation)
            .where(
                RuleEvaluation.user_id == user_id,
                RuleEvaluation.evaluated_at >= since,
            )
            .order_by(RuleEvaluation.evaluated_at.desc())
            .limit(limit * 2)  # Fetch extra to improve matching
        ).scalars().all()
        for ev in evals:
            # Key by ISO timestamp (second precision) for fuzzy matching
            key = ev.evaluated_at.strftime("%Y-%m-%dT%H:%M") if ev.evaluated_at else ""
            if key not in evaluations_by_ts:
                evaluations_by_ts[key] = {
                    "matched_rules": ev.matched_rules,
                    "outcomes_applied": ev.outcomes_applied,
                    "context_snapshot": ev.context_snapshot,
                }

    events = []
    for log in logs:
        # Try to find a matching rule evaluation
        why_trace = None
        if log.timestamp:
            key = log.timestamp.strftime("%Y-%m-%dT%H:%M")
            why_trace = evaluations_by_ts.get(key)

        events.append(
            {
                "id": log.id,
                "event_type": log.event_type,
                "xp_delta": log.xp_delta,
                "star_delta": log.star_delta,
                "timestamp": log.timestamp.isoformat() if log.timestamp else None,
                "metadata": log.metadata_,
                "why_trace": why_trace,
            }
        )

    return {"events": events}
