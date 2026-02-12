"""
synapse.services.channel_service — Guild Channel Auto-Discovery
=================================================================

Maps guild channels to zones based on category name matching.
Extracted from seed.py to keep seed logic and channel logic separate.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from synapse.database.models import Zone, ZoneChannel

logger = logging.getLogger(__name__)


def sync_guild_channels(engine, guild_id: int, channels: list[dict]) -> int:
    """Auto-discover and map guild channels to zones.

    Parameters
    ----------
    engine : SQLAlchemy Engine
    guild_id : Discord guild snowflake
    channels : list of dicts with keys: id, name, category_name

    Returns the number of newly mapped channels.
    """
    with Session(engine) as session:
        # Get existing zone mappings
        existing_channel_ids: set[int] = set()
        existing_mappings = session.scalars(
            select(ZoneChannel)
        ).all()
        for m in existing_mappings:
            existing_channel_ids.add(m.channel_id)

        # Get all zones for this guild
        zones = session.scalars(
            select(Zone).where(Zone.guild_id == guild_id, Zone.active.is_(True))
        ).all()
        zone_by_name: dict[str, Zone] = {z.name.lower(): z for z in zones}

        # Find the general fallback zone
        fallback_zone = zone_by_name.get("general")
        if not fallback_zone:
            # Use the first zone if no 'general' exists
            if zones:
                fallback_zone = zones[0]
            else:
                logger.warning(
                    "No zones exist for guild %d — skipping channel discovery.", guild_id
                )
                return 0

        mapped_count = 0
        for ch in channels:
            ch_id = ch["id"]
            if ch_id in existing_channel_ids:
                continue  # Already mapped

            # Try to match category name to zone name
            category = (ch.get("category_name") or "").lower()
            target_zone = None
            for zone_name, zone in zone_by_name.items():
                if zone_name in category or category in zone_name:
                    target_zone = zone
                    break

            if target_zone is None:
                target_zone = fallback_zone

            session.add(ZoneChannel(zone_id=target_zone.id, channel_id=ch_id))
            mapped_count += 1
            logger.info(
                "Auto-mapped channel #%s (%d) → zone '%s'",
                ch.get("name", "unknown"), ch_id, target_zone.name,
            )

        if mapped_count:
            session.commit()
            logger.info(
                "Auto-discovery complete: %d new channels mapped for guild %d.",
                mapped_count, guild_id,
            )
        else:
            logger.info("Auto-discovery: no new channels to map for guild %d.", guild_id)

        return mapped_count
