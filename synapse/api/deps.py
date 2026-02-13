"""
synapse.api.deps — FastAPI dependency injection
=================================================
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Annotated

import jwt
from fastapi import Depends, Header, HTTPException, status
from jwt.exceptions import InvalidTokenError
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from synapse.config import SynapseConfig, load_config
from synapse.database.engine import create_db_engine

_WEAK_SECRETS = frozenset({
    "synapse-dev-secret-change-me",
    "change-me",
    "secret",
    "dev",
    "",
})

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
            "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(64))\""
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


def get_setting(session: Session, key: str, default=None):
    """Read a single setting value from the DB."""
    from synapse.database.models import Setting
    row = session.get(Setting, key)
    if row is None:
        return default
    try:
        return json.loads(row.value_json)
    except (json.JSONDecodeError, TypeError):
        return row.value_json


def get_current_admin(
    authorization: Annotated[str | None, Header()] = None,
    engine: Engine = Depends(get_engine),
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
