"""
synapse.services.seed — Database Seed Service
===============================================

Seeds default zones, multipliers, season, achievements, and settings
from YAML fixture files in the ``seeds/`` directory.

Per D04-01: YAML is used only for initial seeding.  Post-deployment,
everything is managed from the Admin Dashboard.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from synapse.database.models import (
    AchievementTemplate,
    Season,
    Setting,
    Zone,
    ZoneMultiplier,
)

logger = logging.getLogger(__name__)

# Resolve the seeds directory relative to the project root
_SEEDS_DIR = Path(__file__).resolve().parent.parent.parent / "seeds"


def _load_yaml(filename: str) -> Any:
    """Load a YAML file from the seeds directory."""
    path = _SEEDS_DIR / filename
    if not path.exists():
        logger.warning("Seed file not found: %s", path)
        return []
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or []


def _seed_settings(session: Session) -> int:
    """Seed default settings from seeds/settings.yaml if table is empty."""
    existing = session.scalar(select(Setting.key).limit(1))
    if existing:
        logger.info("Settings already seeded — skipping.")
        return 0

    items = _load_yaml("settings.yaml")
    if not items:
        return 0

    count = 0
    for item in items:
        session.add(Setting(
            key=item["key"],
            value_json=json.dumps(item["value"]),
            category=item.get("category", "general"),
            description=item.get("description"),
        ))
        count += 1

    logger.info("Seeded %d settings.", count)
    return count


def _seed_zones(session: Session, guild_id: int) -> dict[str, Zone]:
    """Seed default zones and multipliers from seeds/zones.yaml."""
    data = _load_yaml("zones.yaml")
    if not data or "zones" not in data:
        return {}

    zone_objs: dict[str, Zone] = {}
    for zdata in data["zones"]:
        z = Zone(
            guild_id=guild_id,
            name=zdata["name"],
            description=zdata.get("description"),
        )
        session.add(z)
        session.flush()
        zone_objs[zdata["name"]] = z

        # Add multipliers
        for itype, (xp_m, star_m) in (zdata.get("multipliers") or {}).items():
            session.add(ZoneMultiplier(
                zone_id=z.id,
                interaction_type=itype,
                xp_multiplier=xp_m,
                star_multiplier=star_m,
            ))

    logger.info("Seeded %d zones with multipliers.", len(zone_objs))
    return zone_objs


def _seed_achievements(session: Session, guild_id: int) -> int:
    """Seed default achievements from seeds/achievements.yaml."""
    data = _load_yaml("achievements.yaml")
    if not data or "achievements" not in data:
        return 0

    count = 0
    for a in data["achievements"]:
        session.add(AchievementTemplate(
            guild_id=guild_id,
            name=a["name"],
            description=a.get("description"),
            category=a.get("category", "social"),
            requirement_type=a["requirement_type"],
            requirement_scope="lifetime",
            requirement_field=a.get("requirement_field"),
            requirement_value=a.get("requirement_value"),
            xp_reward=a.get("xp_reward", 0),
            gold_reward=a.get("gold_reward", 0),
            rarity=a.get("rarity", "common"),
        ))
        count += 1

    logger.info("Seeded %d achievement templates.", count)
    return count


def seed_database(engine, guild_id: int) -> None:
    """Seed default configuration if not already present.

    This is idempotent — it only creates rows if the tables are empty
    for the given guild_id.
    """
    with Session(engine) as session:
        # Check if zones already seeded (proxy for full seed)
        existing_zones = session.scalar(
            select(Zone.id).where(Zone.guild_id == guild_id).limit(1)
        )

        # Always try to seed settings (independent of guild)
        _seed_settings(session)

        if existing_zones:
            logger.info(
                "Database already seeded for guild %d — skipping zones/achievements.",
                guild_id,
            )
            session.commit()
            return

        logger.info("Seeding database for guild %d…", guild_id)

        # Season
        now = datetime.now(UTC)
        season = Season(
            guild_id=guild_id,
            name="Spring 2026",
            starts_at=now,
            ends_at=now + timedelta(days=120),
            active=True,
        )
        session.add(season)
        session.flush()

        # Zones + multipliers
        _seed_zones(session, guild_id)

        # Achievements
        _seed_achievements(session, guild_id)

        session.commit()
        logger.info("Database seeded successfully for guild %d.", guild_id)
