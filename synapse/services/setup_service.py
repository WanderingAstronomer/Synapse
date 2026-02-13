"""
synapse.services.setup_service — First-Run Bootstrap & Guild Discovery
========================================================================

Replaces the legacy ``seed.py`` YAML-based initialization.  Instead of
reading fixture files, this service reads a **live guild snapshot** from
the database (written by the bot on ``on_ready``) and generates zones,
channel mappings, a default season, and baseline settings.

Key design choices (see D-IMPL-08 through D-IMPL-11):

- **Setup state** is tracked by a ``setup.initialized`` key in the
  ``Setting`` table.
- **Guild snapshot** is a JSON blob in ``Setting`` under the key
  ``guild.snapshot``.  The bot writes it every time it connects;
  the API reads it when the admin triggers bootstrap.
- **Idempotent re-runs** — calling ``bootstrap_guild()`` twice produces
  the same result.  Zones are upserted by name; channels are upserted
  by Discord snowflake; settings are insert-if-missing.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from synapse.database.models import (
    Season,
    Setting,
    Zone,
    ZoneChannel,
    ZoneMultiplier,
)

logger = logging.getLogger(__name__)

# Default multipliers for auto-created zones
_DEFAULT_MULTIPLIERS: dict[str, tuple[float, float]] = {
    "MESSAGE": (1.0, 1.0),
    "REACTION_RECEIVED": (1.0, 1.0),
    "VOICE_MINUTE": (1.0, 1.0),
    "THREAD_CREATE": (1.0, 1.0),
}

# Keys used in the Setting table for setup state
SETUP_INITIALIZED_KEY = "setup.initialized"
GUILD_SNAPSHOT_KEY = "guild.snapshot"
BOOTSTRAP_VERSION_KEY = "setup.bootstrap_version"
BOOTSTRAP_TIMESTAMP_KEY = "setup.bootstrap_timestamp"

# Current bootstrap version — bump when logic changes materially
BOOTSTRAP_VERSION = 1


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
@dataclass
class ChannelInfo:
    """Flattened representation of a guild channel."""
    id: int
    name: str
    type: str  # "text", "voice", "category", "forum", "stage"
    category_id: int | None = None
    category_name: str | None = None


@dataclass
class GuildSnapshot:
    """What the bot writes to the DB on connect."""
    guild_id: int
    guild_name: str
    channels: list[ChannelInfo] = field(default_factory=list)
    afk_channel_id: int | None = None
    captured_at: str = ""

    def to_json(self) -> str:
        return json.dumps({
            "guild_id": self.guild_id,
            "guild_name": self.guild_name,
            "channels": [
                {
                    "id": ch.id,
                    "name": ch.name,
                    "type": ch.type,
                    "category_id": ch.category_id,
                    "category_name": ch.category_name,
                }
                for ch in self.channels
            ],
            "afk_channel_id": self.afk_channel_id,
            "captured_at": self.captured_at or datetime.now(UTC).isoformat(),
        })

    @classmethod
    def from_json(cls, raw: str) -> GuildSnapshot:
        data = json.loads(raw)
        channels = [
            ChannelInfo(
                id=ch["id"],
                name=ch["name"],
                type=ch["type"],
                category_id=ch.get("category_id"),
                category_name=ch.get("category_name"),
            )
            for ch in data.get("channels", [])
        ]
        return cls(
            guild_id=data["guild_id"],
            guild_name=data["guild_name"],
            channels=channels,
            afk_channel_id=data.get("afk_channel_id"),
            captured_at=data.get("captured_at", ""),
        )


@dataclass
class BootstrapResult:
    """Structured result from a bootstrap run."""
    success: bool = True
    zones_created: int = 0
    zones_existing: int = 0
    channels_mapped: int = 0
    channels_existing: int = 0
    season_created: bool = False
    settings_written: int = 0
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Setup status helpers
# ---------------------------------------------------------------------------
def get_setup_status(engine) -> dict:
    """Return the current setup state as a dict for the API."""
    with Session(engine) as session:
        initialized = _get_setting(session, SETUP_INITIALIZED_KEY, False)
        version = _get_setting(session, BOOTSTRAP_VERSION_KEY, None)
        timestamp = _get_setting(session, BOOTSTRAP_TIMESTAMP_KEY, None)
        snapshot_raw = _get_raw_setting(session, GUILD_SNAPSHOT_KEY)

        has_snapshot = snapshot_raw is not None
        snapshot_info = None
        if has_snapshot and snapshot_raw:
            try:
                snap = GuildSnapshot.from_json(snapshot_raw)
                snapshot_info = {
                    "guild_id": str(snap.guild_id),
                    "guild_name": snap.guild_name,
                    "channel_count": len(snap.channels),
                    "captured_at": snap.captured_at,
                }
            except (json.JSONDecodeError, KeyError):
                has_snapshot = False

        zone_count = session.scalar(select(Zone.id).limit(1)) is not None

        return {
            "initialized": initialized,
            "bootstrap_version": version,
            "bootstrap_timestamp": timestamp,
            "has_guild_snapshot": has_snapshot,
            "guild_snapshot": snapshot_info,
            "has_zones": zone_count,
        }


def save_guild_snapshot(engine, snapshot: GuildSnapshot) -> None:
    """Persist the guild snapshot to the Setting table (called by bot)."""
    with Session(engine) as session:
        _upsert_setting(session, GUILD_SNAPSHOT_KEY, snapshot.to_json(),
                        category="setup", description="Guild channel snapshot from bot")
        session.commit()
    logger.info(
        "Guild snapshot saved: %d channels for guild %d",
        len(snapshot.channels), snapshot.guild_id,
    )


# ---------------------------------------------------------------------------
# Bot heartbeat
# ---------------------------------------------------------------------------
BOT_HEARTBEAT_KEY = "bot.heartbeat"


def save_bot_heartbeat(engine) -> None:
    """Write the current UTC timestamp as a heartbeat (called every ~30s by the bot)."""
    ts = datetime.now(UTC).isoformat()
    with Session(engine) as session:
        _upsert_setting(session, BOT_HEARTBEAT_KEY, json.dumps(ts),
                        category="setup", description="Bot last-alive heartbeat")
        session.commit()


def get_bot_heartbeat(engine) -> dict:
    """Return the bot heartbeat status for the health endpoint."""
    with Session(engine) as session:
        raw = _get_raw_setting(session, BOT_HEARTBEAT_KEY)
        if not raw:
            return {"status": "offline", "last_heartbeat": None}
        try:
            ts_str = json.loads(raw)
            last_dt = datetime.fromisoformat(ts_str)
            age_seconds = (datetime.now(UTC) - last_dt).total_seconds()
            status = "online" if age_seconds < 90 else "offline"
            return {
                "status": status,
                "last_heartbeat": ts_str,
                "age_seconds": round(age_seconds, 1),
            }
        except (json.JSONDecodeError, ValueError):
            return {"status": "offline", "last_heartbeat": None}


# ---------------------------------------------------------------------------
# Bootstrap logic
# ---------------------------------------------------------------------------
def bootstrap_guild(engine, guild_id: int) -> BootstrapResult:
    """Run first-run guild bootstrap: create zones, map channels, create season.

    Reads the guild snapshot from the Setting table (written by the bot
    on ``on_ready``).  If no snapshot exists, returns a warning.

    This function is **idempotent** — safe to call multiple times.
    """
    result = BootstrapResult()

    with Session(engine) as session:
        # Read guild snapshot (raw JSON string — don't double-decode)
        snapshot_raw = _get_raw_setting(session, GUILD_SNAPSHOT_KEY)
        if not snapshot_raw:
            result.success = False
            result.warnings.append(
                "No guild snapshot found.  The bot must connect to Discord "
                "at least once before bootstrap can run."
            )
            return result

        try:
            snapshot = GuildSnapshot.from_json(snapshot_raw)
        except (json.JSONDecodeError, KeyError) as exc:
            result.success = False
            result.warnings.append(f"Guild snapshot is corrupt: {exc}")
            return result

        if snapshot.guild_id != guild_id:
            result.warnings.append(
                f"Snapshot guild ({snapshot.guild_id}) differs from config guild "
                f"({guild_id}).  Using snapshot data anyway."
            )

        # ------------------------------------------------------------------
        # Step 1: Create zones from Discord categories
        # ------------------------------------------------------------------
        categories: dict[str, int] = {}  # name -> category snowflake
        for ch in snapshot.channels:
            if ch.type == "category":
                categories[ch.name] = ch.id

        # If guild has no categories, create a single "General" zone
        if not categories:
            categories["General"] = 0
            result.warnings.append(
                "Guild has no categories — created a single 'General' zone."
            )

        existing_zones = {
            z.name.lower(): z
            for z in session.scalars(
                select(Zone).where(Zone.guild_id == guild_id)
            ).all()
        }

        zone_by_name: dict[str, Zone] = {}
        for cat_name in categories:
            lower = cat_name.lower()
            if lower in existing_zones:
                zone_by_name[cat_name] = existing_zones[lower]
                result.zones_existing += 1
            else:
                zone = Zone(
                    guild_id=guild_id,
                    name=cat_name,
                    description=f"Auto-created from Discord category '{cat_name}'",
                )
                session.add(zone)
                session.flush()  # get zone.id

                # Add default multipliers
                for itype, (xp_m, star_m) in _DEFAULT_MULTIPLIERS.items():
                    session.add(ZoneMultiplier(
                        zone_id=zone.id,
                        interaction_type=itype,
                        xp_multiplier=xp_m,
                        star_multiplier=star_m,
                    ))

                zone_by_name[cat_name] = zone
                result.zones_created += 1
                logger.info("Created zone '%s' (id=%d)", cat_name, zone.id)

        # ------------------------------------------------------------------
        # Step 2: Map channels to zones by category membership
        # ------------------------------------------------------------------
        existing_channel_ids: set[int] = {
            row
            for row in session.scalars(select(ZoneChannel.channel_id)).all()
        }

        # Build a fallback zone (first zone or "General")
        fallback_zone = zone_by_name.get("General") or next(iter(zone_by_name.values()), None)

        for ch in snapshot.channels:
            if ch.type == "category":
                continue  # Don't map category channels themselves
            if ch.id in existing_channel_ids:
                result.channels_existing += 1
                continue

            # Find zone by category name
            target_zone = None
            if ch.category_name and ch.category_name in zone_by_name:
                target_zone = zone_by_name[ch.category_name]
            elif fallback_zone:
                target_zone = fallback_zone

            if target_zone:
                session.add(ZoneChannel(
                    zone_id=target_zone.id,
                    channel_id=ch.id,
                ))
                result.channels_mapped += 1

        # ------------------------------------------------------------------
        # Step 3: Ensure a default season exists
        # ------------------------------------------------------------------
        existing_season = session.scalar(
            select(Season.id).where(
                Season.guild_id == guild_id,
                Season.active.is_(True),
            ).limit(1)
        )
        if not existing_season:
            now = datetime.now(UTC)
            session.add(Season(
                guild_id=guild_id,
                name="Season 1",
                starts_at=now,
                ends_at=now + timedelta(days=120),
                active=True,
            ))
            result.season_created = True
            logger.info("Created default season for guild %d", guild_id)

        # ------------------------------------------------------------------
        # Step 4: Write default settings
        # ------------------------------------------------------------------
        defaults = _default_settings()
        for key, (value, category, desc) in defaults.items():
            if not _setting_exists(session, key):
                _upsert_setting(session, key, json.dumps(value), category, desc)
                result.settings_written += 1

        # ------------------------------------------------------------------
        # Step 5: Mark setup as initialized
        # ------------------------------------------------------------------
        _upsert_setting(
            session, SETUP_INITIALIZED_KEY, json.dumps(True),
            "setup", "Whether first-run bootstrap has completed",
        )
        _upsert_setting(
            session, BOOTSTRAP_VERSION_KEY, json.dumps(BOOTSTRAP_VERSION),
            "setup", "Bootstrap logic version",
        )
        _upsert_setting(
            session, BOOTSTRAP_TIMESTAMP_KEY,
            json.dumps(datetime.now(UTC).isoformat()),
            "setup", "When bootstrap last ran",
        )

        session.commit()

    logger.info(
        "Bootstrap complete: %d zones created, %d channels mapped, season=%s",
        result.zones_created, result.channels_mapped, result.season_created,
    )
    return result


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------
def _get_setting(session: Session, key: str, default=None):
    """Read a setting value, JSON-decoded."""
    row = session.get(Setting, key)
    if row is None:
        return default
    try:
        return json.loads(row.value_json)
    except (json.JSONDecodeError, TypeError):
        return row.value_json


def _get_raw_setting(session: Session, key: str) -> str | None:
    """Read a setting's raw ``value_json`` string without decoding."""
    row = session.get(Setting, key)
    return row.value_json if row else None


