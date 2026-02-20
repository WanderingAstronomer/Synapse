"""
synapse.services.marketplace_service — Marketplace Purchase & Inventory Logic
==============================================================================

Implements the cosmetic marketplace purchase pipeline, inventory reads,
and equip/unequip operations.  Admin CRUD lives in ``admin_service``.

Purchase invariants (non-negotiable)
-------------------------------------
- **Atomic deduction**: currency is debited via ``UPDATE ... WHERE balance >= cost``
  in a single SQL statement.  No check-then-act.
- **Idempotency**: duplicate purchases are rejected via the
  ``uq_user_inventory_user_item`` unique constraint.  The caller receives
  ``AlreadyOwnedError`` rather than a DB error leaking to the API layer.
- **Flag gate**: all purchase paths check ``flags.marketplace_enabled``.
  If the flag is absent or falsy the endpoint is unavailable.
- **Expiry guard**: items with ``expires_at < now()`` are treated as inactive
  and cannot be purchased.

Bot role IPC
------------
When a ``DISCORD_ROLE`` purchase succeeds, ``notify_role_assignment``
publishes a ``synapse_events`` payload so the bot cog can assign the Discord
role asynchronously.  Role assignment failure never fails the purchase — the
inventory record is the source of truth.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from synapse.database.models import (
    MarketplaceItem,
    MarketplaceItemType,
    Setting,
    User,
    UserInventory,
)
from synapse.engine.cache import send_event_notify

if TYPE_CHECKING:
    from sqlalchemy import Engine

ROLE_ASSIGN_EVENT_TYPE = "marketplace_role_assignment"

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Domain exceptions
# ---------------------------------------------------------------------------


class MarketplaceDisabledError(ValueError):
    """Raised when the marketplace feature flag is off."""


class ItemNotFoundError(ValueError):
    """Raised when the item does not exist or is not purchasable."""


class ItemExpiredError(ValueError):
    """Raised when the item's ``expires_at`` has passed."""


class InsufficientFundsError(ValueError):
    """Raised when the user cannot afford the item with the chosen currency."""


