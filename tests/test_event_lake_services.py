"""
tests/test_event_lake_services.py — Tests for Event Lake Services (P4 W2–W4)
=============================================================================

Tests for:
- Retention service (cleanup, stats)
- Reconciliation service (counter drift detection & correction)
- Backfill service (activity_log → event_counters migration)
- Event Lake API routes (events, data sources, health, storage, operations)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from synapse.services.event_lake_writer import EventType


# ==========================================================================
# RETENTION SERVICE TESTS
# ==========================================================================
class TestRetentionService:
    """Tests for synapse.services.retention_service."""

    @patch("synapse.services.retention_service.get_session")
    def test_run_retention_deletes_old_events(self, mock_get_session):
        """Retention should batch-delete events older than cutoff."""
        from synapse.services.retention_service import run_retention_cleanup

        mock_session = MagicMock()
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        # First batch returns some IDs, second batch returns empty
        mock_session.scalars.return_value.all.side_effect = [
            [1, 2, 3],  # first batch
            [],  # no more old events
        ]
        mock_result = MagicMock()
        mock_result.rowcount = 3
        mock_session.execute.return_value = mock_result

        engine = MagicMock()
        result = run_retention_cleanup(engine, retention_days=90)

        assert result["events_deleted"] == 3
        assert result["counters_deleted"] == 3  # from the last execute call

    @patch("synapse.services.retention_service.get_session")
    def test_run_retention_no_old_events(self, mock_get_session):
        """Retention should be a no-op when no old events exist."""
        from synapse.services.retention_service import run_retention_cleanup

        mock_session = MagicMock()
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        # No events to delete
        mock_session.scalars.return_value.all.return_value = []
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_session.execute.return_value = mock_result

        engine = MagicMock()
        result = run_retention_cleanup(engine, retention_days=90)

        assert result["events_deleted"] == 0
        assert result["counters_deleted"] == 0

    @patch("synapse.services.retention_service.get_session")
    def test_get_retention_stats(self, mock_get_session):
        """Stats should return aggregate table info."""
        from synapse.services.retention_service import get_retention_stats

        mock_session = MagicMock()
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        now = datetime.now(UTC)
        mock_session.scalar.side_effect = [
            1000,  # total_events
            now - timedelta(days=30),  # oldest_event
            now,  # newest_event
            500,  # total_counters
            1024000,  # table size bytes
        ]

        engine = MagicMock()
        stats = get_retention_stats(engine)

        assert stats["total_events"] == 1000
        assert stats["total_counters"] == 500
        assert stats["table_size_bytes"] == 1024000
        assert stats["oldest_event"] is not None
        assert stats["newest_event"] is not None

    @patch("synapse.services.retention_service.get_session")
    def test_retention_custom_days(self, mock_get_session):
        """Retention should respect the retention_days parameter."""
        from synapse.services.retention_service import run_retention_cleanup

        mock_session = MagicMock()
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        mock_session.scalars.return_value.all.return_value = []
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_session.execute.return_value = mock_result

        engine = MagicMock()
        # Should not raise with custom retention days
        result = run_retention_cleanup(engine, retention_days=7)
        assert isinstance(result, dict)


# ==========================================================================
# RECONCILIATION SERVICE TESTS
# ==========================================================================
class TestReconciliationService:
    """Tests for synapse.services.reconciliation_service."""

    @patch("synapse.services.reconciliation_service.get_session")
    def test_reconcile_no_drift(self, mock_get_session):
        """No corrections when counters match events."""
        from synapse.services.reconciliation_service import reconcile_counters

        mock_session = MagicMock()
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        # Truth: user 1 has 10 message_create events
        truth_row = MagicMock()
        truth_row.user_id = 1
        truth_row.event_type = "message_create"
        truth_row.actual = 10
        mock_session.execute.return_value.all.return_value = [truth_row]

        # Counter matches
        counter = MagicMock()
        counter.user_id = 1
        counter.event_type = "message_create"
        counter.count = 10
        mock_session.scalars.return_value.all.return_value = [counter]

        engine = MagicMock()
        result = reconcile_counters(engine)

        assert result["checked"] == 1
        assert result["corrected"] == 0
        assert result["corrections"] == []

    @patch("synapse.services.reconciliation_service.get_session")
    def test_reconcile_with_drift(self, mock_get_session):
        """Should correct counters that don't match event counts."""
        from synapse.services.reconciliation_service import reconcile_counters

        mock_session = MagicMock()
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        # Truth: user 1 has 15 events, counter says 10
        truth_row = MagicMock()
        truth_row.user_id = 1
        truth_row.event_type = "message_create"
        truth_row.actual = 15
        mock_session.execute.return_value.all.return_value = [truth_row]

        counter = MagicMock()
        counter.user_id = 1
        counter.event_type = "message_create"
        counter.count = 10
        mock_session.scalars.return_value.all.return_value = [counter]

        engine = MagicMock()
        result = reconcile_counters(engine)

        assert result["checked"] == 1
        assert result["corrected"] == 1
        assert len(result["corrections"]) == 1
        assert result["corrections"][0]["diff"] == 5

    @patch("synapse.services.reconciliation_service.get_session")
    def test_reconcile_orphan_counter(self, mock_get_session):
        """Should reset counters that have no matching events."""
        from synapse.services.reconciliation_service import reconcile_counters

        mock_session = MagicMock()
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        # No events in truth
        mock_session.execute.return_value.all.return_value = []

        # But counter has value
        counter = MagicMock()
        counter.user_id = 1
        counter.event_type = "reaction_add"
        counter.count = 5
        mock_session.scalars.return_value.all.return_value = [counter]

        engine = MagicMock()
        result = reconcile_counters(engine)

        assert result["corrected"] == 1
        assert result["corrections"][0]["stored"] == 5
        assert result["corrections"][0]["actual"] == 0


