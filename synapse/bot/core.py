"""
synapse.bot.core — Bot Instance & Cog Loader
=============================================

**Why this file exists:**
This is the beating heart of Synapse.  It defines a :class:`SynapseBot`
subclass of ``commands.Bot`` that:

1. Stores the shared config (``bot.cfg``) and DB engine (``bot.engine``)
   so every Cog can access them via ``self.bot.cfg`` / ``self.bot.engine``.
2. Automatically discovers and loads every Cog in ``synapse/bot/cogs/``.
3. Syncs the slash-command tree on startup (guild-scoped for dev, global
   for production — controlled by the ``DEV_GUILD_ID`` env var).
4. Auto-discovers guild channels and maps them to categories on startup.
5. Auto-creates a ``#synapse-achievements`` channel for notifications.
6. Starts the announcement throttle drain task.

Architecture note:
    The Bot object is the **central nervous system**.  Cogs are pluggable
    "organs" that can be added, removed, or hot-reloaded without touching
    core.py.  This is the standard discord.py pattern for large bots.
"""

from __future__ import annotations

import asyncio
import logging
import os

import discord
from discord.ext import commands
from sqlalchemy import Engine

from synapse.config import SynapseConfig
from synapse.database.engine import run_db
from synapse.engine.cache import ConfigCache
from synapse.engine.events import SynapseEvent
from synapse.services.announcement_service import start_queue, stop_queue
from synapse.services.channel_service import sync_channels_from_snapshot
from synapse.services.event_lake_writer import EventLakeWriter
from synapse.services.reward_service import process_event
from synapse.services.setup_service import (
    ChannelInfo,
    GuildSnapshot,
    save_guild_snapshot,
)

logger = logging.getLogger(__name__)

# Cog modules to load on startup.  Add new filenames here as you build more.
EXTENSIONS: list[str] = [
    "synapse.bot.cogs.social",
    "synapse.bot.cogs.reactions",
    "synapse.bot.cogs.voice",
    "synapse.bot.cogs.threads",
    "synapse.bot.cogs.membership",
    "synapse.bot.cogs.meta",
    "synapse.bot.cogs.admin",
    "synapse.bot.cogs.tasks",
]

# Name of the auto-created achievements channel
ACHIEVEMENTS_CHANNEL_NAME = "synapse-achievements"


