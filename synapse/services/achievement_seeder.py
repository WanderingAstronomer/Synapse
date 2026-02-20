"""
synapse.services.achievement_seeder — Default Achievement Taxonomy Seeder
==========================================================================

Idempotent seeder for the achievement taxonomy tables:
``achievement_rarities``, ``achievement_categories``, and ``seasons``.

Called once during bot startup (``setup_hook``) and safe to re-run at any
time — existing records are never modified or deleted.

Architecture note
-----------------
The seeder writes directly via a Session context manager rather than
going through ``admin_service`` because there is no meaningful human actor
to attribute to a bootstrap operation.  The audit trail is intentionally
not populated for seed data.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from synapse.database.models import AchievementCategory, AchievementRarity, Season

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default taxonomy definitions
# ---------------------------------------------------------------------------

_DEFAULT_RARITIES: list[dict] = [
    {"name": "Common", "color": "#9e9e9e", "emoji": "⬜", "sort_order": 0},
    {"name": "Uncommon", "color": "#4caf50", "emoji": "🟩", "sort_order": 1},
    {"name": "Rare", "color": "#2196f3", "emoji": "🟦", "sort_order": 2},
    {"name": "Epic", "color": "#9c27b0", "emoji": "🟪", "sort_order": 3},
    {"name": "Legendary", "color": "#ff9800", "emoji": "🟧", "sort_order": 4},
]

_DEFAULT_CATEGORIES: list[dict] = [
    {"name": "General", "icon": "🏅", "sort_order": 0},
    {"name": "Social", "icon": "💬", "sort_order": 1},
    {"name": "Activity", "icon": "⚡", "sort_order": 2},
    {"name": "Milestone", "icon": "🎯", "sort_order": 3},
    {"name": "Special", "icon": "✨", "sort_order": 4},
]

# Founding season: starts now, ends 10 years out — admin should set real dates.
_FOUNDING_SEASON_NAME = "Founding Season"
_FOUNDING_SEASON_DURATION_DAYS = 365 * 10  # ~10 years


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def seed_default_taxonomy(
    engine,  # type: ignore[type-arg]
    guild_id: int,
) -> dict[str, int]:
    """Upsert default rarity tiers and achievement categories.

    Parameters
    ----------
    engine : sqlalchemy.Engine
        Synchronous SQLAlchemy engine.
    guild_id : int
        The guild for which to seed taxonomy records.

    Returns
    -------
    dict[str, int]
        ``{"rarities": N, "categories": M}`` — counts of newly inserted rows.
    """
    inserted: dict[str, int] = {"rarities": 0, "categories": 0}

    with Session(engine) as session:
        # ── rarities ───────────────────────────────────────────────────────
        existing_rarity_names: set[str] = set(
            session.scalars(
                select(AchievementRarity.name).where(AchievementRarity.guild_id == guild_id)
            ).all()
        )

        for defn in _DEFAULT_RARITIES:
            if defn["name"] in existing_rarity_names:
                continue
            session.add(
                AchievementRarity(
                    guild_id=guild_id,
                    name=defn["name"],
                    color=defn["color"],
                    emoji=defn["emoji"],
                    sort_order=defn["sort_order"],
                )
            )
            inserted["rarities"] += 1

        # ── categories ─────────────────────────────────────────────────────
        existing_cat_names: set[str] = set(
            session.scalars(
                select(AchievementCategory.name).where(AchievementCategory.guild_id == guild_id)
            ).all()
        )

        for defn in _DEFAULT_CATEGORIES:
            if defn["name"] in existing_cat_names:
                continue
            session.add(
                AchievementCategory(
                    guild_id=guild_id,
                    name=defn["name"],
                    icon=defn["icon"],
                    sort_order=defn["sort_order"],
                )
            )
            inserted["categories"] += 1

        if inserted["rarities"] or inserted["categories"]:
            try:
                session.commit()
            except IntegrityError:
                # Benign race at startup (two workers on same guild) — discard.
                session.rollback()
                logger.debug("Taxonomy seed race for guild %d — rows already present.", guild_id)
                return {"rarities": 0, "categories": 0}
            logger.info(
                "Seeded %d rarity tiers and %d categories for guild %d.",
                inserted["rarities"],
                inserted["categories"],
                guild_id,
            )
        else:
            logger.debug("Achievement taxonomy already present for guild %d.", guild_id)

    return inserted


def seed_default_season(
    engine,  # type: ignore[type-arg]
    guild_id: int,
) -> bool:
    """Create a Founding Season if no seasons exist for this guild.

    Parameters
    ----------
    engine : sqlalchemy.Engine
        Synchronous SQLAlchemy engine.
    guild_id : int
        The guild for which to seed the initial season.

    Returns
    -------
    bool
        ``True`` if a new season was created, ``False`` if one already existed.
    """
    with Session(engine) as session:
        exists = session.scalar(select(Season.id).where(Season.guild_id == guild_id).limit(1))
        if exists is not None:
            logger.debug("Season already exists for guild %d — skipping.", guild_id)
            return False

        now = datetime.now(UTC)
        session.add(
            Season(
                guild_id=guild_id,
                name=_FOUNDING_SEASON_NAME,
                starts_at=now,
                ends_at=now + timedelta(days=_FOUNDING_SEASON_DURATION_DAYS),
                active=True,
            )
        )

        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            logger.debug("Season seed race for guild %d — season already inserted.", guild_id)
            return False

        logger.info("Seeded Founding Season for guild %d (active=True).", guild_id)
        return True
