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
from discord.ext import commands, tasks

from synapse.database.engine import run_db
from synapse.database.models import InteractionType
from synapse.constants import count_emojis
from synapse.engine.events import SynapseEvent
from synapse.services.announcement_service import announce_rewards

if TYPE_CHECKING:
    from synapse.bot.core import SynapseBot

logger = logging.getLogger(__name__)


class Social(commands.Cog, name="Social"):
    """Awards XP and Stars for Discord messages with quality scoring."""

    def __init__(self, bot: SynapseBot) -> None:
        self.bot = bot
        # Per-user-per-channel cooldown: (user_id, channel_id) → timestamp
        self._cooldowns: dict[tuple[int, int], float] = {}

    async def cog_load(self) -> None:
        """Start the cooldown cleanup loop when the cog is loaded."""
        self._cleanup_cooldowns.start()

    async def cog_unload(self) -> None:
        """Stop the cooldown cleanup loop when the cog is unloaded."""
        self._cleanup_cooldowns.cancel()

    @tasks.loop(minutes=5)
    async def _cleanup_cooldowns(self) -> None:
        """Prune expired entries from the cooldown dict (TD-006)."""
        now = time.time()
        cutoff = now - (2 * self.bot.cache.get_int("cooldown_seconds", 30))
        before = len(self._cooldowns)
        self._cooldowns = {k: v for k, v in self._cooldowns.items() if v > cutoff}
        pruned = before - len(self._cooldowns)
        if pruned:
            logger.debug("Pruned %d expired cooldown entries", pruned)

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
                "emoji_count": count_emojis(message.content),  # improved regex
                "channel_name": getattr(message.channel, "name", "unknown"),
            },
        )

    def _write_lake_event(self, message: discord.Message) -> bool:
        """Write message_create event to the Event Lake (P4).

        Privacy: content is processed in-memory for metadata extraction
        and never persisted — only numerical/boolean metadata is stored.
        """
        ref = message.reference
        is_reply = ref is not None and ref.message_id is not None
        reply_to_user_id: int | None = None
        if is_reply and ref is not None and ref.resolved and hasattr(ref.resolved, "author"):
            reply_to_user_id = ref.resolved.author.id  # type: ignore[union-attr]

        return self.bot.lake_writer.write_message_create(
            guild_id=message.guild.id if message.guild else 0,
            user_id=message.author.id,
            channel_id=message.channel.id,
            message_id=message.id,
            content=message.content,
            attachment_count=len(message.attachments),
            is_reply=is_reply,
            reply_to_user_id=reply_to_user_id,
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Core XP/Star loop — fires on every guild message."""
        logger.debug(
            "Gateway event: MESSAGE from %s in #%s (bot=%s, guild=%s)",
            message.author.name,
            getattr(message.channel, "name", "DM"),
            message.author.bot,
            message.guild.name if message.guild else "None",
        )
        try:
            await self._handle_message(message)
        except Exception:
            logger.exception(
                "Error processing message %s from user %s",
                message.id,
                message.author.id,
                extra={"event_type": "message", "user_id": message.author.id,
                       "message_id": message.id},
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

        # --- Event Lake capture (P4) ----------------------------------------
        # Write to the Event Lake first (parallel with reward pipeline).
        # Content is processed in-memory and discarded — never persisted.
        success = await run_db(self._write_lake_event, message)
        if not success:
            logger.warning("Event Lake write failed for message %s", message.id)

        # Build event and process (reward pipeline — will be replaced by Rules Engine in P6)
        event = self._build_message_event(message)
        result, was_duplicate = await run_db(
            self.bot.process_event_sync,
            event,
            message.author.display_name,
        )

        if was_duplicate:
            logger.debug("Duplicate event for message %s — skipping announcements", message.id)
            return

        level_str = f" Level {result.new_level} UP!" if result.leveled_up else ""
        logger.info(
            "Message processed: %s (+%d XP, +%d ☆)%s",
            message.author.display_name,
            result.xp,
            result.stars,
            level_str,
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
