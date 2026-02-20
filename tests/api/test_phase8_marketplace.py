"""
tests.test_phase8_marketplace — Phase 8: Marketplace Service Tests
===================================================================

Covers the marketplace purchase pipeline, inventory reads, equip/unequip,
and the Discord role-assignment cog logic.

All tests are mock-based — no real database, no Docker, no Discord required.
"""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

from synapse.services.marketplace_service import (
    AlreadyOwnedError,
    InsufficientFundsError,
    ItemExpiredError,
    ItemNotFoundError,
    MarketplaceDisabledError,
    get_all_admin_items,
    get_shop_items,
    get_user_inventory,
    notify_role_assignment,
    purchase_item,
    set_equipped,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_session_ctx(session_obj: MagicMock) -> MagicMock:
    """Wrap a MagicMock so ``with Session(engine) as s:`` works."""
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=session_obj)
    ctx.__exit__ = MagicMock(return_value=False)
    return ctx


def _make_setting(value: bool) -> MagicMock:
    import json

    s = MagicMock()
    s.value_json = json.dumps(value)
    return s


def _make_item(
    item_id: int = 1,
    guild_id: int = 100,
    active: bool = True,
    expires_at=None,
    cost_xp: int | None = 500,
    cost_gold: int | None = 100,
    item_type_str: str = "cosmetic_badge",
    discord_role_id: int | None = None,
    name: str = "Test Badge",
) -> MagicMock:
    from synapse.database.models import MarketplaceItemType

    item = MagicMock()
    item.id = item_id
    item.guild_id = guild_id
    item.active = active
    item.expires_at = expires_at
    item.cost_xp = cost_xp
    item.cost_gold = cost_gold
    item.discord_role_id = discord_role_id
    item.name = name
    item.item_type = MarketplaceItemType.COSMETIC_BADGE
    return item


def _make_inventory(user_id: int = 42, item_id: int = 1) -> MagicMock:
    inv = MagicMock()
    inv.user_id = user_id
    inv.item_id = item_id
    inv.is_equipped = False
    return inv


@contextmanager
def _savepoint_ctx(raises: Exception | None = None):
    """Context manager mimicking session.begin_nested() SAVEPOINT."""
    if raises is None:
        yield
    else:
        yield  # Enter without error, but flush will raise via mock


# ---------------------------------------------------------------------------
# TestGetShopItems
# ---------------------------------------------------------------------------


class TestGetShopItems:
    def test_returns_active_items(self):
        from datetime import UTC, datetime, timedelta

        item = _make_item(expires_at=datetime.now(UTC) + timedelta(days=1))
        session = MagicMock()
        session.scalars.return_value.all.return_value = [item]

        with patch(
            "synapse.services.marketplace_service.Session",
            return_value=_mock_session_ctx(session),
        ):
            result = get_shop_items(MagicMock(), guild_id=100)

        assert len(result) == 1
        assert result[0] is item

    def test_filters_expired_items(self):
        from datetime import UTC, datetime, timedelta

        item_valid = _make_item(item_id=1, expires_at=datetime.now(UTC) + timedelta(days=1))
        item_expired = _make_item(item_id=2, expires_at=datetime.now(UTC) - timedelta(seconds=1))
        session = MagicMock()
        session.scalars.return_value.all.return_value = [item_valid, item_expired]

        with patch(
            "synapse.services.marketplace_service.Session",
            return_value=_mock_session_ctx(session),
        ):
            result = get_shop_items(MagicMock(), guild_id=100)

        ids = [r.id for r in result]
        assert 1 in ids
        assert 2 not in ids

    def test_returns_empty_when_no_items(self):
        session = MagicMock()
        session.scalars.return_value.all.return_value = []

        with patch(
            "synapse.services.marketplace_service.Session",
            return_value=_mock_session_ctx(session),
        ):
            result = get_shop_items(MagicMock(), guild_id=100)

        assert result == []

    def test_item_with_no_expiry_is_included(self):
        item = _make_item(expires_at=None)
        session = MagicMock()
        session.scalars.return_value.all.return_value = [item]

        with patch(
            "synapse.services.marketplace_service.Session",
            return_value=_mock_session_ctx(session),
        ):
            result = get_shop_items(MagicMock(), guild_id=100)

        assert len(result) == 1


