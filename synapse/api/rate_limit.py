"""
synapse.api.rate_limit — Per-Admin Mutation Rate Limiting
==========================================================

Implements the admin write-endpoint throttle documented in §7.8 and README:
30 mutations per minute per admin session.

Uses a sliding-window counter keyed by admin user ID (JWT ``sub`` claim).
Returns HTTP 429 with a ``Retry-After`` header when the limit is exceeded.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict
from typing import Any

from fastapi import Request, status
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)

# Default: 30 mutations per 60-second sliding window
DEFAULT_RATE_LIMIT = 30
DEFAULT_WINDOW_SECONDS = 60

# HTTP methods considered "mutations"
_MUTATION_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class AdminRateLimiter:
    """Sliding-window rate limiter keyed by admin user ID.

    Thread-safe — safe for use in both sync and async contexts.
    """

    def __init__(
        self,
        max_requests: int = DEFAULT_RATE_LIMIT,
        window_seconds: int = DEFAULT_WINDOW_SECONDS,
    ) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._lock = threading.Lock()
        # admin_id → list of request timestamps
        self._requests: dict[str, list[float]] = defaultdict(list)

    def _prune(self, admin_id: str, now: float) -> None:
        """Remove timestamps outside the current window."""
        cutoff = now - self.window_seconds
        timestamps = self._requests[admin_id]
        # Find the first index within the window
        idx = 0
        while idx < len(timestamps) and timestamps[idx] < cutoff:
            idx += 1
        if idx:
            self._requests[admin_id] = timestamps[idx:]

    def check(self, admin_id: str) -> tuple[bool, dict[str, Any]]:
        """Check if the admin is within rate limits.

        Returns (allowed, info) where info contains:
          - remaining: requests remaining in the window
          - reset: seconds until the oldest request expires
          - limit: the max requests per window
        """
        now = time.monotonic()
        with self._lock:
            self._prune(admin_id, now)
            count = len(self._requests[admin_id])
            remaining = max(0, self.max_requests - count)

            if count >= self.max_requests:
                oldest = self._requests[admin_id][0]
                reset = self.window_seconds - (now - oldest)
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

    def record(self, admin_id: str) -> None:
        """Record a successful request."""
        now = time.monotonic()
        with self._lock:
            self._requests[admin_id].append(now)

    def reset(self, admin_id: str | None = None) -> None:
        """Clear rate limit state. If admin_id is None, clear all."""
        with self._lock:
            if admin_id is None:
                self._requests.clear()
            else:
                self._requests.pop(admin_id, None)


# Module-level singleton
_limiter = AdminRateLimiter()


def get_rate_limiter() -> AdminRateLimiter:
    """Return the global rate limiter instance."""
    return _limiter


class AdminRateLimitMiddleware(BaseHTTPMiddleware):
    """Starlette middleware that rate-limits mutation requests on /api/admin/*.

    Only applies to POST/PUT/PATCH/DELETE on paths starting with /api/admin/.
    Extracts the admin user ID from the JWT (already validated by deps).
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Only rate-limit mutations on admin endpoints
        if (
            request.method not in _MUTATION_METHODS
            or not request.url.path.startswith("/api/admin")
        ):
            return await call_next(request)

        limiter = get_rate_limiter()
        # Extract admin ID from Authorization header
        admin_id = self._extract_admin_id(request)
        if admin_id is None:
            # No valid auth — let the route handler return 401
            return await call_next(request)

        allowed, info = limiter.check(admin_id)

        if not allowed:
            logger.warning(
                "Rate limit exceeded for admin %s: %d/%d requests in window",
                admin_id, limiter.max_requests, limiter.window_seconds,
            )
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "detail": {
                        "error": "rate_limit_exceeded",
                        "message": (
                            f"Rate limit exceeded: {limiter.max_requests}"
                            " mutations per minute."
                        ),
                        "retry_after": info["reset"],
                    }
                },
                headers={"Retry-After": str(info["reset"])},
            )

        # Process the request, then record it
        response = await call_next(request)

        # Only count successful mutations (2xx/3xx)
        if response.status_code < 400:
            limiter.record(admin_id)

        # Add rate limit headers to response
        _, post_info = limiter.check(admin_id)
        response.headers["X-RateLimit-Limit"] = str(post_info["limit"])
        response.headers["X-RateLimit-Remaining"] = str(post_info["remaining"])
        response.headers["X-RateLimit-Reset"] = str(post_info["reset"])

        return response

    def _extract_admin_id(self, request: Request) -> str | None:
        """Extract the admin user ID from the JWT without full validation.

        The route-level dependency handles full JWT validation; here we just
        need the subject claim for rate-limit keying.
        """
        import jwt
        from jwt.exceptions import InvalidTokenError

        from synapse.api.deps import JWT_ALGORITHM, JWT_SECRET

        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            return None
        token = auth_header.split(" ", 1)[1]
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            return payload.get("sub")
        except InvalidTokenError:
            return None
