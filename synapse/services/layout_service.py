"""
synapse.services.layout_service — Page layout and card management
===================================================================

CRUD operations for the card system.  Each page gets a ``PageLayout``
row with ordered ``CardConfig`` children.

Default layouts are seeded once during bootstrap (setup_service).
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from synapse.constants import ALLOWED_CARD_FIELDS
from synapse.database.models import (
    AdminLog,
    CardConfig,
    PageLayout,
)

# ---------------------------------------------------------------------------
# Default page definitions — seeded on first GET
# ---------------------------------------------------------------------------
DEFAULT_PAGES: list[dict[str, Any]] = [
    {
        "page_slug": "dashboard",
        "display_name": "Dashboard",
        "cards": [
            {"card_type": "hero_banner", "position": 0, "grid_span": 3,
             "title": "Welcome", "subtitle": "Community Dashboard"},
            {"card_type": "metric", "position": 1, "grid_span": 1,
             "title": "Total Members", "config_json": {"metric_key": "total_members"}},
            {"card_type": "metric", "position": 2, "grid_span": 1,
             "title": "Total XP", "config_json": {"metric_key": "total_xp"}},
            {"card_type": "metric", "position": 3, "grid_span": 1,
             "title": "Total Gold", "config_json": {"metric_key": "total_gold"}},
            {"card_type": "top_members", "position": 4, "grid_span": 2,
             "title": "Top Members"},
            {"card_type": "recent_achievements", "position": 5, "grid_span": 1,
             "title": "Recent Achievements"},
        ],
    },
    {
        "page_slug": "leaderboard",
        "display_name": "Leaderboard",
        "cards": [
            {"card_type": "leaderboard_table", "position": 0, "grid_span": 3,
             "title": "Leaderboard"},
        ],
    },
    {
        "page_slug": "activity",
        "display_name": "Activity",
        "cards": [
            {"card_type": "activity_feed", "position": 0, "grid_span": 3,
             "title": "Recent Activity"},
        ],
    },
    {
        "page_slug": "achievements",
        "display_name": "Achievements",
        "cards": [
            {"card_type": "achievement_grid", "position": 0, "grid_span": 3,
             "title": "Achievements"},
        ],
    },
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def seed_default_layouts(session: Session, guild_id: int) -> None:
    """Insert default page layouts and cards if none exist for the guild.

    Called once during bootstrap (setup_service.bootstrap_guild).
    NOT called lazily on GET — if layouts are missing after setup,
    that is a real error.
    """
    existing = session.execute(
        select(PageLayout.page_slug).where(PageLayout.guild_id == guild_id)
    ).scalars().all()
    existing_slugs = set(existing)

    for page_def in DEFAULT_PAGES:
        if page_def["page_slug"] in existing_slugs:
            continue
        layout = PageLayout(
            id=str(uuid4()),
            guild_id=guild_id,
            page_slug=page_def["page_slug"],
            display_name=page_def["display_name"],
        )
        session.add(layout)
        session.flush()  # Ensure layout.id is available for FK
        for card_def in page_def.get("cards", []):
            card = CardConfig(
                id=str(uuid4()),
                page_layout_id=layout.id,
                card_type=card_def["card_type"],
                position=card_def.get("position", 0),
                grid_span=card_def.get("grid_span", 1),
                title=card_def.get("title"),
                subtitle=card_def.get("subtitle"),
                config_json=card_def.get("config_json"),
            )
            session.add(card)
    session.flush()


# ---------------------------------------------------------------------------
# Page Layout CRUD
# ---------------------------------------------------------------------------
def get_layout(session: Session, guild_id: int, page_slug: str) -> dict[str, Any] | None:
    """Get a page layout with its cards."""
    layout = session.execute(
        select(PageLayout)
        .options(joinedload(PageLayout.cards))
        .where(PageLayout.guild_id == guild_id, PageLayout.page_slug == page_slug)
    ).unique().scalar_one_or_none()

    if not layout:
        return None

    return _layout_to_dict(layout)


def get_all_layouts(session: Session, guild_id: int) -> list[dict[str, Any]]:
    """Get all page layouts for a guild."""
    layouts = session.execute(
        select(PageLayout)
        .options(joinedload(PageLayout.cards))
        .where(PageLayout.guild_id == guild_id)
        .order_by(PageLayout.page_slug)
    ).unique().scalars().all()

    return [_layout_to_dict(layout) for layout in layouts]


def save_layout(
    session: Session,
    guild_id: int,
    page_slug: str,
    *,
    display_name: str | None = None,
    layout_json: dict | None = None,
    card_order: list[str] | None = None,
    actor_id: int | None = None,
) -> dict[str, Any]:
    """Update a page layout.  Optionally reorders cards by ``card_order`` IDs."""
    layout = session.execute(
        select(PageLayout)
        .options(joinedload(PageLayout.cards))
        .where(PageLayout.guild_id == guild_id, PageLayout.page_slug == page_slug)
    ).unique().scalar_one_or_none()

    if not layout:
        raise ValueError(f"Layout not found: {page_slug}")

    before = _layout_to_dict(layout)

    if display_name is not None:
        layout.display_name = display_name
    if layout_json is not None:
        layout.layout_json = layout_json
    if actor_id is not None:
        layout.updated_by = actor_id

    # Reorder cards if card_order provided
    if card_order is not None:
        card_map = {c.id: c for c in layout.cards}
        for pos, card_id in enumerate(card_order):
            if card_id in card_map:
                card_map[card_id].position = pos

    session.flush()

    after = _layout_to_dict(layout)
    if actor_id and before != after:
        session.add(AdminLog(
            actor_id=actor_id,
            action_type="UPDATE",
            target_table="page_layouts",
            target_id=layout.id,
            before_snapshot=before,
            after_snapshot=after,
        ))

    return after


# ---------------------------------------------------------------------------
# Card CRUD
# ---------------------------------------------------------------------------
def create_card(
    session: Session,
    page_layout_id: str,
    *,
    card_type: str,
    position: int = 0,
    grid_span: int = 1,
    title: str | None = None,
    subtitle: str | None = None,
    config_json: dict | None = None,
    actor_id: int | None = None,
) -> dict[str, Any]:
    """Add a new card to a page layout."""
    card = CardConfig(
        id=str(uuid4()),
        page_layout_id=page_layout_id,
        card_type=card_type,
        position=position,
        grid_span=grid_span,
        title=title,
        subtitle=subtitle,
        config_json=config_json,
    )
    session.add(card)
    session.flush()

    result = _card_to_dict(card)
    if actor_id:
        session.add(AdminLog(
            actor_id=actor_id,
            action_type="CREATE",
            target_table="card_configs",
            target_id=card.id,
            after_snapshot=result,
        ))

    return result


def update_card(
    session: Session,
    card_id: str,
    *,
    updates: dict[str, Any],
    actor_id: int | None = None,
) -> dict[str, Any]:
    """Patch a card's configuration."""
    card = session.get(CardConfig, card_id)
    if not card:
        raise ValueError(f"Card not found: {card_id}")

    before = _card_to_dict(card)

    allowed = ALLOWED_CARD_FIELDS
    for key, value in updates.items():
        if key in allowed:
            setattr(card, key, value)

    session.flush()

    after = _card_to_dict(card)
    if actor_id and before != after:
        session.add(AdminLog(
            actor_id=actor_id,
            action_type="UPDATE",
            target_table="card_configs",
            target_id=card.id,
            before_snapshot=before,
            after_snapshot=after,
        ))

    return after


