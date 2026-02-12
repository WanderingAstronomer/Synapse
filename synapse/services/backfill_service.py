"""
synapse.services.backfill_service — Activity Log → Event Counter Backfill
==========================================================================

One-shot migration utility that reads the legacy ``activity_log`` table and
populates ``event_counters`` so the new counter-based achievement engine
has historical data from day one.

Reference: PLAN_OF_ATTACK_P4.md Task #13

Mapping from legacy ``activity_log.event_type`` to Event Lake types:
    MESSAGE          → message_create
    REACTION_GIVEN   → reaction_add
    REACTION_RECEIVED→ (skipped — no equivalent Event Lake type)
    THREAD_CREATE    → thread_create
    VOICE_TICK       → voice_join  (approximation — each tick ~ one session)
    MANUAL_AWARD     → (skipped — not a natural event)
    ACHIEVEMENT_EARNED → (skipped — not a natural event)

Only the ``lifetime`` period is backfilled; daily and season counters
are left to accumulate organically.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import Engine, func, select, text

from synapse.database.engine import get_session
from synapse.database.models import ActivityLog

logger = logging.getLogger(__name__)

# Map legacy event_types to Event Lake event_types
LEGACY_TYPE_MAP: dict[str, str] = {
    "MESSAGE": "message_create",
    "REACTION_GIVEN": "reaction_add",
    "THREAD_CREATE": "thread_create",
    "VOICE_TICK": "voice_join",
}


def backfill_counters_from_activity_log(
    engine: Engine,
    *,
    dry_run: bool = False,
) -> dict:
    """Aggregate activity_log rows and upsert into event_counters.

    Args:
        engine: SQLAlchemy engine.
        dry_run: If True, compute but don't write. Returns what *would* be written.

    Returns:
        ``{"rows_read": N, "counters_upserted": M, "skipped_types": [...]}``
    """
    skipped_types: set[str] = set()
    upserted = 0
    rows_read = 0

    with get_session(engine) as session:
        # Aggregate legacy events: COUNT per (user_id, event_type)
        q = (
            select(
                ActivityLog.user_id,
                ActivityLog.event_type,
                func.count().label("cnt"),
            )
            .group_by(ActivityLog.user_id, ActivityLog.event_type)
        )
        results = session.execute(q).all()

        for row in results:
            rows_read += 1
            lake_type = LEGACY_TYPE_MAP.get(row.event_type)
            if lake_type is None:
                skipped_types.add(row.event_type)
                continue

            if not dry_run:
                session.execute(
                    text("""
                        INSERT INTO event_counters
                            (user_id, event_type, zone_id, period, count)
                        VALUES (:uid, :etype, 0, 'lifetime', :count)
                        ON CONFLICT (user_id, event_type, zone_id, period)
                        DO UPDATE SET count = GREATEST(
                            event_counters.count,
                            :count
                        )
                    """),
                    {"uid": row.user_id, "etype": lake_type, "count": row.cnt},
                )
            upserted += 1

    action = "would upsert" if dry_run else "upserted"
    logger.info(
        "Backfill: %s %d counters from %d activity_log aggregates "
        "(skipped types: %s)",
        action, upserted, rows_read, sorted(skipped_types),
    )

    return {
        "rows_read": rows_read,
        "counters_upserted": upserted,
        "skipped_types": sorted(skipped_types),
        "dry_run": dry_run,
        "timestamp": datetime.now(UTC).isoformat(),
    }
