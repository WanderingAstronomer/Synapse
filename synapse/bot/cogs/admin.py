"""
synapse.bot.cogs.admin — Admin Slash Commands
===============================================

Discord slash commands for server admins:
- /award — manually award XP/Gold to a member
- /create-achievement — create a new achievement template
- /grant-achievement — grant an achievement to a specific user
- /season — create a new season

All commands require the configured admin_role_id.
Admin sees ephemeral confirmation; public celebrations route through
announcement_service for preference gating and channel resolution.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from synapse.database.engine import run_db
from synapse.database.models import TriggerType
from synapse.services.admin_service import create_achievement, create_season
from synapse.services.announcement_service import (
    announce_achievement_grant,
    announce_manual_award,
)
from synapse.services.reward_service import award_manual, grant_achievement

if TYPE_CHECKING:
    from synapse.bot.core import SynapseBot

logger = logging.getLogger(__name__)


def is_admin():
    """Decorator that checks if the user has the configured admin role."""
    async def predicate(interaction: discord.Interaction) -> bool:
        bot: SynapseBot = interaction.client  # type: ignore[assignment]
        if not interaction.user or not hasattr(interaction.user, "roles"):
            return False
        admin_role_id = bot.cfg.admin_role_id
        return any(role.id == admin_role_id for role in interaction.user.roles)
    return app_commands.check(predicate)


class Admin(commands.Cog, name="Admin"):
    """Server administration commands for Synapse."""

    def __init__(self, bot: SynapseBot) -> None:
        self.bot = bot

    # -------------------------------------------------------------------
    # /award
    # -------------------------------------------------------------------
    @app_commands.command(name="award", description="Award XP and/or Gold to a member.")
    @app_commands.describe(
        member="The member to award",
        xp="Amount of XP to award (default 0)",
        gold="Amount of Gold to award (default 0)",
        reason="Reason for the award",
    )
    @is_admin()
    async def award(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        xp: int = 0,
        gold: int = 0,
        reason: str = "Manual admin award",
    ) -> None:
        """Manually award XP and/or Gold to a member."""
        if xp <= 0 and gold <= 0:
            await interaction.response.send_message(
                "❌ Please specify a positive XP or Gold amount.",
                ephemeral=True,
            )
            return

        await run_db(
            award_manual,
            self.bot.engine,
            user_id=member.id,
            display_name=member.display_name,
            guild_id=interaction.guild_id or 0,
            xp=xp,
            gold=gold,
            reason=reason,
            admin_id=interaction.user.id,
        )

        # Ephemeral confirmation to admin
        summary = (
            f"Awarded to **{member.display_name}**:\n"
            + (f"  +{xp} XP\n" if xp > 0 else "")
            + (f"  +{gold} 🪙 Gold\n" if gold > 0 else "")
            + f"Reason: {reason}"
        )
        await interaction.response.send_message(
            f"✅ {summary}", ephemeral=True,
        )

        # Public announcement via shared service (preference-gated)
        await announce_manual_award(
            self.bot,
            recipient_id=member.id,
            display_name=member.display_name,
            avatar_url=member.display_avatar.url,
            xp=xp,
            gold=gold,
            reason=reason,
            admin_name=interaction.user.display_name,
            fallback_channel=interaction.channel,
        )

    # -------------------------------------------------------------------
    # /create-achievement
    # -------------------------------------------------------------------
    @app_commands.command(
        name="create-achievement",
        description="Create a new achievement template.",
    )
    @app_commands.describe(
        name="Achievement name",
        description="Achievement description",
        requirement_type="How the achievement is earned",
        requirement_field="Stat field for counter_threshold (e.g. messages_sent)",
        requirement_value="Numeric threshold to reach",
        xp_reward="XP bonus when earned",
        gold_reward="Gold bonus when earned",
        rarity="Rarity tier",
    )
    @app_commands.choices(
        requirement_type=[
            app_commands.Choice(name=t.value.replace("_", " ").title(), value=t.value)
            for t in TriggerType
        ],
    )
    @is_admin()
    async def create_ach(
        self,
        interaction: discord.Interaction,
        name: str,
        description: str,
        requirement_type: str = "custom",
        requirement_field: str | None = None,
        requirement_value: int | None = None,
        xp_reward: int = 0,
        gold_reward: int = 0,
        rarity: str = "common",
    ) -> None:
        """Create a new achievement template."""
        tmpl = await run_db(
            create_achievement,
            self.bot.engine,
            guild_id=interaction.guild_id or 0,
            name=name,
            description=description,
            requirement_type=requirement_type,
            requirement_field=requirement_field,
            requirement_value=requirement_value,
            xp_reward=xp_reward,
            gold_reward=gold_reward,
            rarity=rarity,
            actor_id=interaction.user.id,
        )

        embed = discord.Embed(
            title="🏆 Achievement Created",
            description=f"**{tmpl.name}**\n{tmpl.description or ''}",
            color=discord.Color.purple(),
        )
        embed.add_field(name="Type", value=tmpl.requirement_type, inline=True)
        embed.add_field(name="Rarity", value=tmpl.rarity, inline=True)
        embed.add_field(name="XP Reward", value=str(tmpl.xp_reward), inline=True)
        await interaction.response.send_message(embed=embed)

    @create_ach.autocomplete("rarity")
    async def _rarity_autocomplete(
        self, interaction: discord.Interaction, current: str,
    ) -> list[app_commands.Choice[str]]:
        """Dynamic rarity autocomplete from per-guild DB config."""
        guild_id = interaction.guild_id or 0
        rarities = self.bot.cache.get_achievement_rarities(guild_id)
        choices = [
            app_commands.Choice(name=r.name.title(), value=r.name)
            for r in rarities
            if current.lower() in r.name.lower()
        ]
        return choices[:25]  # Discord caps at 25

    # -------------------------------------------------------------------
    # /grant-achievement
    # -------------------------------------------------------------------
    @app_commands.command(
        name="grant-achievement",
        description="Grant a specific achievement to a member.",
    )
    @app_commands.describe(
        member="The member to grant the achievement to",
        achievement_id="The achievement template ID",
    )
    @is_admin()
    async def grant_ach(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        achievement_id: int,
    ) -> None:
        """Grant an achievement to a specific user."""
        success, msg = await run_db(
            grant_achievement,
            self.bot.engine,
            user_id=member.id,
            display_name=member.display_name,
            guild_id=interaction.guild_id or 0,
            achievement_id=achievement_id,
            admin_id=interaction.user.id,
        )

        if success:
            # Ephemeral confirmation to admin
            await interaction.response.send_message(
                f"✅ {msg}", ephemeral=True,
            )
            # Public rich announcement via shared service (preference-gated)
            await announce_achievement_grant(
                self.bot,
                recipient_id=member.id,
                display_name=member.display_name,
                avatar_url=member.display_avatar.url,
                achievement_id=achievement_id,
                admin_name=interaction.user.display_name,
                fallback_channel=interaction.channel,
            )
        else:
            embed = discord.Embed(
                title="❌ Grant Failed",
                description=msg,
                color=discord.Color.red(),
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    # -------------------------------------------------------------------
    # /season
    # -------------------------------------------------------------------
    @app_commands.command(
        name="season",
        description="Create a new season (deactivates the current one).",
    )
    @app_commands.describe(
        name="Season name (e.g. 'Summer 2026')",
        duration_days="How many days the season lasts (default 120)",
    )
    @is_admin()
    async def new_season(
        self,
        interaction: discord.Interaction,
        name: str,
        duration_days: int = 120,
    ) -> None:
        """Create a new season, rolling over from the current one."""
        now = datetime.now(UTC)
        season = await run_db(
            create_season,
            self.bot.engine,
            guild_id=interaction.guild_id or 0,
            name=name,
            starts_at=now,
            ends_at=now + timedelta(days=duration_days),
            actor_id=interaction.user.id,
        )

        embed = discord.Embed(
            title="🌟 New Season Started",
            description=f"**{season.name}**",
            color=discord.Color.gold(),
        )
        embed.add_field(
            name="Duration",
            value=f"{duration_days} days",
            inline=True,
        )
        await interaction.response.send_message(embed=embed)

    # -------------------------------------------------------------------
    # Error handler for missing admin role
    # -------------------------------------------------------------------
    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message(
                "🔒 You need the Admin role to use this command.",
                ephemeral=True,
            )
        else:
            raise error


async def setup(bot: SynapseBot) -> None:
    await bot.add_cog(Admin(bot))
