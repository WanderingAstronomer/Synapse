"""
synapse.bot.cogs.reactions — Reaction XP/Star Engine
=====================================================

Listens for on_raw_reaction_add events and generates:
- REACTION_GIVEN event for the reactor
- REACTION_RECEIVED event for the message author

Uses raw events to avoid cache misses on old messages.
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

if TYPE_CHECKING:
    from synapse.bot.core import SynapseBot

logger = logging.getLogger(__name__)


class Reactions(commands.Cog, name="Reactions"):
    """Awards XP and Stars for giving and receiving reactions."""

    def __init__(self, bot: SynapseBot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        """Fire when any reaction is added, even on uncached messages."""
        logger.debug(
            "Gateway event: REACTION_ADD from user %s on message %s in channel %s",
            payload.user_id, payload.message_id, payload.channel_id,
        )
        try:
            await self._handle_reaction(payload)
        except Exception:
            logger.exception(
                "Error processing reaction on message %s from user %s",
                payload.message_id, payload.user_id,
                extra={"event_type": "reaction_add", "user_id": payload.user_id,
                       "message_id": payload.message_id},
            )

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent) -> None:
        """Fire when any reaction is removed — Event Lake capture only (P4)."""
        try:
            if payload.guild_id is None:
                return
            await run_db(
                self.bot.lake_writer.write_reaction_remove,
                guild_id=payload.guild_id,
                user_id=payload.user_id,
                channel_id=payload.channel_id,
                message_id=payload.message_id,
                emoji_name=str(payload.emoji),
            )
        except Exception:
            logger.exception(
                "Error processing reaction remove on message %s from user %s",
                payload.message_id, payload.user_id,
                extra={"event_type": "reaction_remove", "user_id": payload.user_id,
                       "message_id": payload.message_id},
            )

    async def _handle_reaction(self, payload: discord.RawReactionActionEvent) -> None:
        """Inner reaction handler (separated for error isolation)."""

        # Gate: Ignore bots
        if payload.member is None or payload.member.bot:
            return

        # Gate: Ignore DMs
        if payload.guild_id is None:
            return

        # --- Event Lake capture (P4) ----------------------------------------
        # Write reaction_add to the Event Lake via raw event (§3B.10).
        # message_author_id resolved below if possible.
        await run_db(
            self.bot.lake_writer.write_reaction_add,
            guild_id=payload.guild_id,
            user_id=payload.user_id,
            channel_id=payload.channel_id,
            message_id=payload.message_id,
            emoji_name=str(payload.emoji),
            message_author_id=None,  # Resolved below for reward pipeline
        )

        # Resolve the channel for announcements
        channel = self.bot.get_channel(payload.channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(payload.channel_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                channel = None

        # --- REACTION_GIVEN (for the reactor) ---
        given_event = SynapseEvent(
            user_id=payload.user_id,
            event_type=InteractionType.REACTION_GIVEN,
            channel_id=payload.channel_id,
            guild_id=payload.guild_id,
            source_event_id=f"rxn_given_{payload.message_id}_{payload.user_id}_{payload.emoji}",
            metadata={
                "emoji": str(payload.emoji),
                "message_id": payload.message_id,
                "channel_name": getattr(channel, "name", ""),
            },
        )

        given_result, given_dup = await run_db(
            self.bot.process_event_sync,
            given_event,
            payload.member.display_name,
        )

        if not given_dup:
            await announce_rewards(
                self.bot,
                result=given_result,
                user_id=payload.user_id,
                display_name=payload.member.display_name,
                avatar_url=payload.member.display_avatar.url,
                fallback_channel=channel if hasattr(channel, "send") else None,
            )

        # --- REACTION_RECEIVED (for the message author) ---
        # We need to fetch the message to know who wrote it.
        try:
            allowed = (discord.TextChannel, discord.Thread, discord.DMChannel)
            if channel is None or not isinstance(channel, allowed):
                return
            message = await channel.fetch_message(payload.message_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return  # Can't fetch — skip

        # Don't award for self-reactions
        if message.author.id == payload.user_id:
            return

        # Don't award for bot messages
        if message.author.bot:
            return

        # Approximate unique reactor count from reaction totals (avoids
        # expensive per-reaction ``reaction.users()`` API calls).
        unique_reactor_estimate = sum(
            r.count for r in message.reactions
        ) - 1  # subtract 1 for the bot's own potential reaction
        unique_reactor_estimate = max(unique_reactor_estimate, 1)

        received_event = SynapseEvent(
            user_id=message.author.id,
            event_type=InteractionType.REACTION_RECEIVED,
            channel_id=payload.channel_id,
            guild_id=payload.guild_id,
            source_event_id=f"rxn_recv_{payload.message_id}_{payload.user_id}_{payload.emoji}",
            metadata={
                "emoji": str(payload.emoji),
                "reactor_id": payload.user_id,
                "message_id": payload.message_id,
                "unique_reactor_count": unique_reactor_estimate,
                "channel_name": getattr(channel, "name", "unknown"),
            },
        )

        recv_result, recv_dup = await run_db(
            self.bot.process_event_sync,
            received_event,
            message.author.display_name,
        )

        if not recv_dup:
            await announce_rewards(
                self.bot,
                result=recv_result,
                user_id=message.author.id,
                display_name=message.author.display_name,
                avatar_url=message.author.display_avatar.url,
                fallback_channel=channel,
            )


async def setup(bot: SynapseBot) -> None:
    await bot.add_cog(Reactions(bot))
