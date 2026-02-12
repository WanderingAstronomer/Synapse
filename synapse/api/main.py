"""
synapse.api.main — FastAPI application entry point
=====================================================

Run with::

    uvicorn synapse.api.main:app --reload --port 8000
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from synapse.api.auth import router as auth_router
from synapse.api.deps import get_engine
from synapse.api.routes.admin import router as admin_router
from synapse.api.routes.event_lake import router as event_lake_router
from synapse.api.routes.public import router as public_router

load_dotenv()

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle — warm the DB engine."""
    engine = get_engine()
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
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://dashboard:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routers
app.include_router(auth_router, prefix="/api")
app.include_router(public_router, prefix="/api")
app.include_router(admin_router, prefix="/api")
app.include_router(event_lake_router, prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok"}
