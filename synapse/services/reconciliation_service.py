"""
synapse.services.reconciliation_service — Counter Reconciliation
=================================================================

Weekly job that validates ``event_counters`` against raw ``event_lake`` rows
and corrects drift if found.

How it works:
    1. Query ``COUNT(*)`` from ``event_lake`` grouped by (user_id, event_type)
       for the current 'lifetime' period.
    2. Compare against the stored ``event_counters`` row for period='lifetime'.
    3. If there is a mismatch, overwrite the counter with the true count.
    4. Log all corrections for audit.

Daily counters (``day:YYYY-MM-DD``) are NOT reconciled because they share
the same retention window as the raw events — once pruned, neither source
can be authoritative.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import Engine, func, select, text

from synapse.database.engine import get_session
from synapse.database.models import EventCounter, EventLake

logger = logging.getLogger(__name__)


def reconcile_counters(engine: Engine) -> dict:
    """Validate lifetime counters against raw event_lake and fix drift.

    Returns ``{"checked": N, "corrected": M, "corrections": [...]}``.
    """
    corrections: list[dict] = []

    with get_session(engine) as session:
        # Ground truth: COUNT(*) per (user_id, event_type) from raw events
        truth_q = (
            select(
                EventLake.user_id,
                EventLake.event_type,
                func.count().label("actual"),
            )
            .group_by(EventLake.user_id, EventLake.event_type)
        )
        truth_rows = session.execute(truth_q).all()
        truth_map: dict[tuple[int, str], int] = {
            (row.user_id, row.event_type): row.actual
            for row in truth_rows
        }

        # Current counters for period='lifetime'
        counter_q = (
            select(EventCounter)
            .where(EventCounter.period == "lifetime")
        )
        counter_rows = session.scalars(counter_q).all()
        counter_map: dict[tuple[int, str], EventCounter] = {
            (c.user_id, c.event_type): c for c in counter_rows
        }

        checked = 0

        # Check each truth entry against stored counter
        for (user_id, event_type), actual in truth_map.items():
            checked += 1
            counter = counter_map.get((user_id, event_type))
            stored = counter.count if counter else 0

            if stored != actual:
                diff = actual - stored
                corrections.append({
                    "user_id": user_id,
                    "event_type": event_type,
                    "stored": stored,
                    "actual": actual,
                    "diff": diff,
                })

                # Upsert correct value
                session.execute(
                    text("""
                        INSERT INTO event_counters
                            (user_id, event_type, period, count)
                        VALUES (:uid, :etype, 'lifetime', :count)
                        ON CONFLICT (user_id, event_type, period)
                        DO UPDATE SET count = :count
                    """),
                    {"uid": user_id, "etype": event_type, "count": actual},
                )

        # Also check for counters that have no matching events (orphans)
        for (user_id, event_type), counter in counter_map.items():
            if (user_id, event_type) not in truth_map and counter.count != 0:
                checked += 1
                corrections.append({
                    "user_id": user_id,
                    "event_type": event_type,
                    "stored": counter.count,
                    "actual": 0,
                    "diff": -counter.count,
                })
                session.execute(
                    text("""
                        UPDATE event_counters
                        SET count = 0
                        WHERE user_id = :uid
                          AND event_type = :etype
                          AND period = 'lifetime'
                    """),
                    {"uid": user_id, "etype": event_type},
                )

    if corrections:
        logger.warning(
            "Counter reconciliation: corrected %d/%d counters: %s",
            len(corrections), checked, corrections,
        )
    else:
        logger.info("Counter reconciliation: all %d counters match", checked)

    return {
        "checked": checked,
        "corrected": len(corrections),
        "corrections": corrections,
        "timestamp": datetime.now(UTC).isoformat(),
    }
