"""
synapse.api.routes.settings — Settings, audit, setup, logs & name resolution
==============================================================================
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from synapse.api.deps import get_config, get_engine, get_session
from synapse.api.rate_limit import rate_limited_admin
from synapse.config import SynapseConfig
from synapse.database.models import AdminLog, Channel, User
from synapse.services import settings_service
from synapse.services.log_buffer import (
    VALID_LEVELS,
    get_current_level,
    get_logs,
    set_capture_level,
)
from synapse.services.setup_service import (
    GuildSnapshot,
    bootstrap_guild,
    get_setup_status,
)

router = APIRouter(prefix="/admin", tags=["admin"])
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------
class SettingUpdate(BaseModel):
    key: str
    value: Any
    category: str | None = None
    description: str | None = None


class ResolveRequest(BaseModel):
    user_ids: list[str] = Field(default_factory=list)
    channel_ids: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
@router.get("/settings")
def get_all_settings(
    admin: dict = Depends(rate_limited_admin),
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
    admin: dict = Depends(rate_limited_admin),
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
    count = settings_service.bulk_upsert(engine, items, actor_id=int(admin["sub"]))
    return {"updated": count}


# ---------------------------------------------------------------------------
# Audit Log
# ---------------------------------------------------------------------------
@router.get("/audit")
def get_audit_log(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    admin: dict = Depends(rate_limited_admin),
    session: Session = Depends(get_session),
):
    """Paginated admin audit log."""
    total = session.scalar(
        select(func.count()).select_from(AdminLog)
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


# ---------------------------------------------------------------------------
# Setup / Bootstrap
# ---------------------------------------------------------------------------
@router.get("/setup/status")
def setup_status(
    admin: dict = Depends(rate_limited_admin),
    engine=Depends(get_engine),
):
    """Return the current first-run setup state."""
    return get_setup_status(engine)


@router.post("/setup/bootstrap")
def run_bootstrap(
    allow_guild_mismatch: bool = Query(False),
    admin: dict = Depends(rate_limited_admin),
    engine=Depends(get_engine),
    cfg: SynapseConfig = Depends(get_config),
):
    """Trigger first-run guild bootstrap (idempotent).

    Syncs channels from Discord, creates a default season, and seeds
    page layouts.  Baseline settings are seeded by init_db() on startup.
    """
    result = bootstrap_guild(
        engine,
        cfg.guild_id,
        allow_guild_mismatch=allow_guild_mismatch,
    )
    if not result.success:
        raise HTTPException(400, detail={
            "message": "Bootstrap failed",
            "warnings": result.warnings,
        })
    return {
        "success": True,
        "channels_synced": result.channels_synced,
        "season_created": result.season_created,
        "settings_written": result.settings_written,
        "warnings": result.warnings,
    }


# ---------------------------------------------------------------------------
# Live Logs
# ---------------------------------------------------------------------------
@router.get("/logs")
def get_live_logs(
    tail: int = Query(200, ge=1, le=5000),
    level: str | None = Query(None),
    logger_filter: str | None = Query(None, alias="logger"),
    admin: dict = Depends(rate_limited_admin),
):
    """Return recent log entries from the in-memory ring buffer."""
    entries = get_logs(tail=tail, level=level, logger_filter=logger_filter)
    return {
        "entries": entries,
        "total": len(entries),
        "capture_level": get_current_level(),
        "valid_levels": list(VALID_LEVELS),
    }


@router.put("/logs/level")
def change_log_level(
    body: dict,
    admin: dict = Depends(rate_limited_admin),
):
    """Change the capture level of the ring-buffer handler on-the-fly."""
    level_name = body.get("level", "").upper()
    if level_name not in VALID_LEVELS:
        valid = ", ".join(VALID_LEVELS)
        raise HTTPException(400, detail=f"Invalid level. Must be one of: {valid}")
    new_level = set_capture_level(level_name)
    return {"level": new_level}


# ---------------------------------------------------------------------------
# Name Resolution: user IDs → names, channel IDs → names
# ---------------------------------------------------------------------------
@router.post("/resolve-names")
def resolve_names(
    body: ResolveRequest,
    admin: dict = Depends(rate_limited_admin),
    session: Session = Depends(get_session),
    engine=Depends(get_engine),
):
    """Resolve Discord Snowflake IDs to human-readable names.

    Users are resolved from the ``users`` table; channels from the
    stored guild snapshot (``guild.snapshot`` setting).
    """
    result: dict[str, Any] = {"users": {}, "channels": {}}

    # --- resolve users ---
    if body.user_ids:
        int_ids = []
        for uid in body.user_ids:
            try:
                int_ids.append(int(uid))
            except (ValueError, TypeError):
                pass
        if int_ids:
            rows = session.scalars(
                select(User).where(User.id.in_(int_ids))
            ).all()
            for u in rows:
                result["users"][str(u.id)] = u.discord_name

    # --- resolve channels from the channels table ---
    if body.channel_ids:
        int_ch_ids = []
        for cid in body.channel_ids:
            try:
                int_ch_ids.append(int(cid))
            except (ValueError, TypeError):
                pass
        if int_ch_ids:
            ch_rows = session.scalars(
                select(Channel).where(Channel.id.in_(int_ch_ids))
            ).all()
            for ch in ch_rows:
                result["channels"][str(ch.id)] = ch.name

    return result
