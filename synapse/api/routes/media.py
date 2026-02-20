"""
synapse.api.routes.media — Media library CRUD & upload
========================================================
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from synapse.api.deps import get_config, get_engine, get_session
from synapse.api.rate_limit import rate_limited_admin
from synapse.config import SynapseConfig
from synapse.database.models import MediaFile, MediaFolder
from synapse.services.media_service import (
    create_folder,
    delete_folder_if_empty,
    list_folders,
    rename_folder,
)

router = APIRouter(prefix="/admin", tags=["admin"])
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------
class MediaUpdate(BaseModel):
    alt_text: str | None = None
    folder_id: int | None = None


class FolderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    parent_id: int | None = None


class FolderRename(BaseModel):
    name: str = Field(min_length=1, max_length=100)


# ---------------------------------------------------------------------------
# Folder management
# ---------------------------------------------------------------------------
@router.get("/folders")
def list_media_folders(
    engine: Any = Depends(get_engine),
    admin: dict = Depends(rate_limited_admin),
    cfg: SynapseConfig = Depends(get_config),
):
    """List all media folders for this guild (flat; client builds tree)."""
    folders = list_folders(engine, cfg.guild_id)
    return {
        "folders": [
            {
                "id": f.id,
                "name": f.name,
                "parent_id": f.parent_id,
                "created_at": f.created_at.isoformat() if f.created_at else None,
            }
            for f in folders
        ]
    }


@router.post("/folders", status_code=201)
def create_media_folder(
    body: FolderCreate,
    engine: Any = Depends(get_engine),
    admin: dict = Depends(rate_limited_admin),
    cfg: SynapseConfig = Depends(get_config),
):
    """Create a new media folder."""
    try:
        folder = create_folder(engine, cfg.guild_id, body.name, body.parent_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"id": folder.id, "name": folder.name, "parent_id": folder.parent_id}


@router.patch("/folders/{folder_id}")
def rename_media_folder(
    folder_id: int,
    body: FolderRename,
    engine: Any = Depends(get_engine),
    admin: dict = Depends(rate_limited_admin),
    cfg: SynapseConfig = Depends(get_config),
):
    """Rename a media folder."""
    try:
        folder = rename_folder(engine, folder_id, cfg.guild_id, body.name)
    except ValueError as exc:
        status = 404 if "not found" in str(exc).lower() else 409
        raise HTTPException(status, str(exc)) from exc
    return {"id": folder.id, "name": folder.name, "parent_id": folder.parent_id}


@router.delete("/folders/{folder_id}", status_code=204)
def delete_media_folder(
    folder_id: int,
    engine: Any = Depends(get_engine),
    admin: dict = Depends(rate_limited_admin),
    cfg: SynapseConfig = Depends(get_config),
):
    """Delete a folder — only succeeds if the folder is empty."""
    try:
        delete_folder_if_empty(engine, folder_id, cfg.guild_id)
    except ValueError as exc:
        status = 404 if "not found" in str(exc).lower() else 409
        raise HTTPException(status, str(exc)) from exc


# ---------------------------------------------------------------------------
# Media library
# ---------------------------------------------------------------------------
@router.get("/media")
def list_media(
    folder_id: int | None = Query(default=None, description="Filter by folder (omit for all)"),
    session: Session = Depends(get_session),
    admin: dict = Depends(rate_limited_admin),
    cfg: SynapseConfig = Depends(get_config),
):
    """List uploaded media files, optionally filtered by folder."""
    stmt = (
        select(MediaFile)
        .where(MediaFile.guild_id == cfg.guild_id)
        .order_by(MediaFile.uploaded_at.desc())
    )
    if folder_id is not None:
        stmt = stmt.where(MediaFile.folder_id == folder_id)
    files = session.scalars(stmt).all()
    return {
        "files": [
            {
                "id": f.id,
                "url": f.url,
                "original_name": f.original_name,
                "content_type": f.content_type,
                "size_bytes": f.size_bytes,
                "alt_text": f.alt_text,
                "folder_id": f.folder_id,
                "uploaded_at": f.uploaded_at.isoformat() if f.uploaded_at else None,
            }
            for f in files
        ]
    }


@router.post("/media")
async def upload_media(
    file: UploadFile,
    folder_id: int | None = Query(default=None, description="Folder to place the file in"),
    session: Session = Depends(get_session),
    engine: Any = Depends(get_engine),
    admin: dict = Depends(rate_limited_admin),
    cfg: SynapseConfig = Depends(get_config),
):
    """Upload an image to the media library."""
    from synapse.services.upload_service import save_upload

    # Validate folder ownership before writing the file
    if folder_id is not None:
        folder = session.get(MediaFolder, folder_id)
        if folder is None or folder.guild_id != cfg.guild_id:
            raise HTTPException(404, "Folder not found")

    content = await file.read()
    try:
        url = await save_upload(file.filename or "upload.png", content, file.content_type)
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
        folder_id=folder_id,
    )
    session.add(media)
    session.commit()
    session.refresh(media)
    return {
        "id": media.id,
        "url": media.url,
        "original_name": media.original_name,
        "folder_id": media.folder_id,
    }


@router.patch("/media/{media_id}")
def update_media(
    media_id: int,
    body: MediaUpdate,
    session: Session = Depends(get_session),
    admin: dict = Depends(rate_limited_admin),
    cfg: SynapseConfig = Depends(get_config),
):
    """Update media metadata (alt text and/or folder assignment)."""
    media = session.get(MediaFile, media_id)
    if not media or media.guild_id != cfg.guild_id:
        raise HTTPException(404, "Media not found")
    if body.alt_text is not None:
        media.alt_text = body.alt_text
    if "folder_id" in body.model_fields_set:
        # Allow moving to a folder or clearing (folder_id=null)
        if body.folder_id is not None:
            folder = session.get(MediaFolder, body.folder_id)
            if folder is None or folder.guild_id != cfg.guild_id:
                raise HTTPException(404, "Folder not found")
        media.folder_id = body.folder_id
    session.commit()
    return {"id": media.id, "alt_text": media.alt_text, "folder_id": media.folder_id}


@router.delete("/media/{media_id}", status_code=204)
def delete_media(
    media_id: int,
    session: Session = Depends(get_session),
    admin: dict = Depends(rate_limited_admin),
    cfg: SynapseConfig = Depends(get_config),
):
    """Delete a media file from the library and disk."""
    from synapse.services.upload_service import delete_upload

    media = session.get(MediaFile, media_id)
    if not media or media.guild_id != cfg.guild_id:
        raise HTTPException(404, "Media not found")
    delete_upload(media.url)
    session.delete(media)
    session.commit()