class TestGetAllAdminItems:
    def test_returns_all_items_including_inactive(self):
        items = [_make_item(item_id=i, active=(i % 2 == 0)) for i in range(1, 5)]
        session = MagicMock()
        session.scalars.return_value.all.return_value = items

        with patch(
            "synapse.services.marketplace_service.Session",
            return_value=_mock_session_ctx(session),
        ):
            result = get_all_admin_items(MagicMock(), guild_id=100)

        assert len(result) == 4


# ---------------------------------------------------------------------------
# TestPurchaseItem
# ---------------------------------------------------------------------------


class TestPurchaseItem:
    """Tests for the purchase_item() pipeline."""

    def _buy(self, session: MagicMock, **kwargs) -> MagicMock:
        """Helper: call purchase_item with session mocked."""
        defaults = {
            "engine": MagicMock(),
            "user_id": 42,
            "guild_id": 100,
            "item_id": 1,
            "currency": "xp",
        }
        defaults.update(kwargs)

        with patch(
            "synapse.services.marketplace_service.Session",
            return_value=_mock_session_ctx(session),
        ):
            return purchase_item(**defaults)

    def _make_session_enabled(
        self,
        item: MagicMock,
        rowcount: int = 1,
        begin_nested_raises: Exception | None = None,
    ) -> MagicMock:
        """Build a ready-pass session with marketplace enabled."""
        session = MagicMock()
        # Feature flag
        session.get.side_effect = lambda model, key: (
            _make_setting(True) if "Setting" in str(model) or hasattr(model, "key") else item
        )

        # Two session.get calls: Setting, then MarketplaceItem
        _call_count = {"n": 0}

        def get_side(cls, pk):
            n = _call_count["n"]
            _call_count["n"] += 1
            if n == 0:
                # First call: Setting("flags.marketplace_enabled")
                return _make_setting(True)
            # Second call: MarketplaceItem
            return item

        session.get.side_effect = get_side

        # execute() for the atomic UPDATE
        exec_result = MagicMock()
        exec_result.rowcount = rowcount
        session.execute.return_value = exec_result

        # begin_nested() SAVEPOINT context manager
        if begin_nested_raises is not None:
            savepoint = MagicMock()
            savepoint.__enter__ = MagicMock(return_value=None)
            savepoint.__exit__ = MagicMock(return_value=False)
            session.flush.side_effect = begin_nested_raises
        else:
            savepoint = MagicMock()
            savepoint.__enter__ = MagicMock(return_value=None)
            savepoint.__exit__ = MagicMock(return_value=False)

        session.begin_nested.return_value = savepoint

        # refresh + expunge no-ops
        inv = _make_inventory()
        session.add = MagicMock()

        return session, inv

    def test_raises_when_marketplace_disabled(self):
        session = MagicMock()
        session.get.return_value = None  # No Setting row → disabled

        with pytest.raises(MarketplaceDisabledError):
            self._buy(session)

    def test_raises_when_flag_is_false(self):
        session = MagicMock()
        session.get.return_value = _make_setting(False)

        with pytest.raises(MarketplaceDisabledError):
            self._buy(session)

    def test_raises_item_not_found(self):
        _call_count = {"n": 0}

        session = MagicMock()

        def get_side(cls, pk):
            n = _call_count["n"]
            _call_count["n"] += 1
            if n == 0:
                return _make_setting(True)
            return None  # Item missing

        session.get.side_effect = get_side

        with pytest.raises(ItemNotFoundError):
            self._buy(session)

    def test_raises_item_not_in_guild(self):
        _call_count = {"n": 0}
        item = _make_item(guild_id=999)  # different guild
        session = MagicMock()

        def get_side(cls, pk):
            n = _call_count["n"]
            _call_count["n"] += 1
            return _make_setting(True) if n == 0 else item

        session.get.side_effect = get_side

        with pytest.raises(ItemNotFoundError):
            self._buy(session, guild_id=100)

    def test_raises_item_expired(self):
        from datetime import UTC, datetime, timedelta

        item = _make_item(expires_at=datetime.now(UTC) - timedelta(days=1))
        _call_count = {"n": 0}
        session = MagicMock()

        def get_side(cls, pk):
            n = _call_count["n"]
            _call_count["n"] += 1
            return _make_setting(True) if n == 0 else item

        session.get.side_effect = get_side

        with pytest.raises(ItemExpiredError):
            self._buy(session)

    def test_raises_invalid_currency_no_xp(self):
        item = _make_item(cost_xp=None, cost_gold=100)
        _call_count = {"n": 0}
        session = MagicMock()

        def get_side(cls, pk):
            n = _call_count["n"]
            _call_count["n"] += 1
            return _make_setting(True) if n == 0 else item

        session.get.side_effect = get_side

        with pytest.raises(ValueError, match="XP"):
            self._buy(session, currency="xp")

    def test_raises_invalid_currency_no_gold(self):
        item = _make_item(cost_xp=500, cost_gold=None)
        _call_count = {"n": 0}
        session = MagicMock()

        def get_side(cls, pk):
            n = _call_count["n"]
            _call_count["n"] += 1
            return _make_setting(True) if n == 0 else item

        session.get.side_effect = get_side

        with pytest.raises(ValueError, match="Gold"):
            self._buy(session, currency="gold")

    def test_raises_insufficient_funds_rowcount_zero(self):
        item = _make_item()
        _call_count = {"n": 0}
        session = MagicMock()

        def get_side(cls, pk):
            n = _call_count["n"]
            _call_count["n"] += 1
            return _make_setting(True) if n == 0 else item

        session.get.side_effect = get_side
        exec_result = MagicMock()
        exec_result.rowcount = 0
        session.execute.return_value = exec_result

        with pytest.raises(InsufficientFundsError):
            self._buy(session)

    def test_success_xp_purchase(self):
        item = _make_item(cost_xp=500)
        _call_count = {"n": 0}
        session = MagicMock()

        def get_side(cls, pk):
            n = _call_count["n"]
            _call_count["n"] += 1
            return _make_setting(True) if n == 0 else item

        session.get.side_effect = get_side
        exec_result = MagicMock()
        exec_result.rowcount = 1
        session.execute.return_value = exec_result
        savepoint = MagicMock()
        savepoint.__enter__ = MagicMock(return_value=None)
        savepoint.__exit__ = MagicMock(return_value=False)
        session.begin_nested.return_value = savepoint

        # notify_role_assignment is patched to avoid PG NOTIFY calls
        with (
            patch(
                "synapse.services.marketplace_service.Session",
                return_value=_mock_session_ctx(session),
            ),
            patch("synapse.services.marketplace_service.notify_role_assignment"),
        ):
            purchase_item(engine=MagicMock(), user_id=42, guild_id=100, item_id=1, currency="xp")

        session.commit.assert_called_once()

    def test_success_gold_purchase(self):
        item = _make_item(cost_gold=100)
        _call_count = {"n": 0}
        session = MagicMock()

        def get_side(cls, pk):
            n = _call_count["n"]
            _call_count["n"] += 1
            return _make_setting(True) if n == 0 else item

        session.get.side_effect = get_side
        exec_result = MagicMock()
        exec_result.rowcount = 1
        session.execute.return_value = exec_result
        savepoint = MagicMock()
        savepoint.__enter__ = MagicMock(return_value=None)
        savepoint.__exit__ = MagicMock(return_value=False)
        session.begin_nested.return_value = savepoint

        with (
            patch(
                "synapse.services.marketplace_service.Session",
                return_value=_mock_session_ctx(session),
            ),
            patch("synapse.services.marketplace_service.notify_role_assignment"),
        ):
            purchase_item(engine=MagicMock(), user_id=42, guild_id=100, item_id=1, currency="gold")

        session.commit.assert_called_once()

    def test_raises_already_owned_on_integrity_error(self):
        item = _make_item()
        _call_count = {"n": 0}
        session = MagicMock()

        def get_side(cls, pk):
            n = _call_count["n"]
            _call_count["n"] += 1
            return _make_setting(True) if n == 0 else item

        session.get.side_effect = get_side
        exec_result = MagicMock()
        exec_result.rowcount = 1
        session.execute.return_value = exec_result

        # SAVEPOINT enters fine, but flush() raises IntegrityError
        savepoint = MagicMock()
        savepoint.__enter__ = MagicMock(return_value=None)
        savepoint.__exit__ = MagicMock(return_value=False)
        session.begin_nested.return_value = savepoint
        session.flush.side_effect = IntegrityError("dup", None, None)

        with patch(
            "synapse.services.marketplace_service.Session",
            return_value=_mock_session_ctx(session),
        ):
            with pytest.raises(AlreadyOwnedError):
                purchase_item(
                    engine=MagicMock(), user_id=42, guild_id=100, item_id=1, currency="xp"
                )

        # Rollback must be called to reverse the XP deduction
        session.rollback.assert_called_once()

    def test_notify_role_sent_for_custom_role_color(self):
        from synapse.database.models import MarketplaceItemType

        item = _make_item(discord_role_id=9001)
        item.item_type = MarketplaceItemType.DISCORD_ROLE

        _call_count = {"n": 0}
        session = MagicMock()

        def get_side(cls, pk):
            n = _call_count["n"]
            _call_count["n"] += 1
            return _make_setting(True) if n == 0 else item

        session.get.side_effect = get_side
        exec_result = MagicMock()
        exec_result.rowcount = 1
        session.execute.return_value = exec_result
        savepoint = MagicMock()
        savepoint.__enter__ = MagicMock(return_value=None)
        savepoint.__exit__ = MagicMock(return_value=False)
        session.begin_nested.return_value = savepoint

        with (
            patch(
                "synapse.services.marketplace_service.Session",
                return_value=_mock_session_ctx(session),
            ),
            patch("synapse.services.marketplace_service.notify_role_assignment") as mock_notify,
        ):
            purchase_item(engine=MagicMock(), user_id=42, guild_id=100, item_id=1, currency="xp")

        mock_notify.assert_called_once()
        # notify_role_assignment called as positional: (engine, user_id, guild_id, discord_role_id)
        all_args = mock_notify.call_args[0] + tuple(mock_notify.call_args[1].values())
        assert 9001 in all_args

    def test_no_notify_for_non_role_item(self):
        item = _make_item(discord_role_id=None)

        _call_count = {"n": 0}
        session = MagicMock()

        def get_side(cls, pk):
            n = _call_count["n"]
            _call_count["n"] += 1
            return _make_setting(True) if n == 0 else item

        session.get.side_effect = get_side
        exec_result = MagicMock()
        exec_result.rowcount = 1
        session.execute.return_value = exec_result
        savepoint = MagicMock()
        savepoint.__enter__ = MagicMock(return_value=None)
        savepoint.__exit__ = MagicMock(return_value=False)
        session.begin_nested.return_value = savepoint

        with (
            patch(
                "synapse.services.marketplace_service.Session",
                return_value=_mock_session_ctx(session),
            ),
            patch("synapse.services.marketplace_service.notify_role_assignment") as mock_notify,
        ):
            purchase_item(engine=MagicMock(), user_id=42, guild_id=100, item_id=1, currency="xp")

        mock_notify.assert_not_called()


