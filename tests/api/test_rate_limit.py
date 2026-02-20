from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from synapse.api.rate_limit import AdminRateLimiter, AdminRateLimitEvent
from synapse.database.models import Base


@pytest.fixture
def db_engine():
    # Use in-memory SQLite with StaticPool to share connection across threads/sessions
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)


@pytest.fixture
def session(db_engine) -> Generator[Session, None, None]:
    with Session(db_engine) as session:
        yield session


class MockClock:
    def __init__(self):
        self._now = datetime(2023, 1, 1, 12, 0, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self._now

    def tick(self, seconds: int = 1):
        self._now += timedelta(seconds=seconds)


@pytest.fixture
def clock():
    return MockClock()


class TestAdminRateLimiter:
    def test_allow_under_limit(self, db_engine, clock):
        limiter = AdminRateLimiter(
            max_requests=5, window_seconds=60, engine=db_engine, time_provider=clock
        )

        allowed, info = limiter.check("admin1")
        assert allowed is True
        assert info["remaining"] == 5
        assert info["limit"] == 5

    def test_record_increments_count(self, db_engine, clock):
        limiter = AdminRateLimiter(
            max_requests=5, window_seconds=60, engine=db_engine, time_provider=clock
        )

        # Record one request
        limiter.record("admin1")  # Returns info, but checks side effects

        # Check reflects the change
        allowed, check_info = limiter.check("admin1")
        assert allowed is True
        assert check_info["remaining"] == 4

    def test_block_over_limit(self, db_engine, clock):
        limiter = AdminRateLimiter(
            max_requests=2, window_seconds=60, engine=db_engine, time_provider=clock
        )

        limiter.record("admin1")
        limiter.record("admin1")  # Count = 2 (max)

        allowed, info = limiter.check("admin1")
        assert allowed is False
        assert info["remaining"] == 0

        # Verify reset time is calculated correctly relative to the first request
        # 1st request at T=0. Reset should be T=60.
        # Current time is T=0 (clock hasn't moved).
        # Wait, check implementation:
        # oldest = timestamps[0] (T=0)
        # reset = (oldest + window - now).total_seconds()
        # reset = (0 + 60 - 0) = 60.
        assert info["reset"] >= 60

    def test_window_expiration(self, db_engine, clock):
        limiter = AdminRateLimiter(
            max_requests=2, window_seconds=60, engine=db_engine, time_provider=clock
        )

        # T=0: Request 1
        limiter.record("admin1")

        # T=10: Request 2 (Limit reached)
        clock.tick(10)
        limiter.record("admin1")

        # Verify blocked
        allowed, _ = limiter.check("admin1")
        assert allowed is False

        # Move forward to T=61.
        # Request 1 (T=0) expires at T=60.
        # Request 2 (T=10) expires at T=70.
        clock.tick(51)  # Now T=61

        # Should have 1 slot free (Request 1 expired)
        allowed, info = limiter.check("admin1")
        # Count in window [1, 61] is 1 (Request 2 at T=10)
        assert allowed is True
        assert info["remaining"] == 1

    def test_cleanup_removes_old_events(self, db_engine, session, clock):
        limiter = AdminRateLimiter(
            max_requests=10, window_seconds=60, engine=db_engine, time_provider=clock
        )

        # Add events
        limiter.record("admin1")  # T=0

        clock.tick(70)  # T=70
        limiter.record("admin1")  # T=70

        # Run cleanup
        # T=70. Window=60. Cutoff=10.
        # Request at T=0 should be deleted.
        # Request at T=70 should remain.
        deleted = limiter.cleanup()
        assert deleted == 1

        # Verify in DB
        events = session.scalars(select(AdminRateLimitEvent)).all()
        assert len(events) == 1
        # SQLite returns naive datetime; normalize for comparison
        ts = events[0].timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        assert ts == datetime(2023, 1, 1, 12, 1, 10, tzinfo=UTC)

    def test_multiple_admins_distinct(self, db_engine, clock):
        limiter = AdminRateLimiter(
            max_requests=1, window_seconds=60, engine=db_engine, time_provider=clock
        )

        limiter.record("admin1")

        # admin1 blocked
        allowed1, _ = limiter.check("admin1")
        assert allowed1 is False

        # admin2 allowed
        allowed2, _ = limiter.check("admin2")
        assert allowed2 is True

    def test_reset(self, db_engine, clock):
        limiter = AdminRateLimiter(
            max_requests=10, window_seconds=60, engine=db_engine, time_provider=clock
        )

        limiter.record("admin1")
        limiter.record("admin2")

        # Reset specific admin
        limiter.reset("admin1")

        allowed, info = limiter.check("admin1")
        assert info["remaining"] == 10  # Fully reset

        allowed, info = limiter.check("admin2")
        assert info["remaining"] == 9  # Still tracked

        # Reset all
        limiter.reset()
        allowed, info = limiter.check("admin2")
        assert info["remaining"] == 10
