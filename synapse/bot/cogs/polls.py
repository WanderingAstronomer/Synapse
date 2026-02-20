"""
synapse.bot.cogs.polls — Poll Vote Capture
==========================================

Listens for ``on_raw_poll_vote_add`` gateway events and writes each vote
to the Event Lake.

Scope (Phase 2)
---------------
- Capture only.  Poll votes are recorded to ``event_lake`` with
  ``event_type = "poll_vote"`` and ``source_category = GATEWAY``.
- No reward pipeline is wired here; that is deferred to Phase 3 once the
  Rules Engine is in place.

Idempotency
-----------
``source_id = f"poll-{poll_message_id}-{user_id}-{answer_id}"`` ensures
that a bot restart or duplicate dispatch can never double-count a vote.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from synapse.database.engine import run_db

if TYPE_CHECKING:
    from synapse.bot.core import SynapseBot

logger = logging.getLogger(__name__)


class Polls(commands.Cog, name="Polls"):
    """Captures poll vote events and persists them to the Event Lake."""

    def __init__(self, bot: SynapseBot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_raw_poll_vote_add(self, payload: discord.RawPollVoteActionEvent) -> None:
        """Fire when any user casts a vote on a Discord poll."""
        logger.debug(
            "Gateway event: POLL_VOTE_ADD from user %s on message %s in channel %s",
            payload.user_id,
            payload.message_id,
            payload.channel_id,
        )
        try:
            await self._handle_poll_vote(payload)
        except Exception:
            logger.exception(
                "Error processing poll vote on message %s from user %s",
                payload.message_id,
                payload.user_id,
            )

    async def _handle_poll_vote(self, payload: discord.RawPollVoteActionEvent) -> None:
        """Inner poll vote handler (separated for error isolation)."""
        # Ignore DM polls (no guild_id) and bot votes
        guild_id = payload.guild_id
        if guild_id is None:
            return

        member = payload.member  # populated by discord.py for guild events
        if member is not None and member.bot:
            return

        inserted = await run_db(
            self.bot.lake_writer.write_poll_vote,
            guild_id=guild_id,
            user_id=payload.user_id,
            channel_id=payload.channel_id,
            poll_message_id=payload.message_id,
            answer_id=payload.answer_id,
        )

        if inserted:
            logger.debug(
                "Poll vote recorded: user=%s poll_message=%s answer=%s guild=%s",
                payload.user_id,
                payload.message_id,
                payload.answer_id,
                guild_id,
            )
        else:
            logger.debug(
                "Poll vote duplicate or source disabled: user=%s poll_message=%s",
                payload.user_id,
                payload.message_id,
            )


async def setup(bot: SynapseBot) -> None:
    """Discord.py cog entry point."""
    await bot.add_cog(Polls(bot))
