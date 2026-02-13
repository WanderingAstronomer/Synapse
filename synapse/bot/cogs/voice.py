"""
synapse.bot.cogs.voice — Voice Channel XP/Star Engine
======================================================

Tracks time spent in voice channels and generates periodic
VOICE_TICK events (default: every 10 minutes, configurable via
the ``voice_tick_minutes`` setting).

Anti-idle: Users who are self-muted AND self-deafened are not counted.
Delegates announcement logic to announcement_service.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

import discord
from discord.ext import commands, tasks

from synapse.database.engine import run_db
from synapse.database.models import InteractionType
from synapse.engine.events import SynapseEvent
from synapse.services.announcement_service import announce_rewards
from synapse.services.reward_service import process_event

if TYPE_CHECKING:
    from synapse.bot.core import SynapseBot

logger = logging.getLogger(__name__)


# Maximum voice star ticks per user per hour (prevents idle farming)
MAX_VOICE_TICKS_PER_HOUR = 6


class Voice(commands.Cog, name="Voice"):
    """Tracks voice channel presence and awards XP/Stars on ticks."""

    def __init__(self, bot: SynapseBot) -> None:
        self.bot = bot
        # {user_id: join_timestamp} — tracks who is in voice and when they joined
        self._voice_sessions: dict[int, float] = {}
        # {user_id: [tick_timestamps]} — for hourly cap enforcement
        self._voice_tick_log: dict[int, list[float]] = {}

    async def cog_load(self) -> None:
        """Start the voice tick loop when the cog is loaded."""
        self.voice_tick_loop.start()

    async def cog_unload(self) -> None:
        """Stop the voice tick loop when the cog is unloaded."""
        self.voice_tick_loop.cancel()

    def _process(self, event: SynapseEvent, display_name: str):
        """Sync wrapper for process_event."""
        return process_event(
            self.bot.engine,
            self.bot.cache,
            event,
            display_name,
        )

    def _is_voice_tick_capped(self, user_id: int) -> bool:
        """Check if user has hit the hourly voice tick cap."""
        now = time.time()
        cutoff = now - 3600  # 1 hour
        ticks = self._voice_tick_log.get(user_id, [])
        # Prune old entries
        ticks = [t for t in ticks if t > cutoff]
        self._voice_tick_log[user_id] = ticks
        if len(ticks) >= MAX_VOICE_TICKS_PER_HOUR:
            return True
        return False

    def _record_voice_tick(self, user_id: int) -> None:
        """Record a voice tick for hourly cap tracking."""
        if user_id not in self._voice_tick_log:
            self._voice_tick_log[user_id] = []
        self._voice_tick_log[user_id].append(time.time())

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        """Track voice join/leave events."""
        before_ch = getattr(before.channel, "name", "None")
        after_ch = getattr(after.channel, "name", "None")
        logger.info(
            "Gateway event: VOICE_STATE %s (%s → %s, bot=%s)",
            member.name, before_ch, after_ch, member.bot,
        )
        try:
            await self._handle_voice_update(member, before, after)
        except Exception:
            logger.exception("Error processing voice state update for user %s", member.id)

    async def _handle_voice_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        """Inner voice state handler — decomposes into join/leave/move (P4).

        Writes Event Lake events AND maintains the legacy tick reward system.
        """
        if member.bot:
            return

        guild_id = member.guild.id
        session_id = after.session_id or before.session_id or str(member.id)

        # --- Voice JOIN (was not in channel, now is) ---
        if before.channel is None and after.channel is not None:
            self._voice_sessions[member.id] = time.time()

            await run_db(
                self.bot.lake_writer.write_voice_join,
                guild_id=guild_id,
                user_id=member.id,
                channel_id=after.channel.id,
                session_id=session_id,
                self_mute=after.self_mute or False,
                self_deaf=after.self_deaf or False,
            )
            logger.debug("%s joined voice channel %s", member, after.channel)

        # --- Voice LEAVE (was in channel, now is not) ---
        elif before.channel is not None and after.channel is None:
            self._voice_sessions.pop(member.id, None)

            await run_db(
                self.bot.lake_writer.write_voice_leave,
                guild_id=guild_id,
                user_id=member.id,
                channel_id=before.channel.id,
                session_id=session_id,
                self_mute=before.self_mute or False,
                self_deaf=before.self_deaf or False,
            )
            logger.debug("%s left voice channel %s", member, before.channel)

        # --- Voice MOVE (changed channels) ---
        elif before.channel is not None and after.channel is not None and before.channel != after.channel:
            self._voice_sessions[member.id] = self._voice_sessions.get(
                member.id, time.time()
            )

            await run_db(
                self.bot.lake_writer.write_voice_move,
                guild_id=guild_id,
                user_id=member.id,
                from_channel_id=before.channel.id,
                to_channel_id=after.channel.id,
                session_id=session_id,
                self_mute=after.self_mute or False,
                self_deaf=after.self_deaf or False,
            )
            logger.debug("%s moved voice %s → %s", member, before.channel, after.channel)

        # --- Mute/deaf state change (same channel) — update tracker ---
        elif before.channel is not None and after.channel is not None:
            self.bot.lake_writer.voice_tracker.update_state(
                member.id, guild_id,
                after.self_mute or False,
                after.self_deaf or False,
            )

    @tasks.loop(minutes=10)
    async def voice_tick_loop(self) -> None:
        """Periodic tick that awards voice XP/Stars to active members."""
        if not self.bot.is_ready():
            return

        for guild in self.bot.guilds:
            for vc in guild.voice_channels:
                for member in vc.members:
                    if member.bot:
                        continue

                    # Anti-idle: skip users who are both self-muted and self-deafened
                    voice = member.voice
                    if voice and voice.self_mute and voice.self_deaf:
                        continue

                    # Only tick users we're tracking
                    if member.id not in self._voice_sessions:
                        self._voice_sessions[member.id] = time.time()

                    # Hourly cap: skip if user has already had MAX ticks this hour
                    if self._is_voice_tick_capped(member.id):
                        continue

                    self._record_voice_tick(member.id)

                    tick_minutes = self.bot.cache.get_int("voice_tick_minutes", 10)
                    event = SynapseEvent(
                        user_id=member.id,
                        event_type=InteractionType.VOICE_TICK,
                        channel_id=vc.id,
                        guild_id=guild.id,
                        source_event_id=None,  # Voice ticks have no natural key
                        metadata={
                            "voice_channel": vc.name,
                            "tick_minutes": tick_minutes,
                            "member_count": len([m for m in vc.members if not m.bot]),
                        },
                    )

                    result, was_duplicate = await run_db(
                        self._process,
                        event,
                        member.display_name,
                    )

                    if not was_duplicate:
                        await announce_rewards(
                            self.bot,
                            result=result,
                            user_id=member.id,
                            display_name=member.display_name,
                            avatar_url=member.display_avatar.url,
                            fallback_channel=None,  # Voice ticks have no text channel
                        )

    @voice_tick_loop.before_loop
    async def before_voice_tick(self) -> None:
        """Wait until the bot is ready before starting voice ticks."""
        await self.bot.wait_until_ready()


async def setup(bot: SynapseBot) -> None:
    await bot.add_cog(Voice(bot))
