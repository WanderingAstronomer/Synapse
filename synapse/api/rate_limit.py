"""
synapse.api.rate_limit — Per-Admin Mutation Rate Limiting
==========================================================

Implements the admin write-endpoint throttle documented in §7.8 and README:
30 mutations per minute per admin session.

Uses a sliding-window counter keyed by admin user ID (JWT ``sub`` claim).
Returns HTTP 429 with a ``Retry-After`` header when the limit is exceeded.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import Engine, delete, func, select
from sqlalchemy.orm import Session

from synapse.api.deps import get_current_admin, get_engine
from synapse.database.models import AdminRateLimitEvent

logger = logging.getLogger(__name__)

# Default: 30 mutations per 60-second sliding window
DEFAULT_RATE_LIMIT = 30
DEFAULT_WINDOW_SECONDS = 60

# HTTP methods considered "mutations"
_MUTATION_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class AdminRateLimiter:
    """Sliding-window rate limiter keyed by admin user ID.

    DB-backed only — uses the ``admin_rate_limit_events`` table for durable
    state that survives restarts.
    """

    def __init__(
        self,
        max_requests: int = DEFAULT_RATE_LIMIT,
        window_seconds: int = DEFAULT_WINDOW_SECONDS,
        *,
        engine: Engine,
    ) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.engine = engine

    def _normalize_dt(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value

    def check(self, admin_id: str) -> tuple[bool, dict[str, Any]]:
        """Check if the admin is within rate limits.

        Returns (allowed, info) where info contains:
          - remaining: requests remaining in the window
          - reset: seconds until the oldest request expires
          - limit: the max requests per window
        """
        now = datetime.now(UTC)
        cutoff = now - timedelta(seconds=self.window_seconds)

        with Session(self.engine) as session:
            session.execute(
                delete(AdminRateLimitEvent).where(
                    AdminRateLimitEvent.admin_id == admin_id,
                    AdminRateLimitEvent.timestamp < cutoff,
                )
            )

            timestamps = session.scalars(
                select(AdminRateLimitEvent.timestamp)
                .where(AdminRateLimitEvent.admin_id == admin_id)
                .order_by(AdminRateLimitEvent.timestamp.asc())
            ).all()

        count = len(timestamps)
        remaining = max(0, self.max_requests - count)

        if count >= self.max_requests:
            oldest = self._normalize_dt(timestamps[0])
            reset = (oldest + timedelta(seconds=self.window_seconds) - now).total_seconds()
            return False, {
                "remaining": 0,
                "reset": max(1, int(reset) + 1),
                "limit": self.max_requests,
            }

        return True, {
            "remaining": remaining,
            "reset": self.window_seconds,
            "limit": self.max_requests,
        }

    def record(self, admin_id: str) -> dict[str, Any]:
        """Record a successful request and return updated rate-limit info.

        Returns the same info dict as ``check()`` so callers don't need a
        separate round-trip to get remaining counts.
        """
        now = datetime.now(UTC)
        cutoff = now - timedelta(seconds=self.window_seconds)

        with Session(self.engine) as session:
            # Prune expired entries
            session.execute(
                delete(AdminRateLimitEvent).where(
                    AdminRateLimitEvent.admin_id == admin_id,
                    AdminRateLimitEvent.timestamp < cutoff,
                )
            )
            # Record new event
            session.add(AdminRateLimitEvent(admin_id=admin_id))
            session.flush()

            # Count current window (including the one just added)
            count = session.scalar(
                select(func.count()).select_from(
                    select(AdminRateLimitEvent.id)
                    .where(AdminRateLimitEvent.admin_id == admin_id)
                    .subquery()
                )
            ) or 0
            session.commit()

        remaining = max(0, self.max_requests - count)
        return {
            "remaining": remaining,
            "reset": self.window_seconds,
            "limit": self.max_requests,
        }

    def reset(self, admin_id: str | None = None) -> None:
        """Clear rate limit state. If admin_id is None, clear all."""
        with Session(self.engine) as session:
            if admin_id is None:
                session.execute(delete(AdminRateLimitEvent))
            else:
                session.execute(
                    delete(AdminRateLimitEvent).where(
                        AdminRateLimitEvent.admin_id == admin_id
                    )
                )
            session.commit()


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
_limiter: AdminRateLimiter | None = None


def get_rate_limiter() -> AdminRateLimiter:
    """Return the global rate limiter instance."""
    if _limiter is None:
        raise RuntimeError("Rate limiter not configured — call configure_rate_limiter() first")
    return _limiter


def configure_rate_limiter(*, engine: Engine) -> None:
    """Configure the global limiter to use durable DB-backed storage."""
    global _limiter
    _limiter = AdminRateLimiter(
        max_requests=DEFAULT_RATE_LIMIT,
        window_seconds=DEFAULT_WINDOW_SECONDS,
        engine=engine,
    )


# ---------------------------------------------------------------------------
# FastAPI dependency — chains after get_current_admin
# ---------------------------------------------------------------------------
async def rate_limited_admin(
    request: Request,
    admin: dict = Depends(get_current_admin),
    engine: Engine = Depends(get_engine),
) -> dict:
    """Validate the admin JWT *and* enforce per-admin mutation rate limits.

    GET/HEAD/OPTIONS requests pass through without rate-limit checks.
    Mutation methods (POST/PUT/PATCH/DELETE) are counted against the
    sliding-window limit.  Raises HTTP 429 when the limit is exceeded.

    Use ``Depends(rate_limited_admin)`` in place of
    ``Depends(get_current_admin)`` on any admin router.
    """
    if request.method not in _MUTATION_METHODS:
        return admin

    limiter = get_rate_limiter()
    admin_id = admin["sub"]

    allowed, info = await asyncio.to_thread(limiter.check, admin_id)

    if not allowed:
        logger.warning(
            "Rate limit exceeded for admin %s: %d/%d requests in window",
            admin_id, limiter.max_requests, limiter.window_seconds,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "rate_limit_exceeded",
                "message": (
                    f"Rate limit exceeded: {limiter.max_requests}"
                    " mutations per minute."
                ),
                "retry_after": info["reset"],
            },
            headers={"Retry-After": str(info["reset"])},
        )

    # Record the request (fire-and-forget — already allowed)
    await asyncio.to_thread(limiter.record, admin_id)

    return admin