# ---------------------------------------------------------------------------
# TestGetUserInventory
# ---------------------------------------------------------------------------


class TestGetUserInventory:
    def test_returns_items_for_user(self):
        invs = [_make_inventory(user_id=42, item_id=i) for i in range(3)]
        session = MagicMock()
        session.scalars.return_value.all.return_value = invs

        with patch(
            "synapse.services.marketplace_service.Session",
            return_value=_mock_session_ctx(session),
        ):
            result = get_user_inventory(MagicMock(), user_id=42, guild_id=100)

        assert len(result) == 3

    def test_returns_empty_for_no_items(self):
        session = MagicMock()
        session.scalars.return_value.all.return_value = []

        with patch(
            "synapse.services.marketplace_service.Session",
            return_value=_mock_session_ctx(session),
        ):
            result = get_user_inventory(MagicMock(), user_id=42, guild_id=100)

        assert result == []


# ---------------------------------------------------------------------------
# TestSetEquipped
# ---------------------------------------------------------------------------


class TestSetEquipped:
    def test_equip_success(self):
        inv = _make_inventory()
        inv.is_equipped = False
        session = MagicMock()
        session.scalar.return_value = inv

        with patch(
            "synapse.services.marketplace_service.Session",
            return_value=_mock_session_ctx(session),
        ):
            set_equipped(MagicMock(), user_id=42, item_id=1, guild_id=100, equipped=True)

        assert inv.is_equipped is True
        session.commit.assert_called_once()

    def test_unequip_success(self):
        inv = _make_inventory()
        inv.is_equipped = True
        session = MagicMock()
        session.scalar.return_value = inv

        with patch(
            "synapse.services.marketplace_service.Session",
            return_value=_mock_session_ctx(session),
        ):
            set_equipped(MagicMock(), user_id=42, item_id=1, guild_id=100, equipped=False)

        assert inv.is_equipped is False

    def test_raises_item_not_found_when_not_owned(self):
        session = MagicMock()
        session.scalar.return_value = None

        with patch(
            "synapse.services.marketplace_service.Session",
            return_value=_mock_session_ctx(session),
        ):
            with pytest.raises(ItemNotFoundError):
                set_equipped(MagicMock(), user_id=42, item_id=999, guild_id=100, equipped=True)


