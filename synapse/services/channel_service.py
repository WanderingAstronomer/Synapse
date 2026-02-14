"""
synapse.services.channel_service — Guild Channel Management
=============================================================

- **sync_channels_from_snapshot**: Upserts Discord channel metadata into the
  ``channels`` table so the dashboard can display names/types without the bot.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from synapse.database.models import Channel

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Channel metadata sync (guild snapshot → channels table)
# ---------------------------------------------------------------------------

def sync_channels_from_snapshot(engine, guild_id: int, channels: list[dict]) -> dict:
    """Upsert Discord channel metadata into the ``channels`` table.

    Parameters
    ----------
    engine : SQLAlchemy Engine
    guild_id : Discord guild snowflake
    channels : list of dicts with keys: id, name, type, category_id, category_name

    Returns a summary dict: {"upserted": N, "removed": N}
    """
    now = datetime.now(UTC)
    upserted = 0
    removed = 0

    with Session(engine) as session:
        incoming_ids: set[int] = set()

        for ch in channels:
            ch_id = ch["id"]
            incoming_ids.add(ch_id)

            row = Channel(
                id=ch_id,
                guild_id=guild_id,
                name=ch.get("name", "unknown"),
                type=ch.get("type", "text"),
                discord_category_id=ch.get("category_id"),
                discord_category_name=ch.get("category_name"),
                position=ch.get("position", 0),
                last_synced_at=now,
            )
            session.merge(row)
            upserted += 1

        # Remove channels that are no longer in the guild
        existing = session.scalars(
            select(Channel.id).where(Channel.guild_id == guild_id)
        ).all()
        stale_ids = set(existing) - incoming_ids
        if stale_ids:
            session.execute(
                Channel.__table__.delete().where(Channel.id.in_(stale_ids))
            )
            removed = len(stale_ids)

        session.commit()

    logger.info(
        "Channel sync for guild %d: %d upserted, %d removed.",
        guild_id, upserted, removed,
    )
    return {"upserted": upserted, "removed": removed}
