"""
synapse.api.deps — FastAPI dependency injection
=================================================
"""

from __future__ import annotations

import os
import time
from functools import lru_cache
from typing import Annotated

import jwt
from fastapi import Depends, Header, HTTPException, status
from jwt.exceptions import InvalidTokenError
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from synapse.config import SynapseConfig, load_config
from synapse.database.engine import create_db_engine
from synapse.database.models import UserProfile

_WEAK_SECRETS = frozenset(
    {
        "synapse-dev-secret-change-me",
        "change-me",
        "secret",
        "dev",
        "",
    }
)

_MIN_SECRET_LENGTH = 32

JWT_ALGORITHM = "HS256"


def _load_jwt_secret() -> str:
    """Load and validate JWT_SECRET from the environment.

    Raises RuntimeError at import time if the secret is missing, blank,
    too short (< 32 chars), or a known weak default.
    """
    secret = os.getenv("JWT_SECRET", "")
    if not secret:
        raise RuntimeError(
            "JWT_SECRET environment variable is not set. "
            'Generate one with: python -c "import secrets; print(secrets.token_urlsafe(64))"'
        )
    if secret in _WEAK_SECRETS:
        raise RuntimeError(
            f"JWT_SECRET is set to a known weak default ('{secret}'). "
            "Please set a strong, unique secret."
        )
    if len(secret) < _MIN_SECRET_LENGTH:
        raise RuntimeError(
            f"JWT_SECRET is too short ({len(secret)} chars). "
            f"Minimum length is {_MIN_SECRET_LENGTH} characters."
        )
    return secret


JWT_SECRET: str = _load_jwt_secret()


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    return create_db_engine()


@lru_cache(maxsize=1)
def get_config() -> SynapseConfig:
    return load_config()


def get_session(engine: Annotated[Engine, Depends(get_engine)]):
    with Session(engine) as session:
        yield session


def get_current_admin(
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    """Validate JWT and return admin user payload. Raises 401 if invalid."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing token")
    token = authorization.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")
    if not payload.get("is_admin"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not admin")
    return payload


# ---------------------------------------------------------------------------
# Phase 5 — Three-Tier Auth route guards
# ---------------------------------------------------------------------------

# Membership verification cache: user_id → (is_active_member, expires_at)
# Cache-first, 5-minute TTL, DB fallback via _check_member_sync.
# dict read/write is GIL-protected — no explicit lock needed for this use case.
_member_cache: dict[int, tuple[bool, float]] = {}
_MEMBER_CACHE_TTL = 300.0  # seconds


def _check_member_sync(engine: Engine, user_id: int) -> bool:
    """Return True if a UserProfile row exists with left_at IS NULL.

    Parameters
    ----------
    engine : Engine
    user_id : int
        Discord snowflake of the user to check.
    """
    with Session(engine) as session:
        profile = session.get(UserProfile, user_id)
        return profile is not None and profile.left_at is None


def get_member_context(
    authorization: Annotated[str | None, Header()] = None,
    engine: Annotated[Engine, Depends(get_engine)] = None,  # type: ignore[assignment]
) -> dict:
    """Validate JWT for any current guild member.

    Decodes the JWT, then verifies the bearer is a current guild member
    using a 5-minute TTL cache backed by ``user_profiles``.  Raises 401
    for missing/invalid tokens and 403 for former members.

    Use this on any endpoint that should be accessible to *all*
    authenticated members (Tier 2 + Tier 3).
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing token")
    token = authorization.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")

    user_id = int(payload.get("sub", 0))
    now = time.monotonic()
    cached = _member_cache.get(user_id)

    if cached is None or now > cached[1]:
        is_member = _check_member_sync(engine, user_id)
        _member_cache[user_id] = (is_member, now + _MEMBER_CACHE_TTL)
    else:
        is_member = cached[0]

    if not is_member:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not a guild member")
    return payload


def get_admin_context(
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    """Validate JWT and require admin (Tier 3).

    Drop-in alternative to ``get_current_admin`` that uses the richer
    JWT payload introduced in Phase 5 while preserving backward
    compatibility with the existing ``is_admin`` field.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing token")
    token = authorization.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")
    if not payload.get("is_admin"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not admin")
    return payload