def delete_card(
    session: Session,
    card_id: str,
    *,
    actor_id: int | None = None,
) -> bool:
    """Remove a card from its page layout."""
    card = session.get(CardConfig, card_id)
    if not card:
        return False

    snapshot = _card_to_dict(card)
    session.delete(card)
    session.flush()

    if actor_id:
        session.add(AdminLog(
            actor_id=actor_id,
            action_type="DELETE",
            target_table="card_configs",
            target_id=card_id,
            before_snapshot=snapshot,
        ))

    return True


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------
def _layout_to_dict(layout: PageLayout) -> dict[str, Any]:
    return {
        "id": layout.id,
        "guild_id": layout.guild_id,
        "page_slug": layout.page_slug,
        "display_name": layout.display_name,
        "layout_json": layout.layout_json,
        "updated_by": layout.updated_by,
        "updated_at": layout.updated_at.isoformat() if layout.updated_at else None,
        "cards": [_card_to_dict(c) for c in sorted(layout.cards, key=lambda c: c.position)],
    }


def _card_to_dict(card: CardConfig) -> dict[str, Any]:
    return {
        "id": card.id,
        "page_layout_id": card.page_layout_id,
        "card_type": card.card_type,
        "position": card.position,
        "grid_span": card.grid_span,
        "title": card.title,
        "subtitle": card.subtitle,
        "config_json": card.config_json,
        "visible": card.visible,
    }
