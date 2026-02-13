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
from synapse.services.event_lake_writer import EventLakeWriter

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

        # --- Audit text-channel access to catch permission override issues ---
        await self._audit_text_channel_access()

        # --- Detect AFK voice channels for Event Lake tagging ---------------
        await self._detect_afk_channels()

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
                        f"\U0001f3c6 {self.cfg.community_name} achievements, level-ups, "
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
        """Build a guild snapshot and persist it for the setup wizard.

        Instead of mapping channels to zones at startup (which requires
        zones to already exist), the bot now captures a full snapshot of
        the guild's channel structure and saves it to the ``Setting``
        table.  The admin dashboard reads this snapshot during the
        first-run bootstrap wizard.

        If zones already exist (i.e. setup has completed), this also runs
        the legacy channel-sync to map any newly created channels.
        """
        from synapse.services.setup_service import (
            ChannelInfo,
            GuildSnapshot,
            save_guild_snapshot,
        )

        for g in self.guilds:
            if g.id != self.cfg.guild_id:
                continue

            # Build a rich channel snapshot
            channel_infos: list[ChannelInfo] = []

            # Categories first
            for cat in g.categories:
                channel_infos.append(ChannelInfo(
                    id=cat.id,
                    name=cat.name,
                    type="category",
                ))

            # Text channels
            for ch in g.text_channels:
                channel_infos.append(ChannelInfo(
                    id=ch.id,
                    name=ch.name,
                    type="text",
                    category_id=ch.category.id if ch.category else None,
                    category_name=ch.category.name if ch.category else None,
                ))

            # Voice channels
            for vc in g.voice_channels:
                channel_infos.append(ChannelInfo(
                    id=vc.id,
                    name=vc.name,
                    type="voice",
                    category_id=vc.category.id if vc.category else None,
                    category_name=vc.category.name if vc.category else None,
                ))

            # Forum channels
            for fc in g.forums:
                channel_infos.append(ChannelInfo(
                    id=fc.id,
                    name=fc.name,
                    type="forum",
                    category_id=fc.category.id if fc.category else None,
                    category_name=fc.category.name if fc.category else None,
                ))

            # Stage channels
            for sc in g.stage_channels:
                channel_infos.append(ChannelInfo(
                    id=sc.id,
                    name=sc.name,
                    type="stage",
                    category_id=sc.category.id if sc.category else None,
                    category_name=sc.category.name if sc.category else None,
                ))

            snapshot = GuildSnapshot(
                guild_id=g.id,
                guild_name=g.name,
                channels=channel_infos,
                afk_channel_id=g.afk_channel.id if g.afk_channel else None,
            )
            save_guild_snapshot(self.engine, snapshot)

            # If zones exist, also run incremental channel-sync
            from synapse.database.engine import run_db
            from synapse.services.channel_service import sync_guild_channels

            flat_channels = [
                {
                    "id": ch.id,
                    "name": ch.name,
                    "category_name": ch.category_name,
                }
                for ch in channel_infos
                if ch.type != "category"
            ]
            if flat_channels:
                mapped = await run_db(
                    sync_guild_channels, self.engine, g.id, flat_channels,
                )
                if mapped:
                    self.cache.load_all()
                    logger.info(
                        "Incremental channel sync: %d new channels mapped.", mapped
                    )

            return  # Only process the primary guild

    # -----------------------------------------------------------------------
    # Detect AFK voice channels for Event Lake tagging (P4, §3B.4)
    # -----------------------------------------------------------------------
    async def _detect_afk_channels(self) -> None:
        """Auto-detect Discord's built-in AFK channel and update the lake writer."""
        afk_ids: set[int] = set()
        for g in self.guilds:
            if g.id != self.cfg.guild_id:
                continue
            if g.afk_channel:
                afk_ids.add(g.afk_channel.id)
                logger.info(
                    "Detected AFK channel: #%s (ID: %d)",
                    g.afk_channel.name, g.afk_channel.id,
                )
            # TODO: Also load admin-designated non-tracked channels from settings
            break

        self.lake_writer.set_afk_channels(afk_ids)
        logger.info("Event Lake AFK channel set: %s", afk_ids or "(none)")

    async def _audit_text_channel_access(self) -> None:
        """Log which text channels the bot can or cannot read in the primary guild."""
        for g in self.guilds:
            if g.id != self.cfg.guild_id:
                continue

            bot_member = g.me or g.get_member(self.user.id if self.user else 0)
            if bot_member is None:
                logger.warning(
                    "Permission audit skipped: bot member not available in guild %s",
                    g.id,
                )
                return

            readable: list[str] = []
            blocked: list[str] = []

            for ch in g.text_channels:
                perms = ch.permissions_for(bot_member)
                label = f"#{ch.name} ({ch.id})"
                if perms.view_channel and perms.read_message_history:
                    readable.append(label)
                else:
                    blocked.append(label)

            logger.info(
                "Permission audit: %d readable text channels, %d blocked in guild %s",
                len(readable), len(blocked), g.id,
            )
            if readable:
                logger.info("Readable text channels: %s", ", ".join(readable))
            if blocked:
                logger.warning("Blocked text channels: %s", ", ".join(blocked))
            return