class AlreadyOwnedError(ValueError):
    """Raised when the user already owns this item."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_marketplace_enabled(session: Session, guild_id: int) -> bool:  # noqa: ARG001
    """Read the ``flags.marketplace_enabled`` setting from the DB.

    ``guild_id`` is accepted (but unused) to preserve the call-site
    signature for future multi-guild support where settings become
    guild-scoped.
    """
    row = session.get(Setting, "flags.marketplace_enabled")
    if row is None:
        return False
    try:
        return bool(json.loads(row.value_json))
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_shop_items(
    engine: Engine,
    guild_id: int,
) -> list[MarketplaceItem]:
    """Return active, non-expired marketplace items for the guild.

    Parameters
    ----------
    engine : Engine
    guild_id : int

    Returns
    -------
    list[MarketplaceItem]
        Sorted by name.  Expired items are excluded.
    """
    now = datetime.now(UTC)
    with Session(engine) as session:
        rows = session.scalars(
            select(MarketplaceItem)
            .where(
                MarketplaceItem.guild_id == guild_id,
                MarketplaceItem.active.is_(True),
            )
            .order_by(MarketplaceItem.name)
        ).all()
        result = [r for r in rows if r.expires_at is None or r.expires_at > now]
        for r in result:
            session.expunge(r)
        return result


def get_all_admin_items(
    engine: Engine,
    guild_id: int,
) -> list[MarketplaceItem]:
    """Return ALL marketplace items for admin view (including inactive/expired).

    Parameters
    ----------
    engine : Engine
    guild_id : int

    Returns
    -------
    list[MarketplaceItem]
    """
    with Session(engine) as session:
        rows = session.scalars(
            select(MarketplaceItem)
            .where(MarketplaceItem.guild_id == guild_id)
            .order_by(MarketplaceItem.name)
        ).all()
        for r in rows:
            session.expunge(r)
        return list(rows)


def purchase_item(
    engine: Engine,
    user_id: int,
    guild_id: int,
    item_id: int,
    currency: Literal["xp", "gold"],
) -> UserInventory:
    """Atomically purchase a marketplace item.

    Parameters
    ----------
    engine : Engine
    user_id : int
        The purchasing member's Discord user ID.
    guild_id : int
    item_id : int
        The ``MarketplaceItem.id`` to purchase.
    currency : "xp" | "gold"
        Which balance to deduct.  Both must be valid choices for the item.

    Returns
    -------
    UserInventory
        The newly created inventory record.

    Raises
    ------
    MarketplaceDisabledError
        Feature flag not set.
    ItemNotFoundError
        Item does not exist, is inactive, or belongs to another guild.
    ItemExpiredError
        Item's ``expires_at`` is in the past.
    InsufficientFundsError
        User does not have enough of the chosen currency.
    AlreadyOwnedError
        User already owns this item (idempotency constraint).
    ValueError
        Chosen currency is not offered by this item.
    """
    now = datetime.now(UTC)

    with Session(engine) as session:
        # ── Feature flag ───────────────────────────────────────────────────
        if not _is_marketplace_enabled(session, guild_id):
            raise MarketplaceDisabledError("Marketplace is not currently enabled.")

        # ── Validate item ──────────────────────────────────────────────────
        item = session.get(MarketplaceItem, item_id)
        if item is None or not item.active or item.guild_id != guild_id:
            raise ItemNotFoundError(f"Item {item_id} not found or not available.")

        if item.expires_at is not None and item.expires_at <= now:
            raise ItemExpiredError(f"Item {item_id!r} has expired.")

        # ── Validate currency selection ────────────────────────────────────
        if currency == "xp":
            cost = item.cost_xp
            if cost is None:
                raise ValueError("This item cannot be purchased with XP.")
        else:  # gold
            cost = item.cost_gold
            if cost is None:
                raise ValueError("This item cannot be purchased with Gold.")

        # ── Atomic deduction (no check-then-act) ──────────────────────────
        # UPDATE users SET xp = xp - :cost WHERE id = :uid AND xp >= :cost
        # rowcount == 0 → insufficient funds.
        col = User.xp if currency == "xp" else User.gold
        stmt = (
            update(User)
            .where(User.id == user_id, col >= cost)
            .values({col.key: col - cost})
            .execution_options(synchronize_session=False)
        )
        result = session.execute(stmt)
        if result.rowcount == 0:
            raise InsufficientFundsError(f"Insufficient {currency} to purchase '{item.name}'.")

        # ── Idempotent inventory insert ────────────────────────────────────
        inventory = UserInventory(
            user_id=user_id,
            item_id=item_id,
            guild_id=guild_id,
        )
        try:
            with session.begin_nested():  # SAVEPOINT
                session.add(inventory)
                session.flush()
        except IntegrityError:
            # Already owned — roll back deduction and raise gracefully
            session.rollback()
            raise AlreadyOwnedError(f"User {user_id} already owns item {item_id}.")

        session.commit()
        session.refresh(inventory)
        session.expunge(inventory)

    # ── Bot role IPC — fire-and-forget, does NOT affect purchase outcome ───
    if (
        item.item_type == MarketplaceItemType.DISCORD_ROLE
        and item.discord_role_id is not None
    ):
        try:
            notify_role_assignment(engine, user_id, guild_id, item.discord_role_id)
        except Exception:
            logger.warning(
                "Role assignment notify failed for user=%d item=%d — "
                "purchase recorded, bot will retry on next poll.",
                user_id,
                item_id,
                exc_info=True,
            )

    return inventory


def notify_role_assignment(
    engine: Engine,
    user_id: int,
    guild_id: int,
    discord_role_id: int,
) -> None:
    """Publish a cross-service event so the bot can assign a Discord role.

    Parameters
    ----------
    engine : Engine
    user_id : int
    guild_id : int
    discord_role_id : int
    """
    send_event_notify(
        engine,
        {
            "type": ROLE_ASSIGN_EVENT_TYPE,
            "user_id": user_id,
            "guild_id": guild_id,
            "discord_role_id": discord_role_id,
        },
    )


def get_user_inventory(
    engine: Engine,
    user_id: int,
    guild_id: int,
) -> list[UserInventory]:
    """Return the user's owned inventory items for the guild.

    Parameters
    ----------
    engine : Engine
    user_id : int
    guild_id : int

    Returns
    -------
    list[UserInventory]
        Ordered by purchase date descending.
    """
    with Session(engine) as session:
        rows = session.scalars(
            select(UserInventory)
            .where(
                UserInventory.user_id == user_id,
                UserInventory.guild_id == guild_id,
            )
            .order_by(UserInventory.purchased_at.desc())
        ).all()
        for r in rows:
            session.expunge(r)
        return list(rows)


def set_equipped(
    engine: Engine,
    user_id: int,
    item_id: int,
    guild_id: int,
    equipped: bool,
) -> UserInventory:
    """Equip or unequip a cosmetic item.

    Parameters
    ----------
    engine : Engine
    user_id : int
    item_id : int
    guild_id : int
    equipped : bool
        ``True`` to equip, ``False`` to unequip.

    Returns
    -------
    UserInventory
        Updated inventory record.

    Raises
    ------
    ItemNotFoundError
        The user does not own this item.
    """
    with Session(engine) as session:
        inv = session.scalar(
            select(UserInventory).where(
                UserInventory.user_id == user_id,
                UserInventory.item_id == item_id,
                UserInventory.guild_id == guild_id,
            )
        )
        if inv is None:
            raise ItemNotFoundError(f"User {user_id} does not own item {item_id}.")
        inv.is_equipped = equipped
        session.commit()
        session.refresh(inv)
        session.expunge(inv)
        return inv
