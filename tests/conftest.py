from __future__ import annotations

import os

# Set test environment variables before any imports
os.environ["JWT_SECRET"] = "test-secret-for-integration-tests-only-do-not-use-in-production"
os.environ["DISCORD_CLIENT_ID"] = "1234567890"
os.environ["DISCORD_CLIENT_SECRET"] = "test-client-secret"
os.environ["DISCORD_REDIRECT_URI"] = "http://localhost:5173/auth/callback"

# ---------------------------------------------------------------------------
# JSONB → TEXT shim for SQLite test backend
# ---------------------------------------------------------------------------
# SQLAlchemy's JSONB type isn't natively renderable in SQLite.  This global
# compiler hook translates JSONB to TEXT so that ``Base.metadata.create_all``
# works in the in-memory SQLite fixtures used by every test module.
# Registering it in conftest.py guarantees it's active before any fixture
# creates tables.
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(element, compiler, **kw):  # type: ignore[misc]
    return "TEXT"


# Intentionally minimal during rework.
# Historical fixtures removed to prevent legacy coupling.
