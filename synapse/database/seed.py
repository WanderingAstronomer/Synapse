"""
synapse.database.seed — Default Settings Seeder
=================================================

Baseline settings seeded on first startup so the dashboard is immediately
usable (economy, anti-gaming, quality, display, announcements).

Idempotent — only inserts keys that don't already exist.  Settings
created by later bootstrap or admin edits are never overwritten.
"""

from __future__ import annotations

import json
import logging

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from synapse.database.models import Setting

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Default settings catalogue
# ---------------------------------------------------------------------------
DEFAULT_SETTINGS: dict[str, tuple[object, str, str]] = {
    "economy.xp_per_message": (5, "economy", "Base XP awarded per message"),
    "economy.xp_per_reaction": (2, "economy", "Base XP awarded per reaction received"),
    "economy.xp_per_voice_minute": (1, "economy", "Base XP per voice minute"),
    "economy.gold_per_message": (1, "economy", "Base gold per message"),
    "economy.message_cooldown_seconds": (
        60, "anti_gaming", "Min seconds between XP-earning messages",
    ),
    "economy.daily_xp_cap": (500, "anti_gaming", "Max XP a user can earn per day"),
    "economy.daily_gold_cap": (100, "anti_gaming", "Max gold a user can earn per day"),
    "anti_gaming.min_message_length": (5, "anti_gaming", "Minimum message length for XP"),
    "anti_gaming.unique_reactor_threshold": (
        3, "anti_gaming", "Unique reactors needed for full value",
    ),
    "anti_gaming.diminishing_returns_after": (
        50, "anti_gaming", "Messages after which diminishing returns kick in",
    ),
    "quality.code_block_bonus": (1.5, "quality", "Multiplier for messages with code blocks"),
    "quality.link_bonus": (1.2, "quality", "Multiplier for messages with links"),
    "quality.long_message_threshold": (200, "quality", "Character count for long-message bonus"),
    "quality.long_message_bonus": (1.3, "quality", "Multiplier for long messages"),
    "announcements.achievement_channel_enabled": (
        True, "announcements", "Post level-ups and achievements",
    ),
    "announcements.leaderboard_public": (True, "display", "Show public leaderboard page"),
    "economy.primary_currency_name": (
        "XP", "economy", "Display name for primary currency (e.g. XP, Honor, Karma)",
    ),
    "economy.secondary_currency_name": (
        "Gold", "economy", "Display name for secondary currency (e.g. Gold, Loot, Credits)",
    ),
    "display.favicon_url": (
        "", "display", "URL for the dashboard favicon (leave blank for default emoji)",
    ),
    "display.primary_color": (
        "", "display", "Primary brand color hex code (e.g. #7c3aed)",
    ),
    "display.dashboard_title": (
        "Community Dashboard", "display", "Display name for the dashboard / home page",
    ),
    "display.leaderboard_title": (
        "Leaderboard", "display", "Display name for the leaderboard page",
    ),
    "display.activity_title": (
        "Activity", "display", "Display name for the activity page",
    ),
    "display.achievements_title": (
        "Achievements", "display", "Display name for the achievements page",
    ),
}
"""Each entry maps ``key`` → ``(default_value, category, description)``."""


# ---------------------------------------------------------------------------
# Seeder
# ---------------------------------------------------------------------------
def seed_default_settings(engine: Engine) -> None:
    """Insert default settings that don't yet exist.

    Runs on every startup but only writes rows for keys that are missing,
    so it is safe to call repeatedly.  Settings created by later bootstrap
    or admin edits are never overwritten.
    """
    session = Session(engine)
    inserted = 0
    try:
        for key, (value, category, desc) in DEFAULT_SETTINGS.items():
            existing = session.get(Setting, key)
            if existing is None:
                session.add(Setting(
                    key=key,
                    value_json=json.dumps(value),
                    category=category,
                    description=desc,
                ))
                inserted += 1
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    if inserted:
        logger.info("Seeded %d default settings.", inserted)
