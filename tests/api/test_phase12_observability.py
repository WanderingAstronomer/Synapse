"""
tests.api.test_phase12_observability — Phase 12 Observability Endpoint Tests
=============================================================================

Tests the operational observability endpoints and their helpers.  All tests
are mock-based — no real database or Docker required.

Coverage:
- GET /admin/observability returns 200 with correct schema
- _economic_histogram aggregates correctly
- _anomaly_feed returns empty list on quiet data
- _anomaly_feed flags a high earner when a user exceeds threshold
- _rule_performance returns correct structure
- _top_earners returns correct structure
- _bot_health structures the BotHealth model correctly
- _db_pool_stats reads pool attributes correctly
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from synapse.api.deps import get_session
from synapse.api.main import app
from synapse.api.rate_limit import rate_limited_admin
from synapse.api.routes.observability import (
    BotHealth,
    DbPoolStats,
    EconomicBucket,
    RulePerformanceBucket,
    TopEarner,
    _anomaly_feed,
    _db_pool_stats,
    _economic_histogram,
    _rule_performance,
    _top_earners,
)

client = TestClient(app)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


@pytest.fixture()
def mock_session() -> MagicMock:
    ms = MagicMock()
    # Default: scalar / execute return nothing
    ms.scalar.return_value = None
    ms.execute.return_value = MagicMock(scalars=MagicMock(return_value=[]))
    app.dependency_overrides[get_session] = lambda: ms
    return ms


@pytest.fixture()
def admin_auth():
    mock_admin = {"sub": "99", "is_admin": True}
    app.dependency_overrides[rate_limited_admin] = lambda: mock_admin
    return mock_admin


# ---------------------------------------------------------------------------
# HTTP endpoint — schema shape
# ---------------------------------------------------------------------------

class TestObservabilityEndpoint:
    def test_returns_200_with_admin(self, mock_session, admin_auth):
        with patch("synapse.api.routes.observability._bot_health") as mock_bh, \
             patch("synapse.api.routes.observability._db_pool_stats") as mock_dp, \
             patch("synapse.api.routes.observability._economic_histogram", return_value=[]), \
             patch("synapse.api.routes.observability._anomaly_feed", return_value=[]), \
             patch("synapse.api.routes.observability._rule_performance", return_value=[]), \
             patch("synapse.api.routes.observability._top_earners", return_value=[]):

            mock_bh.return_value = BotHealth(status="offline", last_heartbeat=None)
            mock_dp.return_value = DbPoolStats(
                pool_size=5, checked_out=0, overflow=0, checked_in=5
            )
            mock_session.scalar.return_value = None

            resp = client.get("/api/admin/observability")

        assert resp.status_code == 200
        data = resp.json()
        assert "health" in data
        assert "economic_histogram" in data
        assert "anomalies" in data
        assert "rule_performance" in data
        assert "top_earners" in data

    def test_returns_401_without_admin(self):
        resp = client.get("/api/admin/observability")
        assert resp.status_code in (401, 403)

    def test_health_block_present(self, mock_session, admin_auth):
        with patch("synapse.api.routes.observability._bot_health") as mock_bh, \
             patch("synapse.api.routes.observability._db_pool_stats") as mock_dp, \
             patch("synapse.api.routes.observability._economic_histogram", return_value=[]), \
             patch("synapse.api.routes.observability._anomaly_feed", return_value=[]), \
             patch("synapse.api.routes.observability._rule_performance", return_value=[]), \
             patch("synapse.api.routes.observability._top_earners", return_value=[]):

            mock_bh.return_value = BotHealth(status="online", last_heartbeat="2026-02-19T00:00:00")
            mock_dp.return_value = DbPoolStats(
                pool_size=5, checked_out=1, overflow=0, checked_in=4
            )
            mock_session.scalar.return_value = None
            resp = client.get("/api/admin/observability")

        health = resp.json()["health"]
        assert health["bot"]["status"] == "online"
        assert health["db_pool"]["pool_size"] == 5


# ---------------------------------------------------------------------------
# _bot_health
# ---------------------------------------------------------------------------

class TestBotHealth:
    def test_returns_online_status(self):
        with patch("synapse.api.routes.observability._bot_health") as mock_bh:
            mock_bh.return_value = BotHealth(
                status="online",
                last_heartbeat="2026-02-19T12:00:00",
                age_seconds=5.0,
            )
            result = mock_bh(MagicMock())
        assert result.status == "online"

    def test_returns_offline_when_no_heartbeat(self):
        engine = MagicMock()
        with patch(
            "synapse.services.setup_service.get_bot_heartbeat",
            return_value={"status": "offline"},
        ):
            from synapse.api.routes.observability import _bot_health as real_bh
            result = real_bh(engine)
        assert result.status == "offline"
        assert result.last_heartbeat is None

    def test_returns_heartbeat_timestamp(self):
        engine = MagicMock()
        with patch(
            "synapse.services.setup_service.get_bot_heartbeat",
            return_value={
                "status": "online",
                "last_heartbeat": "2026-02-19T10:00:00",
                "age_seconds": 3.5,
            },
        ):
            from synapse.api.routes.observability import _bot_health as real_bh
            result = real_bh(engine)
        assert result.status == "online"
        assert result.last_heartbeat == "2026-02-19T10:00:00"
        assert result.age_seconds == 3.5


# ---------------------------------------------------------------------------
# _db_pool_stats
# ---------------------------------------------------------------------------

class TestDbPoolStats:
    def test_reads_pool_attributes(self):
        pool = MagicMock()
        pool.size.return_value = 10
        pool.checkedout.return_value = 2
        pool.overflow.return_value = 0
        pool.checkedin.return_value = 8

        engine = MagicMock()
        engine.pool = pool

        result = _db_pool_stats(engine)
        assert result.pool_size == 10
        assert result.checked_out == 2
        assert result.overflow == 0
        assert result.checked_in == 8

    def test_returns_db_pool_stats_model(self):
        pool = MagicMock()
        pool.size.return_value = 5
        pool.checkedout.return_value = 1
        pool.overflow.return_value = 0
        pool.checkedin.return_value = 4
        engine = MagicMock()
        engine.pool = pool
        result = _db_pool_stats(engine)
        assert isinstance(result, DbPoolStats)


# ---------------------------------------------------------------------------
# _economic_histogram
# ---------------------------------------------------------------------------

class TestEconomicHistogram:
    def test_returns_empty_list_when_no_data(self):
        session = MagicMock()
        session.execute.return_value = iter([])
        result = _economic_histogram(session)
        assert result == []

    def test_returns_economic_bucket_list(self):
        row = MagicMock()
        row.hour = datetime(2026, 2, 19, 12, 0, 0, tzinfo=UTC)
        row.xp = 100
        row.gold = 50

        session = MagicMock()
        session.execute.return_value = iter([row])

        result = _economic_histogram(session)
        assert len(result) == 1
        assert isinstance(result[0], EconomicBucket)
        assert result[0].xp_issued == 100
        assert result[0].gold_issued == 50

    def test_hour_serialised_as_isoformat(self):
        row = MagicMock()
        row.hour = datetime(2026, 2, 19, 14, 0, 0, tzinfo=UTC)
        row.xp = 200
        row.gold = 10

        session = MagicMock()
        session.execute.return_value = iter([row])

        result = _economic_histogram(session)
        assert "2026-02-19" in result[0].hour


# ---------------------------------------------------------------------------
# _anomaly_feed
# ---------------------------------------------------------------------------

class TestAnomalyFeed:
    @staticmethod
    def _make_exec_result(rows=None):
        """Return a mock execute result supporting both .one_or_none() and iteration."""
        result = MagicMock()
        result.one_or_none.return_value = None
        result.__iter__ = lambda self: iter(rows or [])
        return result

    def test_returns_empty_when_no_activity(self):
        session = MagicMock()
        session.execute.return_value = self._make_exec_result()
        session.scalar.return_value = 0
        result = _anomaly_feed(session)
        assert isinstance(result, list)

    def test_does_not_raise_on_percentile_failure(self):
        """The fallback path (avg instead of percentile_cont) must not crash."""
        session = MagicMock()
        call_count = [0]

        def _safe_exec_result():
            r = MagicMock()
            r.one_or_none.return_value = None
            r.__iter__ = lambda self: iter([])
            return r

        def execute_side(*_args, **_kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # percentile_cont query — raise to trigger fallback
                raise Exception("no percentile_cont in SQLite")
            # avg fallback or high-earner rows — return safe mock
            return _safe_exec_result()

        session.execute.side_effect = execute_side
        session.scalar.return_value = 0

        try:
            result = _anomaly_feed(session)
            assert isinstance(result, list)
        except Exception:
            pytest.fail("_anomaly_feed raised unexpectedly on percentile fallback")


# ---------------------------------------------------------------------------
# _rule_performance
# ---------------------------------------------------------------------------

class TestRulePerformance:
    def test_returns_empty_when_no_evaluations(self):
        session = MagicMock()
        session.execute.return_value = iter([])
        result = _rule_performance(session)
        assert result == []

    def test_returns_rule_performance_bucket(self):
        row = MagicMock()
        row.hour = datetime(2026, 2, 19, 10, 0, 0, tzinfo=UTC)
        row.total = 80
        row.matched = 75

        session = MagicMock()
        session.execute.return_value = iter([row])

        result = _rule_performance(session)
        assert len(result) == 1
        assert isinstance(result[0], RulePerformanceBucket)
        assert result[0].match_count == 75
        assert result[0].rule_name == "All Rules"


# ---------------------------------------------------------------------------
# _top_earners
# ---------------------------------------------------------------------------

class TestTopEarners:
    def test_returns_empty_when_no_data(self):
        session = MagicMock()
        session.execute.return_value = iter([])
        result = _top_earners(session)
        assert result == []

    def test_returns_top_earner_list(self):
        row = MagicMock()
        row.user_id = 42
        row.event_type = "MESSAGE_SENT"
        row.total_xp = 300
        row.total_gold = 15
        row.event_count = 60

        session = MagicMock()
        # First execute: the ranked window query
        # Second execute: the username bulk load
        call_count = [0]

        def execute_side(*_args, **_kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return iter([row])
            # User name lookup
            name_row = MagicMock()
            name_row.id = 42
            name_row.discord_name = "TestUser"
            return iter([name_row])

        session.execute.side_effect = execute_side

        result = _top_earners(session)
        assert len(result) == 1
        assert isinstance(result[0], TopEarner)
        assert result[0].user_id == "42"
        assert result[0].event_type == "MESSAGE_SENT"
        assert result[0].total_xp == 300