def _setting_exists(session: Session, key: str) -> bool:
    return session.get(Setting, key) is not None


def _upsert_setting(
    session: Session,
    key: str,
    value_json: str,
    category: str = "general",
    description: str | None = None,
) -> None:
    """Insert or update a setting row."""
    row = session.get(Setting, key)
    if row:
        row.value_json = value_json
        if description:
            row.description = description
    else:
        session.add(Setting(
            key=key,
            value_json=value_json,
            category=category,
            description=description,
        ))


def _default_settings() -> dict[str, tuple]:
    """Return default settings as {key: (value, category, description)}."""
    return {
        "economy.xp_per_message": (5, "economy", "Base XP awarded per message"),
        "economy.xp_per_reaction": (2, "economy", "Base XP awarded per reaction received"),
        "economy.xp_per_voice_minute": (1, "economy", "Base XP per voice minute"),
        "economy.gold_per_message": (1, "economy", "Base gold per message"),
        "economy.message_cooldown_seconds": (60, "anti_gaming", "Min seconds between XP-earning messages"),
        "economy.daily_xp_cap": (500, "anti_gaming", "Max XP a user can earn per day"),
        "economy.daily_gold_cap": (100, "anti_gaming", "Max gold a user can earn per day"),
        "anti_gaming.min_message_length": (5, "anti_gaming", "Minimum message length for XP"),
        "anti_gaming.unique_reactor_threshold": (3, "anti_gaming", "Unique reactors needed for full value"),
        "anti_gaming.diminishing_returns_after": (50, "anti_gaming", "Messages after which diminishing returns kick in"),
        "quality.code_block_bonus": (1.5, "quality", "Multiplier for messages with code blocks"),
        "quality.link_bonus": (1.2, "quality", "Multiplier for messages with links"),
        "quality.long_message_threshold": (200, "quality", "Character count for long-message bonus"),
        "quality.long_message_bonus": (1.3, "quality", "Multiplier for long messages"),
        "announcements.achievement_channel_enabled": (True, "announcements", "Post level-ups and achievements"),
        "announcements.leaderboard_public": (True, "display", "Show public leaderboard page"),
        "economy.primary_currency_name": ("XP", "economy", "Display name for primary currency (e.g. XP, Honor, Karma)"),
        "economy.secondary_currency_name": ("Gold", "economy", "Display name for secondary currency (e.g. Gold, Loot, Credits)"),
    }
