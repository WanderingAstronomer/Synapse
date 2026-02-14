"""
synapse.api.routes.layouts -- Layout & Card endpoints
===========================================================

Public endpoints:
    GET /layouts/{page_slug}     — Page layout with cards (for rendering)
    GET /layouts                 — All page layouts (public, for sidebar names)

Admin endpoints:
    PUT  /admin/layouts/{page_slug}   — Save layout (display name, card order)
    PATCH /admin/cards/{card_id}      — Update a single card config
    POST  /admin/cards                — Add a new card
    DELETE /admin/cards/{card_id}     — Remove a card
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from synapse.api.deps import get_config, get_session
from synapse.api.rate_limit import rate_limited_admin
from synapse.services import layout_service

router = APIRouter(tags=["layouts"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------
class LayoutUpdate(BaseModel):
    display_name: str | None = None
    layout_json: dict | None = None
    card_order: list[str] | None = None


class CardCreate(BaseModel):
    page_layout_id: str
    card_type: str
    position: int = 0
    grid_span: int = Field(default=1, ge=1, le=3)
    title: str | None = None
    subtitle: str | None = None
    config_json: dict | None = None


class CardUpdate(BaseModel):
    card_type: str | None = None
    position: int | None = None
    grid_span: int | None = Field(default=None, ge=1, le=3)
    title: str | None = None
    subtitle: str | None = None
    config_json: dict | None = None
    visible: bool | None = None


# ---------------------------------------------------------------------------
# Public — layouts & brand
# ---------------------------------------------------------------------------
@router.get("/layouts")
def list_layouts(session: Session = Depends(get_session)):
    """Return all page layouts (for sidebar navigation labels)."""
    cfg = get_config()
    return layout_service.get_all_layouts(session, cfg.guild_id)


@router.get("/layouts/{page_slug}")
def get_layout(page_slug: str, session: Session = Depends(get_session)):
    """Return a page layout with its cards."""
    cfg = get_config()
    layout = layout_service.get_layout(session, cfg.guild_id, page_slug)
    if not layout:
        raise HTTPException(404, f"Layout not found: {page_slug}")
    return layout


@router.get("/metrics/available")
def get_available_metrics():
    """Return the list of metric keys available for metric card configuration."""
    return [
        {"key": "total_members", "label": "Total Members", "icon": ""},
        {"key": "total_xp", "label": "Total XP", "icon": ""},
        {"key": "total_gold", "label": "Total Gold", "icon": ""},
        {"key": "active_users_7d", "label": "Active (7d)", "icon": ""},
        {"key": "active_users_30d", "label": "Active (30d)", "icon": ""},
        {"key": "top_level", "label": "Top Level", "icon": ""},
        {"key": "total_achievements", "label": "Achievements Earned", "icon": ""},
    ]


# ---------------------------------------------------------------------------
# Admin — layout mutations
# ---------------------------------------------------------------------------
@router.put("/admin/layouts/{page_slug}")
def update_layout(
    page_slug: str,
    body: LayoutUpdate,
    admin: dict = Depends(rate_limited_admin),
    session: Session = Depends(get_session),
):
    """Save layout changes (display name, card order, grid positions)."""
    cfg = get_config()
    try:
        result = layout_service.save_layout(
            session,
            cfg.guild_id,
            page_slug,
            display_name=body.display_name,
            layout_json=body.layout_json,
            card_order=body.card_order,
            actor_id=int(admin["sub"]),
        )
        session.commit()
        return result
    except ValueError as exc:
        raise HTTPException(404, str(exc))


# ---------------------------------------------------------------------------
# Admin — card mutations
# ---------------------------------------------------------------------------
@router.post("/admin/cards")
def create_card(
    body: CardCreate,
    admin: dict = Depends(rate_limited_admin),
    session: Session = Depends(get_session),
):
    """Add a new card to a page layout."""
    result = layout_service.create_card(
        session,
        body.page_layout_id,
        card_type=body.card_type,
        position=body.position,
        grid_span=body.grid_span,
        title=body.title,
        subtitle=body.subtitle,
        config_json=body.config_json,
        actor_id=int(admin["sub"]),
    )
    session.commit()
    return result


@router.patch("/admin/cards/{card_id}")
def update_card(
    card_id: str,
    body: CardUpdate,
    admin: dict = Depends(rate_limited_admin),
    session: Session = Depends(get_session),
):
    """Update a single card's configuration."""
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(400, "No fields to update")
    try:
        result = layout_service.update_card(
            session,
            card_id,
            updates=updates,
            actor_id=int(admin["sub"]),
        )
        session.commit()
        return result
    except ValueError as exc:
        raise HTTPException(404, str(exc))


@router.delete("/admin/cards/{card_id}")
def delete_card(
    card_id: str,
    admin: dict = Depends(rate_limited_admin),
    session: Session = Depends(get_session),
):
    """Remove a card from its page layout."""
    deleted = layout_service.delete_card(
        session, card_id, actor_id=int(admin["sub"])
    )
    if not deleted:
        raise HTTPException(404, f"Card not found: {card_id}")
    session.commit()
    return {"deleted": True}

