"""
synapse.bot.cogs.threads — Thread Creation XP/Star Engine
===========================================================

Awards XP/Stars when members create new threads.
Delegates announcement logic to announcement_service.
"""

from __future__ import annotations

import logging
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


class Threads(commands.Cog, name="Threads"):
    """Awards XP and Stars for creating new threads."""

    def __init__(self, bot: SynapseBot) -> None:
        self.bot = bot

    def _process(self, event: SynapseEvent, display_name: str):
        """Sync wrapper for process_event."""
        return process_event(
            self.bot.engine,
            self.bot.cache,
            event,
            display_name,
        )

    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread) -> None:
        """Award XP/Stars for creating a new thread."""
        try:
            await self._handle_thread_create(thread)
        except Exception:
            logger.exception("Error processing thread creation %s", thread.id)

    async def _handle_thread_create(self, thread: discord.Thread) -> None:
        """Inner thread create handler (separated for error isolation)."""
        if thread.owner is None or thread.owner.bot:
            return
        if thread.guild is None:
            return

        event = SynapseEvent(
            user_id=thread.owner.id,
            event_type=InteractionType.THREAD_CREATE,
            channel_id=thread.parent_id or thread.id,
            guild_id=thread.guild.id,
            source_event_id=str(thread.id),
            metadata={
                "thread_name": thread.name,
                "parent_channel": getattr(thread.parent, "name", "unknown"),
            },
        )

        result, was_duplicate = await run_db(
            self._process,
            event,
            thread.owner.display_name,
        )

        if not was_duplicate:
            fallback = thread.parent if thread.parent else thread
            await announce_rewards(
                self.bot,
                result=result,
                user_id=thread.owner.id,
                display_name=thread.owner.display_name,
                avatar_url=thread.owner.display_avatar.url,
                fallback_channel=fallback,
            )


async def setup(bot: SynapseBot) -> None:
    await bot.add_cog(Threads(bot))
