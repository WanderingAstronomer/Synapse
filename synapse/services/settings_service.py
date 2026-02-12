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

from synapse.database.models import Setting
from synapse.engine.cache import send_notify

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

def get_setting(engine, key: str) -> Setting | None:
    """Fetch a single setting by key."""
    with Session(engine) as session:
        return session.get(Setting, key)


def get_settings_by_category(engine, category: str) -> list[Setting]:
    """Fetch all settings in a given category."""
    with Session(engine) as session:
        return list(
            session.scalars(
                select(Setting)
                .where(Setting.category == category)
                .order_by(Setting.key)
            ).all()
        )


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


def bulk_upsert(engine, settings: list[dict]) -> int:
    """Upsert many settings at once.

    Each dict should have at least ``key`` and ``value``.
    Optional: ``category``, ``description``.

    Returns the number of rows touched.
    """
    count = 0
    with Session(engine) as session:
        for item in settings:
            key = item["key"]
            value_json = json.dumps(item["value"])
            existing = session.get(Setting, key)
            if existing:
                existing.value_json = value_json
                if "category" in item:
                    existing.category = item["category"]
                if "description" in item:
                    existing.description = item["description"]
            else:
                session.add(Setting(
                    key=key,
                    value_json=value_json,
                    category=item.get("category", "general"),
                    description=item.get("description"),
                ))
            count += 1
        session.commit()

    send_notify(engine, "settings")
    return count
