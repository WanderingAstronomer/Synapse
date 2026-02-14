"""
synapse.services.announcement_service — Unified Announcement Service
=====================================================================

Cross-cutting service that owns user-preference gating, channel
resolution, and throttle-safe public celebrations.

Embed construction lives in :mod:`synapse.services.embeds`.
Throttle logic lives in :mod:`synapse.services.throttle`.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from discord.abc import Messageable, Snowflake

from synapse.database.engine import run_db
from synapse.database.models import AchievementTemplate, UserPreferences
from synapse.services.embeds import (
    build_achievement_embed,
    build_achievement_fallback_embed,
    build_level_up_embed,
    build_manual_award_embed,
)
from synapse.services.throttle import AnnouncementThrottle

if TYPE_CHECKING:
    import discord

    from synapse.bot.core import SynapseBot

logger = logging.getLogger(__name__)

# Module-level throttle instance
_throttle = AnnouncementThrottle()


def start_queue(loop: asyncio.AbstractEventLoop) -> None:
    """Start the announcement throttle drain task. Call from on_ready."""
    _throttle.start(loop)


def stop_queue() -> None:
    """Stop the drain task. Call from bot close."""
    _throttle.stop()


# ---------------------------------------------------------------------------
# Helpers (sync — run via run_db)
# ---------------------------------------------------------------------------
def _load_preferences(engine, user_id: int) -> UserPreferences | None:
    from synapse.database.engine import get_session  # noqa: E402 — avoid circular

    with get_session(engine) as session:
        return session.get(UserPreferences, user_id)


def _load_achievement_template(engine, ach_id: int) -> AchievementTemplate | None:
    from synapse.database.engine import get_session  # noqa: E402 — avoid circular

    with get_session(engine) as session:
        tmpl = session.get(AchievementTemplate, ach_id)
        if tmpl:
            session.expunge(tmpl)
        return tmpl


# ---------------------------------------------------------------------------
# Channel resolution
# ---------------------------------------------------------------------------
def resolve_announce_channel(
    bot: SynapseBot,
    *,
    achievement_template: AchievementTemplate | None = None,
    fallback_channel: Snowflake | Messageable | None = None,
) -> Messageable | None:
    """Resolve the target channel for an announcement.

    Priority: per-template → synapse_achievements_channel → global config → fallback.
    """
    if achievement_template and achievement_template.announce_channel_id:
        ch = bot.get_channel(achievement_template.announce_channel_id)
        if ch and isinstance(ch, Messageable):
            return ch

    synapse_ch_id = getattr(bot, "synapse_announce_channel_id", None)
    if synapse_ch_id:
        ch = bot.get_channel(synapse_ch_id)
        if ch and isinstance(ch, Messageable):
            return ch

    if bot.cfg.announce_channel_id:
        ch = bot.get_channel(bot.cfg.announce_channel_id)
        if ch and isinstance(ch, Messageable):
            return ch

    if isinstance(fallback_channel, Messageable):
        return fallback_channel
    return None


# ---------------------------------------------------------------------------
# Sending helper (handles throttle + queue)
# ---------------------------------------------------------------------------
async def _send_embed(
    channel: Messageable | None, embed: discord.Embed
) -> None:
    if channel is None:
        return
    channel_id = getattr(channel, "id", 0)
    if _throttle.is_allowed(channel_id):
        try:
            await channel.send(embed=embed)
        except Exception:
            logger.exception(
                "Failed to send announcement embed to channel %d", channel_id
            )
    else:
        _throttle.enqueue(channel_id, embed, channel)


# ---------------------------------------------------------------------------
# Public API — called by cogs
# ---------------------------------------------------------------------------
async def announce_rewards(
    bot: SynapseBot,
    *,
    result,  # RewardResult
    user_id: int,
    display_name: str,
    avatar_url: str,
    fallback_channel: Snowflake | Messageable | None = None,
) -> None:
    """Announce level-ups and achievements from a process_event result."""
    if not result.leveled_up and not result.achievements_earned:
        return

    prefs: UserPreferences | None = await run_db(
        _load_preferences, bot.engine, user_id
    )

    if result.leveled_up:
        announce_lu = prefs.announce_level_up if prefs else True
        if announce_lu:
            target = resolve_announce_channel(
                bot, fallback_channel=fallback_channel
            )
            embed = build_level_up_embed(
                user_id,
                display_name,
                avatar_url,
                result.new_level,
                result.gold_bonus,
            )
            await _send_embed(target, embed)

    if result.achievements_earned:
        announce_ach = prefs.announce_achievements if prefs else True
        if announce_ach:
            for ach_id in result.achievements_earned:
                tmpl: AchievementTemplate | None = await run_db(
                    _load_achievement_template, bot.engine, ach_id
                )
                if tmpl:
                    target = resolve_announce_channel(
                        bot,
                        achievement_template=tmpl,
                        fallback_channel=fallback_channel,
                    )
                    embed = build_achievement_embed(
                        user_id, display_name, avatar_url, tmpl
                    )
                else:
                    target = resolve_announce_channel(
                        bot, fallback_channel=fallback_channel
                    )
                    embed = build_achievement_fallback_embed(
                        user_id, display_name, avatar_url
                    )
                await _send_embed(target, embed)


async def announce_manual_award(
    bot: SynapseBot,
    *,
    recipient_id: int,
    display_name: str,
    avatar_url: str,
    xp: int,
    gold: int,
    reason: str,
    admin_name: str,
    fallback_channel: Snowflake | Messageable | None = None,
) -> None:
    """Announce a manual XP/Gold award (from /award command)."""
    prefs: UserPreferences | None = await run_db(
        _load_preferences, bot.engine, recipient_id
    )
    announce = prefs.announce_awards if prefs else True
    if not announce:
        return

    target = resolve_announce_channel(bot, fallback_channel=fallback_channel)
    embed = build_manual_award_embed(
        recipient_id, display_name, avatar_url, xp, gold, reason, admin_name
    )
    await _send_embed(target, embed)


async def announce_achievement_grant(
    bot: SynapseBot,
    *,
    recipient_id: int,
    display_name: str,
    avatar_url: str,
    achievement_id: int,
    admin_name: str,
    fallback_channel: Snowflake | Messageable | None = None,
) -> None:
    """Announce a manually granted achievement (from /grant-achievement)."""
    prefs: UserPreferences | None = await run_db(
        _load_preferences, bot.engine, recipient_id
    )
    announce = prefs.announce_achievements if prefs else True
    if not announce:
        return

    tmpl: AchievementTemplate | None = await run_db(
        _load_achievement_template, bot.engine, achievement_id
    )
    if tmpl:
        target = resolve_announce_channel(
            bot,
            achievement_template=tmpl,
            fallback_channel=fallback_channel,
        )
        embed = build_achievement_embed(
            recipient_id, display_name, avatar_url, tmpl
        )
        embed.set_footer(text=f"Granted by {admin_name}")
    else:
        target = resolve_announce_channel(
            bot, fallback_channel=fallback_channel
        )
        embed = build_achievement_fallback_embed(
            recipient_id, display_name, avatar_url
        )
        embed.set_footer(text=f"Granted by {admin_name}")

    await _send_embed(target, embed)
