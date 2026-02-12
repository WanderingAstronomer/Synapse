"""
tests/test_announcements.py — Unit Tests for Announcement Service
==================================================================

Tests the unified announcement service's throttle, channel resolution,
embed builders, preference gating, and public API.
"""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from synapse.constants import RARITY_EMOJI
from synapse.services.announcement_service import (
    _send_embed,
    announce_achievement_grant,
    announce_manual_award,
    announce_rewards,
    resolve_announce_channel,
)
from synapse.services.embeds import (
    RARITY_COLORS,
    build_achievement_embed,
    build_achievement_fallback_embed,
    build_level_up_embed,
    build_manual_award_embed,
)
from synapse.services.throttle import AnnouncementThrottle


# Helper to run async tests without pytest-asyncio
def run_async(coro):
    """Run an async coroutine in a new event loop."""
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_bot(
    *,
    synapse_ch_id: int | None = None,
    config_ch_id: int | None = None,
    channels: dict[int, object] | None = None,
) -> MagicMock:
    """Create a lightweight mock SynapseBot."""
    bot = MagicMock()
    bot.synapse_announce_channel_id = synapse_ch_id
    bot.cfg = SimpleNamespace(announce_channel_id=config_ch_id)
    bot.engine = MagicMock()

    def _get_channel(ch_id):
        if channels and ch_id in channels:
            return channels[ch_id]
        return None

    bot.get_channel = _get_channel
    return bot


def _make_messageable(channel_id: int = 100) -> MagicMock:
    """Create a mock Messageable channel."""
    ch = MagicMock(spec=discord.TextChannel)
    ch.id = channel_id
    ch.send = AsyncMock()
    return ch


def _make_achievement_template(
    *,
    ach_id: int = 1,
    name: str = "Test Achievement",
    rarity: str = "rare",
    description: str = "A test achievement",
    xp_reward: int = 50,
    gold_reward: int = 25,
    badge_image_url: str | None = None,
    announce_channel_id: int | None = None,
) -> MagicMock:
    """Create a mock AchievementTemplate."""
    tmpl = MagicMock()
    tmpl.id = ach_id
    tmpl.name = name
    tmpl.rarity = rarity
    tmpl.description = description
    tmpl.xp_reward = xp_reward
    tmpl.gold_reward = gold_reward
    tmpl.badge_image_url = badge_image_url
    tmpl.announce_channel_id = announce_channel_id
    return tmpl


def _make_reward_result(
    *,
    leveled_up: bool = False,
    new_level: int = 2,
    gold_bonus: int = 10,
    achievements_earned: list[int] | None = None,
) -> SimpleNamespace:
    """Create a mock RewardResult."""
    return SimpleNamespace(
        leveled_up=leveled_up,
        new_level=new_level,
        gold_bonus=gold_bonus,
        achievements_earned=achievements_earned or [],
    )


# ===========================================================================
# Test: AnnouncementThrottle
# ===========================================================================
class TestAnnouncementThrottle:
    """Tests for the sliding-window throttle."""

    def test_allows_up_to_max(self):
        throttle = AnnouncementThrottle(max_per_window=3, window=60)
        ch_id = 100
        assert throttle.is_allowed(ch_id) is True
        assert throttle.is_allowed(ch_id) is True
        assert throttle.is_allowed(ch_id) is True
        # 4th should be blocked
        assert throttle.is_allowed(ch_id) is False

    def test_different_channels_independent(self):
        throttle = AnnouncementThrottle(max_per_window=1, window=60)
        assert throttle.is_allowed(100) is True
        assert throttle.is_allowed(100) is False
        # Different channel should be independent
        assert throttle.is_allowed(200) is True
        assert throttle.is_allowed(200) is False

    def test_window_expires(self):
        throttle = AnnouncementThrottle(max_per_window=1, window=1)
        ch_id = 100
        assert throttle.is_allowed(ch_id) is True
        assert throttle.is_allowed(ch_id) is False
        # Wait for window to expire
        time.sleep(1.1)
        assert throttle.is_allowed(ch_id) is True

    def test_enqueue_and_drain(self):
        throttle = AnnouncementThrottle(max_per_window=1, window=60)
        ch = _make_messageable(100)
        embed = discord.Embed(title="Test")

        # Fill the window
        assert throttle.is_allowed(100) is True
        # Now enqueue
        throttle.enqueue(100, embed, ch)
        assert not throttle._queues[100].empty()

    def test_drain_sends_when_allowed(self):
        async def _inner():
            throttle = AnnouncementThrottle(max_per_window=2, window=1)
            ch = _make_messageable(100)
            embed = discord.Embed(title="Queued")

            # Use up the window
            throttle.is_allowed(100)
            throttle.is_allowed(100)
            # Enqueue
            throttle.enqueue(100, embed, ch)

            # Wait for window to expire
            await asyncio.sleep(1.1)
            await throttle.drain_once()

            ch.send.assert_awaited_once_with(embed=embed)
        run_async(_inner())


