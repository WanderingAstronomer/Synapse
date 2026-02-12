"""
synapse.services.embeds — Discord embed builders for announcements
====================================================================

All embed construction lives here so the announcement service and
cogs only need to supply data — no layout concerns.
"""

from __future__ import annotations

import discord

from synapse.constants import RARITY_EMOJI
from synapse.database.models import AchievementTemplate

# Discord-native Color objects for embed sidebar
RARITY_COLORS: dict[str, discord.Color] = {
    "common": discord.Color.light_grey(),
    "uncommon": discord.Color.green(),
    "rare": discord.Color.blue(),
    "epic": discord.Color.purple(),
    "legendary": discord.Color.gold(),
}


def build_level_up_embed(
    user_id: int,
    display_name: str,
    avatar_url: str,
    new_level: int,
    gold_bonus: int,
) -> discord.Embed:
    """Build a level-up celebration embed with @mention."""
    embed = discord.Embed(
        title="\u26a1 Level Up!",
        description=(
            f"<@{user_id}> reached **Level {new_level}**!\n"
            f"+{gold_bonus} \U0001fa99 Gold awarded."
        ),
        color=discord.Color.gold(),
    )
    embed.set_thumbnail(url=avatar_url)
    return embed


def build_achievement_embed(
    user_id: int,
    display_name: str,
    avatar_url: str,
    tmpl: AchievementTemplate,
) -> discord.Embed:
    """Build a rich achievement celebration embed with @mention."""
    rarity = tmpl.rarity or "common"
    color = RARITY_COLORS.get(rarity, discord.Color.purple())
    emoji = RARITY_EMOJI.get(rarity, "\u26aa")
    embed = discord.Embed(
        title="\U0001f3c6 Achievement Unlocked!",
        description=(
            f"<@{user_id}> earned "
            f"{emoji} **{tmpl.name}** ({rarity})\n\n"
            f"*{tmpl.description or 'No description.'}*"
        ),
        color=color,
    )
    if tmpl.xp_reward or tmpl.gold_reward:
        rewards = []
        if tmpl.xp_reward:
            rewards.append(f"+{tmpl.xp_reward} XP")
        if tmpl.gold_reward:
            rewards.append(f"+{tmpl.gold_reward} \U0001fa99 Gold")
        embed.add_field(name="Rewards", value=" | ".join(rewards), inline=False)
    if tmpl.badge_image_url:
        embed.set_thumbnail(url=tmpl.badge_image_url)
    else:
        embed.set_thumbnail(url=avatar_url)
    return embed


def build_achievement_fallback_embed(
    user_id: int,
    display_name: str,
    avatar_url: str,
) -> discord.Embed:
    """Build a fallback achievement embed when template lookup fails."""
    embed = discord.Embed(
        title="\U0001f3c6 Achievement Unlocked!",
        description=f"<@{user_id}> earned a new achievement!",
        color=discord.Color.purple(),
    )
    embed.set_thumbnail(url=avatar_url)
    return embed


def build_manual_award_embed(
    recipient_id: int,
    display_name: str,
    avatar_url: str,
    xp: int,
    gold: int,
    reason: str,
    admin_name: str,
) -> discord.Embed:
    """Build a manual award celebration embed."""
    embed = discord.Embed(
        title="\U0001f381 Manual Award",
        description=(
            f"<@{recipient_id}> received:\n"
            + (f"  +{xp} XP\n" if xp > 0 else "")
            + (f"  +{gold} \U0001fa99 Gold\n" if gold > 0 else "")
            + f"\nReason: {reason}"
        ),
        color=discord.Color.green(),
    )
    embed.set_thumbnail(url=avatar_url)
    embed.set_footer(text=f"Awarded by {admin_name}")
    return embed
