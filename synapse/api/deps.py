"""
synapse.api.deps — FastAPI dependency injection
=================================================
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from jose import JWTError, jwt
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from synapse.config import SynapseConfig, load_config
from synapse.database.engine import create_db_engine

JWT_SECRET = os.getenv("JWT_SECRET", "synapse-dev-secret-change-me")
JWT_ALGORITHM = "HS256"


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
    except JWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")
    if not payload.get("is_admin"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not admin")
    return payload
