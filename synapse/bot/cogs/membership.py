"""
synapse.bot.cogs.membership — Member Join/Leave Event Lake Capture
===================================================================

Captures GUILD_MEMBER_ADD and GUILD_MEMBER_REMOVE gateway events
into the Event Lake.  Requires the GUILD_MEMBERS privileged intent.

Per §3B.4 Tier 3: membership events are toggleable and privileged.
No reward processing — join/leave events are data capture only (for now).
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


class Membership(commands.Cog, name="Membership"):
    """Captures member join and leave events to the Event Lake."""

    def __init__(self, bot: SynapseBot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """Capture GUILD_MEMBER_ADD → member_join event."""
        try:
            if member.bot:
                return

            await run_db(
                self.bot.lake_writer.write_member_join,
                guild_id=member.guild.id,
                user_id=member.id,
                joined_at=member.joined_at,
            )
            logger.info("Member joined: %s (ID: %d)", member.display_name, member.id)

        except Exception:
            logger.exception(
                "Error processing member_join for %s", member.id,
                extra={"event_type": "member_join", "user_id": member.id},
            )

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        """Capture GUILD_MEMBER_REMOVE → member_leave event."""
        try:
            if member.bot:
                return

            await run_db(
                self.bot.lake_writer.write_member_leave,
                guild_id=member.guild.id,
                user_id=member.id,
            )
            logger.info("Member left: %s (ID: %d)", member.display_name, member.id)

        except Exception:
            logger.exception(
                "Error processing member_leave for %s", member.id,
                extra={"event_type": "member_leave", "user_id": member.id},
            )


async def setup(bot: SynapseBot) -> None:
    await bot.add_cog(Membership(bot))