# ===========================================================================
# Test: resolve_announce_channel
# ===========================================================================
class TestResolveAnnounceChannel:
    """Tests for channel resolution priority."""

    def test_per_template_channel_first(self):
        per_tmpl_ch = _make_messageable(500)
        synapse_ch = _make_messageable(600)
        fallback_ch = _make_messageable(700)

        tmpl = _make_achievement_template(announce_channel_id=500)

        bot = _make_bot(
            synapse_ch_id=600,
            config_ch_id=800,
            channels={500: per_tmpl_ch, 600: synapse_ch},
        )

        result = resolve_announce_channel(
            bot,
            achievement_template=tmpl,
            fallback_channel=fallback_ch,
        )
        assert result is per_tmpl_ch

    def test_synapse_channel_second(self):
        synapse_ch = _make_messageable(600)
        fallback_ch = _make_messageable(700)

        bot = _make_bot(
            synapse_ch_id=600,
            config_ch_id=None,
            channels={600: synapse_ch},
        )

        result = resolve_announce_channel(
            bot, fallback_channel=fallback_ch,
        )
        assert result is synapse_ch

    def test_global_config_third(self):
        config_ch = _make_messageable(800)
        fallback_ch = _make_messageable(700)

        bot = _make_bot(
            synapse_ch_id=None,
            config_ch_id=800,
            channels={800: config_ch},
        )

        result = resolve_announce_channel(
            bot, fallback_channel=fallback_ch,
        )
        assert result is config_ch

    def test_fallback_last(self):
        fallback_ch = _make_messageable(700)

        bot = _make_bot(
            synapse_ch_id=None,
            config_ch_id=None,
            channels={},
        )

        result = resolve_announce_channel(
            bot, fallback_channel=fallback_ch,
        )
        assert result is fallback_ch

    def test_returns_none_when_nothing_available(self):
        bot = _make_bot(synapse_ch_id=None, config_ch_id=None, channels={})
        result = resolve_announce_channel(bot)
        assert result is None


# ===========================================================================
# Test: Embed Builders
# ===========================================================================
class TestEmbedBuilders:
    """Tests that embeds contain user mentions and correct info."""

    def test_level_up_embed_has_mention(self):
        embed = build_level_up_embed(
            user_id=12345,
            display_name="TestUser",
            avatar_url="https://example.com/avatar.png",
            new_level=5,
            gold_bonus=15,
        )
        assert "<@12345>" in embed.description
        assert "Level 5" in embed.description
        assert "15" in embed.description

    def test_achievement_embed_has_mention(self):
        tmpl = _make_achievement_template(
            name="Star Collector",
            rarity="epic",
            xp_reward=100,
            gold_reward=50,
        )
        embed = build_achievement_embed(
            user_id=67890,
            display_name="Achiever",
            avatar_url="https://example.com/ach.png",
            tmpl=tmpl,
        )
        assert "<@67890>" in embed.description
        assert "Star Collector" in embed.description
        assert "epic" in embed.description
        # Check rewards field
        assert any("100 XP" in (f.value or "") for f in embed.fields)

    def test_achievement_fallback_embed_has_mention(self):
        embed = build_achievement_fallback_embed(
            user_id=11111,
            display_name="Someone",
            avatar_url="https://example.com/sb.png",
        )
        assert "<@11111>" in embed.description

    def test_manual_award_embed_has_mention(self):
        embed = build_manual_award_embed(
            recipient_id=22222,
            display_name="Recipient",
            avatar_url="https://example.com/r.png",
            xp=50,
            gold=25,
            reason="Being awesome",
            admin_name="AdminUser",
        )
        assert "<@22222>" in embed.description
        assert "50 XP" in embed.description or "+50" in embed.description
        assert "AdminUser" in embed.footer.text


