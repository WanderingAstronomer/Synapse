"""synapse.bot.cogs.membership — Member Join/Leave Event Lake + Profile Sync
============================================================================

Captures GUILD_MEMBER_ADD and GUILD_MEMBER_REMOVE gateway events
into the Event Lake and keeps the ``user_profiles`` / ``user_guild_roles``
Read Model current.

Per §3B.4 Tier 3: membership events are toggleable and privileged.
No reward processing — join/leave events are data capture only (for now).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from synapse.database.engine import run_db
from synapse.services.profile_service import anonymize_on_leave, sync_member_roles, upsert_profile

if TYPE_CHECKING:
    from synapse.bot.core import SynapseBot

logger = logging.getLogger(__name__)


class Membership(commands.Cog, name="Membership"):
    """Captures member join and leave events to the Event Lake."""

    def __init__(self, bot: SynapseBot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """Capture GUILD_MEMBER_ADD → Event Lake write + profile upsert."""
        try:
            if member.bot:
                return

            await run_db(
                self.bot.lake_writer.write_member_join,
                guild_id=member.guild.id,
                user_id=member.id,
                joined_at=member.joined_at,
            )

            # --- Profile sync (Phase 5) ---
            avatar_url: str | None = member.display_avatar.url if member.display_avatar else None
            await run_db(
                upsert_profile,
                self.bot.engine,
                member.id,
                member.guild.id,
                member.name,
                avatar_url,
            )
            roles = [
                (r.id, r.name)
                for r in member.roles
                if r.id != member.guild.id  # exclude @everyone
            ]
            await run_db(
                sync_member_roles,
                self.bot.engine,
                member.id,
                member.guild.id,
                roles,
            )

            logger.info("Member joined: %s (ID: %d)", member.display_name, member.id)

        except Exception:
            logger.exception(
                "Error processing member_join for %s",
                member.id,
                extra={"event_type": "member_join", "user_id": member.id},
            )

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        """Capture GUILD_MEMBER_REMOVE → Event Lake write + profile anonymize."""
        try:
            if member.bot:
                return

            await run_db(
                self.bot.lake_writer.write_member_leave,
                guild_id=member.guild.id,
                user_id=member.id,
            )

            # --- Anonymize profile (Phase 5) ---
            await run_db(
                anonymize_on_leave,
                self.bot.engine,
                member.id,
                member.guild.id,
            )

            logger.info("Member left: %s (ID: %d)", member.display_name, member.id)

        except Exception:
            logger.exception(
                "Error processing member_leave for %s",
                member.id,
                extra={"event_type": "member_leave", "user_id": member.id},
            )


async def setup(bot: SynapseBot) -> None:
    await bot.add_cog(Membership(bot))
