"""
synapse.api.main — FastAPI application entry point
=====================================================

Run with::

    uvicorn synapse.api.main:app --reload --port 8000
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.staticfiles import StaticFiles

load_dotenv()

from synapse.api.auth import router as auth_router  # noqa: E402
from synapse.api.deps import get_engine  # noqa: E402
from synapse.api.rate_limit import configure_rate_limiter  # noqa: E402
from synapse.api.routes.admin import router as admin_router  # noqa: E402
from synapse.api.routes.event_lake import router as event_lake_router  # noqa: E402
from synapse.api.routes.layouts import router as layouts_router  # noqa: E402
from synapse.api.routes.public import router as public_router  # noqa: E402
from synapse.services.log_buffer import install_handler  # noqa: E402
from synapse.services.upload_service import UPLOAD_DIR, ensure_upload_dir  # noqa: E402

logger = logging.getLogger(__name__)


def _cors_origins() -> list[str]:
    """Resolve allowed CORS origins from env with safe defaults.

    Priority:
      1) CORS_ALLOW_ORIGINS (comma-separated)
      2) FRONTEND_URL (single origin)
    """
    raw = os.getenv("CORS_ALLOW_ORIGINS", "").strip()
    if raw:
        return [origin.strip().rstrip("/") for origin in raw.split(",") if origin.strip()]

    frontend_url = os.getenv("FRONTEND_URL", "").strip()
    if frontend_url:
        return [frontend_url.rstrip("/")]

    return []


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle — warm the DB engine."""
    # Ensure our log handler is attached to Uvicorn loggers.
    # We do this here (after startup) because Uvicorn reconfigures logging
    # when it starts, often wiping handlers added at import time.
    install_handler()

    # Ensure upload directory exists
    ensure_upload_dir()

    engine = get_engine()
    configure_rate_limiter(engine=engine)
    logger.info("Synapse API started — engine ready (%s)", engine.url.database)
    yield
    logger.info("Synapse API shutting down")


app = FastAPI(
    title="Synapse Dashboard API",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — allow the SvelteKit dev server and production frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routers
app.include_router(auth_router, prefix="/api")
app.include_router(public_router, prefix="/api")
app.include_router(admin_router, prefix="/api")
app.include_router(event_lake_router, prefix="/api")
app.include_router(layouts_router, prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok"}


# Serve uploaded files as static assets with caching headers
if UPLOAD_DIR.exists():
    app.mount(
        "/api/uploads",
        StaticFiles(directory=str(UPLOAD_DIR)),
        name="uploads",
    )


@app.get("/api/health/bot")
def bot_health():
    """Return the bot's heartbeat status."""
    from synapse.services.setup_service import get_bot_heartbeat

    engine = get_engine()
    return get_bot_heartbeat(engine)
