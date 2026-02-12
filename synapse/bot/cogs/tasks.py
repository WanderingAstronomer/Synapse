"""
synapse.bot.cogs.tasks — Periodic Background Tasks
=====================================================

Scheduled jobs that run on ``discord.ext.tasks`` loops:

- **Retention cleanup** — daily, removes Event Lake rows older than
  ``event_lake_retention_days`` (default 90).
- **Counter reconciliation** — weekly, validates event_counters against
  raw Event Lake and corrects drift.

These tasks fire in the bot process (not a separate worker) to keep
the deployment simple.  They run via ``run_db()`` to avoid blocking
the event loop.
"""

from __future__ import annotations

import logging

from discord.ext import commands, tasks

from synapse.database.engine import run_db

logger = logging.getLogger(__name__)


class PeriodicTasks(commands.Cog):
    """Cog for scheduled background maintenance tasks."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        """Start task loops when the cog is loaded."""
        self.retention_loop.start()
        self.reconciliation_loop.start()

    async def cog_unload(self) -> None:
        """Cancel task loops on unload."""
        self.retention_loop.cancel()
        self.reconciliation_loop.cancel()

    # -------------------------------------------------------------------
    # Retention cleanup — runs every 24 hours
    # -------------------------------------------------------------------
    @tasks.loop(hours=24)
    async def retention_loop(self):
        """Delete Event Lake rows older than the configured retention window."""
        from synapse.services.retention_service import run_retention_cleanup

        # Read retention_days from settings (default 90)
        retention_days = self.bot.cache.get_int("event_lake_retention_days", 90)

        try:
            result = await run_db(
                run_retention_cleanup, self.bot.engine, retention_days,
            )
            logger.info(
                "Retention task complete: %d events, %d counters deleted",
                result["events_deleted"], result["counters_deleted"],
            )
        except Exception:
            logger.exception("Retention task failed")

    @retention_loop.before_loop
    async def _wait_retention(self):
        await self.bot.wait_until_ready()

    # -------------------------------------------------------------------
    # Counter reconciliation — runs every 7 days
    # -------------------------------------------------------------------
    @tasks.loop(hours=168)  # 7 days
    async def reconciliation_loop(self):
        """Validate lifetime counters against raw events and fix drift."""
        from synapse.services.reconciliation_service import reconcile_counters

        try:
            result = await run_db(reconcile_counters, self.bot.engine)
            logger.info(
                "Reconciliation task complete: checked=%d corrected=%d",
                result["checked"], result["corrected"],
            )
        except Exception:
            logger.exception("Reconciliation task failed")

    @reconciliation_loop.before_loop
    async def _wait_reconciliation(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PeriodicTasks(bot))
