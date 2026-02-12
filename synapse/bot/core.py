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
4. Auto-discovers guild channels and maps them to zones on startup.
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
from synapse.engine.cache import ConfigCache

logger = logging.getLogger(__name__)

# Cog modules to load on startup.  Add new filenames here as you build more.
EXTENSIONS: list[str] = [
    "synapse.bot.cogs.social",
    "synapse.bot.cogs.reactions",
    "synapse.bot.cogs.voice",
    "synapse.bot.cogs.threads",
    "synapse.bot.cogs.meta",
    "synapse.bot.cogs.admin",
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
        # --- Intents --------------------------------------------------------
        # message_content is REQUIRED for prefix commands and on_message XP.
        # members is needed to resolve Member objects in slash commands.
        # voice_states for voice XP tracking.
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.voice_states = True

        super().__init__(
            command_prefix=cfg.bot_prefix,
            intents=intents,
            description=f"{cfg.club_name} — {cfg.club_motto}",
        )

        # Attach shared state so Cogs can read it via self.bot.*
        self.cfg = cfg
        self.engine = engine
        self.cache = cache

        # Will be set in on_ready after auto-creating the achievements channel
        self.synapse_announce_channel_id: int | None = None

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

        # --- Auto-discover guild channels and map to zones ------------------
        await self._auto_discover_channels()

        # --- Start announcement throttle drain task -------------------------
        from synapse.services.announcement_service import start_queue
        start_queue(asyncio.get_running_loop())
        logger.info("Announcement throttle drain task started.")

    async def close(self) -> None:
        """Graceful shutdown — stop background tasks."""
        from synapse.services.announcement_service import stop_queue
        stop_queue()
        await super().close()

    # -----------------------------------------------------------------------
    # Auto-create #synapse-achievements
    # -----------------------------------------------------------------------
    async def _ensure_achievements_channel(self) -> None:
        """Create #synapse-achievements in the primary guild if it doesn't exist."""
        for g in self.guilds:
            if g.id != self.cfg.guild_id:
                continue

            # Check if channel already exists
            for ch in g.text_channels:
                if ch.name == ACHIEVEMENTS_CHANNEL_NAME:
                    self.synapse_announce_channel_id = ch.id
                    logger.info(
                        "Found existing #%s channel (ID: %d)",
                        ACHIEVEMENTS_CHANNEL_NAME, ch.id,
                    )
                    return

            # Create the channel
            try:
                new_ch = await g.create_text_channel(
                    name=ACHIEVEMENTS_CHANNEL_NAME,
                    topic=(
                        f"\U0001f3c6 {self.cfg.club_name} achievements, level-ups, "
                        "and celebrations \u2014 powered by Synapse"
                    ),
                    reason="Synapse: auto-created unified notification channel",
                )
                self.synapse_announce_channel_id = new_ch.id
                logger.info(
                    "Created #%s channel (ID: %d) in guild %s",
                    ACHIEVEMENTS_CHANNEL_NAME, new_ch.id, g.name,
                )
            except discord.Forbidden:
                logger.warning(
                    "Missing permissions to create #%s in guild %s \u2014 "
                    "achievement announcements will use fallback channels.",
                    ACHIEVEMENTS_CHANNEL_NAME, g.name,
                )
            except Exception:
                logger.exception(
                    "Failed to create #%s in guild %s",
                    ACHIEVEMENTS_CHANNEL_NAME, g.name,
                )
            return  # Only process the primary guild

    # -----------------------------------------------------------------------
    # Auto-discover guild channels and map to zones
    # -----------------------------------------------------------------------
    async def _auto_discover_channels(self) -> None:
        """Scan guild channels and auto-map unmapped ones to zones."""
        from synapse.database.engine import run_db
        from synapse.services.channel_service import sync_guild_channels

        for g in self.guilds:
            if g.id != self.cfg.guild_id:
                continue

            channels = []
            for ch in g.text_channels:
                channels.append({
                    "id": ch.id,
                    "name": ch.name,
                    "category_name": ch.category.name if ch.category else None,
                })
            for vc in g.voice_channels:
                channels.append({
                    "id": vc.id,
                    "name": vc.name,
                    "category_name": vc.category.name if vc.category else None,
                })

            if channels:
                mapped = await run_db(
                    sync_guild_channels, self.engine, g.id, channels,
                )
                if mapped:
                    # Reload the cache so new mappings take effect immediately
                    self.cache.load_all()
                    logger.info(
                        "Auto-discovered %d channels, cache reloaded.", mapped
                    )
            return  # Only process the primary guild
