"""
synapse.services.throttle — Sliding-window announcement throttle
=================================================================

Rate-limits per-channel embed delivery and queues overflow for
background draining every ~10 seconds.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict

import discord
from discord.abc import Messageable

logger = logging.getLogger(__name__)


class AnnouncementThrottle:
    """Sliding-window throttle with an async queue for overflow embeds.

    - Up to ``max_per_window`` embeds per channel per ``window`` seconds.
    - Excess embeds are queued and drained every ~10 s by a background task.
    """

    def __init__(self, max_per_window: int = 3, window: int = 60) -> None:
        self.max_per_window = max_per_window
        self.window = window
        self._timestamps: dict[int, list[float]] = defaultdict(list)
        self._queues: dict[int, asyncio.Queue[tuple[discord.Embed, Messageable]]] = {}
        self._drain_task: asyncio.Task | None = None

    def is_allowed(self, channel_id: int) -> bool:
        """Return True if we can send right now; False → caller should enqueue."""
        now = time.time()
        cutoff = now - self.window
        stamps = self._timestamps[channel_id]
        self._timestamps[channel_id] = [t for t in stamps if t > cutoff]
        if len(self._timestamps[channel_id]) >= self.max_per_window:
            return False
        self._timestamps[channel_id].append(now)
        return True

    def enqueue(
        self, channel_id: int, embed: discord.Embed, channel: Messageable
    ) -> None:
        """Put an embed on the overflow queue for later delivery."""
        if channel_id not in self._queues:
            self._queues[channel_id] = asyncio.Queue()
        self._queues[channel_id].put_nowait((embed, channel))

    async def drain_once(self) -> None:
        """Attempt to send queued embeds for channels whose window has reopened."""
        for ch_id, queue in list(self._queues.items()):
            while not queue.empty():
                if not self.is_allowed(ch_id):
                    break
                embed, channel = queue.get_nowait()
                try:
                    await channel.send(embed=embed)
                except Exception:
                    logger.exception(
                        "Failed to send queued embed to channel %d", ch_id
                    )

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        """Start the background drain task."""
        if self._drain_task is not None:
            return

        async def _drain_loop() -> None:
            while True:
                await asyncio.sleep(10)
                try:
                    await self.drain_once()
                except Exception:
                    logger.exception("Throttle drain error")

        self._drain_task = loop.create_task(
            _drain_loop(), name="announce-drain"
        )

    def stop(self) -> None:
        """Cancel the drain task."""
        if self._drain_task:
            self._drain_task.cancel()
            self._drain_task = None
