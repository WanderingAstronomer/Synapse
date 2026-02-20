"""
synapse.api.routes.marketplace — Shop & Admin Marketplace Endpoints
====================================================================

Two routers in one file:

``shop_router``  (prefix ``/shop``)
    - ``GET  /shop/items``              — public list of active items
    - ``POST /shop/{item_id}/purchase`` — member auth required
    - ``GET  /shop/inventory``          — member auth required
    - ``PATCH /shop/inventory/{item_id}/equip``   — member auth
    - ``PATCH /shop/inventory/{item_id}/unequip`` — member auth

``admin_marketplace_router``  (prefix ``/admin``)
    - ``GET    /admin/marketplace/items``
    - ``POST   /admin/marketplace/items``
    - ``PATCH  /admin/marketplace/items/{item_id}``
    - ``PATCH  /admin/marketplace/items/{item_id}/deactivate``
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from synapse.api.deps import (
    get_config,
    get_engine,
    get_member_context,
    get_session,
)
from synapse.api.rate_limit import rate_limited_admin
from synapse.config import SynapseConfig
from synapse.services import admin_service
from synapse.services.marketplace_service import (
    AlreadyOwnedError,
    InsufficientFundsError,
    ItemExpiredError,
    ItemNotFoundError,
    MarketplaceDisabledError,
    get_all_admin_items,
    get_shop_items,
    get_user_inventory,
    purchase_item,
    set_equipped,
)

if TYPE_CHECKING:
    from synapse.database.models import MarketplaceItem, UserInventory

shop_router = APIRouter(prefix="/shop", tags=["shop"])
admin_marketplace_router = APIRouter(prefix="/admin", tags=["admin"])
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class PurchaseRequest(BaseModel):
    currency: str = "gold"  # "xp" | "gold"


class ItemCreate(BaseModel):
    name: str
    description: str | None = None
    item_type: str = "COSMETIC_BADGE"
    cost_xp: int | None = None
    cost_gold: int | None = None
    rarity_id: int | None = None
    overlay_id: int | None = None
    image_url: str | None = None
    discord_role_id: int | None = None
    season_id: int | None = None
    expires_at: str | None = None  # ISO-8601 datetime string


class ItemUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    item_type: str | None = None
    cost_xp: int | None = None
    cost_gold: int | None = None
    rarity_id: int | None = None
    overlay_id: int | None = None
    image_url: str | None = None
    discord_role_id: int | None = None
    season_id: int | None = None
    active: bool | None = None
    expires_at: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _item_dict(item: MarketplaceItem) -> dict:
    return {
        "id": item.id,
        "name": item.name,
        "description": item.description,
        "item_type": item.item_type,
        "cost_xp": item.cost_xp,
        "cost_gold": item.cost_gold,
        "rarity_id": item.rarity_id,
        "overlay_id": item.overlay_id,
        "image_url": item.image_url,
        "discord_role_id": (str(item.discord_role_id) if item.discord_role_id else None),
        "season_id": item.season_id,
        "active": item.active,
        "expires_at": item.expires_at.isoformat() if item.expires_at else None,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


def _inventory_dict(inv: UserInventory) -> dict:
    return {
        "id": inv.id,
        "item_id": inv.item_id,
        "guild_id": str(inv.guild_id),
        "is_equipped": inv.is_equipped,
        "purchased_at": inv.purchased_at.isoformat() if inv.purchased_at else None,
        "expires_at": inv.expires_at.isoformat() if inv.expires_at else None,
    }


# ---------------------------------------------------------------------------
# Shop — public / member endpoints
# ---------------------------------------------------------------------------


@shop_router.get("/items")
def list_shop_items(
    session: Session = Depends(get_session),
    cfg: SynapseConfig = Depends(get_config),
):
    """List active, non-expired shop items.  No authentication required."""
    engine = session.get_bind()
    items = get_shop_items(engine, cfg.guild_id)
    return {"items": [_item_dict(i) for i in items]}


@shop_router.post("/{item_id}/purchase", status_code=201)
def purchase(
    item_id: int,
    body: PurchaseRequest,
    member: dict = Depends(get_member_context),
    engine=Depends(get_engine),
    cfg: SynapseConfig = Depends(get_config),
):
    """Purchase an item.  Requires guild member authentication."""
    currency = body.currency.lower()
    if currency not in ("xp", "gold"):
        raise HTTPException(400, "currency must be 'xp' or 'gold'")

    user_id = int(member["sub"])
    try:
        inv = purchase_item(engine, user_id, cfg.guild_id, item_id, currency)  # type: ignore[arg-type]
    except MarketplaceDisabledError:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Marketplace is not enabled.")
    except ItemNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Item not found.")
    except ItemExpiredError:
        raise HTTPException(status.HTTP_410_GONE, "This item has expired.")
    except InsufficientFundsError as exc:
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, str(exc))
    except AlreadyOwnedError:
        raise HTTPException(status.HTTP_409_CONFLICT, "You already own this item.")
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    return _inventory_dict(inv)


@shop_router.get("/inventory")
def list_inventory(
    member: dict = Depends(get_member_context),
    engine=Depends(get_engine),
    cfg: SynapseConfig = Depends(get_config),
):
    """List the authenticated member's purchased items."""
    user_id = int(member["sub"])
    items = get_user_inventory(engine, user_id, cfg.guild_id)
    return {"inventory": [_inventory_dict(i) for i in items]}


