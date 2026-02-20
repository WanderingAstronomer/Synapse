"""
synapse.services.profile_service — Discord Identity Cache Sync
==============================================================

Pure synchronous functions for maintaining ``user_profiles`` and
``user_guild_roles`` rows.  All functions receive a raw SQLAlchemy
``Engine`` and open their own sessions.  Call via ``run_db()``.

Three public operations
-----------------------
upsert_profile
    Called on ``on_message`` and ``on_member_join``.  INSERT or UPDATE
    the profile row; never clobbers ``left_at`` set by a prior leave.

sync_member_roles
    Called on ``on_member_join`` and ``on_member_update``.  Atomically
    replaces the user's role set for the guild.

anonymize_on_leave
    Called on ``on_member_remove``.  Sets username → "Former Member",
    avatar_url → NULL, records left_at.  Roles are deleted too.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import delete
from sqlalchemy.orm import Session

from synapse.database.models import User, UserGuildRole, UserProfile

if TYPE_CHECKING:
    from sqlalchemy import Engine

logger = logging.getLogger(__name__)

__all__ = [
    "upsert_profile",
    "sync_member_roles",
    "anonymize_on_leave",
]

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def upsert_profile(
    engine: Engine,
    discord_id: int,
    guild_id: int,
    username: str,
    avatar_url: str | None,
) -> None:
    """Insert or update a UserProfile row (dialect-agnostic).

    If a row already exists, ``username``, ``avatar_url``, and
    ``last_seen`` are refreshed.  A non-NULL ``left_at`` is cleared
    (handles the case where a banned+unbanned member sends their first
    message while still technically having a stale leave timestamp).

    Parameters
    ----------
    engine : Engine
        SQLAlchemy engine (synchronous).
    discord_id : int
        Discord user snowflake (PK).
    guild_id : int
        Discord guild snowflake.
    username : str
        Current display/username — never empty.
    avatar_url : str | None
        CDN avatar URL, or ``None`` when unavailable.
    """
    now = datetime.now(UTC)
    with Session(engine) as session:
        existing = session.get(UserProfile, discord_id)
        if existing is not None:
            existing.username = username
            existing.avatar_url = avatar_url
            existing.last_seen = now
            if existing.left_at is not None:
                existing.left_at = None  # re-activated member
        else:
            session.add(
                UserProfile(
                    discord_id=discord_id,
                    guild_id=guild_id,
                    username=username,
                    avatar_url=avatar_url,
                    last_seen=now,
                    left_at=None,
                )
            )
        session.commit()


def sync_member_roles(
    engine: Engine,
    discord_id: int,
    guild_id: int,
    roles: list[tuple[int, str | None]],
) -> None:
    """Replace all role memberships for a user in a guild.

    Deletes existing ``user_guild_roles`` rows, then inserts the
    current set.  The operation is atomic within one transaction.

    Parameters
    ----------
    engine : Engine
    discord_id : int
    guild_id : int
    roles : list[tuple[int, str | None]]
        List of ``(role_id, role_name)`` pairs.  Pass an empty list to
        clear all roles (e.g. after anonymization, though ``CASCADE``
        handles that too).
    """
    now = datetime.now(UTC)
    with Session(engine) as session:
        session.execute(
            delete(UserGuildRole).where(
                UserGuildRole.user_id == discord_id,
                UserGuildRole.guild_id == guild_id,
            )
        )
        for role_id, role_name in roles:
            session.add(
                UserGuildRole(
                    user_id=discord_id,
                    role_id=role_id,
                    guild_id=guild_id,
                    role_name=role_name,
                    synced_at=now,
                )
            )
        session.commit()


def anonymize_on_leave(
    engine: Engine,
    discord_id: int,
    guild_id: int,
) -> None:
    """Anonymize a user's profile when they leave the guild.

    Sets ``username = "Former Member"``, clears ``avatar_url``, records
    ``left_at``.  Roles are deleted explicitly (FK CASCADE also covers
    this, but being explicit avoids relying on DB-level behavior for
    correctness).

    If no profile row exists (user left before sending a message) the
    function is a no-op.

    Parameters
    ----------
    engine : Engine
    discord_id : int
    guild_id : int
    """
    now = datetime.now(UTC)
    with Session(engine) as session:
        profile = session.get(UserProfile, discord_id)
        if profile is None:
            logger.debug(
                "anonymize_on_leave: no profile for discord_id=%d — skipping",
                discord_id,
            )
            return

        profile.username = "Former Member"
        profile.avatar_url = None
        profile.left_at = now

        # Anonymize global user record (P11-04)
        user = session.get(User, discord_id)
        if user:
            user.discord_name = "Former Member"
            user.discord_avatar_hash = None

        session.execute(
            delete(UserGuildRole).where(
                UserGuildRole.user_id == discord_id,
                UserGuildRole.guild_id == guild_id,
            )
        )
        session.commit()
