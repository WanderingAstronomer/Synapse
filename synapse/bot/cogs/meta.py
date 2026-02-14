"""
synapse.bot.cogs.meta — Profile, Leaderboard, & User Commands
===============================================================

Hybrid commands for user self-service:
- /profile — View XP, level, gold, stars, achievements, rank
- /link-github — Associate a GitHub account
- /leaderboard — Top members by XP or stars
- /preferences — Toggle DM notifications and visibility
- /buy-coffee — Spend gold on a fun cosmetic item
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import func, select, update

from synapse.constants import RANK_BADGES, xp_for_level
from synapse.database.engine import get_session, run_db
from synapse.database.models import (
    AchievementRarity,
    AchievementTemplate,
    Season,
    User,
    UserAchievement,
    UserPreferences,
    UserStats,
)

if TYPE_CHECKING:
    from synapse.bot.core import SynapseBot

_GITHUB_RE = re.compile(r"^[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,37}[a-zA-Z0-9])?$")


class Meta(commands.Cog, name="Meta"):
    """Profile management, leaderboards, and user preferences."""

    def __init__(self, bot: SynapseBot) -> None:
        self.bot = bot

    # -------------------------------------------------------------------
    # DB helpers
    # -------------------------------------------------------------------
    def _link_github(self, user_id: int, display_name: str, gh_user: str) -> User:
        with get_session(self.bot.engine) as session:
            user = session.get(User, user_id)
            if user is None:
                user = User(id=user_id, discord_name=display_name, github_username=gh_user)
                session.add(user)
            else:
                user.github_username = gh_user
                user.discord_name = display_name
            session.flush()
            session.expunge(user)
            return user

    def _get_profile(self, user_id: int, guild_id: int) -> dict:
        """Get full profile data including stats and achievements."""
        with get_session(self.bot.engine) as session:
            user = session.get(User, user_id)
            if user is None:
                return {"found": False}

            total: int = session.scalar(select(func.count(User.id))) or 0
            above: int = session.scalar(
                select(func.count(User.id)).where(User.xp > user.xp)
            ) or 0
            rank = above + 1

            # Get season stats
            season = session.scalar(
                select(Season).where(Season.guild_id == guild_id, Season.active.is_(True))
            )
            stats = None
            if season:
                stats = session.get(UserStats, (user_id, season.id))

            # Get earned achievements
            achievements = session.scalars(
                select(AchievementTemplate)
                .join(UserAchievement, UserAchievement.achievement_id == AchievementTemplate.id)
                .where(UserAchievement.user_id == user_id)
                .order_by(AchievementTemplate.name)
                .limit(10)
            ).all()

            # Build rarity lookup for emoji display
            rarity_map = {
                r.id: r for r in session.scalars(select(AchievementRarity)).all()
            }

            ach_count = session.scalar(
                select(func.count(UserAchievement.achievement_id))
                .where(UserAchievement.user_id == user_id)
            ) or 0

            return {
                "found": True,
                "user": {
                    "discord_name": user.discord_name,
                    "xp": user.xp,
                    "level": user.level,
                    "gold": user.gold,
                    "github_username": user.github_username,
                },
                "rank": rank,
                "total": total,
                "stats": {
                    "season_stars": stats.season_stars if stats else 0,
                    "lifetime_stars": stats.lifetime_stars if stats else 0,
                    "messages_sent": stats.messages_sent if stats else 0,
                    "reactions_given": stats.reactions_given if stats else 0,
                    "voice_minutes": stats.voice_minutes if stats else 0,
                },
                "achievements": [
                    {
                        "name": a.name,
                        "rarity": (
                            rarity_map[a.rarity_id].name
                            if a.rarity_id and a.rarity_id in rarity_map
                            else None
                        ),
                        "emoji": (
                            rarity_map[a.rarity_id].emoji
                            if a.rarity_id
                            and a.rarity_id in rarity_map
                            and rarity_map[a.rarity_id].emoji
                            else "\u26aa"
                        ),
                    }
                    for a in achievements
                ],
                "achievement_count": ach_count,
                "season_name": season.name if season else "No active season",
            }

    def _get_leaderboard(self, guild_id: int, sort_by: str, limit: int) -> list[dict]:
        """Get leaderboard data sorted by XP or stars."""
        with get_session(self.bot.engine) as session:
            if sort_by == "stars":
                season = session.scalar(
                    select(Season).where(
                        Season.guild_id == guild_id, Season.active.is_(True)
                    )
                )
                if not season:
                    return []
                rows = session.execute(
                    select(User.discord_name, UserStats.season_stars, User.level)
                    .join(UserStats, UserStats.user_id == User.id)
                    .where(UserStats.season_id == season.id)
                    .order_by(UserStats.season_stars.desc())
                    .limit(limit)
                ).all()
                return [
                    {"name": r[0], "value": r[1], "level": r[2]}
                    for r in rows
                ]
            else:
                rows = session.execute(
                    select(User.discord_name, User.xp, User.level)
                    .order_by(User.xp.desc())
                    .limit(limit)
                ).all()
                return [
                    {"name": r[0], "value": r[1], "level": r[2]}
                    for r in rows
                ]

    def _toggle_preference(self, user_id: int, field: str, value: bool) -> bool:
        """Toggle a user preference field."""
        with get_session(self.bot.engine) as session:
            prefs = session.get(UserPreferences, user_id)
            if prefs is None:
                prefs = UserPreferences(user_id=user_id)
                session.add(prefs)
                session.flush()
            setattr(prefs, field, value)
            return getattr(prefs, field)

    def _buy_coffee(self, user_id: int, cost: int) -> tuple[bool, int]:
        """Attempt to spend gold on coffee. Returns (success, remaining_gold).

        Uses atomic SQL UPDATE with a guard clause to prevent race
        conditions under concurrent commands.
        """
        with get_session(self.bot.engine) as session:
            row = session.execute(
                update(User)
                .where(User.id == user_id, User.gold >= cost)
                .values(gold=User.gold - cost)
                .returning(User.gold)
            ).first()
            if row is not None:
                return True, row[0]
            # Purchase failed — either user missing or insufficient gold
            user = session.get(User, user_id)
            return False, user.gold if user else 0

    # -------------------------------------------------------------------
    # /link-github
    # -------------------------------------------------------------------
    @commands.hybrid_command(  # type: ignore[arg-type]
        name="link-github",
        description="Link your GitHub account to your Synapse profile.",
    )
    @app_commands.describe(username="Your GitHub username (e.g. octocat)")
    async def link_github(self, ctx: commands.Context, username: str) -> None:
        if not _GITHUB_RE.match(username):
            await ctx.send(
                "\u274c That doesn't look like a valid GitHub username.\n"
                "Usernames are 1\u201339 characters: letters, numbers, and hyphens.",
                ephemeral=True,
            )
            return
        user = await run_db(self._link_github, ctx.author.id, ctx.author.display_name, username)
        embed = discord.Embed(
            title="\U0001f517 GitHub Linked!",
            description=(
                f"**{ctx.author.display_name}** is now linked to "
                f"[**{user.github_username}**](https://github.com/{user.github_username})."
            ),
            color=discord.Color.green(),
        )
        await ctx.send(embed=embed, ephemeral=True)

    # -------------------------------------------------------------------
    # /profile
    # -------------------------------------------------------------------
    @commands.hybrid_command(  # type: ignore[arg-type]
        name="profile",
        description="View your (or another member's) Synapse profile.",
    )
    @app_commands.describe(member="The member to look up (defaults to you)")
    async def profile(self, ctx: commands.Context, member: discord.Member | None = None) -> None:
        target = member or ctx.author
        guild_id = ctx.guild.id if ctx.guild else 0

        data = await run_db(self._get_profile, target.id, guild_id)

        if not data["found"]:
            await ctx.send(
                f"\U0001f50d **{target.display_name}** hasn't earned any XP yet.",
                ephemeral=True,
            )
            return

        u = data["user"]
        required_xp = xp_for_level(u["level"], self.bot.cache)
        stats = data["stats"]

        embed = discord.Embed(
            title=f"\U0001f9e0 {u['discord_name']}'s Synapse Profile",
            color=discord.Color.purple(),
        )
        embed.set_thumbnail(url=target.display_avatar.url)

        embed.add_field(name="Level", value=str(u["level"]), inline=True)
        embed.add_field(name="XP", value=f"{u['xp']} / {required_xp}", inline=True)
        embed.add_field(name="Gold", value=f"\U0001fa99 {u['gold']}", inline=True)
        embed.add_field(name="Rank", value=f"#{data['rank']} of {data['total']}", inline=True)

        # Stars
        embed.add_field(
            name="\u2b50 Stars",
            value=f"Season: {stats['season_stars']} | Lifetime: {stats['lifetime_stars']}",
            inline=True,
        )

        # Stats summary
        stat_text = (
            f"\U0001f4ac {stats['messages_sent']} msgs | "
            f"\U0001f44d {stats['reactions_given']} rxns | "
            f"\U0001f3a4 {stats['voice_minutes']}m voice"
        )
        embed.add_field(name="Season Stats", value=stat_text, inline=False)

        # Achievements
        if data["achievements"]:
            ach_lines = [
                f"{a['emoji']} {a['name']}"
                for a in data["achievements"][:5]
            ]
            ach_text = "\n".join(ach_lines)
            if data["achievement_count"] > 5:
                ach_text += f"\n*...and {data['achievement_count'] - 5} more*"
            embed.add_field(
                name=f"\U0001f3c6 Achievements ({data['achievement_count']})",
                value=ach_text,
                inline=False,
            )

        # GitHub
        gh = u["github_username"]
        if gh:
            embed.add_field(name="GitHub", value=f"[{gh}](https://github.com/{gh})", inline=True)

        embed.set_footer(text=f"{data['season_name']} | {self.bot.cfg.community_name}")
        await ctx.send(embed=embed)

    # -------------------------------------------------------------------
    # /leaderboard
    # -------------------------------------------------------------------
    @commands.hybrid_command(  # type: ignore[arg-type]
        name="leaderboard",
        description="View the top members by XP or Stars.",
    )
    @app_commands.describe(sort_by="Sort by XP or Stars")
    @app_commands.choices(sort_by=[
        app_commands.Choice(name="XP", value="xp"),
        app_commands.Choice(name="Stars", value="stars"),
    ])
    async def leaderboard(self, ctx: commands.Context, sort_by: str = "xp") -> None:
        guild_id = ctx.guild.id if ctx.guild else 0
        limit = self.bot.cache.get_int("leaderboard_size", 25)

        rows = await run_db(self._get_leaderboard, guild_id, sort_by, limit)

        if not rows:
            await ctx.send(
                "No data yet! Start chatting to appear on the leaderboard.",
                ephemeral=True,
            )
            return

        label = "XP" if sort_by == "xp" else "\u2b50 Stars"
        lines = []
        for i, r in enumerate(rows, 1):
            medal = RANK_BADGES[i-1] if 0 < i <= len(RANK_BADGES) else f"**{i}.**"
            lines.append(f"{medal} **{r['name']}** — {r['value']:,} {label} (Lv. {r['level']})")

        embed = discord.Embed(
            title=f"\U0001f3c6 Leaderboard — Top {len(rows)} by {label}",
            description="\n".join(lines),
            color=discord.Color.gold(),
        )
        embed.set_footer(text=self.bot.cfg.community_name)
        await ctx.send(embed=embed)

    # -------------------------------------------------------------------
    # /preferences
    # -------------------------------------------------------------------
    @commands.hybrid_command(  # type: ignore[arg-type]
        name="preferences",
        description="Toggle your notification and visibility preferences.",
    )
    @app_commands.describe(
        setting="Which preference to toggle",
        enabled="Turn on (True) or off (False)",
    )
    @app_commands.choices(setting=[
        app_commands.Choice(name="Announce Level-Ups", value="announce_level_up"),
        app_commands.Choice(name="Announce Achievements", value="announce_achievements"),
        app_commands.Choice(name="Announce Awards", value="announce_awards"),
    ])
    async def preferences(self, ctx: commands.Context, setting: str, enabled: bool) -> None:
        valid_fields = {"announce_level_up", "announce_achievements", "announce_awards"}
        if setting not in valid_fields:
            await ctx.send("\u274c Invalid preference.", ephemeral=True)
            return
        value = await run_db(self._toggle_preference, ctx.author.id, setting, enabled)
        status = "\u2705 Enabled" if value else "\u274c Disabled"
        pretty_name = setting.replace("_", " ").title()
        await ctx.send(f"**{pretty_name}**: {status}", ephemeral=True)

    # -------------------------------------------------------------------
    # /buy-coffee
    # -------------------------------------------------------------------
    @commands.hybrid_command(  # type: ignore[arg-type]
        name="buy-coffee",
        description="Spend gold to buy a virtual coffee! (Minimal gold sink)",
    )
    async def buy_coffee(self, ctx: commands.Context) -> None:
        cost = self.bot.cache.get_int("coffee_gold_cost", 50)
        success, remaining = await run_db(self._buy_coffee, ctx.author.id, cost)

        if success:
            embed = discord.Embed(
                title="\u2615 Coffee Purchased!",
                description=(
                    f"**{ctx.author.display_name}** bought a virtual coffee "
                    f"for {cost} \U0001fa99 Gold.\n"
                    f"Remaining: {remaining} \U0001fa99"
                ),
                color=discord.Color.from_rgb(139, 90, 43),
            )
        else:
            embed = discord.Embed(
                title="\u274c Not Enough Gold",
                description=f"You need {cost} \U0001fa99 Gold. You have {remaining}.",
                color=discord.Color.red(),
            )
        await ctx.send(embed=embed, ephemeral=True)


async def setup(bot: SynapseBot) -> None:
    await bot.add_cog(Meta(bot))
