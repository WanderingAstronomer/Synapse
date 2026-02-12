"""
synapse.services.retention_service — Event Lake Retention Cleanup
==================================================================

Periodic cleanup of aged Event Lake rows and stale day-counters.

Reference: 03B_DATA_LAKE.md §3B.7 — Retention & Pruning
    - Default retention: 90 days (configurable via ``event_lake_retention_days``).
    - Counter pruning: ``day:*`` counters older than retention window.
    - Runs as a ``discord.ext.tasks`` loop (daily) or can be invoked ad-hoc.

**Deletion is batched** to avoid locking the table for too long:
rows are removed in chunks of ``BATCH_SIZE`` with a small sleep between
batches so the DB can serve normal writes without contention.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import Engine, delete, func, select, text

from synapse.database.engine import get_session
from synapse.database.models import EventCounter, EventLake

logger = logging.getLogger(__name__)

# How many rows to delete in each batch (avoids long-held row locks)
BATCH_SIZE = 5_000


def run_retention_cleanup(
    engine: Engine,
    retention_days: int = 90,
) -> dict[str, int]:
    """Delete Event Lake rows older than ``retention_days``.

    Also prunes ``day:*`` counters whose date is before the cutoff.

    Returns a summary dict: ``{"events_deleted": N, "counters_deleted": M}``.
    """
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    events_deleted = 0
    counters_deleted = 0

    # --- Batch-delete old events ---
    while True:
        with get_session(engine) as session:
            # Find IDs of rows to delete (bounded batch)
            ids = session.scalars(
                select(EventLake.id)
                .where(EventLake.timestamp < cutoff)
                .limit(BATCH_SIZE)
            ).all()

            if not ids:
                break

            result = session.execute(
                delete(EventLake).where(EventLake.id.in_(ids))
            )
            events_deleted += result.rowcount  # type: ignore[operator]
            logger.info(
                "Retention: deleted %d event_lake rows (total so far: %d)",
                result.rowcount, events_deleted,
            )

    # --- Prune stale day counters ---
    cutoff_day = cutoff.strftime("%Y-%m-%d")
    with get_session(engine) as session:
        # day:YYYY-MM-DD  — delete where the date portion is before cutoff
        result = session.execute(
            text("""
                DELETE FROM event_counters
                WHERE period LIKE 'day:%'
                  AND SUBSTRING(period FROM 5) < :cutoff_day
            """),
            {"cutoff_day": cutoff_day},
        )
        counters_deleted = result.rowcount  # type: ignore[assignment]
        logger.info("Retention: pruned %d stale day counters", counters_deleted)

    logger.info(
        "Retention cleanup complete — %d events, %d counters removed "
        "(retention_days=%d, cutoff=%s)",
        events_deleted, counters_deleted, retention_days, cutoff.isoformat(),
    )
    return {"events_deleted": events_deleted, "counters_deleted": counters_deleted}


def get_retention_stats(engine: Engine) -> dict:
    """Return Event Lake size statistics for the health dashboard."""
    with get_session(engine) as session:
        total_events = session.scalar(
            select(func.count()).select_from(EventLake)
        ) or 0

        oldest_event = session.scalar(
            select(func.min(EventLake.timestamp))
        )

        newest_event = session.scalar(
            select(func.max(EventLake.timestamp))
        )

        total_counters = session.scalar(
            select(func.count()).select_from(EventCounter)
        ) or 0

        # Approximate table size via pg_total_relation_size
        try:
            size_bytes = session.scalar(
                text("SELECT pg_total_relation_size('event_lake')")
            ) or 0
        except Exception:
            size_bytes = 0

    return {
        "total_events": total_events,
        "total_counters": total_counters,
        "oldest_event": oldest_event.isoformat() if oldest_event else None,
        "newest_event": newest_event.isoformat() if newest_event else None,
        "table_size_bytes": size_bytes,
    }
