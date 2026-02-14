"""
synapse.services.upload_service — File upload handling
========================================================

Handles image uploads for card backgrounds, brand assets, etc.
Files are stored in a configurable ``uploads/`` directory (Docker volume)
and served via a static-file endpoint.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from pathlib import Path

UPLOAD_DIR = Path(os.getenv("SYNAPSE_UPLOAD_DIR", "uploads"))
MAX_FILE_SIZE = 25 * 1024 * 1024  # 25 MB
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
ALLOWED_MIME_TYPES = {
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    "image/svg+xml",
}


def ensure_upload_dir() -> None:
    """Create the upload directory if it doesn't exist."""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


async def save_upload(filename: str, content: bytes, content_type: str | None = None) -> str:
    """Validate and persist an uploaded file.

    Parameters
    ----------
    filename:
        Original filename from the upload.
    content:
        Raw file bytes.
    content_type:
        MIME type from the upload header.

    Returns
    -------
    str
        URL path to the saved file (e.g. ``/api/uploads/abc123.png``).

    Raises
    ------
    ValueError
        If validation fails (wrong type, too large, etc.).
    """
    # Size check
    if len(content) > MAX_FILE_SIZE:
        raise ValueError(
            f"File too large: {len(content)} bytes (max {MAX_FILE_SIZE // 1024 // 1024}MB)"
        )

    # Extension check
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(
            f"File type not allowed: {ext!r}. "
            f"Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    # MIME type check (if provided)
    if content_type and content_type not in ALLOWED_MIME_TYPES:
        raise ValueError(
            f"MIME type not allowed: {content_type!r}. "
            f"Allowed: {', '.join(sorted(ALLOWED_MIME_TYPES))}"
        )

    # Generate unique filename to avoid collisions
    unique_name = f"{uuid.uuid4().hex}{ext}"
    dest = UPLOAD_DIR / unique_name

    # Offload blocking file I/O to a thread to avoid stalling the event loop
    await asyncio.to_thread(dest.write_bytes, content)

    return f"/api/uploads/{unique_name}"


def delete_upload(url_path: str) -> bool:
    """Remove an uploaded file by its URL path.

    Returns True if the file existed and was deleted.
    """
    if not url_path.startswith("/api/uploads/"):
        return False
    filename = url_path.rsplit("/", 1)[-1]
    filepath = UPLOAD_DIR / filename
    if filepath.exists() and filepath.is_file():
        filepath.unlink()
        return True
    return False
