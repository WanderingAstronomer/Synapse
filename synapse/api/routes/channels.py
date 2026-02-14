"""
synapse.api.routes.channels — Channel defaults, overrides & sync
===================================================================
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from synapse.api.deps import get_config, get_engine, get_session
from synapse.api.rate_limit import rate_limited_admin
from synapse.config import SynapseConfig
from synapse.database.models import Channel, ChannelOverride, ChannelTypeDefault
from synapse.services import admin_service

router = APIRouter(prefix="/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------
class TypeDefaultUpsert(BaseModel):
    channel_type: str  # text, voice, forum, stage, announcement
    event_type: str = "*"  # InteractionType value or '*'
    xp_multiplier: float = 1.0
    star_multiplier: float = 1.0


class OverrideUpsert(BaseModel):
    channel_id: int
    event_type: str = "*"
    xp_multiplier: float = 1.0
    star_multiplier: float = 1.0
    reason: str | None = None


VALID_CHANNEL_TYPES = {"text", "voice", "forum", "stage", "announcement"}


# ---------------------------------------------------------------------------
# Channel Type Defaults
# ---------------------------------------------------------------------------
@router.get("/channel-defaults")
def list_channel_defaults(
    admin: dict = Depends(rate_limited_admin),
    session: Session = Depends(get_session),
    cfg: SynapseConfig = Depends(get_config),
):
    """Return all channel type default rules for this guild."""
    rows = session.scalars(
        select(ChannelTypeDefault)
        .where(ChannelTypeDefault.guild_id == cfg.guild_id)
        .order_by(ChannelTypeDefault.channel_type, ChannelTypeDefault.event_type)
    ).all()
    return {
        "defaults": [
            {
                "id": d.id,
                "channel_type": d.channel_type,
                "event_type": d.event_type,
                "xp_multiplier": d.xp_multiplier,
                "star_multiplier": d.star_multiplier,
            }
            for d in rows
        ]
    }


@router.put("/channel-defaults")
def upsert_channel_default(
    body: TypeDefaultUpsert,
    admin: dict = Depends(rate_limited_admin),
    engine=Depends(get_engine),
    cfg: SynapseConfig = Depends(get_config),
):
    """Create or update a channel type default rule."""
    if body.channel_type not in VALID_CHANNEL_TYPES:
        raise HTTPException(400, f"Invalid channel_type. Must be one of: {sorted(VALID_CHANNEL_TYPES)}")
    row = admin_service.upsert_type_default(
        engine,
        guild_id=cfg.guild_id,
        channel_type=body.channel_type,
        event_type=body.event_type,
        xp_multiplier=body.xp_multiplier,
        star_multiplier=body.star_multiplier,
        actor_id=int(admin["sub"]),
    )
    return {
        "id": row.id,
        "channel_type": row.channel_type,
        "event_type": row.event_type,
        "xp_multiplier": row.xp_multiplier,
        "star_multiplier": row.star_multiplier,
    }


@router.delete("/channel-defaults/{default_id}", status_code=204)
def delete_channel_default(
    default_id: int,
    admin: dict = Depends(rate_limited_admin),
    engine=Depends(get_engine),
):
    if not admin_service.delete_type_default(
        engine, default_id=default_id, actor_id=int(admin["sub"])
    ):
        raise HTTPException(404, "Type default not found")
    return None


# ---------------------------------------------------------------------------
# Channel Overrides
# ---------------------------------------------------------------------------
@router.get("/channel-overrides")
def list_channel_overrides(
    channel_id: int | None = None,
    admin: dict = Depends(rate_limited_admin),
    session: Session = Depends(get_session),
    cfg: SynapseConfig = Depends(get_config),
):
    """Return channel overrides, optionally filtered by channel_id."""
    stmt = select(ChannelOverride).where(ChannelOverride.guild_id == cfg.guild_id)
    if channel_id is not None:
        stmt = stmt.where(ChannelOverride.channel_id == channel_id)
    stmt = stmt.order_by(ChannelOverride.channel_id, ChannelOverride.event_type)
    rows = session.scalars(stmt).all()
    return {
        "overrides": [
            {
                "id": o.id,
                "channel_id": str(o.channel_id),
                "event_type": o.event_type,
                "xp_multiplier": o.xp_multiplier,
                "star_multiplier": o.star_multiplier,
                "reason": o.reason,
            }
            for o in rows
        ]
    }


@router.put("/channel-overrides")
def upsert_channel_override(
    body: OverrideUpsert,
    admin: dict = Depends(rate_limited_admin),
    engine=Depends(get_engine),
    cfg: SynapseConfig = Depends(get_config),
):
    """Create or update a per-channel override."""
    row = admin_service.upsert_channel_override(
        engine,
        guild_id=cfg.guild_id,
        channel_id=body.channel_id,
        event_type=body.event_type,
        xp_multiplier=body.xp_multiplier,
        star_multiplier=body.star_multiplier,
        reason=body.reason,
        actor_id=int(admin["sub"]),
    )
    return {
        "id": row.id,
        "channel_id": str(row.channel_id),
        "event_type": row.event_type,
        "xp_multiplier": row.xp_multiplier,
        "star_multiplier": row.star_multiplier,
        "reason": row.reason,
    }


@router.delete("/channel-overrides/{override_id}", status_code=204)
def delete_channel_override_(
    override_id: int,
    admin: dict = Depends(rate_limited_admin),
    engine=Depends(get_engine),
):
    if not admin_service.delete_channel_override(
        engine, override_id=override_id, actor_id=int(admin["sub"])
    ):
        raise HTTPException(404, "Override not found")
    return None


# ---------------------------------------------------------------------------
# Channels
# ---------------------------------------------------------------------------
@router.get("/channels")
def list_channels(
    admin: dict = Depends(rate_limited_admin),
    session: Session = Depends(get_session),
    cfg: SynapseConfig = Depends(get_config),
):
    """Return all synced Discord channels for this guild."""
    rows = session.scalars(
        select(Channel)
        .where(Channel.guild_id == cfg.guild_id)
        .order_by(Channel.discord_category_name.nulls_last(), Channel.name)
    ).all()
    return {
        "channels": [
            {
                "id": str(ch.id),
                "name": ch.name,
                "type": ch.type,
                "discord_category_id": str(ch.discord_category_id) if ch.discord_category_id else None,
                "discord_category_name": ch.discord_category_name,
                "position": ch.position,
            }
            for ch in rows
        ]
    }


@router.post("/channels/sync")
def sync_channels(
    admin: dict = Depends(rate_limited_admin),
    session: Session = Depends(get_session),
    engine=Depends(get_engine),
    cfg: SynapseConfig = Depends(get_config),
):
    """Re-sync channel metadata from the stored guild snapshot."""
    from synapse.database.models import Setting
    from synapse.services.channel_service import sync_channels_from_snapshot

    snap_row = session.get(Setting, "guild.snapshot")
    if not snap_row or not snap_row.value_json:
        raise HTTPException(404, "No guild snapshot found. Run bootstrap or wait for bot to connect.")

    try:
        from synapse.services.setup_service import GuildSnapshot
        snapshot = GuildSnapshot.from_json(snap_row.value_json)
    except Exception:
        raise HTTPException(500, "Failed to parse guild snapshot.")

    ch_dicts = [
        {
            "id": ch.id,
            "name": ch.name,
            "type": ch.type,
            "category_id": ch.category_id,
            "category_name": ch.category_name,
            "position": 0,
        }
        for ch in snapshot.channels
    ]
    result = sync_channels_from_snapshot(engine, cfg.guild_id, ch_dicts)
    return {"synced": True, **result}
