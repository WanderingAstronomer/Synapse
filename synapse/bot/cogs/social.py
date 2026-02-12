"""
synapse.bot.cogs.social — Message XP/Star Engine
==================================================

Listens for on_message events, normalizes them into SynapseEvents,
and processes them through the reward pipeline.

Pipeline:
1. on_message fires → gate checks (bot, DM, cooldown)
2. Build SynapseEvent with message metadata
3. Call reward_service.process_event (runs on background thread via run_db)
4. Delegate announcement logic to announcement_service
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from synapse.database.engine import run_db
from synapse.database.models import InteractionType
from synapse.engine.events import SynapseEvent
from synapse.services.announcement_service import announce_rewards
from synapse.services.reward_service import process_event

if TYPE_CHECKING:
    from synapse.bot.core import SynapseBot

logger = logging.getLogger(__name__)


class Social(commands.Cog, name="Social"):
    """Awards XP and Stars for Discord messages with quality scoring."""

    def __init__(self, bot: SynapseBot) -> None:
        self.bot = bot
        # Per-user-per-channel cooldown: (user_id, channel_id) → timestamp
        self._cooldowns: dict[tuple[int, int], float] = {}

    def _build_message_event(self, message: discord.Message) -> SynapseEvent:
        """Build a SynapseEvent from a Discord message."""
        return SynapseEvent(
            user_id=message.author.id,
            event_type=InteractionType.MESSAGE,
            channel_id=message.channel.id,
            guild_id=message.guild.id if message.guild else 0,
            source_event_id=str(message.id),
            metadata={
                "length": len(message.content),
                "has_code_block": "```" in message.content,
                "has_link": "http" in message.content,
                "has_attachment": len(message.attachments) > 0,
                "attachment_count": len(message.attachments),
                "emoji_count": message.content.count(":"),  # rough estimate
                "channel_name": getattr(message.channel, "name", "unknown"),
            },
        )

    def _process(self, event: SynapseEvent, display_name: str):
        """Sync wrapper for process_event (runs on background thread)."""
        return process_event(
            self.bot.engine,
            self.bot.cache,
            event,
            display_name,
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Core XP/Star loop — fires on every guild message."""
        try:
            await self._handle_message(message)
        except Exception:
            logger.exception(
                "Error processing message %s from user %s",
                message.id,
                message.author.id,
            )

    async def _handle_message(self, message: discord.Message) -> None:
        """Inner message handler (separated for error isolation)."""

        # Gate 1: Ignore bots
        if message.author.bot:
            logger.debug("Ignoring bot message from %s", message.author.name)
            return

        # Gate 2: Ignore DMs
        if message.guild is None:
            logger.debug("Ignoring DM from %s", message.author.name)
            return

        # Gate 3: Per-user-per-channel cooldown
        now = time.time()
        cooldown_key = (message.author.id, message.channel.id)
        last = self._cooldowns.get(cooldown_key, 0.0)
        cooldown_seconds = self.bot.cache.get_int("cooldown_seconds", 30)
        if now - last < cooldown_seconds:
            logger.debug(
                "Cooldown active for %s in channel %s (%.1f/%.0f seconds remaining)",
                message.author.name,
                getattr(message.channel, "name", "unknown"),
                cooldown_seconds - (now - last),
                cooldown_seconds,
            )
            return
        self._cooldowns[cooldown_key] = now

        # Build event and process
        event = self._build_message_event(message)
        result, was_duplicate = await run_db(
            self._process,
            event,
            message.author.display_name,
        )

        if was_duplicate:
            logger.debug("Duplicate event for message %s — skipping announcements", message.id)
            return

        logger.info(
            "Message processed: %s (+%d XP, +%d ☆) [Level %d%s]",
            message.author.display_name,
            result.xp,
            result.stars,
            result.new_level if result.leveled_up else result.xp,
            " UP!" if result.leveled_up else ""
        )

        # Delegate all announcement logic to the shared service
        await announce_rewards(
            self.bot,
            result=result,
            user_id=message.author.id,
            display_name=message.author.display_name,
            avatar_url=message.author.display_avatar.url,
            fallback_channel=message.channel,
        )


async def setup(bot: SynapseBot) -> None:
    await bot.add_cog(Social(bot))
