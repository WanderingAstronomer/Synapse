"""
synapse.services.media_service — Media folder management & SVG overlay seeder
===============================================================================

Provides pure-sync DB operations for the media library folder hierarchy and
the idempotent SVG overlay seeder.  All functions follow the ``run_db``
convention: they are synchronous, accept a SQLAlchemy Engine as their first
argument, and must be called via ``await run_db(fn, engine, ...)`` from async
contexts.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from synapse.database.models import MediaFile, MediaFolder, SvgOverlay
from synapse.services.upload_service import UPLOAD_DIR

if TYPE_CHECKING:
    from sqlalchemy import Engine

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default SVG overlay definitions
# ---------------------------------------------------------------------------

# Minimal SVG border frames for each rarity tier.  These are written as static
# files on first startup and referenced by URL path identical to other uploads.
_DEFAULT_OVERLAYS: dict[str, str] = {
    "border_common": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
        '<rect x="2" y="2" width="96" height="96" rx="8" ry="8"'
        ' fill="none" stroke="#9ca3af" stroke-width="3"/>'
        "</svg>"
    ),
    "border_rare": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
        '<rect x="2" y="2" width="96" height="96" rx="8" ry="8"'
        ' fill="none" stroke="#3b82f6" stroke-width="4"/>'
        '<rect x="5" y="5" width="90" height="90" rx="6" ry="6"'
        ' fill="none" stroke="#93c5fd" stroke-width="1" opacity="0.5"/>'
        "</svg>"
    ),
    "border_epic": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
        '<rect x="2" y="2" width="96" height="96" rx="8" ry="8"'
        ' fill="none" stroke="#8b5cf6" stroke-width="4"/>'
        '<rect x="5" y="5" width="90" height="90" rx="6" ry="6"'
        ' fill="none" stroke="#c4b5fd" stroke-width="1" opacity="0.5"/>'
        '<circle cx="2" cy="2" r="3" fill="#8b5cf6"/>'
        '<circle cx="98" cy="2" r="3" fill="#8b5cf6"/>'
        '<circle cx="2" cy="98" r="3" fill="#8b5cf6"/>'
        '<circle cx="98" cy="98" r="3" fill="#8b5cf6"/>'
        "</svg>"
    ),
    "border_legendary": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
        '<rect x="2" y="2" width="96" height="96" rx="8" ry="8"'
        ' fill="none" stroke="#f59e0b" stroke-width="4"/>'
        '<rect x="5" y="5" width="90" height="90" rx="6" ry="6"'
        ' fill="none" stroke="#fcd34d" stroke-width="1" opacity="0.6"/>'
        '<polygon points="50,2 54,14 67,14 57,22 61,34 50,26 39,34 43,22 33,14 46,14"'
        ' fill="#f59e0b" opacity="0.3"/>'
        "</svg>"
    ),
}

# ---------------------------------------------------------------------------
# Folder CRUD
# ---------------------------------------------------------------------------


def create_folder(
    engine: Engine,
    guild_id: int,
    name: str,
    parent_id: int | None = None,
) -> MediaFolder:
    """Create a new media folder.

    Parameters
    ----------
    engine:
        SQLAlchemy synchronous engine.
    guild_id:
        Discord guild ID that owns this folder.
    name:
        Folder name (max 100 chars).
    parent_id:
        Optional parent folder ID for nested hierarchy.

    Returns
    -------
    MediaFolder
        The newly created (and committed) folder row.

    Raises
    ------
    ValueError
        If a folder with the same ``(guild_id, parent_id, name)`` already exists,
        or if ``parent_id`` does not belong to ``guild_id``.
    """
    with Session(engine) as session:
        # Validate parent belongs to same guild
        if parent_id is not None:
            parent = session.get(MediaFolder, parent_id)
            if parent is None or parent.guild_id != guild_id:
                raise ValueError(f"Parent folder {parent_id} not found")

        folder = MediaFolder(guild_id=guild_id, name=name, parent_id=parent_id)
        session.add(folder)
        try:
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            raise ValueError(f"Folder {name!r} already exists in this location") from exc
        session.refresh(folder)
        return folder


def rename_folder(
    engine: Engine,
    folder_id: int,
    guild_id: int,
    new_name: str,
) -> MediaFolder:
    """Rename a media folder.

    Parameters
    ----------
    engine:
        SQLAlchemy synchronous engine.
    folder_id:
        ID of the folder to rename.
    guild_id:
        Guild ID — used to prevent cross-guild mutations.
    new_name:
        New folder name.

    Returns
    -------
    MediaFolder
        The updated folder.

    Raises
    ------
    ValueError
        If the folder is not found or a name collision exists.
    """
    with Session(engine) as session:
        folder = session.get(MediaFolder, folder_id)
        if folder is None or folder.guild_id != guild_id:
            raise ValueError(f"Folder {folder_id} not found")
        folder.name = new_name
        try:
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            raise ValueError(f"Folder {new_name!r} already exists in this location") from exc
        session.refresh(folder)
        return folder


def delete_folder_if_empty(
    engine: Engine,
    folder_id: int,
    guild_id: int,
) -> None:
    """Delete a media folder, raising if it is not empty.

    Parameters
    ----------
    engine:
        SQLAlchemy synchronous engine.
    folder_id:
        ID of the folder to delete.
    guild_id:
        Guild ID — used to prevent cross-guild mutations.

    Raises
    ------
    ValueError
        If the folder is not found, contains files, or has sub-folders.
    """
    with Session(engine) as session:
        folder = session.get(MediaFolder, folder_id)
        if folder is None or folder.guild_id != guild_id:
            raise ValueError(f"Folder {folder_id} not found")

        file_count = session.scalar(
            select(func.count()).select_from(MediaFile).where(MediaFile.folder_id == folder_id)
        )
        if file_count:
            raise ValueError(
                f"Cannot delete folder {folder_id!r}: it contains {file_count} file(s)"
            )

        child_count = session.scalar(
            select(func.count()).select_from(MediaFolder).where(MediaFolder.parent_id == folder_id)
        )
        if child_count:
            raise ValueError(
                f"Cannot delete folder {folder_id!r}: it has {child_count} sub-folder(s)"
            )

        session.delete(folder)
        session.commit()


def list_folders(engine: Engine, guild_id: int) -> list[MediaFolder]:
    """Return all folders for a guild, ordered by name.

    Parameters
    ----------
    engine:
        SQLAlchemy synchronous engine.
    guild_id:
        Discord guild ID.

    Returns
    -------
    list[MediaFolder]
        Flat list (caller builds tree if needed).
    """
    with Session(engine) as session:
        folders = session.scalars(
            select(MediaFolder)
            .where(MediaFolder.guild_id == guild_id)
            .order_by(MediaFolder.parent_id.nulls_first(), MediaFolder.name)
        ).all()
        return list(folders)


# ---------------------------------------------------------------------------
# SVG overlay seeder
# ---------------------------------------------------------------------------


def seed_svg_overlays(engine: Engine, guild_id: int) -> int:
    """Seed default SVG overlay records (idempotent).

    Writes each default SVG to the ``uploads/`` directory if the file does
    not already exist, then inserts a corresponding ``SvgOverlay`` row if one
    with the same ``(guild_id, name)`` is not already present.

    Parameters
    ----------
    engine:
        SQLAlchemy synchronous engine.
    guild_id:
        Discord guild ID to associate the overlays with.

    Returns
    -------
    int
        Number of new overlay records created (0 if all already existed).
    """
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    created = 0

    with Session(engine) as session:
        for name, svg_content in _DEFAULT_OVERLAYS.items():
            svg_filename = f"default_{name}.svg"
            svg_path = UPLOAD_DIR / svg_filename
            svg_url = f"/api/uploads/{svg_filename}"

            # Write file if absent
            if not svg_path.exists():
                svg_path.write_text(svg_content, encoding="utf-8")
                logger.debug("Wrote default SVG overlay file: %s", svg_filename)

            # Insert DB record if absent
            existing = session.scalar(
                select(SvgOverlay).where(
                    SvgOverlay.guild_id == guild_id,
                    SvgOverlay.name == name,
                )
            )
            if existing is None:
                overlay = SvgOverlay(
                    guild_id=guild_id,
                    name=name,
                    svg_url=svg_url,
                    is_default=True,
                )
                session.add(overlay)
                created += 1

        session.commit()

    if created:
        logger.info("Seeded %d default SVG overlays for guild %s", created, guild_id)
    return created