# ===========================================================================
# Test: Preference Gating
# ===========================================================================
class TestPreferenceGating:
    """Tests that announcements respect user preference opt-outs."""

    def test_level_up_suppressed_when_opted_out(self):
        """When prefs.announce_level_up is False, no level-up embed sent."""
        async def _inner():
            bot = _make_bot(synapse_ch_id=100, channels={100: _make_messageable(100)})
            result = _make_reward_result(leveled_up=True, new_level=3, gold_bonus=10)

            prefs = MagicMock()
            prefs.announce_level_up = False
            prefs.announce_achievements = True

            with patch(
                "synapse.services.announcement_service.run_db",
                new=AsyncMock(return_value=prefs),
            ):
                with patch(
                    "synapse.services.announcement_service._send_embed",
                    new=AsyncMock(),
                ) as mock_send:
                    await announce_rewards(
                        bot,
                        result=result,
                        user_id=1,
                        display_name="User",
                        avatar_url="https://example.com/a.png",
                    )
                    mock_send.assert_not_awaited()
        run_async(_inner())

    def test_awards_suppressed_when_opted_out(self):
        """When prefs.announce_awards is False, no manual award embed sent."""
        async def _inner():
            bot = _make_bot(synapse_ch_id=100, channels={100: _make_messageable(100)})

            prefs = MagicMock()
            prefs.announce_awards = False

            with patch(
                "synapse.services.announcement_service.run_db",
                new=AsyncMock(return_value=prefs),
            ):
                with patch(
                    "synapse.services.announcement_service._send_embed",
                    new=AsyncMock(),
                ) as mock_send:
                    await announce_manual_award(
                        bot,
                        recipient_id=1,
                        display_name="User",
                        avatar_url="https://example.com/a.png",
                        xp=100,
                        gold=50,
                        reason="Testing",
                        admin_name="Admin",
                    )
                    mock_send.assert_not_awaited()
        run_async(_inner())

    def test_achievement_suppressed_when_opted_out(self):
        """When prefs.announce_achievements is False, no achievement embed."""
        async def _inner():
            bot = _make_bot(synapse_ch_id=100, channels={100: _make_messageable(100)})

            prefs = MagicMock()
            prefs.announce_achievements = False

            with patch(
                "synapse.services.announcement_service.run_db",
                new=AsyncMock(return_value=prefs),
            ):
                with patch(
                    "synapse.services.announcement_service._send_embed",
                    new=AsyncMock(),
                ) as mock_send:
                    await announce_achievement_grant(
                        bot,
                        recipient_id=1,
                        display_name="User",
                        avatar_url="https://example.com/a.png",
                        achievement_id=1,
                        admin_name="Admin",
                    )
                    mock_send.assert_not_awaited()
        run_async(_inner())


# ===========================================================================
# Test: _send_embed
# ===========================================================================
class TestSendEmbed:
    """Tests for the throttle-aware send helper."""

    def test_send_embed_none_channel_noop(self):
        """Sending to None channel should be a no-op."""
        async def _inner():
            embed = discord.Embed(title="Test")
            await _send_embed(None, embed)
        run_async(_inner())

    def test_send_embed_calls_channel_send(self):
        """When throttle allows, embed should be sent directly."""
        async def _inner():
            ch = _make_messageable(999)
            embed = discord.Embed(title="Direct")

            with patch.object(
                AnnouncementThrottle, "is_allowed", return_value=True
            ):
                await _send_embed(ch, embed)
            ch.send.assert_awaited_once_with(embed=embed)
        run_async(_inner())


# ===========================================================================
# Test: Constants sanity
# ===========================================================================
class TestConstants:
    """Sanity checks on module-level constants."""

    def test_all_rarities_have_colors(self):
        for rarity in ("common", "uncommon", "rare", "epic", "legendary"):
            assert rarity in RARITY_COLORS

    def test_all_rarities_have_emoji(self):
        for rarity in ("common", "uncommon", "rare", "epic", "legendary"):
            assert rarity in RARITY_EMOJI

    def test_rarity_colors_are_discord_color(self):
        for rarity, color in RARITY_COLORS.items():
            assert isinstance(color, discord.Color), f"{rarity} color is not discord.Color"