@shop_router.patch("/inventory/{item_id}/equip")
def equip(
    item_id: int,
    member: dict = Depends(get_member_context),
    engine=Depends(get_engine),
    cfg: SynapseConfig = Depends(get_config),
):
    """Equip a cosmetic item from the member's inventory."""
    user_id = int(member["sub"])
    try:
        inv = set_equipped(engine, user_id, item_id, cfg.guild_id, equipped=True)
    except ItemNotFoundError:
        raise HTTPException(404, "Item not in inventory.")
    return _inventory_dict(inv)


@shop_router.patch("/inventory/{item_id}/unequip")
def unequip(
    item_id: int,
    member: dict = Depends(get_member_context),
    engine=Depends(get_engine),
    cfg: SynapseConfig = Depends(get_config),
):
    """Unequip a cosmetic item."""
    user_id = int(member["sub"])
    try:
        inv = set_equipped(engine, user_id, item_id, cfg.guild_id, equipped=False)
    except ItemNotFoundError:
        raise HTTPException(404, "Item not in inventory.")
    return _inventory_dict(inv)


# ---------------------------------------------------------------------------
# Admin — marketplace management endpoints
# ---------------------------------------------------------------------------


@admin_marketplace_router.get("/marketplace/items")
def admin_list_items(
    admin: dict = Depends(rate_limited_admin),
    engine=Depends(get_engine),
    cfg: SynapseConfig = Depends(get_config),
):
    """List all marketplace items (including inactive and expired)."""
    items = get_all_admin_items(engine, cfg.guild_id)
    return {"items": [_item_dict(i) for i in items]}


@admin_marketplace_router.post("/marketplace/items", status_code=201)
def admin_create_item(
    body: ItemCreate,
    admin: dict = Depends(rate_limited_admin),
    engine=Depends(get_engine),
    cfg: SynapseConfig = Depends(get_config),
):
    """Create a new marketplace item."""
    from datetime import datetime

    # Parse optional ISO-8601 expires_at
    expires_at = None
    if body.expires_at:
        try:
            expires_at = datetime.fromisoformat(body.expires_at)
            if expires_at.tzinfo is None:
                from datetime import UTC
                expires_at = expires_at.replace(tzinfo=UTC)
        except ValueError:
            raise HTTPException(400, "Invalid expires_at format.  Use ISO-8601.")

    item = admin_service.create_marketplace_item(
        engine,
        guild_id=cfg.guild_id,
        name=body.name,
        description=body.description,
        item_type=body.item_type,
        cost_xp=body.cost_xp,
        cost_gold=body.cost_gold,
        rarity_id=body.rarity_id,
        overlay_id=body.overlay_id,
        image_url=body.image_url,
        discord_role_id=body.discord_role_id,
        season_id=body.season_id,
        expires_at=expires_at,
        actor_id=int(admin["sub"]),
    )

    return _item_dict(item)


@admin_marketplace_router.patch("/marketplace/items/{item_id}")
def admin_update_item(
    item_id: int,
    body: ItemUpdate,
    admin: dict = Depends(rate_limited_admin),
    engine=Depends(get_engine),
):
    """Update mutable fields on a marketplace item."""
    from datetime import datetime

    kwargs = body.model_dump(exclude_unset=True)
    if not kwargs:
        raise HTTPException(400, "No fields to update.")

    # Parse expires_at if present
    if "expires_at" in kwargs:
        try:
            kwargs["expires_at"] = datetime.fromisoformat(kwargs["expires_at"])
            if kwargs["expires_at"].tzinfo is None:
                from datetime import UTC
                kwargs["expires_at"] = kwargs["expires_at"].replace(tzinfo=UTC)
        except ValueError:
            raise HTTPException(400, "Invalid expires_at format.  Use ISO-8601.")

    item = admin_service.update_marketplace_item(
        engine,
        item_id,
        actor_id=int(admin["sub"]),
        **kwargs,
    )
    if item is None:
        raise HTTPException(404, "Item not found.")
    return _item_dict(item)


@admin_marketplace_router.patch("/marketplace/items/{item_id}/deactivate", status_code=200)
def admin_deactivate_item(
    item_id: int,
    admin: dict = Depends(rate_limited_admin),
    engine=Depends(get_engine),
):
    """Soft-delete a marketplace item (set active=False)."""
    item = admin_service.deactivate_marketplace_item(
        engine,
        item_id,
        actor_id=int(admin["sub"]),
    )
    if item is None:
        raise HTTPException(404, "Item not found.")
    return _item_dict(item)