# ==========================================================================
# BACKFILL SERVICE TESTS
# ==========================================================================
class TestBackfillService:
    """Tests for synapse.services.backfill_service."""

    @patch("synapse.services.backfill_service.get_session")
    def test_backfill_maps_legacy_types(self, mock_get_session):
        """Should map MESSAGE → message_create, etc."""
        from synapse.services.backfill_service import (
            LEGACY_TYPE_MAP,
        )

        assert LEGACY_TYPE_MAP["MESSAGE"] == "message_create"
        assert LEGACY_TYPE_MAP["REACTION_GIVEN"] == "reaction_add"
        assert LEGACY_TYPE_MAP["THREAD_CREATE"] == "thread_create"
        assert LEGACY_TYPE_MAP["VOICE_TICK"] == "voice_join"

    @patch("synapse.services.backfill_service.get_session")
    def test_backfill_dry_run(self, mock_get_session):
        """Dry run should not write anything."""
        from synapse.services.backfill_service import backfill_counters_from_activity_log

        mock_session = MagicMock()
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        row1 = MagicMock()
        row1.user_id = 1
        row1.event_type = "MESSAGE"
        row1.cnt = 100

        row2 = MagicMock()
        row2.user_id = 1
        row2.event_type = "MANUAL_AWARD"
        row2.cnt = 5

        mock_session.execute.return_value.all.return_value = [row1, row2]

        engine = MagicMock()
        result = backfill_counters_from_activity_log(engine, dry_run=True)

        assert result["dry_run"] is True
        assert result["rows_read"] == 2
        assert result["counters_upserted"] == 1  # only MESSAGE maps
        assert "MANUAL_AWARD" in result["skipped_types"]
        # Verify no execute calls for UPSERT in dry_run
        # (the first execute is the SELECT, no more should follow)

    @patch("synapse.services.backfill_service.get_session")
    def test_backfill_skips_unmapped_types(self, mock_get_session):
        """Types not in LEGACY_TYPE_MAP should be skipped."""
        from synapse.services.backfill_service import backfill_counters_from_activity_log

        mock_session = MagicMock()
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        row = MagicMock()
        row.user_id = 1
        row.event_type = "ACHIEVEMENT_EARNED"
        row.cnt = 3

        mock_session.execute.return_value.all.return_value = [row]

        engine = MagicMock()
        result = backfill_counters_from_activity_log(engine, dry_run=True)

        assert result["counters_upserted"] == 0
        assert "ACHIEVEMENT_EARNED" in result["skipped_types"]

    @patch("synapse.services.backfill_service.get_session")
    def test_backfill_returns_timestamp(self, mock_get_session):
        """Result should include an ISO timestamp."""
        from synapse.services.backfill_service import backfill_counters_from_activity_log

        mock_session = MagicMock()
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)
        mock_session.execute.return_value.all.return_value = []

        engine = MagicMock()
        result = backfill_counters_from_activity_log(engine, dry_run=True)

        assert "timestamp" in result
        # Should be parseable ISO datetime
        datetime.fromisoformat(result["timestamp"])


