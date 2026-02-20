"""
synapse.bot.cogs.marketplace — Discord Role Assignment for Marketplace Purchases
=================================================================================

Handles the asynchronous side-effect of ``DISCORD_ROLE`` marketplace
purchases: assigns the configured Discord role to the purchasing member.

Role assignment is fire-and-forget from the API's perspective.  This cog
provides two complementary delivery paths:

1. **Poll loop** (60s interval) — scans all active ``DISCORD_ROLE``
   inventory records and ensures every owner has the role.  Idempotent.
2. **Event callback** — reacts immediately to ``synapse_events`` payloads
    of type ``marketplace_role_assignment`` sent by
    ``marketplace_service.notify_role_assignment``.

Role assignment failure is logged but does not affect the purchase record.
The poll loop means transient failures are self-healing.

Constraints
-----------
- Maximum 3 attempts per (user, role) pair per poll cycle.
- Exponential back-off between attempts (1s, 2s, 4s).
- Discord API calls are gated behind ``asyncio.Semaphore(5)``
  to prevent thundering-herd effects on large guilds.
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import TYPE_CHECKING

import discord
from discord.ext import commands, tasks
from sqlalchemy import select

from synapse.database.engine import run_db
from synapse.database.models import MarketplaceItem, MarketplaceItemType, UserInventory

if TYPE_CHECKING:
    from synapse.bot.core import SynapseBot

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Sync DB helper (called via run_db)
# ---------------------------------------------------------------------------


def _fetch_role_assignments(engine) -> list[tuple[int, int]]:  # type: ignore[type-arg]
    """Return list of ``(user_id, discord_role_id)`` to assign.

    Selects all active DISCORD_ROLE inventory records.
    The Discord role grant is idempotent, so no separate tracking needed.
    """
    from sqlalchemy.orm import Session

    with Session(engine) as session:
        rows = session.execute(
            select(UserInventory.user_id, MarketplaceItem.discord_role_id)
            .join(MarketplaceItem, MarketplaceItem.id == UserInventory.item_id)
            .where(
                MarketplaceItem.item_type == MarketplaceItemType.DISCORD_ROLE,
                MarketplaceItem.discord_role_id.isnot(None),
                MarketplaceItem.active.is_(True),
            )
        ).all()
        return [(r.user_id, r.discord_role_id) for r in rows]


# ---------------------------------------------------------------------------
# Async helpers
# ---------------------------------------------------------------------------


class MarketplaceCog(commands.Cog, name="Marketplace"):
    """Background role-assignment worker for marketplace purchases."""

    MAX_RETRIES = 3
    CONCURRENCY_LIMIT = 5
    ROLE_ASSIGN_EVENT_TYPE = "marketplace_role_assignment"

    def __init__(self, bot: SynapseBot) -> None:
        self.bot = bot
        self._sem = asyncio.Semaphore(self.CONCURRENCY_LIMIT)

    async def cog_load(self) -> None:
        self.bot.cache.register_event_callback(
            self.ROLE_ASSIGN_EVENT_TYPE,
            self._on_role_assignment,
            loop=asyncio.get_running_loop(),
        )
        self.role_sync_loop.start()

    async def cog_unload(self) -> None:
        self.role_sync_loop.cancel()

    async def _assign_role_with_retry(
        self,
        guild: discord.Guild,
        user_id: int,
        discord_role_id: int,
    ) -> None:
        """Attempt to assign ``discord_role_id`` to ``user_id`` with retries."""
        role = guild.get_role(discord_role_id)
        if role is None:
            logger.debug(
                "Role %d not found in guild %d — skipping assignment for user %d.",
                discord_role_id,
                guild.id,
                user_id,
            )
            return

        member = guild.get_member(user_id)
        if member is None:
            return  # Member not in cache — not in guild

        if role in member.roles:
            return  # Already has the role — true no-op

        async with self._sem:
            for attempt in range(self.MAX_RETRIES):
                try:
                    await member.add_roles(role, reason="Marketplace purchase")
                    logger.info(
                        "Assigned role %r (%d) to member %d (guild %d).",
                        role.name,
                        discord_role_id,
                        user_id,
                        guild.id,
                    )
                    return
                except discord.Forbidden:
                    logger.warning(
                        "Missing permission to assign role %d to user %d.",
                        discord_role_id,
                        user_id,
                    )
                    return  # Permissions won't change — stop retrying
                except discord.HTTPException as exc:
                    wait = (2**attempt) + random.uniform(0, 1)  # noqa: S311
                    if attempt < self.MAX_RETRIES - 1:
                        logger.debug(
                            "Role assign attempt %d failed (%s) — retrying in %.1fs.",
                            attempt + 1,
                            exc,
                            wait,
                        )
                        await asyncio.sleep(wait)
                    else:
                        logger.warning(
                            "Role %d assign failed for user %d after %d attempts: %s",
                            discord_role_id,
                            user_id,
                            self.MAX_RETRIES,
                            exc,
                        )

    @tasks.loop(seconds=60)
    async def role_sync_loop(self) -> None:
        """Scan all DISCORD_ROLE purchases and ensure roles are assigned."""
        if not self.bot.cfg.guild_id:
            return

        guild = self.bot.get_guild(self.bot.cfg.guild_id)
        if guild is None:
            return

        try:
            pairs: list[tuple[int, int]] = await run_db(_fetch_role_assignments, self.bot.engine)
        except Exception:
            logger.exception("Failed to fetch role assignments from DB.")
            return

        if not pairs:
            return

        # Process independently — failure of one user does not block others.
        # But cap the number of active coroutines to prevent task explosion.
        # Use simple chunking or just rely on the semaphore if the count is manageable.
        # However, for 10k users, launching 10k tasks is bad even with a semaphore inside.
        # We'll stick to the semaphore inside but consider batching if needed.
        # Re-reading KNOWN_ISSUES P08-02: "A guild with thousands of members triggers thousands
        # of simultaneous Discord API calls"
        # The issue is likely that the semaphore is INSIDE the function, so 1000 tasks start,
        # do the pre-checks (get_role, get_member) and then wait at the semaphore.
        # If get_member/get_role are fast, maybe it's fine?
        # But if the semaphore is meant to bound the LOOP, it should be outside?

        # ACTUALLY, checking the code:
        # The semaphore is self._sem.

        # The suggested fix is:
        # sem = asyncio.Semaphore(10)
        # async def limited(task):
        #     async with sem:
        #          await task

        # My code does exactly that inside _assign_role_with_retry:
        # async with self._sem:
        #    ...

        # So maybe the issue is that I should not even Create the tasks if they are too many?
        # Or maybe the previous audit missed that I already have a semaphore?

        # Wait! The semaphore is only acquired AFTER `get_role` and `get_member`.
        # If I have 10k users, I do 10k cache lookups immediately.
        # That's CPU bound work on the event loop!

        # Better to have the semaphore wrappering the ENTIRE call to
        # _assign_role_with_retry including the args prep.
        # OR just use a bounded gatherer (chunked).

        # Let's implement chunking (processing in batches) which is safer for huge lists.

        batch_size = 50
        for i in range(0, len(pairs), batch_size):
            chunk = pairs[i : i + batch_size]
            tasks_list = [
                self._assign_role_with_retry(guild, user_id, role_id)
                for user_id, role_id in chunk
            ]
            results = await asyncio.gather(*tasks_list, return_exceptions=True)

            for (user_id, role_id), exc in zip(chunk, results):
                if isinstance(exc, Exception):
                    logger.warning(
                        "Unhandled error in role sync for user=%d role=%d: %s",
                        user_id,
                        role_id,
                        exc,
                    )

            # Short yield to let other events process
            await asyncio.sleep(0.1)

    @role_sync_loop.before_loop
    async def _wait_ready(self) -> None:
        await self.bot.wait_until_ready()

    async def _on_role_assignment(self, data: dict) -> None:
        """Handle marketplace role-assignment events from the event bus."""
        guild_id = int(data.get("guild_id", 0))
        if guild_id != self.bot.cfg.guild_id:
            return

        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return

        user_id = int(data["user_id"])
        discord_role_id = int(data["discord_role_id"])
        await self._assign_role_with_retry(guild, user_id, discord_role_id)


async def setup(bot: SynapseBot) -> None:
    await bot.add_cog(MarketplaceCog(bot))
