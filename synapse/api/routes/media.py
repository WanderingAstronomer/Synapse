"""
synapse.api.routes.media — Media library CRUD & upload
========================================================
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from synapse.api.deps import get_config, get_engine, get_session
from synapse.api.rate_limit import rate_limited_admin
from synapse.config import SynapseConfig
from synapse.database.models import MediaFile

router = APIRouter(prefix="/admin", tags=["admin"])
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------
class MediaUpdate(BaseModel):
    alt_text: str | None = None


# ---------------------------------------------------------------------------
# Media library
# ---------------------------------------------------------------------------
@router.get("/media")
def list_media(
    session: Session = Depends(get_session),
    admin: dict = Depends(rate_limited_admin),
    cfg: SynapseConfig = Depends(get_config),
):
    """List all uploaded media files."""
    files = session.scalars(
        select(MediaFile)
        .where(MediaFile.guild_id == cfg.guild_id)
        .order_by(MediaFile.uploaded_at.desc())
    ).all()
    return {
        "files": [
            {
                "id": f.id,
                "url": f.url,
                "original_name": f.original_name,
                "content_type": f.content_type,
                "size_bytes": f.size_bytes,
                "alt_text": f.alt_text,
                "uploaded_at": f.uploaded_at.isoformat()
                if f.uploaded_at else None,
            }
            for f in files
        ]
    }


@router.post("/media")
async def upload_media(
    file: UploadFile,
    session: Session = Depends(get_session),
    engine: Any = Depends(get_engine),
    admin: dict = Depends(rate_limited_admin),
    cfg: SynapseConfig = Depends(get_config),
):
    """Upload an image to the media library."""
    from synapse.services.upload_service import save_upload

    content = await file.read()
    try:
        url = await save_upload(
            file.filename or "upload.png", content, file.content_type
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    media = MediaFile(
        guild_id=cfg.guild_id,
        filename=url.rsplit("/", 1)[-1],
        original_name=file.filename or "upload.png",
        url=url,
        content_type=file.content_type,
        size_bytes=len(content),
        uploaded_by=admin.get("user_id"),
    )
    session.add(media)
    session.commit()
    session.refresh(media)
    return {
        "id": media.id,
        "url": media.url,
        "original_name": media.original_name,
    }


@router.patch("/media/{media_id}")
def update_media(
    media_id: int,
    body: MediaUpdate,
    session: Session = Depends(get_session),
    admin: dict = Depends(rate_limited_admin),
):
    """Update media metadata (alt text)."""
    media = session.get(MediaFile, media_id)
    if not media:
        raise HTTPException(404, "Media not found")
    if body.alt_text is not None:
        media.alt_text = body.alt_text
    session.commit()
    return {"id": media.id, "alt_text": media.alt_text}


@router.delete("/media/{media_id}", status_code=204)
def delete_media(
    media_id: int,
    session: Session = Depends(get_session),
    admin: dict = Depends(rate_limited_admin),
):
    """Delete a media file from the library and disk."""
    from synapse.services.upload_service import delete_upload

    media = session.get(MediaFile, media_id)
    if not media:
        raise HTTPException(404, "Media not found")
    delete_upload(media.url)
    session.delete(media)
    session.commit()