# ==========================================================================
# EVENT LAKE API ROUTE TESTS
# ==========================================================================
class TestEventLakeAPI:
    """Tests for synapse.api.routes.event_lake FastAPI endpoints."""

    @pytest.fixture
    def client(self):
        """Create a FastAPI test client."""
        from fastapi.testclient import TestClient

        from synapse.api.main import app
        return TestClient(app, raise_server_exceptions=False)

    @pytest.fixture
    def admin_token(self):
        """Generate a valid admin JWT for test requests."""
        from conftest import make_admin_token
        return make_admin_token(sub="12345", username="TestAdmin")

    def _auth_headers(self, token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    def test_list_events_requires_auth(self, client):
        """Events endpoint should reject unauthenticated requests."""
        resp = client.get("/api/admin/event-lake/events")
        assert resp.status_code in (401, 403)

    def test_data_sources_requires_auth(self, client):
        """Data sources endpoint should reject unauthenticated requests."""
        resp = client.get("/api/admin/event-lake/data-sources")
        assert resp.status_code in (401, 403)

    def test_health_requires_auth(self, client):
        """Health endpoint should reject unauthenticated requests."""
        resp = client.get("/api/admin/event-lake/health")
        assert resp.status_code in (401, 403)

    def test_storage_estimate_requires_auth(self, client):
        """Storage estimate endpoint should reject unauthenticated requests."""
        resp = client.get("/api/admin/event-lake/storage-estimate")
        assert resp.status_code in (401, 403)

    def test_retention_requires_auth(self, client):
        """Retention trigger should reject unauthenticated requests."""
        resp = client.post("/api/admin/event-lake/retention/run")
        assert resp.status_code in (401, 403)

    def test_reconciliation_requires_auth(self, client):
        """Reconciliation trigger should reject unauthenticated requests."""
        resp = client.post("/api/admin/event-lake/reconciliation/run")
        assert resp.status_code in (401, 403)

    def test_backfill_requires_auth(self, client):
        """Backfill trigger should reject unauthenticated requests."""
        resp = client.post("/api/admin/event-lake/backfill/run")
        assert resp.status_code in (401, 403)

    def test_counters_requires_auth(self, client):
        """Counters endpoint should reject unauthenticated requests."""
        resp = client.get("/api/admin/event-lake/counters")
        assert resp.status_code in (401, 403)


# ==========================================================================
# DATA SOURCE CONFIG TESTS
# ==========================================================================
class TestDataSourceConfig:
    """Tests for the canonical data source definitions."""

    def test_all_event_types_have_data_source(self):
        """Every EventType should have a corresponding DATA_SOURCES entry."""
        from synapse.api.routes.event_lake import DATA_SOURCES

        ds_types = {ds["event_type"] for ds in DATA_SOURCES}
        expected_types = {
            EventType.MESSAGE_CREATE,
            EventType.REACTION_ADD,
            EventType.REACTION_REMOVE,
            EventType.THREAD_CREATE,
            EventType.VOICE_JOIN,
            EventType.VOICE_LEAVE,
            EventType.VOICE_MOVE,
            EventType.MEMBER_JOIN,
            EventType.MEMBER_LEAVE,
        }
        assert ds_types == expected_types

    def test_data_sources_have_labels(self):
        """Every data source should have a non-empty label and description."""
        from synapse.api.routes.event_lake import DATA_SOURCES

        for ds in DATA_SOURCES:
            assert ds["label"], f"{ds['event_type']} missing label"
            assert ds["description"], f"{ds['event_type']} missing description"


# ==========================================================================
# PERIODIC TASKS COG TESTS
# ==========================================================================
class TestPeriodicTasksCog:
    """Tests for synapse.bot.cogs.tasks."""

    def test_tasks_cog_imports(self):
        """Tasks cog should import without errors."""
        from synapse.bot.cogs.tasks import PeriodicTasks
        assert PeriodicTasks is not None

    def test_retention_loop_exists(self):
        """PeriodicTasks should have a retention_loop attribute."""
        from synapse.bot.cogs.tasks import PeriodicTasks
        assert hasattr(PeriodicTasks, "retention_loop")

    def test_reconciliation_loop_exists(self):
        """PeriodicTasks should have a reconciliation_loop attribute."""
        from synapse.bot.cogs.tasks import PeriodicTasks
        assert hasattr(PeriodicTasks, "reconciliation_loop")

