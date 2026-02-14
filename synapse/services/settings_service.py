"""
synapse.services.settings_service — Settings CRUD & NOTIFY
============================================================

Provides typed read/write access to the ``settings`` table.
Every mutation fires a PG NOTIFY so :class:`~synapse.engine.cache.ConfigCache`
invalidates automatically.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from synapse.database.models import AdminLog, Setting
from synapse.engine.cache import send_notify

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

def get_setting(engine, key: str) -> dict | None:
    """Fetch a single setting by key, returned as a plain dict."""
    with Session(engine) as session:
        row = session.get(Setting, key)
        if row is None:
            return None
        return {
            "key": row.key,
            "value_json": row.value_json,
            "category": row.category,
            "description": row.description,
        }


def get_setting_value(session: Session, key: str, default=None):
    """Read a single setting's parsed value from an existing session.

    Parameters
    ----------
    session : Session
        An open SQLAlchemy session.
    key : str
        The setting key to look up.
    default
        Returned when the key does not exist or the stored JSON is invalid.

    Returns
    -------
    The JSON-decoded value, or *default*.
    """
    row = session.get(Setting, key)
    if row is None:
        return default
    try:
        return json.loads(row.value_json)
    except (json.JSONDecodeError, TypeError):
        return row.value_json


def get_all_settings(engine) -> list[Setting]:
    """Fetch every setting row, ordered by category then key."""
    with Session(engine) as session:
        rows = session.scalars(
            select(Setting).order_by(Setting.category, Setting.key)
        ).all()
        # Expunge so callers can read outside the session
        for r in rows:
            session.expunge(r)
        return list(rows)


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------

def upsert_setting(
    engine,
    *,
    key: str,
    value: Any,
    category: str = "general",
    description: str | None = None,
) -> Setting:
    """Insert or update a single setting.  Fires PG NOTIFY on commit."""
    value_json = json.dumps(value)
    with Session(engine) as session:
        existing = session.get(Setting, key)
        if existing:
            existing.value_json = value_json
            if category:
                existing.category = category
            if description is not None:
                existing.description = description
        else:
            existing = Setting(
                key=key,
                value_json=value_json,
                category=category,
                description=description,
            )
            session.add(existing)
        session.commit()

    send_notify(engine, "settings")
    return existing


def bulk_upsert(engine, settings: list[dict], *, actor_id: int | None = None) -> int:
    """Upsert many settings at once.

    Each dict should have at least ``key`` and ``value``.
    Optional: ``category``, ``description``.

    When *actor_id* is provided, each change is individually recorded in the
    ``admin_log`` table with before/after snapshots so the audit log shows
    exactly who changed what.

    Returns the number of rows touched.
    """
    count = 0
    with Session(engine) as session:
        for item in settings:
            key = item["key"]
            value_json = json.dumps(item["value"])
            existing = session.get(Setting, key)

            # Capture "before" snapshot for audit logging
            before_snapshot: dict | None = None
            if existing and actor_id is not None:
                before_snapshot = {
                    "key": existing.key,
                    "value": json.loads(existing.value_json) if existing.value_json else None,
                    "category": existing.category,
                    "description": existing.description,
                }

            if existing:
                existing.value_json = value_json
                if "category" in item:
                    existing.category = item["category"]
                if "description" in item:
                    existing.description = item["description"]
            else:
                existing = Setting(
                    key=key,
                    value_json=value_json,
                    category=item.get("category", "general"),
                    description=item.get("description"),
                )
                session.add(existing)

            # Write audit log entry
            if actor_id is not None:
                after_snapshot = {
                    "key": key,
                    "value": item["value"],
                    "category": existing.category,
                    "description": existing.description,
                }
                # Only log if something actually changed
                if before_snapshot != after_snapshot:
                    session.add(AdminLog(
                        actor_id=actor_id,
                        action_type="UPDATE" if before_snapshot else "CREATE",
                        target_table="settings",
                        target_id=key,
                        before_snapshot=before_snapshot,
                        after_snapshot=after_snapshot,
                    ))

            count += 1
        session.commit()

    send_notify(engine, "settings")
    return count
