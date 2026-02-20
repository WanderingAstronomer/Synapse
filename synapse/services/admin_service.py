"""
synapse.services.admin_service — Admin Mutation Service Layer
==============================================================

Shared service module for all admin config mutations per 07 §7.9.
Every write follows the pattern:
  1. Begin transaction
  2. Read "before" snapshot
  3. Apply change
  4. Write admin_log with before/after JSONB
  5. NOTIFY config_changed, '<table>'
  6. Commit
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import func as sa_func
from sqlalchemy import select
from sqlalchemy.orm import Session

from synapse.database.models import (
    AchievementCategory,
    AchievementRarity,
    AchievementSeries,
    AchievementTemplate,
    AdminLog,
    ChannelOverride,
    ChannelTypeDefault,
    RewardRule,
    RuleSnapshot,
    Season,
    Setting,
)
from synapse.engine.cache import notify_before_commit

if TYPE_CHECKING:
    from synapse.database.models import MarketplaceItem

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Generic audit helpers
# ---------------------------------------------------------------------------


def _row_to_dict(obj: Any) -> dict | None:
    """Convert a SQLAlchemy model instance to a JSON-serializable dict."""
    if obj is None:
        return None
    result = {}
    for col in obj.__table__.columns:
        val = getattr(obj, col.key if col.key != "metadata" else "metadata_", None)
        if isinstance(val, datetime):
            val = val.isoformat()
        result[col.name] = val
    return result


def _log_admin_action(
    session: Session,
    *,
    actor_id: int,
    action_type: str,
    target_table: str,
    target_id: str | None,
    before: dict | None,
    after: dict | None,
    ip_address: str | None = None,
    reason: str | None = None,
) -> None:
    """Insert a row into admin_log within the current transaction."""
    session.add(
        AdminLog(
            actor_id=actor_id,
            action_type=action_type,
            target_table=target_table,
            target_id=target_id,
            before_snapshot=before,
            after_snapshot=after,
            ip_address=ip_address,
            reason=reason,
        )
    )


def _audited_create(
    engine,
    row: Any,
    *,
    table_name: str,
    actor_id: int,
    ip_address: str | None = None,
) -> Any:
    """Generic audited CREATE: add -> flush -> log -> notify -> commit -> return.

    Parameters
    ----------
    row : ORM instance (already constructed, not yet added to a session).
    """
    with Session(engine, expire_on_commit=False) as session:
        session.add(row)
        session.flush()
        _log_admin_action(
            session,
            actor_id=actor_id,
            action_type="CREATE",
            target_table=table_name,
            target_id=str(row.id),
            before=None,
            after=_row_to_dict(row),
            ip_address=ip_address,
        )
        notify_before_commit(session, table_name)
        session.commit()
        session.refresh(row)
        session.expunge(row)
        return row


def _audited_update(
    engine,
    model_cls: type,
    pk: int,
    *,
    table_name: str,
    actor_id: int,
    frozen_keys: tuple[str, ...] = ("id", "guild_id"),
    ip_address: str | None = None,
    **kwargs: Any,
) -> Any | None:
    """Generic audited UPDATE: get -> before -> apply kwargs -> log -> commit.

    Returns the updated (expunged) object, or ``None`` if not found.
    """
    with Session(engine, expire_on_commit=False) as session:
        obj = session.get(model_cls, pk)
        if obj is None:
            return None
        before = _row_to_dict(obj)
        for key, value in kwargs.items():
            if hasattr(obj, key) and key not in frozen_keys:
                setattr(obj, key, value)
        session.flush()
        _log_admin_action(
            session,
            actor_id=actor_id,
            action_type="UPDATE",
            target_table=table_name,
            target_id=str(obj.id),
            before=before,
            after=_row_to_dict(obj),
            ip_address=ip_address,
        )
        notify_before_commit(session, table_name)
        session.commit()
        session.refresh(obj)
        session.expunge(obj)
        return obj


def _audited_delete(
    engine,
    model_cls: type,
    pk: int,
    *,
    table_name: str,
    actor_id: int,
    ip_address: str | None = None,
) -> bool:
    """Generic audited DELETE: get -> log -> delete -> commit -> notify.

    Returns ``True`` if the row existed and was deleted.
    """
    with Session(engine) as session:
        obj = session.get(model_cls, pk)
        if obj is None:
            return False
        _log_admin_action(
            session,
            actor_id=actor_id,
            action_type="DELETE",
            target_table=table_name,
            target_id=str(obj.id),
            before=_row_to_dict(obj),
            after=None,
            ip_address=ip_address,
        )
        session.delete(obj)
        notify_before_commit(session, table_name)
        session.commit()
        return True


def _audited_upsert(
    engine,
    model_cls: type,
    lookup_kwargs: dict[str, Any],
    *,
    table_name: str,
    actor_id: int,
    ip_address: str | None = None,
    **values: Any,
) -> Any:
    """Generic audited UPSERT: get by lookup -> update or create -> log -> commit.

    Returns the updated/created (expunged) object.
    """
    with Session(engine, expire_on_commit=False) as session:
        # Construct lookup query
        stmt = select(model_cls)
        for key, val in lookup_kwargs.items():
            stmt = stmt.where(getattr(model_cls, key) == val)

        obj = session.scalar(stmt)
        before = _row_to_dict(obj)
        action = "UPDATE" if obj else "CREATE"

        if not obj:
            # Create new instance with merged lookup + values
            obj = model_cls(**{**lookup_kwargs, **values})
            session.add(obj)
        else:
            # Update existing instance
            for key, val in values.items():
                if hasattr(obj, key):
                    setattr(obj, key, val)

        session.flush()
        _log_admin_action(
            session,
            actor_id=actor_id,
            action_type=action,
            target_table=table_name,
            target_id=str(obj.id),
            before=before,
            after=_row_to_dict(obj),
            ip_address=ip_address,
        )
        notify_before_commit(session, table_name)
        session.commit()
        session.refresh(obj)
        session.expunge(obj)
        return obj


# ---------------------------------------------------------------------------
# Channel Type Default CRUD
# ---------------------------------------------------------------------------


def upsert_type_default(
    engine,
    *,
    guild_id: int,
    channel_type: str,
    event_type: str,
    xp_multiplier: float = 1.0,
    star_multiplier: float = 1.0,
    actor_id: int,
) -> ChannelTypeDefault:
    """Create or update a channel type default rule."""
    return _audited_upsert(
        engine,
        ChannelTypeDefault,
        {
            "guild_id": guild_id,
            "channel_type": channel_type,
            "event_type": event_type,
        },
        table_name="channel_type_defaults",
        actor_id=actor_id,
        xp_multiplier=xp_multiplier,
        star_multiplier=star_multiplier,
    )


def delete_type_default(engine, *, default_id: int, actor_id: int) -> bool:
    """Delete a channel type default. Returns True if found and deleted."""
    return _audited_delete(
        engine,
        ChannelTypeDefault,
        default_id,
        table_name="channel_type_defaults",
        actor_id=actor_id,
    )


# ---------------------------------------------------------------------------
# Channel Override CRUD
# ---------------------------------------------------------------------------


def upsert_channel_override(
    engine,
    *,
    guild_id: int,
    channel_id: int,
    event_type: str,
    xp_multiplier: float = 1.0,
    star_multiplier: float = 1.0,
    reason: str | None = None,
    actor_id: int,
) -> ChannelOverride:
    """Create or update a per-channel override."""
    return _audited_upsert(
        engine,
        ChannelOverride,
        {
            "guild_id": guild_id,
            "channel_id": channel_id,
            "event_type": event_type,
        },
        table_name="channel_overrides",
        actor_id=actor_id,
        xp_multiplier=xp_multiplier,
        star_multiplier=star_multiplier,
        reason=reason,
    )


def delete_channel_override(engine, *, override_id: int, actor_id: int) -> bool:
    """Delete a channel override. Returns True if found and deleted."""
    return _audited_delete(
        engine,
        ChannelOverride,
        override_id,
        table_name="channel_overrides",
        actor_id=actor_id,
    )


# ---------------------------------------------------------------------------
# Achievement Template CRUD
# ---------------------------------------------------------------------------


def create_achievement(
    engine,
    *,
    guild_id: int,
    name: str,
    description: str | None = None,
    category_id: int | None = None,
    rarity_id: int | None = None,
    trigger_type: str = "manual",
    trigger_config: dict | None = None,
    series_id: int | None = None,
    series_order: int | None = None,
    xp_reward: int = 0,
    gold_reward: int = 0,
    badge_image: str | None = None,
    announce_channel_id: int | None = None,
    is_hidden: bool = False,
    max_earners: int | None = None,
    actor_id: int,
    ip_address: str | None = None,
) -> AchievementTemplate:
    """Create a new achievement template."""
    return _audited_create(
        engine,
        AchievementTemplate(
            guild_id=guild_id,
            name=name,
            description=description,
            category_id=category_id,
            rarity_id=rarity_id,
            trigger_type=trigger_type,
            trigger_config=trigger_config or {},
            series_id=series_id,
            series_order=series_order,
            xp_reward=xp_reward,
            gold_reward=gold_reward,
            badge_image=badge_image,
            announce_channel_id=announce_channel_id,
            is_hidden=is_hidden,
            max_earners=max_earners,
        ),
        table_name="achievement_templates",
        actor_id=actor_id,
        ip_address=ip_address,
    )


def update_achievement(
    engine,
    *,
    achievement_id: int,
    actor_id: int,
    ip_address: str | None = None,
    **kwargs,
) -> AchievementTemplate | None:
    """Update an existing achievement template."""
    return _audited_update(
        engine,
        AchievementTemplate,
        achievement_id,
        table_name="achievement_templates",
        actor_id=actor_id,
        frozen_keys=("id", "guild_id", "created_at"),
        ip_address=ip_address,
        **kwargs,
    )


def delete_achievement(
    engine,
    *,
    achievement_id: int,
    actor_id: int,
    ip_address: str | None = None,
) -> bool:
    """Delete an achievement template."""
    return _audited_delete(
        engine,
        AchievementTemplate,
        achievement_id,
        table_name="achievement_templates",
        actor_id=actor_id,
        ip_address=ip_address,
    )


# ---------------------------------------------------------------------------
# Achievement Category CRUD
# ---------------------------------------------------------------------------


def create_achievement_category(
    engine,
    *,
    guild_id: int,
    name: str,
    icon: str | None = None,
    sort_order: int = 0,
    actor_id: int,
    ip_address: str | None = None,
) -> AchievementCategory:
    """Create a new achievement category."""
    return _audited_create(
        engine,
        AchievementCategory(guild_id=guild_id, name=name, icon=icon, sort_order=sort_order),
        table_name="achievement_categories",
        actor_id=actor_id,
        ip_address=ip_address,
    )


def update_achievement_category(
    engine,
    *,
    category_id: int,
    actor_id: int,
    ip_address: str | None = None,
    **kwargs,
) -> AchievementCategory | None:
    """Update an existing achievement category."""
    return _audited_update(
        engine,
        AchievementCategory,
        category_id,
        table_name="achievement_categories",
        actor_id=actor_id,
        ip_address=ip_address,
        **kwargs,
    )


def delete_achievement_category(
    engine,
    *,
    category_id: int,
    actor_id: int,
    ip_address: str | None = None,
) -> bool:
    """Delete an achievement category."""
    return _audited_delete(
        engine,
        AchievementCategory,
        category_id,
        table_name="achievement_categories",
        actor_id=actor_id,
        ip_address=ip_address,
    )


# ---------------------------------------------------------------------------
# Achievement Rarity CRUD
# ---------------------------------------------------------------------------


def create_achievement_rarity(
    engine,
    *,
    guild_id: int,
    name: str,
    color: str = "#9e9e9e",
    emoji: str | None = None,
    sort_order: int = 0,
    actor_id: int,
    ip_address: str | None = None,
) -> AchievementRarity:
    """Create a new achievement rarity tier."""
    return _audited_create(
        engine,
        AchievementRarity(
            guild_id=guild_id, name=name, color=color, emoji=emoji, sort_order=sort_order,
        ),
        table_name="achievement_rarities",
        actor_id=actor_id,
        ip_address=ip_address,
    )


def update_achievement_rarity(
    engine,
    *,
    rarity_id: int,
    actor_id: int,
    ip_address: str | None = None,
    **kwargs,
) -> AchievementRarity | None:
    """Update an existing achievement rarity tier."""
    return _audited_update(
        engine,
        AchievementRarity,
        rarity_id,
        table_name="achievement_rarities",
        actor_id=actor_id,
        ip_address=ip_address,
        **kwargs,
    )


def delete_achievement_rarity(
    engine,
    *,
    rarity_id: int,
    actor_id: int,
    ip_address: str | None = None,
) -> bool:
    """Delete an achievement rarity tier."""
    return _audited_delete(
        engine,
        AchievementRarity,
        rarity_id,
        table_name="achievement_rarities",
        actor_id=actor_id,
        ip_address=ip_address,
    )


# ---------------------------------------------------------------------------
# Achievement Series CRUD
# ---------------------------------------------------------------------------


def create_achievement_series(
    engine,
    *,
    guild_id: int,
    name: str,
    description: str | None = None,
    actor_id: int,
    ip_address: str | None = None,
) -> AchievementSeries:
    """Create a new achievement series."""
    return _audited_create(
        engine,
        AchievementSeries(guild_id=guild_id, name=name, description=description),
        table_name="achievement_series",
        actor_id=actor_id,
        ip_address=ip_address,
    )


def update_achievement_series(
    engine,
    *,
    series_id: int,
    actor_id: int,
    ip_address: str | None = None,
    **kwargs,
) -> AchievementSeries | None:
    """Update an existing achievement series."""
    return _audited_update(
        engine,
        AchievementSeries,
        series_id,
        table_name="achievement_series",
        actor_id=actor_id,
        ip_address=ip_address,
        **kwargs,
    )


def delete_achievement_series(
    engine,
    *,
    series_id: int,
    actor_id: int,
    ip_address: str | None = None,
) -> bool:
    """Delete an achievement series."""
    return _audited_delete(
        engine,
        AchievementSeries,
        series_id,
        table_name="achievement_series",
        actor_id=actor_id,
        ip_address=ip_address,
    )


# ---------------------------------------------------------------------------
# Season Management
# ---------------------------------------------------------------------------


def create_season(
    engine,
    *,
    guild_id: int,
    name: str,
    starts_at: datetime,
    ends_at: datetime,
    actor_id: int,
    ip_address: str | None = None,
    activate: bool = True,
) -> Season:
    """Create a new season, optionally deactivating the current one."""
    with Session(engine, expire_on_commit=False) as session:
        if activate:
            current = session.scalar(
                select(Season).where(Season.guild_id == guild_id, Season.active.is_(True))
            )
            if current:
                before_curr = _row_to_dict(current)
                current.active = False
                _log_admin_action(
                    session,
                    actor_id=actor_id,
                    action_type="SEASON_ROLL",
                    target_table="seasons",
                    target_id=str(current.id),
                    before=before_curr,
                    after=_row_to_dict(current),
                    ip_address=ip_address,
                )

        season = Season(
            guild_id=guild_id,
            name=name,
            starts_at=starts_at,
            ends_at=ends_at,
            active=activate,
        )
        session.add(season)
        session.flush()
        _log_admin_action(
            session,
            actor_id=actor_id,
            action_type="CREATE",
            target_table="seasons",
            target_id=str(season.id),
            before=None,
            after=_row_to_dict(season),
            ip_address=ip_address,
        )
        session.commit()

        session.refresh(season)
        session.expunge(season)
        return season


# ---------------------------------------------------------------------------
# Marketplace Items
# ---------------------------------------------------------------------------


def create_marketplace_item(
    engine,
    *,
    guild_id: int,
    name: str,
    description: str | None = None,
    item_type: str = "COSMETIC_BADGE",
    cost_xp: int | None = None,
    cost_gold: int | None = None,
    rarity_id: int | None = None,
    overlay_id: int | None = None,
    image_url: str | None = None,
    discord_role_id: int | None = None,
    season_id: int | None = None,
    expires_at: datetime | None = None,
    actor_id: int,
    ip_address: str | None = None,
) -> MarketplaceItem:
    """Create a new marketplace item, with audit trail."""
    from synapse.database.models import MarketplaceItem

    return _audited_create(
        engine,
        MarketplaceItem(
            guild_id=guild_id,
            name=name,
            description=description,
            item_type=item_type,
            cost_xp=cost_xp,
            cost_gold=cost_gold,
            rarity_id=rarity_id,
            overlay_id=overlay_id,
            image_url=image_url,
            discord_role_id=discord_role_id,
            season_id=season_id,
            expires_at=expires_at,
            active=True,
        ),
        table_name="marketplace_items",
        actor_id=actor_id,
        ip_address=ip_address,
    )


def update_marketplace_item(
    engine,
    item_id: int,
    *,
    actor_id: int,
    ip_address: str | None = None,
    **kwargs: Any,
) -> MarketplaceItem | None:
    """Update mutable fields on a marketplace item."""
    from synapse.database.models import MarketplaceItem

    return _audited_update(
        engine,
        MarketplaceItem,
        item_id,
        table_name="marketplace_items",
        actor_id=actor_id,
        frozen_keys=("id", "guild_id"),
        ip_address=ip_address,
        **kwargs,
    )


def deactivate_marketplace_item(
    engine,
    item_id: int,
    *,
    actor_id: int,
    ip_address: str | None = None,
) -> MarketplaceItem | None:
    """Soft-delete a marketplace item by setting ``active = False``."""
    from synapse.database.models import MarketplaceItem

    return _audited_update(
        engine,
        MarketplaceItem,
        item_id,
        table_name="marketplace_items",
        actor_id=actor_id,
        frozen_keys=("id", "guild_id"),
        ip_address=ip_address,
        active=False,
    )


# ---------------------------------------------------------------------------
# Reward Rules CRUD
# ---------------------------------------------------------------------------


def list_reward_rules(engine, *, guild_id: int) -> list[RewardRule]:
    """Return all reward rules for a guild, ordered by priority descending."""
    with Session(engine, expire_on_commit=False) as session:
        stmt = (
            select(RewardRule)
            .where(RewardRule.guild_id == guild_id)
            .order_by(RewardRule.priority.desc(), RewardRule.id)
        )
        rows = list(session.scalars(stmt))
        for r in rows:
            session.expunge(r)
        return rows


def get_reward_rule(engine, rule_id: int) -> RewardRule | None:
    """Return a single reward rule by ID."""
    with Session(engine, expire_on_commit=False) as session:
        rule = session.get(RewardRule, rule_id)
        if rule:
            session.expunge(rule)
        return rule


def create_reward_rule(
    engine,
    *,
    guild_id: int,
    name: str,
    predicates: list[dict] | None = None,
    outcomes: list[dict] | None = None,
    priority: int = 50,
    is_active: bool = True,
    actor_id: int,
    ip_address: str | None = None,
) -> RewardRule:
    """Create a new reward rule with audit trail."""
    return _audited_create(
        engine,
        RewardRule(
            guild_id=guild_id,
            name=name,
            predicates=predicates or [],
            outcomes=outcomes or [],
            priority=priority,
            is_active=is_active,
        ),
        table_name="reward_rules",
        actor_id=actor_id,
        ip_address=ip_address,
    )


def update_reward_rule(
    engine,
    rule_id: int,
    *,
    actor_id: int,
    ip_address: str | None = None,
    **kwargs: Any,
) -> RewardRule | None:
    """Update mutable fields on a reward rule."""
    return _audited_update(
        engine,
        RewardRule,
        rule_id,
        table_name="reward_rules",
        actor_id=actor_id,
        frozen_keys=("id", "guild_id"),
        ip_address=ip_address,
        **kwargs,
    )


def delete_reward_rule(
    engine,
    rule_id: int,
    *,
    actor_id: int,
    ip_address: str | None = None,
) -> bool:
    """Delete a reward rule with audit trail."""
    return _audited_delete(
        engine,
        RewardRule,
        rule_id,
        table_name="reward_rules",
        actor_id=actor_id,
        ip_address=ip_address,
    )


def reorder_reward_rules(
    engine,
    *,
    guild_id: int,
    rule_priorities: list[dict[str, int]],
    actor_id: int,
    ip_address: str | None = None,
) -> int:
    """Bulk-update priorities for reward rules.

    Parameters
    ----------
    rule_priorities : list[dict]
        Each dict must have ``id`` and ``priority`` keys.

    Returns
    -------
    int
        Number of rules updated.
    """
    updated = 0
    with Session(engine, expire_on_commit=False) as session:
        for item in rule_priorities:
            rule = session.get(RewardRule, item["id"])
            if rule is None or rule.guild_id != guild_id:
                continue
            before = _row_to_dict(rule)
            rule.priority = item["priority"]
            session.flush()
            _log_admin_action(
                session,
                actor_id=actor_id,
                action_type="UPDATE",
                target_table="reward_rules",
                target_id=str(rule.id),
                before=before,
                after=_row_to_dict(rule),
                ip_address=ip_address,
            )
            updated += 1
        if updated:
            notify_before_commit(session, "reward_rules")
            session.commit()
    return updated


# ---------------------------------------------------------------------------
# Rule Snapshots
# ---------------------------------------------------------------------------


def publish_rule_snapshot(
    engine,
    *,
    guild_id: int,
    actor_id: int,
    ip_address: str | None = None,
) -> RuleSnapshot:
    """Snapshot current active rules and publish as a new version.

    Sets all previous snapshots for this guild to ``is_active = False``
    and creates a new one with ``is_active = True``.
    """
    with Session(engine, expire_on_commit=False) as session:
        # Get current active rules
        rules = list(
            session.scalars(
                select(RewardRule)
                .where(RewardRule.guild_id == guild_id, RewardRule.is_active.is_(True))
                .order_by(RewardRule.priority.desc())
            )
        )
        rules_json = [
            {
                "id": r.id,
                "name": r.name,
                "priority": r.priority,
                "predicates": r.predicates,
                "outcomes": r.outcomes,
            }
            for r in rules
        ]

        # Get next version number
        max_ver = session.scalar(
            select(sa_func.coalesce(sa_func.max(RuleSnapshot.version), 0)).where(
                RuleSnapshot.guild_id == guild_id
            )
        )
        next_version = (max_ver or 0) + 1

        # Deactivate old snapshots
        for old in session.scalars(
            select(RuleSnapshot).where(
                RuleSnapshot.guild_id == guild_id, RuleSnapshot.is_active.is_(True)
            )
        ):
            old.is_active = False

        snapshot = RuleSnapshot(
            guild_id=guild_id,
            version=next_version,
            rules_json=rules_json,
            published_by=actor_id,
            is_active=True,
        )
        session.add(snapshot)
        session.flush()

        _log_admin_action(
            session,
            actor_id=actor_id,
            action_type="CREATE",
            target_table="rule_snapshots",
            target_id=str(snapshot.id),
            before=None,
            after={
                "version": next_version,
                "rules_count": len(rules_json),
                "is_active": True,
            },
            ip_address=ip_address,
        )
        notify_before_commit(session, "rule_snapshots")
        session.commit()
        session.refresh(snapshot)
        session.expunge(snapshot)
        return snapshot


def list_rule_snapshots(
    engine,
    *,
    guild_id: int,
    limit: int = 20,
) -> list[RuleSnapshot]:
    """Return recent rule snapshots, newest first."""
    with Session(engine, expire_on_commit=False) as session:
        stmt = (
            select(RuleSnapshot)
            .where(RuleSnapshot.guild_id == guild_id)
            .order_by(RuleSnapshot.published_at.desc())
            .limit(limit)
        )
        rows = list(session.scalars(stmt))
        for r in rows:
            session.expunge(r)
        return rows


# ---------------------------------------------------------------------------
# Feature Flag Management
# ---------------------------------------------------------------------------


def toggle_feature_flag(
    engine,
    *,
    flag_key: str,
    flag_label: str,
    flag_description: str,
    new_value: bool,
    actor_id: int,
    ip_address: str | None = None,
) -> None:
    """Audited feature-flag toggle following the standard admin mutation pattern.

    Parameters
    ----------
    engine :
        SQLAlchemy engine.
    flag_key :
        The settings table key (e.g. ``"flags.firewall_enabled"``).
    flag_label :
        Human-readable label used in log messages.
    flag_description :
        Description stored when creating the setting row for the first time.
    new_value :
        The boolean value to set.
    actor_id :
        Discord user ID of the admin performing the toggle.
    ip_address :
        Optional IP address for the audit log.
    """
    with Session(engine, expire_on_commit=False) as session:
        existing = session.get(Setting, flag_key)

        before: dict | None = None
        action: str

        if existing:
            before = {
                "key": existing.key,
                "value": json.loads(existing.value_json) if existing.value_json else None,
            }
            existing.value_json = json.dumps(new_value)
            action = "UPDATE"
        else:
            existing = Setting(
                key=flag_key,
                value_json=json.dumps(new_value),
                category="flags",
                description=flag_description,
            )
            session.add(existing)
            action = "CREATE"

        after = {"key": flag_key, "value": new_value}
        _log_admin_action(
            session,
            actor_id=actor_id,
            action_type=action,
            target_table="settings",
            target_id=flag_key,
            before=before,
            after=after,
            ip_address=ip_address,
        )
        notify_before_commit(session, "settings")
        session.commit()
