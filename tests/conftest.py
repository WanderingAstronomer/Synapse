"""
tests/conftest.py — Shared Test Fixtures
=========================================
"""

from __future__ import annotations

import os

# ---------------------------------------------------------------------------
# Ensure a valid JWT_SECRET is always set for test runs.
# This must happen before any import of synapse.api.deps which validates
# the secret at module-load time.
# ---------------------------------------------------------------------------
_TEST_JWT_SECRET = "test-secret-for-pytest-only-" + "x" * 40  # > 32 chars
os.environ.setdefault("JWT_SECRET", _TEST_JWT_SECRET)

import pytest  # noqa: E402
from sqlalchemy import Engine, create_engine  # noqa: E402

# ---------------------------------------------------------------------------
# Make JSONB columns work in SQLite for testing.
# SQLite doesn't support JSONB natively, but SQLAlchemy's JSON type works.
# We register a custom type compiler so SQLite renders JSONB as TEXT.
# ---------------------------------------------------------------------------
from sqlalchemy.dialects.postgresql import JSONB as PG_JSONB  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from synapse.database.models import Base  # noqa: E402

_jsonb_sqlite_registered = False


def _register_jsonb_sqlite_compat():
    """Register SQLite compilation for PG JSONB type (idempotent)."""
    global _jsonb_sqlite_registered
    if _jsonb_sqlite_registered:
        return
    from sqlalchemy.ext.compiler import compiles

    @compiles(PG_JSONB, "sqlite")
    def _compile_jsonb_as_text(type_, compiler, **kw):
        return "TEXT"

    _jsonb_sqlite_registered = True


_register_jsonb_sqlite_compat()


@pytest.fixture
def db_engine() -> Engine:
    """Create an in-memory SQLite engine with all Synapse tables.

    JSONB columns are transparently mapped to TEXT for SQLite compatibility.
    """
    engine = create_engine("sqlite://", echo=False)
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def db_session(db_engine: Engine):
    """Provide a transactional session that rolls back after each test."""
    with Session(db_engine) as session:
        yield session
        session.rollback()


@pytest.fixture
def admin_token():
    """Generate a valid admin JWT for use in API integration tests."""
    import jwt

    from synapse.api.deps import JWT_ALGORITHM, JWT_SECRET

    return jwt.encode(
        {"sub": "99999", "username": "FixtureAdmin", "is_admin": True},
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )


@pytest.fixture
def auth_headers(admin_token: str) -> dict[str, str]:
    """Authorization headers containing a valid admin JWT."""
    return {"Authorization": f"Bearer {admin_token}"}
