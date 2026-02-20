"""
tests.test_projection_service — Unit Tests for the Projection Pipeline
=======================================================================

Tests the pure/mockable parts of the projection service:
- _apply_outcomes: XP/gold are accumulated correctly on a User stub
- replay_projection: result dict aggregation is correct
- ProjectionWorker: start/stop lifecycle respects the stop event

No database, no Discord, no Docker required.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from synapse.services.projection_service import (
    BATCH_SIZE,
    MAX_LOOP_ITERATIONS,
    POLL_INTERVAL_SEC,
    WORKER_ID,
    ProjectionWorker,
    _apply_outcomes,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(xp: int = 0, gold: int = 0, level: int = 1) -> SimpleNamespace:
    """Lightweight stand-in for a User ORM row."""
    return SimpleNamespace(id=42, xp=xp, gold=gold, level=level)


def _one_tick() -> asyncio.Future:  # type: ignore[type-arg]
    """Yield exactly one event-loop tick without calling asyncio.sleep."""
    loop = asyncio.get_event_loop()
    fut: asyncio.Future[None] = loop.create_future()
    loop.call_soon(fut.set_result, None)
    return fut


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestConstants:
    def test_batch_size_is_sane(self):
        assert 10 <= BATCH_SIZE <= 1000

    def test_poll_interval_positive(self):
        assert POLL_INTERVAL_SEC > 0

    def test_max_loop_iterations_large(self):
        assert MAX_LOOP_ITERATIONS >= 1_000

    def test_worker_id_non_empty(self):
        assert WORKER_ID and isinstance(WORKER_ID, str)


# ---------------------------------------------------------------------------
# _apply_outcomes
# ---------------------------------------------------------------------------


class TestApplyOutcomes:
    def test_xp_accumulated(self):
        user = _make_user()
        session = MagicMock()

        with patch(
            "synapse.services.projection_service.get_active_season",
            return_value=None,
        ):
            _apply_outcomes(session, user, {"xp": 15, "gold": 0}, guild_id=1000)

        assert user.xp == 15

    def test_gold_accumulated(self):
        user = _make_user(gold=5)
        session = MagicMock()

        with patch(
            "synapse.services.projection_service.get_active_season",
            return_value=None,
        ):
            _apply_outcomes(session, user, {"xp": 0, "gold": 10}, guild_id=1000)

        assert user.gold == 15

    def test_zero_outcomes_no_change(self):
        user = _make_user(xp=100, gold=50)
        session = MagicMock()

        with patch(
            "synapse.services.projection_service.get_active_season",
            return_value=None,
        ):
            _apply_outcomes(session, user, {"xp": 0, "gold": 0}, guild_id=1000)

        assert user.xp == 100
        assert user.gold == 50

    def test_xp_and_gold_accumulated_together(self):
        user = _make_user(xp=10, gold=3)
        session = MagicMock()

        with patch(
            "synapse.services.projection_service.get_active_season",
            return_value=None,
        ):
            _apply_outcomes(session, user, {"xp": 5, "gold": 2}, guild_id=1000)

        assert user.xp == 15
        assert user.gold == 5

    def test_missing_keys_default_to_zero(self):
        """outcomes dict may omit keys — missing ones default to 0."""
        user = _make_user(xp=50)
        session = MagicMock()

        with patch(
            "synapse.services.projection_service.get_active_season",
            return_value=None,
        ):
            _apply_outcomes(session, user, {}, guild_id=1000)

        assert user.xp == 50  # unchanged


# ---------------------------------------------------------------------------
# ProjectionWorker lifecycle
# ---------------------------------------------------------------------------


class TestProjectionWorkerLifecycle:
    def test_start_creates_task(self):
        worker = ProjectionWorker()
        mock_engine = MagicMock()
        mock_cache = MagicMock()
        mock_cache.get_bool.return_value = False

        async def run():
            sleep_mock = "synapse.services.projection_service.asyncio.sleep"
            with patch(sleep_mock, side_effect=lambda _d: _one_tick()):
                worker.start(mock_engine, mock_cache, guild_id=1000)
                assert worker._task is not None
                assert not worker._task.done()
                await worker.stop()

        asyncio.run(run())

    def test_stop_is_idempotent(self):
        worker = ProjectionWorker()

        async def run():
            # stop before start — should not raise
            await worker.stop()
            await worker.stop()

        asyncio.run(run())

    def test_double_start_ignored(self):
        worker = ProjectionWorker()
        mock_engine = MagicMock()
        mock_cache = MagicMock()
        mock_cache.get_bool.return_value = False

        async def run():
            sleep_mock = "synapse.services.projection_service.asyncio.sleep"
            with patch(sleep_mock, side_effect=lambda _d: _one_tick()):
                worker.start(mock_engine, mock_cache, guild_id=1000)
                task_before = worker._task
                worker.start(mock_engine, mock_cache, guild_id=1000)  # second call
                task_after = worker._task
                assert task_before is task_after  # same task, not replaced
                await worker.stop()

        asyncio.run(run())

    def test_stop_signals_run_loop(self):
        """The worker loop exits promptly when stop() is called."""
        worker = ProjectionWorker()
        mock_engine = MagicMock()
        mock_cache = MagicMock()
        mock_cache.get_bool.return_value = False  # flag off → sleeps

        async def run():
            sleep_mock = "synapse.services.projection_service.asyncio.sleep"
            with patch(sleep_mock, side_effect=lambda _d: _one_tick()):
                worker.start(mock_engine, mock_cache, guild_id=1000)
                # Give the loop one tick to enter its first sleep
                await _one_tick()
                await worker.stop()
                assert worker._task is None

        asyncio.run(run())

    def test_worker_calls_process_batch_when_flag_on(self):
        """When flag is enabled, _process_batch is called via run_db."""
        worker = ProjectionWorker()
        mock_engine = MagicMock()
        mock_cache = MagicMock()
        mock_cache.get_bool.return_value = True  # flag ON

        call_count = 0

        async def fake_run_db(fn, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            worker._stop_event.set()  # stop after the first batch
            return 0  # empty batch (triggers sleep path)

        async def run():
            with (
                patch(
                    "synapse.services.projection_service.run_db",
                    side_effect=fake_run_db,
                ),
                patch(
                    "synapse.services.projection_service.asyncio.sleep",
                    side_effect=lambda _d: _one_tick(),
                ),
            ):
                worker.start(mock_engine, mock_cache, guild_id=1000)
                await asyncio.wait_for(worker._task, timeout=2.0)

        asyncio.run(run())
        assert call_count >= 1

    def test_worker_does_not_call_process_batch_when_flag_off(self):
        """When flag is disabled, _process_batch must never be called."""
        worker = ProjectionWorker()
        mock_engine = MagicMock()
        mock_cache = MagicMock()
        mock_cache.get_bool.return_value = False  # flag OFF

        call_count = 0

        async def fake_run_db(fn, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            return 0

        iterations = 0

        def _stop_after_one(_delay):
            nonlocal iterations
            iterations += 1
            if iterations >= 1:
                worker._stop_event.set()  # signal stop on first sleep
            return _one_tick()

        async def run():
            with (
                patch(
                    "synapse.services.projection_service.run_db",
                    side_effect=fake_run_db,
                ),
                patch(
                    "synapse.services.projection_service.asyncio.sleep",
                    side_effect=_stop_after_one,
                ),
            ):
                worker.start(mock_engine, mock_cache, guild_id=1000)
                await asyncio.wait_for(worker._task, timeout=2.0)

        asyncio.run(run())
        assert call_count == 0


# ---------------------------------------------------------------------------
# replay_projection result shape
# ---------------------------------------------------------------------------


class TestReplayProjectionShape:
    def test_empty_result_structure(self):
        """replay_projection returns expected keys even for empty input."""
        mock_engine = MagicMock()

        # Patch Session to return no evaluations
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_session.scalars.return_value.all.return_value = []

        with patch(
            "synapse.services.projection_service.Session",
            return_value=mock_session,
        ):
            from synapse.services.projection_service import replay_projection

            result = replay_projection(mock_engine)

        assert "rows_read" in result
        assert "by_user" in result
        assert result["rows_read"] == 0
        assert result["by_user"] == {}

    def test_aggregation_sums_per_user(self):
        """Multiple evaluations for the same user sum correctly."""
        from synapse.services.projection_service import replay_projection

        mock_engine = MagicMock()
        ev1 = SimpleNamespace(id=1, user_id=10, outcomes_applied={"xp": 15, "gold": 0})
        ev2 = SimpleNamespace(id=2, user_id=10, outcomes_applied={"xp": 5, "gold": 2})
        ev3 = SimpleNamespace(id=3, user_id=20, outcomes_applied={"xp": 10, "gold": 0})

        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_session.scalars.return_value.all.return_value = [ev1, ev2, ev3]

        with patch(
            "synapse.services.projection_service.Session",
            return_value=mock_session,
        ):
            result = replay_projection(mock_engine)

        assert result["rows_read"] == 3
        assert result["by_user"][10] == {"xp": 20, "gold": 2}
        assert result["by_user"][20] == {"xp": 10, "gold": 0}
