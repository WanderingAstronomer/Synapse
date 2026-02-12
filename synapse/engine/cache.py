"""
synapse.engine.cache — In-Memory Config Cache with PG LISTEN/NOTIFY
=====================================================================

Implements the caching strategy per the original Reward Engine design (§5.12, D05-08).
Note: 05_REWARD_ENGINE.md has been superseded by 05_RULES_ENGINE.md in v4.0 docs.
Config data (zones, multipliers, achievement templates, settings) is cached
in memory.  Cache invalidation uses PostgreSQL LISTEN/NOTIFY so admin
changes propagate near-instantly.
"""

from __future__ import annotations

import asyncio
import json
import logging
import select as _select
import threading
from typing import TYPE_CHECKING, Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from synapse.database.models import (
    AchievementTemplate,
    Setting,
    Zone,
    ZoneMultiplier,
)

if TYPE_CHECKING:
    from sqlalchemy import Engine

logger = logging.getLogger(__name__)

# The PG channel name used for config invalidation
NOTIFY_CHANNEL = "config_changed"


class ConfigCache:
    """Thread-safe in-memory cache for zone/multiplier/achievement/setting config.

    Usage:
        cache = ConfigCache(engine)
        cache.load_all()  # Initial load
        cache.start_listener()  # Background PG LISTEN task

        zone = cache.get_zone_for_channel(channel_id)
        xp_mult, star_mult = cache.get_multipliers(zone_id, event_type)
        templates = cache.get_active_achievements(guild_id)

        # Typed setting accessors
        base_xp = cache.get_int("base_xp_message", default=15)
        factor  = cache.get_float("level_factor", default=1.25)
    """

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._lock = threading.Lock()

        # channel_id → Zone
        self._channel_zone: dict[int, Zone] = {}
        # (zone_id, interaction_type) → (xp_mult, star_mult)
        self._multipliers: dict[tuple[int, str], tuple[float, float]] = {}
        # guild_id → list[AchievementTemplate]
        self._achievements: dict[int, list[AchievementTemplate]] = {}
        # zone_id → Zone
        self._zones: dict[int, Zone] = {}
        # key → parsed JSON value
        self._settings: dict[str, Any] = {}

        self._listener_task: asyncio.Task | None = None

    # -------------------------------------------------------------------
    # Cache loading (synchronous — called via run_db or directly)
    # -------------------------------------------------------------------
    def load_all(self) -> None:
        """Load all config caches from DB. Call on startup."""
        self._load_zones()
        self._load_multipliers()
        self._load_achievements()
        self._load_settings()
        logger.info(
            "ConfigCache loaded: %d channel mappings, %d multiplier rules, "
            "%d achievement templates, %d settings",
            len(self._channel_zone),
            len(self._multipliers),
            sum(len(v) for v in self._achievements.values()),
            len(self._settings),
        )

    def _load_zones(self) -> None:
        with Session(self._engine) as session:
            zones = session.scalars(
                select(Zone).where(Zone.active.is_(True))
            ).all()
            channel_zone: dict[int, Zone] = {}
            zones_by_id: dict[int, Zone] = {}
            for z in zones:
                # Eagerly load channels
                for ch in z.channels:
                    channel_zone[ch.channel_id] = z
                zones_by_id[z.id] = z
                session.expunge(z)

        with self._lock:
            self._channel_zone = channel_zone
            self._zones = zones_by_id

    def _load_multipliers(self) -> None:
        with Session(self._engine) as session:
            rows = session.scalars(select(ZoneMultiplier)).all()
            mults: dict[tuple[int, str], tuple[float, float]] = {}
            for m in rows:
                mults[(m.zone_id, m.interaction_type)] = (
                    m.xp_multiplier,
                    m.star_multiplier,
                )

        with self._lock:
            self._multipliers = mults

    def _load_achievements(self) -> None:
        with Session(self._engine) as session:
            templates = session.scalars(
                select(AchievementTemplate).where(AchievementTemplate.active.is_(True))
            ).all()
            by_guild: dict[int, list[AchievementTemplate]] = {}
            for t in templates:
                session.expunge(t)
                by_guild.setdefault(t.guild_id, []).append(t)

        with self._lock:
            self._achievements = by_guild

    def _load_settings(self) -> None:
        with Session(self._engine) as session:
            rows = session.scalars(select(Setting)).all()
            parsed: dict[str, Any] = {}
            for row in rows:
                try:
                    parsed[row.key] = json.loads(row.value_json)
                except (json.JSONDecodeError, TypeError):
                    parsed[row.key] = row.value_json

        with self._lock:
            self._settings = parsed

    # -------------------------------------------------------------------
    # Cache reads (thread-safe)
    # -------------------------------------------------------------------
    def get_zone_for_channel(self, channel_id: int) -> Zone | None:
        with self._lock:
            return self._channel_zone.get(channel_id)

    def get_multipliers(self, zone_id: int | None, event_type: str) -> tuple[float, float]:
        """Returns (xp_multiplier, star_multiplier) for zone+event."""
        if zone_id is None:
            return (1.0, 1.0)
        with self._lock:
            return self._multipliers.get((zone_id, event_type), (1.0, 1.0))

    def get_active_achievements(self, guild_id: int) -> list[AchievementTemplate]:
        with self._lock:
            return list(self._achievements.get(guild_id, []))

    def get_zone(self, zone_id: int) -> Zone | None:
        with self._lock:
            return self._zones.get(zone_id)

    # -------------------------------------------------------------------
    # Typed setting accessors (thread-safe)
    # -------------------------------------------------------------------
    def get_setting(self, key: str, default: Any = None) -> Any:
        """Return the parsed JSON value for *key*, or *default*."""
        with self._lock:
            return self._settings.get(key, default)

    def get_int(self, key: str, default: int = 0) -> int:
        """Return an integer setting, falling back to *default*."""
        val = self.get_setting(key)
        if val is None:
            return default
        try:
            return int(val)
        except (TypeError, ValueError):
            return default

    def get_float(self, key: str, default: float = 0.0) -> float:
        """Return a float setting, falling back to *default*."""
        val = self.get_setting(key)
        if val is None:
            return default
        try:
            return float(val)
        except (TypeError, ValueError):
            return default

    def get_str(self, key: str, default: str = "") -> str:
        """Return a string setting, falling back to *default*."""
        val = self.get_setting(key)
        if val is None:
            return default
        return str(val)

    def get_bool(self, key: str, default: bool = False) -> bool:
        """Return a boolean setting, falling back to *default*."""
        val = self.get_setting(key)
        if val is None:
            return default
        if isinstance(val, bool):
            return val
        if isinstance(val, str):
            return val.lower() in ("true", "1", "yes")
        return bool(val)

    # -------------------------------------------------------------------
    # Cache invalidation via NOTIFY
    # -------------------------------------------------------------------
    def handle_notify(self, table_name: str) -> None:
        """Reload the relevant cache partition when a NOTIFY arrives."""
        table_name = table_name.strip().lower()
        logger.info("Config cache invalidation for table: %s", table_name)

        if table_name in ("zones", "zone_channels"):
            self._load_zones()
        elif table_name == "zone_multipliers":
            self._load_multipliers()
        elif table_name == "achievement_templates":
            self._load_achievements()
        elif table_name == "settings":
            self._load_settings()
        else:
            logger.warning("Unknown table in NOTIFY: %s — ignoring", table_name)

    def start_listener(self, loop: asyncio.AbstractEventLoop | None = None) -> None:
        """Start a background thread that LISTENs on the PG channel.

        The thread uses raw psycopg2 connection + select() to avoid
        blocking the asyncio event loop.
        """
        import psycopg2

        def _listen_thread() -> None:
            # NOTE: str(engine.url) hides the password by default (***).
            # psycopg2 needs the real password for LISTEN/NOTIFY.
            raw_url = self._engine.url.render_as_string(hide_password=False)
            # Convert SQLAlchemy URL to psycopg2 DSN
            dsn = raw_url.replace("postgresql+psycopg2://", "postgresql://")
            try:
                conn = psycopg2.connect(dsn)
                conn.set_isolation_level(0)  # autocommit
                cur = conn.cursor()
                cur.execute(f"LISTEN {NOTIFY_CHANNEL};")
                logger.info("PG LISTEN started on channel '%s'", NOTIFY_CHANNEL)

                while True:
                    if _select.select([conn], [], [], 5.0) == ([], [], []):
                        continue
                    conn.poll()
                    while conn.notifies:
                        notify = conn.notifies.pop(0)
                        payload = notify.payload or ""
                        logger.debug("NOTIFY received: %s", payload)
                        try:
                            self.handle_notify(payload)
                        except Exception:
                            logger.exception("Error handling NOTIFY payload: %s", payload)
            except Exception:
                logger.exception("PG LISTEN thread crashed")

        thread = threading.Thread(target=_listen_thread, daemon=True, name="pg-notify-listener")
        thread.start()
        logger.info("PG NOTIFY listener thread started")


def send_notify(engine: Engine, table_name: str) -> None:
    """Send a NOTIFY on the config_changed channel.

    Called by the service layer after committing an admin mutation.
    Must be called OUTSIDE the transaction (after commit) using a
    separate connection or autocommit mode.
    """
    with engine.connect() as conn:
        conn.execute(text(f"NOTIFY {NOTIFY_CHANNEL}, '{table_name}'"))
        conn.commit()