class SynapseBot(commands.Bot):
    """Custom Bot subclass that carries project-wide state.

    Parameters
    ----------
    cfg:
        The parsed :class:`SynapseConfig` from ``config.yaml``.
    engine:
        A SQLAlchemy :class:`Engine` connected to PostgreSQL.
    """

    def __init__(self, cfg: SynapseConfig, engine: Engine, cache: ConfigCache) -> None:
        # --- Intents (§3B.2) ------------------------------------------------
        # Standard intents included in default():
        #   GUILDS, GUILD_MESSAGES, GUILD_MESSAGE_REACTIONS, GUILD_VOICE_STATES
        # Privileged intents (must enable in Developer Portal):
        #   MESSAGE_CONTENT — quality analysis (length, code, links)
        #   GUILD_MEMBERS   — join/leave tracking, member cache
        # Explicitly disabled:
        #   GUILD_PRESENCES — bandwidth bomb, no engagement value
        intents = discord.Intents.default()
        intents.message_content = True    # Privileged: quality analysis
        intents.members = True            # Privileged: join/leave tracking
        intents.presences = False         # Explicitly disabled: too expensive

        super().__init__(
            command_prefix=cfg.bot_prefix,
            intents=intents,
            description=f"{cfg.community_name} — {cfg.community_motto}",
        )

        # Attach shared state so Cogs can read it via self.bot.*
        self.cfg = cfg
        self.engine = engine
        self.cache = cache

        # Event Lake writer (P4) — shared by all cogs for event capture
        self.lake_writer = EventLakeWriter(engine)

        # Will be set in on_ready after auto-creating the achievements channel
        self.synapse_announce_channel_id: int | None = None

    def process_event_sync(self, event: SynapseEvent, display_name: str):
        """Process a reward event synchronously.  Call via ``run_db()``."""
        return process_event(self.engine, self.cache, event, display_name)

    # -----------------------------------------------------------------------
    # Lifecycle hooks
    # -----------------------------------------------------------------------
    async def setup_hook(self) -> None:
        """Called once before the bot connects to Discord.

        We use this to load all Cog extensions.  If any extension fails to
        load, we log the error but keep going — one broken Cog shouldn't
        take down the whole bot.
        """
        for ext in EXTENSIONS:
            try:
                await self.load_extension(ext)
                logger.info("Loaded extension: %s", ext)
            except Exception as exc:
                logger.error("Failed to load extension %s: %s", ext, exc)

    async def on_ready(self) -> None:
        """Fired when the bot has connected and the cache is populated."""
        assert self.user is not None  # guaranteed after on_ready
        logger.info("Logged in as %s (ID: %s)", self.user.name, self.user.id)

        # --- Slash-command sync ---------------------------------------------
        dev_guild_id = os.getenv("DEV_GUILD_ID")
        if dev_guild_id:
            guild = discord.Object(id=int(dev_guild_id))
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            logger.info("Synced %d commands to dev guild %s", len(synced), dev_guild_id)
        else:
            synced = await self.tree.sync()
            logger.info("Synced %d commands globally", len(synced))

        # --- Auto-create #synapse-achievements channel ----------------------
        await self._ensure_achievements_channel()

        # --- Auto-discover guild channels and map to categories ------------------
        await self._auto_discover_channels()

        # --- Audit text-channel access to catch permission override issues ---
        await self._audit_text_channel_access()

        # --- Detect AFK voice channels for Event Lake tagging ---------------
        await self._detect_afk_channels()

        # --- Start announcement throttle drain task -------------------------
        start_queue(asyncio.get_running_loop())
        logger.info("Announcement throttle drain task started.")

        # --- Register event callbacks for cross-service notifications -------
        await self._register_event_callbacks()

    async def close(self) -> None:
        """Graceful shutdown — stop background tasks and listener thread."""
        logger.info("Bot shutting down…")
        self.cache.stop_listener()  # Graceful PG LISTEN thread exit (TD-005)
        stop_queue()
        await super().close()

    # -----------------------------------------------------------------------
    # Cross-service event callbacks (PG NOTIFY → bot actions)
    # -----------------------------------------------------------------------
    async def _register_event_callbacks(self) -> None:
        """Register async callbacks for events arriving via PG NOTIFY."""
        loop = asyncio.get_running_loop()
        self.cache.register_event_callback(
            "achievement_granted", self._on_achievement_granted, loop=loop,
        )
        logger.info("Event callbacks registered on asyncio loop")

    async def _on_achievement_granted(self, data: dict) -> None:
        """Handle an achievement_granted event from the API.

        Fires the same rich announcement used by the bot /grant command.
        """
        from synapse.services.announcement_service import announce_achievement_grant

        recipient_id = int(data["recipient_id"])
        display_name = data.get("display_name", "Unknown")
        achievement_id = int(data["achievement_id"])
        admin_name = data.get("admin_name", "Admin")

        # Try to resolve avatar from guild member cache
        guild = self.get_guild(self.cfg.guild_id)
        avatar_url = ""
        if guild:
            member = guild.get_member(recipient_id)
            if member:
                avatar_url = member.display_avatar.url
                display_name = member.display_name  # prefer live name

        await announce_achievement_grant(
            self,
            recipient_id=recipient_id,
            display_name=display_name,
            avatar_url=avatar_url,
            achievement_id=achievement_id,
            admin_name=admin_name,
        )

    # -----------------------------------------------------------------------
    # Auto-create #synapse-achievements
    # -----------------------------------------------------------------------
    async def _ensure_achievements_channel(self) -> None:
        """Create #synapse-achievements in the primary guild if it doesn't exist."""
        guild = self.get_guild(self.cfg.guild_id)
        if guild is None:
            logger.warning("Primary guild %d not found — skipping achievements channel", self.cfg.guild_id)
            return

        # Check if channel already exists
        for ch in guild.text_channels:
            if ch.name == ACHIEVEMENTS_CHANNEL_NAME:
                self.synapse_announce_channel_id = ch.id
                logger.info(
                    "Found existing #%s channel (ID: %d)",
                    ACHIEVEMENTS_CHANNEL_NAME, ch.id,
                )
                return

        # Create the channel
        try:
            new_ch = await guild.create_text_channel(
                name=ACHIEVEMENTS_CHANNEL_NAME,
                topic=(
                    f"\U0001f3c6 {self.cfg.community_name} achievements, level-ups, "
                    "and celebrations \u2014 powered by Synapse"
                ),
                reason="Synapse: auto-created unified notification channel",
            )
            self.synapse_announce_channel_id = new_ch.id
            logger.info(
                "Created #%s channel (ID: %d) in guild %s",
                ACHIEVEMENTS_CHANNEL_NAME, new_ch.id, guild.name,
            )
        except discord.Forbidden:
            logger.warning(
                "Missing permissions to create #%s in guild %s — "
                "achievement announcements will use fallback channels.",
                ACHIEVEMENTS_CHANNEL_NAME, guild.name,
            )
        except Exception:
            logger.exception(
                "Failed to create #%s in guild %s",
                ACHIEVEMENTS_CHANNEL_NAME, guild.name,
            )

    # -----------------------------------------------------------------------
    # Auto-discover guild channels and map to categories
    # -----------------------------------------------------------------------
    async def _auto_discover_channels(self) -> None:
        """Build a guild snapshot and persist it for the setup wizard.

        Captures a full snapshot of the guild's channel structure and saves
        it to the ``Setting`` table.  The admin dashboard reads this snapshot
        during the first-run bootstrap wizard.

        If categories already exist (i.e. setup has completed), this also runs
        the channel-sync to map any newly created channels.
        """
        guild = self.get_guild(self.cfg.guild_id)
        if guild is None:
            logger.warning(
                "Primary guild %d not found — skipping channel discovery",
                self.cfg.guild_id,
            )
            return

        # Categories first (no parent category)
        channel_infos: list[ChannelInfo] = [
            ChannelInfo(id=c.id, name=c.name, type="category")
            for c in guild.categories
        ]

        # All other channel types share the same shape
        _channel_sources = [
            ("text_channels", "text"),
            ("voice_channels", "voice"),
            ("forums", "forum"),
            ("stage_channels", "stage"),
        ]
        for attr, ch_type in _channel_sources:
            for ch in getattr(guild, attr, []):
                channel_infos.append(ChannelInfo(
                    id=ch.id,
                    name=ch.name,
                    type=ch_type,
                    category_id=ch.category.id if ch.category else None,
                    category_name=ch.category.name if ch.category else None,
                ))

        snapshot = GuildSnapshot(
            guild_id=guild.id,
            guild_name=guild.name,
            channels=channel_infos,
            afk_channel_id=guild.afk_channel.id if guild.afk_channel else None,
        )
        save_guild_snapshot(self.engine, snapshot)

        # Sync channel metadata to the channels table
        ch_dicts = [
            {
                "id": ch.id,
                "name": ch.name,
                "type": ch.type,
                "category_id": ch.category_id,
                "category_name": ch.category_name,
                "position": 0,
            }
            for ch in channel_infos
        ]
        await run_db(sync_channels_from_snapshot, self.engine, guild.id, ch_dicts)

    # -----------------------------------------------------------------------
    # Detect AFK voice channels for Event Lake tagging (P4, §3B.4)
    # -----------------------------------------------------------------------
    async def _detect_afk_channels(self) -> None:
        """Auto-detect Discord's built-in AFK channel and update the lake writer."""
        afk_ids: set[int] = set()
        guild = self.get_guild(self.cfg.guild_id)
        if guild is not None and guild.afk_channel:
            afk_ids.add(guild.afk_channel.id)
            logger.info(
                "Detected AFK channel: #%s (ID: %d)",
                guild.afk_channel.name, guild.afk_channel.id,
            )
            # TODO: Also load admin-designated non-tracked channels from settings

        self.lake_writer.set_afk_channels(afk_ids)
        logger.info("Event Lake AFK channel set: %s", afk_ids or "(none)")

    async def _audit_text_channel_access(self) -> None:
        """Log which text channels the bot can or cannot read in the primary guild."""
        guild = self.get_guild(self.cfg.guild_id)
        if guild is None:
            logger.warning(
                "Permission audit skipped: guild %d not found",
                self.cfg.guild_id,
            )
            return

        bot_member = guild.me or guild.get_member(self.user.id if self.user else 0)
        if bot_member is None:
            logger.warning(
                "Permission audit skipped: bot member not available in guild %s",
                guild.id,
            )
            return

        readable: list[str] = []
        blocked: list[str] = []

        for ch in guild.text_channels:
            perms = ch.permissions_for(bot_member)
            label = f"#{ch.name} ({ch.id})"
            if perms.view_channel and perms.read_message_history:
                readable.append(label)
            else:
                blocked.append(label)

        logger.info(
            "Permission audit: %d readable text channels, %d blocked in guild %s",
            len(readable), len(blocked), guild.id,
        )
        if readable:
            logger.debug("Readable text channels: %s", ", ".join(readable))
        if blocked:
            logger.debug("Blocked text channels: %s", ", ".join(blocked))
