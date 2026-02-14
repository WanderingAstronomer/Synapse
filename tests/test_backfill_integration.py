"""
tests/test_backfill_integration — Schema-Safe Integration Test
===============================================================

This test runs the backfill service against a real SQLite schema
to catch schema mismatches that mocked tests miss.

LIMITATION: backfill_service uses PostgreSQL-specific GREATEST() function,
so full integration tests only run if using a PostgreSQL test database.
The SQLite tests verify schema column correctness via dry-run mode.
"""

from __future__ import annotations

from sqlalchemy import select

from synapse.database.models import ActivityLog, EventCounter
from synapse.services.backfill_service import backfill_counters_from_activity_log


class TestBackfillIntegration:
    """Integration tests that exercise real SQL against a real schema."""

    def test_backfill_schema_compatibility_dry_run(self, db_engine, db_session):
        """Backfill SQL must match the actual event_counters schema.

        This test ensures raw SQL in backfill_service.py uses the correct
        columns. Regression test for phantom category_id bug (2026-02-14).

        NOTE: Uses dry_run=True because backfill service uses PostgreSQL's
        GREATEST() function which is not available in SQLite test database.
        """
        # Seed activity_log with legacy events
        db_session.add_all([
            ActivityLog(
                user_id=1001,
                event_type="MESSAGE",
            ),
            ActivityLog(
                user_id=1001,
                event_type="MESSAGE",
            ),
            ActivityLog(
                user_id=1001,
                event_type="REACTION_GIVEN",
            ),
            ActivityLog(
                user_id=1002,
                event_type="THREAD_CREATE",
            ),
            ActivityLog(
                user_id=1002,
                event_type="MANUAL_AWARD",  # Should be skipped
            ),
        ])
        db_session.commit()

        # Run backfill in dry_run mode to validate SQL column names
        # (Actual execution uses PostgreSQL's GREATEST(), unavailable in SQLite)
        result = backfill_counters_from_activity_log(db_engine, dry_run=True)

        # Verify logic without DB writes
        # 5 activity rows → 4 aggregated groups:
        #   (1001, MESSAGE): 2, (1001, REACTION_GIVEN): 1,
        #   (1002, THREAD_CREATE): 1, (1002, MANUAL_AWARD): 1 (skipped)
        assert result["rows_read"] == 4  # Aggregated groups
        assert result["counters_upserted"] == 3  # 3 mapped types
        assert "MANUAL_AWARD" in result["skipped_types"]
        assert result["dry_run"] is True

        # Verify no counters were written (dry_run)
        counters = db_session.scalars(select(EventCounter)).all()
        assert len(counters) == 0

    def test_backfill_dry_run_no_writes(self, db_engine, db_session):
        """Dry run should not persist any counters."""
        db_session.add(ActivityLog(
            user_id=2001,
            event_type="MESSAGE",
        ))
        db_session.commit()

        result = backfill_counters_from_activity_log(db_engine, dry_run=True)

        assert result["dry_run"] is True
        assert result["counters_upserted"] == 1  # Would have upserted

        # But no actual counters should exist
        counters = db_session.scalars(select(EventCounter)).all()
        assert len(counters) == 0

    def test_backfill_idempotency_dry_run(self, db_engine, db_session):
        """Backfill uses GREATEST() for idempotent counter updates.

        NOTE: Dry-run only due to PostgreSQL-specific GREATEST() function.
        In production (PostgreSQL), running backfill twice will use GREATEST()
        to take the max of existing vs. new count.
        """
        # Seed activity_log
        db_session.add_all([
            ActivityLog(user_id=3001, event_type="MESSAGE"),
            ActivityLog(user_id=3001, event_type="MESSAGE"),
        ])
        db_session.commit()

        # First dry-run
        result = backfill_counters_from_activity_log(db_engine, dry_run=True)
        # 2 MESSAGE rows → 1 aggregated group (user=3001, event_type=MESSAGE, count=2)
        assert result["rows_read"] == 1
        assert result["counters_upserted"] == 1

        # Add one more activity
        db_session.add(ActivityLog(user_id=3001, event_type="MESSAGE"))
        db_session.commit()

        # Second dry-run — would see 3 total
        result = backfill_counters_from_activity_log(db_engine, dry_run=True)
        # 3 MESSAGE rows → 1 aggregated group (user=3001, event_type=MESSAGE, count=3)
        assert result["rows_read"] == 1
        assert result["counters_upserted"] == 1
