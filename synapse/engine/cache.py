"""
synapse.engine.cache — In-Memory Config Cache with PG LISTEN/NOTIFY
=====================================================================

Implements the caching strategy for the channel-first reward system.
Config data (channel type defaults, channel overrides, achievement templates,
settings) is cached in memory.  Cache invalidation uses PostgreSQL
LISTEN/NOTIFY so admin changes propagate near-instantly.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import select as _select
import threading
import time
from typing import TYPE_CHECKING, Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from synapse.database.models import (
    AchievementCategory,
    AchievementRarity,
    AchievementTemplate,
    Channel,
    ChannelOverride,
    ChannelTypeDefault,
    Setting,
)

if TYPE_CHECKING:
    from sqlalchemy import Engine

logger = logging.getLogger(__name__)

# The PG channel name used for config invalidation
NOTIFY_CHANNEL = "config_changed"

# PG channel for cross-service event notifications (e.g. achievement grants)
EVENT_NOTIFY_CHANNEL = "synapse_events"

# Allowlist of table names accepted by send_notify() (F-005).
ALLOWED_NOTIFY_TABLES: frozenset[str] = frozenset({
    "channel_type_defaults",
    "channel_overrides",
    "channels",
    "achievement_templates",
    "achievement_categories",
    "achievement_rarities",
    "achievement_series",
    "settings",
})


class ConfigCache:
    """Thread-safe in-memory cache for reward rules, achievements, and settings.

    Resolution order for multipliers:
      1. ChannelOverride(channel_id, event_type)  — exact match
      2. ChannelOverride(channel_id, '*')          — wildcard event
      3. ChannelTypeDefault(channel.type, event_type) — type default
      4. ChannelTypeDefault(channel.type, '*')     — type wildcard
      5. (1.0, 1.0)                                — system default

    Usage:
        cache = ConfigCache(engine)
        cache.load_all()
        cache.start_listener()

        xp_mult, star_mult = cache.resolve_multipliers(channel_id, event_type)
        templates = cache.get_active_achievements(guild_id)
        base_xp = cache.get_int("base_xp_message", default=15)
    """

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._lock = threading.Lock()

        # (guild_id, channel_type, event_type) → (xp_mult, star_mult)
        self._type_defaults: dict[tuple[int, str, str], tuple[float, float]] = {}
        # (channel_id, event_type) → (xp_mult, star_mult)
        self._overrides: dict[tuple[int, str], tuple[float, float]] = {}
        # channel_id → (guild_id, channel_type)
        self._channel_info: dict[int, tuple[int, str]] = {}
        # guild_id → list[AchievementTemplate]
        self._achievements: dict[int, list[AchievementTemplate]] = {}
        # guild_id → list[AchievementCategory]
        self._achievement_categories: dict[int, list[AchievementCategory]] = {}
        # guild_id → list[AchievementRarity]
        self._achievement_rarities: dict[int, list[AchievementRarity]] = {}
        # series_id → list[AchievementTemplate]  (ordered by series_order)
        self._series_tiers: dict[int, list[AchievementTemplate]] = {}
        # key → parsed JSON value
        self._settings: dict[str, Any] = {}

        self._listener_task: asyncio.Task | None = None
        self._listener_healthy: bool = False
        self._listener_failed: bool = False
        self._listener_thread: threading.Thread | None = None
        self._shutdown_event = threading.Event()

        # Event notification callbacks: event_type → async callable
        self._event_callbacks: dict[str, Any] = {}
        self._event_loop: asyncio.AbstractEventLoop | None = None

    # -------------------------------------------------------------------
    # Cache loading (synchronous — called via run_db or directly)
    # -------------------------------------------------------------------
    def load_all(self) -> None:
        """Load all config caches from DB. Call on startup."""
        self._load_channels()
        self._load_type_defaults()
        self._load_overrides()
        self._load_achievements()
        self._load_achievement_categories()
        self._load_achievement_rarities()
        self._load_settings()
        logger.info(
            "ConfigCache loaded: %d channels, %d type defaults, "
            "%d overrides, %d achievement templates, %d categories, "
            "%d rarities, %d settings",
            len(self._channel_info),
            len(self._type_defaults),
            len(self._overrides),
            sum(len(v) for v in self._achievements.values()),
            sum(len(v) for v in self._achievement_categories.values()),
            sum(len(v) for v in self._achievement_rarities.values()),
            len(self._settings),
        )

    def _load_channels(self) -> None:
        """Load channel_id → (guild_id, type) mapping."""
        with Session(self._engine) as session:
            rows = session.scalars(select(Channel)).all()
            info: dict[int, tuple[int, str]] = {}
            for ch in rows:
                info[ch.id] = (ch.guild_id, ch.type)
        with self._lock:
            self._channel_info = info

    def _load_type_defaults(self) -> None:
        with Session(self._engine) as session:
            rows = session.scalars(select(ChannelTypeDefault)).all()
            defaults: dict[tuple[int, str, str], tuple[float, float]] = {}
            for d in rows:
                defaults[(d.guild_id, d.channel_type, d.event_type)] = (
                    d.xp_multiplier,
                    d.star_multiplier,
                )
        with self._lock:
            self._type_defaults = defaults

    def _load_overrides(self) -> None:
        with Session(self._engine) as session:
            rows = session.scalars(select(ChannelOverride)).all()
            ovr: dict[tuple[int, str], tuple[float, float]] = {}
            for o in rows:
                ovr[(o.channel_id, o.event_type)] = (
                    o.xp_multiplier,
                    o.star_multiplier,
                )
        with self._lock:
            self._overrides = ovr

    def _load_achievements(self) -> None:
        with Session(self._engine) as session:
            templates = session.scalars(
                select(AchievementTemplate).where(AchievementTemplate.active.is_(True))
            ).all()
            by_guild: dict[int, list[AchievementTemplate]] = {}
            by_series: dict[int, list[AchievementTemplate]] = {}
            for t in templates:
                session.expunge(t)
                by_guild.setdefault(t.guild_id, []).append(t)
                if t.series_id is not None:
                    by_series.setdefault(t.series_id, []).append(t)

            # Sort series tiers by series_order
            for sid in by_series:
                by_series[sid].sort(key=lambda x: x.series_order or 0)

        with self._lock:
            self._achievements = by_guild
            self._series_tiers = by_series

    def _load_achievement_categories(self) -> None:
        with Session(self._engine) as session:
            rows = session.scalars(
                select(AchievementCategory).order_by(AchievementCategory.sort_order)
            ).all()
            by_guild: dict[int, list[AchievementCategory]] = {}
            for c in rows:
                session.expunge(c)
                by_guild.setdefault(c.guild_id, []).append(c)
        with self._lock:
            self._achievement_categories = by_guild

    def _load_achievement_rarities(self) -> None:
        with Session(self._engine) as session:
            rows = session.scalars(
                select(AchievementRarity).order_by(AchievementRarity.sort_order)
            ).all()
            by_guild: dict[int, list[AchievementRarity]] = {}
            for r in rows:
                session.expunge(r)
                by_guild.setdefault(r.guild_id, []).append(r)
        with self._lock:
            self._achievement_rarities = by_guild

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
    def resolve_multipliers(
        self, channel_id: int, event_type: str
    ) -> tuple[float, float]:
        """Resolve (xp_multiplier, star_multiplier) for a channel + event.

        Resolution order:
          1. override(channel_id, event_type)
          2. override(channel_id, '*')
          3. type_default(channel.type, event_type)
          4. type_default(channel.type, '*')
          5. (1.0, 1.0)
        """
        with self._lock:
            # 1. Exact override
            result = self._overrides.get((channel_id, event_type))
            if result is not None:
                return result

            # 2. Wildcard override
            result = self._overrides.get((channel_id, "*"))
            if result is not None:
                return result

            # 3+4. Type defaults (need guild_id + channel_type)
            info = self._channel_info.get(channel_id)
            if info is not None:
                guild_id, ch_type = info
                # 3. Exact type default
                result = self._type_defaults.get((guild_id, ch_type, event_type))
                if result is not None:
                    return result
                # 4. Wildcard type default
                result = self._type_defaults.get((guild_id, ch_type, "*"))
                if result is not None:
                    return result

        return (1.0, 1.0)

    def get_active_achievements(self, guild_id: int) -> list[AchievementTemplate]:
        with self._lock:
            return list(self._achievements.get(guild_id, []))

    def get_series_predecessor(
        self, series_id: int, current_order: int,
    ) -> AchievementTemplate | None:
        """Return the template with the tier just before *current_order*.

        Returns None if there is no predecessor (i.e. current_order == 1
        or the series is unknown).
        """
        with self._lock:
            tiers = self._series_tiers.get(series_id, [])
        # Find the highest-ordered tier that is still below current_order
        predecessor = None
        for t in tiers:
            if t.series_order is not None and t.series_order < current_order:
                predecessor = t
        return predecessor

    def get_achievement_categories(
        self, guild_id: int,
    ) -> list[AchievementCategory]:
        with self._lock:
            return list(self._achievement_categories.get(guild_id, []))

    def get_achievement_rarities(
        self, guild_id: int,
    ) -> list[AchievementRarity]:
        with self._lock:
            return list(self._achievement_rarities.get(guild_id, []))

    # -------------------------------------------------------------------
    # Typed setting accessors (thread-safe)
    # -------------------------------------------------------------------
    def get_setting(self, key: str, default: Any = None) -> Any:
        """Return the parsed JSON value for *key*, or *default*."""
        with self._lock:
            return self._settings.get(key, default)

    def get_int(self, key: str, default: int = 0) -> int:
        val = self.get_setting(key)
        if val is None:
            return default
        try:
            return int(val)
        except (TypeError, ValueError):
            return default

    def get_float(self, key: str, default: float = 0.0) -> float:
        val = self.get_setting(key)
        if val is None:
            return default
        try:
            return float(val)
        except (TypeError, ValueError):
            return default

    def get_bool(self, key: str, default: bool = False) -> bool:
        val = self.get_setting(key)
        if val is None:
            return default
        return bool(val)

    # -------------------------------------------------------------------
    # Cache invalidation via NOTIFY
    # -------------------------------------------------------------------
    def handle_notify(self, table_name: str) -> None:
        """Reload the relevant cache partition when a NOTIFY arrives."""
        table_name = table_name.strip().lower()
        logger.info("Config cache invalidation for table: %s", table_name)

        if table_name == "channel_type_defaults":
            self._load_type_defaults()
        elif table_name == "channel_overrides":
            self._load_overrides()
        elif table_name == "channels":
            self._load_channels()
        elif table_name == "achievement_templates":
            self._load_achievements()
        elif table_name == "achievement_categories":
            self._load_achievement_categories()
        elif table_name == "achievement_rarities":
            self._load_achievement_rarities()
        elif table_name == "achievement_series":
            self._load_achievements()  # series data lives in templates
        elif table_name == "settings":
            self._load_settings()
        else:
            logger.warning("Unknown table in NOTIFY: %s — ignoring", table_name)

    @property
    def listener_healthy(self) -> bool:
        """Return True if the LISTEN thread is alive and connected."""
        return self._listener_healthy and not self._listener_failed

    @property
    def listener_failed(self) -> bool:
        """Return True if the listener exhausted reconnect attempts."""
        return self._listener_failed

    def stop_listener(self) -> None:
        """Signal the listener thread to stop and wait for it to exit."""
        self._shutdown_event.set()
        if self._listener_thread is not None and self._listener_thread.is_alive():
            self._listener_thread.join(timeout=5)
            logger.info("PG NOTIFY listener thread stopped")

    def start_listener(self, loop: asyncio.AbstractEventLoop | None = None) -> None:
        """Start a background thread that LISTENs on the PG channel.

        The thread uses raw psycopg2 connection + select() to avoid
        blocking the asyncio event loop.  Includes automatic reconnection
        with exponential backoff + jitter if the connection drops (F-006).
        """
        import psycopg2

        # Maximum backoff: 60 seconds
        max_backoff = 60.0
        base_backoff = 1.0
        max_reconnect_attempts = 10  # Circuit breaker (TD-002)

        def _listen_thread() -> None:
            # NOTE: str(engine.url) hides the password by default (***).
            # psycopg2 needs the real password for LISTEN/NOTIFY.
            raw_url = self._engine.url.render_as_string(hide_password=False)
            # Convert SQLAlchemy URL to psycopg2 DSN
            dsn = raw_url.replace("postgresql+psycopg2://", "postgresql://")
            attempt = 0

            while not self._shutdown_event.is_set():
                conn = None
                try:
                    conn = psycopg2.connect(dsn)
                    conn.set_isolation_level(0)  # autocommit
                    cur = conn.cursor()
                    cur.execute(f"LISTEN {NOTIFY_CHANNEL};")
                    cur.execute(f"LISTEN {EVENT_NOTIFY_CHANNEL};")
                    logger.info(
                        "PG LISTEN started on channels '%s', '%s'",
                        NOTIFY_CHANNEL, EVENT_NOTIFY_CHANNEL,
                    )

                    # Reset backoff on successful connection
                    attempt = 0
                    self._listener_healthy = True

                    while not self._shutdown_event.is_set():
                        if _select.select([conn], [], [], 5.0) == ([], [], []):
                            continue
                        conn.poll()
                        while conn.notifies:
                            notify = conn.notifies.pop(0)
                            channel = notify.channel
                            payload = notify.payload or ""
                            logger.debug(
                                "NOTIFY received on '%s': %s", channel, payload,
                            )
                            try:
                                if channel == EVENT_NOTIFY_CHANNEL:
                                    self._dispatch_event(payload)
                                else:
                                    self.handle_notify(payload)
                            except Exception:
                                logger.exception(
                                    "Error handling NOTIFY on '%s': %s",
                                    channel, payload,
                                )

                except Exception:
                    self._listener_healthy = False
                    attempt += 1

                    # Circuit breaker: stop retrying after max attempts (TD-002)
                    if attempt >= max_reconnect_attempts:
                        logger.critical(
                            "PG LISTEN exhausted %d retries. "
                            "Cache invalidation disabled.",
                            max_reconnect_attempts,
                        )
                        self._listener_failed = True
                        break

                    backoff = min(base_backoff * (2 ** (attempt - 1)), max_backoff)
                    jitter = random.uniform(0, backoff * 0.5)
                    wait = backoff + jitter
                    logger.exception(
                        "PG LISTEN connection lost (attempt %d/%d). "
                        "Reconnecting in %.1fs…",
                        attempt, max_reconnect_attempts, wait,
                    )
                    # Interruptible sleep: exits early on shutdown signal
                    if self._shutdown_event.wait(timeout=wait):
                        break
                finally:
                    if conn is not None:
                        try:
                            conn.close()
                        except Exception:
                            pass

        thread = threading.Thread(target=_listen_thread, daemon=True, name="pg-notify-listener")
        self._listener_thread = thread
        thread.start()
        logger.info("PG NOTIFY listener thread started")

    def register_event_callback(
        self,
        event_type: str,
        callback: Any,
        loop: asyncio.AbstractEventLoop | None = None,
    ) -> None:
        """Register an async callback for a specific event type.

        Parameters
        ----------
        event_type : str
            Event type key (e.g. ``"achievement_granted"``).
        callback : coroutine function
            Async callable invoked with the parsed JSON payload dict.
        loop : asyncio.AbstractEventLoop, optional
            Event loop on which to schedule the callback.  Stored once.
        """
        self._event_callbacks[event_type] = callback
        if loop is not None:
            self._event_loop = loop
        logger.info("Registered event callback for '%s'", event_type)

    def _dispatch_event(self, raw_payload: str) -> None:
        """Parse a JSON event payload and dispatch to the registered callback."""
        try:
            data = json.loads(raw_payload)
        except (json.JSONDecodeError, TypeError):
            logger.warning("Invalid event payload (not JSON): %s", raw_payload)
            return

        event_type = data.get("type")
        if not event_type:
            logger.warning("Event payload missing 'type' key: %s", raw_payload)
            return

        callback = self._event_callbacks.get(event_type)
        if callback is None:
            logger.debug("No callback registered for event type '%s'", event_type)
            return

        loop = self._event_loop
        if loop is None or loop.is_closed():
            logger.warning(
                "Cannot dispatch event '%s' — no event loop available", event_type,
            )
            return

        asyncio.run_coroutine_threadsafe(callback(data), loop)


def notify_before_commit(session: Session, table_name: str) -> None:
    """Execute NOTIFY within the current transaction (fires atomically on commit).

    Eliminates the race window between commit and a separate-connection
    NOTIFY that existed in :func:`send_notify` (TD-001).

    Parameters
    ----------
    session : Session
        The active SQLAlchemy session (must not yet be committed).
    table_name : str
        Must be in :data:`ALLOWED_NOTIFY_TABLES`.
    """
    if table_name not in ALLOWED_NOTIFY_TABLES:
        raise ValueError(
            f"Invalid table name for NOTIFY: '{table_name}'. "
            f"Allowed: {sorted(ALLOWED_NOTIFY_TABLES)}"
        )
    session.execute(text(f"NOTIFY {NOTIFY_CHANNEL}, '{table_name}'"))


def send_notify(engine: Engine, table_name: str) -> None:
    """Send a NOTIFY on the config_changed channel (separate connection).

    .. deprecated::
        Prefer :func:`notify_before_commit` which fires atomically with
        the transaction commit, eliminating the race window (TD-001).

    The *table_name* is validated against an allowlist to prevent
    SQL injection (F-005).
    """
    if table_name not in ALLOWED_NOTIFY_TABLES:
        raise ValueError(
            f"Invalid table name for NOTIFY: '{table_name}'. "
            f"Allowed: {sorted(ALLOWED_NOTIFY_TABLES)}"
        )
    with engine.connect() as conn:
        conn.execute(text(f"NOTIFY {NOTIFY_CHANNEL}, '{table_name}'"))
        conn.commit()


def send_event_notify(engine: Engine, payload: dict) -> None:
    """Send a NOTIFY on the synapse_events channel with a JSON payload.

    Used for cross-service event dispatch (e.g. telling the bot to
    announce an achievement granted via the API).

    Parameters
    ----------
    engine : Engine
        SQLAlchemy engine for database access.
    payload : dict
        Must include a ``"type"`` key.  Serialised to JSON.
    """
    if "type" not in payload:
        raise ValueError("Event payload must include a 'type' key")
    raw = json.dumps(payload, default=str)
    # Escape single quotes for PG
    escaped = raw.replace("'", "''")
    with engine.connect() as conn:
        conn.execute(text(f"NOTIFY {EVENT_NOTIFY_CHANNEL}, '{escaped}'"))
        conn.commit()