# ---------------------------------------------------------------------------
# TestNotifyRoleAssignment
# ---------------------------------------------------------------------------


class TestNotifyRoleAssignment:
    def test_sends_event_notify_with_correct_payload(self):
        engine = MagicMock()

        with patch("synapse.services.marketplace_service.send_event_notify") as mock_send:
            notify_role_assignment(engine, user_id=42, guild_id=100, discord_role_id=9001)

        mock_send.assert_called_once_with(
            engine,
            {
                "type": "marketplace_role_assignment",
                "user_id": 42,
                "guild_id": 100,
                "discord_role_id": 9001,
            },
        )


# ---------------------------------------------------------------------------
# TestMarketplaceCogImport
# ---------------------------------------------------------------------------


class TestMarketplaceCogImport:
    """Smoke tests for bot cog importability and structure."""

    def test_cog_imports(self):
        from synapse.bot.cogs.marketplace import setup

        assert callable(setup)

    def test_fetch_role_assignments_is_callable(self):
        from synapse.bot.cogs.marketplace import _fetch_role_assignments

        assert callable(_fetch_role_assignments)

    def test_cog_class_has_expected_attributes(self):
        from synapse.bot.cogs.marketplace import MarketplaceCog

        assert hasattr(MarketplaceCog, "role_sync_loop")
        assert hasattr(MarketplaceCog, "cog_load")
        assert hasattr(MarketplaceCog, "cog_unload")

    def test_role_assign_event_type_constant(self):
        from synapse.services.marketplace_service import ROLE_ASSIGN_EVENT_TYPE

        assert ROLE_ASSIGN_EVENT_TYPE == "marketplace_role_assignment"
