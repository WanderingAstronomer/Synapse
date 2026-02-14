"""
synapse.api.routes.admin — Admin router hub
=============================================

Aggregates all admin sub-routers so ``main.py`` can include a single
``admin_router`` for backward compatibility.
"""

from __future__ import annotations

from fastapi import APIRouter

from synapse.api.routes.achievements import router as achievements_router
from synapse.api.routes.channels import router as channels_router
from synapse.api.routes.media import router as media_router
from synapse.api.routes.settings import router as settings_router

router = APIRouter()

# Each sub-router already carries prefix="/admin" and tags=["admin"],
# so we include them without extra prefix/tags.
router.include_router(channels_router)
router.include_router(achievements_router)
router.include_router(settings_router)
router.include_router(media_router)
