"""
synapse.api.routes.rules — Reward Rules Admin Endpoints
=========================================================

JWT-protected admin routes for:
    - CRUD on ``reward_rules``
    - Bulk priority reorder
    - Snapshot publish + history
    - Rule dry-run / test simulation
    - Event type taxonomy metadata
    - Rule evaluation trace queries
    - Projection worker status
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import Engine, select
from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session

from synapse.api.deps import get_config, get_engine, get_session
from synapse.api.rate_limit import rate_limited_admin
from synapse.config import SynapseConfig
from synapse.database.models import (
    EventLake,
    InteractionType,
    ProjectionCheckpoint,
    RewardRule,
    RuleEvaluation,
    RuleSnapshot,
    ScalingCurve,
)
from synapse.engine.events import EventType, SynapseEvent
from synapse.engine.rule_engine import RuleEngine
from synapse.services import admin_service

router = APIRouter(prefix="/admin/rules", tags=["rules"])
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class RuleCreate(BaseModel):
    name: str
    predicates: list[dict[str, Any]] = []
    outcomes: list[dict[str, Any]] = []
    priority: int = 50
    is_active: bool = True


class RuleUpdate(BaseModel):
    name: str | None = None
    predicates: list[dict[str, Any]] | None = None
    outcomes: list[dict[str, Any]] | None = None
    priority: int | None = None
    is_active: bool | None = None


class PriorityItem(BaseModel):
    id: int
    priority: int


class ReorderRequest(BaseModel):
    rules: list[PriorityItem]


class DryRunRequest(BaseModel):
    """Evaluate rules against a synthetic or replayed event."""

    # If event_lake_id is set, replay that stored event.
    event_lake_id: int | None = None
    # Otherwise, provide a synthetic event:
    event_type: str | None = None
    user_id: int | None = None
    channel_id: int | None = None
    metadata: dict[str, Any] = {}
    context: dict[str, Any] = {}
    # Optional: only test specific rule IDs (empty = test all active rules)
    rule_ids: list[int] = []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rule_dict(rule: RewardRule) -> dict[str, Any]:
    return {
        "id": rule.id,
        "guild_id": str(rule.guild_id),
        "name": rule.name,
        "predicates": rule.predicates,
        "outcomes": rule.outcomes,
        "priority": rule.priority,
        "is_active": rule.is_active,
        "created_at": rule.created_at.isoformat() if rule.created_at else None,
        "updated_at": rule.updated_at.isoformat() if rule.updated_at else None,
    }


def _snapshot_dict(snap: RuleSnapshot) -> dict[str, Any]:
    return {
        "id": snap.id,
        "guild_id": str(snap.guild_id),
        "version": snap.version,
        "rules_json": snap.rules_json,
        "rules_count": len(snap.rules_json) if snap.rules_json else 0,
        "published_by": str(snap.published_by) if snap.published_by else None,
        "published_at": snap.published_at.isoformat() if snap.published_at else None,
        "is_active": snap.is_active,
    }


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


@router.get("")
def list_rules(
    admin: dict = Depends(rate_limited_admin),
    engine: Engine = Depends(get_engine),
    cfg: SynapseConfig = Depends(get_config),
):
    """List all reward rules for this guild, ordered by priority descending."""
    rules = admin_service.list_reward_rules(engine, guild_id=cfg.guild_id)
    return {"rules": [_rule_dict(r) for r in rules]}


@router.post("", status_code=201)
def create_rule(
    body: RuleCreate,
    admin: dict = Depends(rate_limited_admin),
    engine: Engine = Depends(get_engine),
    cfg: SynapseConfig = Depends(get_config),
):
    """Create a new reward rule."""
    rule = admin_service.create_reward_rule(
        engine,
        guild_id=cfg.guild_id,
        name=body.name,
        predicates=body.predicates,
        outcomes=body.outcomes,
        priority=body.priority,
        is_active=body.is_active,
        actor_id=int(admin["sub"]),
    )
    return _rule_dict(rule)


@router.patch("/reorder")
def reorder_rules(
    body: ReorderRequest,
    admin: dict = Depends(rate_limited_admin),
    engine: Engine = Depends(get_engine),
    cfg: SynapseConfig = Depends(get_config),
):
    """Bulk-update priorities for reward rules."""
    updated = admin_service.reorder_reward_rules(
        engine,
        guild_id=cfg.guild_id,
        rule_priorities=[{"id": r.id, "priority": r.priority} for r in body.rules],
        actor_id=int(admin["sub"]),
    )
    return {"updated": updated}


# ---------------------------------------------------------------------------
# Snapshots
# ---------------------------------------------------------------------------


@router.post("/publish", status_code=201)
def publish_snapshot(
    admin: dict = Depends(rate_limited_admin),
    engine: Engine = Depends(get_engine),
    cfg: SynapseConfig = Depends(get_config),
):
    """Snapshot current active rules and publish as a new version."""
    snap = admin_service.publish_rule_snapshot(
        engine,
        guild_id=cfg.guild_id,
        actor_id=int(admin["sub"]),
    )
    return _snapshot_dict(snap)


@router.get("/snapshots")
def list_snapshots(
    limit: int = Query(20, ge=1, le=100),
    admin: dict = Depends(rate_limited_admin),
    engine: Engine = Depends(get_engine),
    cfg: SynapseConfig = Depends(get_config),
):
    """List recent rule snapshots, newest first."""
    snaps = admin_service.list_rule_snapshots(
        engine,
        guild_id=cfg.guild_id,
        limit=limit,
    )
    return {"snapshots": [_snapshot_dict(s) for s in snaps]}


# ---------------------------------------------------------------------------
# Dry-Run / Simulation
# ---------------------------------------------------------------------------


@router.post("/test")
def dry_run_rule(
    body: DryRunRequest,
    admin: dict = Depends(rate_limited_admin),
    engine_dep: Engine = Depends(get_engine),
    cfg: SynapseConfig = Depends(get_config),
    session: Session = Depends(get_session),
):
    """Evaluate rules against a sample event without persisting.

    Supports two modes:
    1. Replay: provide ``event_lake_id`` to re-evaluate a stored event.
    2. Synthetic: provide ``event_type``, ``user_id``, etc.
    """
    # Build the SynapseEvent
    if body.event_lake_id:
        # Replay mode: load from event lake
        lake_event = session.get(EventLake, body.event_lake_id)
        if lake_event is None:
            raise HTTPException(404, "Event not found in lake.")
        event = SynapseEvent(
            user_id=lake_event.user_id,
            event_type=InteractionType(
                lake_event.event_type.upper()
                if lake_event.event_type.upper() in InteractionType.__members__
                else "MESSAGE"
            ),
            channel_id=lake_event.channel_id or 0,
            guild_id=lake_event.guild_id,
            metadata=lake_event.payload or {},
            context=body.context,
        )
    else:
        if not body.event_type:
            raise HTTPException(400, "Provide event_type or event_lake_id.")
        event = SynapseEvent(
            user_id=body.user_id or 0,
            event_type=InteractionType(body.event_type),
            channel_id=body.channel_id or 0,
            guild_id=cfg.guild_id,
            metadata=body.metadata,
            context=body.context,
        )

    # Load rules
    if body.rule_ids:
        all_rules = admin_service.list_reward_rules(engine_dep, guild_id=cfg.guild_id)
        rules_data = [
            {
                "id": r.id,
                "name": r.name,
                "priority": r.priority,
                "predicates": r.predicates,
                "outcomes": r.outcomes,
            }
            for r in all_rules
            if r.id in set(body.rule_ids)
        ]
    else:
        all_rules = admin_service.list_reward_rules(engine_dep, guild_id=cfg.guild_id)
        rules_data = [
            {
                "id": r.id,
                "name": r.name,
                "priority": r.priority,
                "predicates": r.predicates,
                "outcomes": r.outcomes,
            }
            for r in all_rules
            if r.is_active
        ]

    # Evaluate
    rule_engine = RuleEngine()
    result = rule_engine.evaluate(event, rules_data, body.context)

    return {
        "matched_rules": result.matched_rules,
        "outcomes_applied": result.outcomes_applied,
        "context_snapshot": result.context_snapshot,
        "rules_tested": len(rules_data),
    }


# ---------------------------------------------------------------------------
# Event Type Taxonomy
# ---------------------------------------------------------------------------


@router.get("/taxonomy")
def get_taxonomy(
    admin: dict = Depends(rate_limited_admin),
    session: Session = Depends(get_session),
    cfg: SynapseConfig = Depends(get_config),
):
    """Serve event type metadata for the rule builder.

    Returns:
    - Known interaction types (reward pipeline types)
    - Known Event Lake event types
    - Observed event types from the lake with counts
    - Available predicate operators
    - Available scaling curves
    - Available context variables
    """
    # Observed event types from the lake (last 30 days)
    from datetime import UTC, datetime, timedelta

    cutoff = datetime.now(UTC) - timedelta(days=30)
    observed = session.execute(
        select(EventLake.event_type, sa_func.count())
        .where(
            EventLake.guild_id == cfg.guild_id,
            EventLake.timestamp >= cutoff,
        )
        .group_by(EventLake.event_type)
        .order_by(sa_func.count().desc())
    ).all()

    return {
        "interaction_types": [
            {"value": t.value, "label": t.value.replace("_", " ").title()} for t in InteractionType
        ],
        "event_lake_types": [
            {"value": t.value, "label": t.value.replace("_", " ").title()} for t in EventType
        ],
        "observed_types": [{"event_type": row[0], "count": row[1]} for row in observed],
        "operators": [
            {"op": "==", "label": "equals"},
            {"op": "!=", "label": "not equals"},
            {"op": ">", "label": "greater than"},
            {"op": ">=", "label": "greater or equal"},
            {"op": "<", "label": "less than"},
            {"op": "<=", "label": "less or equal"},
            {"op": "contains", "label": "contains"},
            {"op": "not_contains", "label": "does not contain"},
        ],
        "scaling_curves": [{"value": c.value, "label": c.value.title()} for c in ScalingCurve],
        "context_variables": [
            {"name": "messages_today", "label": "Messages today", "type": "int"},
            {"name": "reactions_today", "label": "Reactions today", "type": "int"},
            {"name": "voice_minutes_today", "label": "Voice minutes today", "type": "int"},
            {"name": "messages_lifetime", "label": "Messages (lifetime)", "type": "int"},
            {"name": "user_level", "label": "User level", "type": "int"},
            {"name": "user_xp", "label": "User XP", "type": "int"},
        ],
        "predicate_fields": [
            {"field": "event_type", "label": "Event type", "type": "string"},
            {"field": "channel_id", "label": "Channel", "type": "snowflake"},
            {"field": "user_id", "label": "User", "type": "snowflake"},
            {"field": "metadata.length", "label": "Message length", "type": "int"},
            {"field": "metadata.has_attachment", "label": "Has attachment", "type": "bool"},
            {"field": "metadata.has_embed", "label": "Has embed", "type": "bool"},
            {"field": "metadata.is_reply", "label": "Is reply", "type": "bool"},
            {"field": "context.messages_today", "label": "Messages today", "type": "int"},
            {"field": "context.reactions_today", "label": "Reactions today", "type": "int"},
            {
                "field": "context.voice_minutes_today",
                "label": "Voice minutes today",
                "type": "int",
            },
            {"field": "context.user_level", "label": "User level", "type": "int"},
        ],
    }


# ---------------------------------------------------------------------------
# Evaluation Trace
# ---------------------------------------------------------------------------


@router.get("/evaluations")
def list_evaluations(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    user_id: int | None = None,
    snapshot_id: int | None = None,
    admin: dict = Depends(rate_limited_admin),
    session: Session = Depends(get_session),
    cfg: SynapseConfig = Depends(get_config),
):
    """Paginated query of rule evaluation traces."""
    base = select(RuleEvaluation).where(RuleEvaluation.guild_id == cfg.guild_id)
    count_base = (
        select(sa_func.count())
        .select_from(RuleEvaluation)
        .where(RuleEvaluation.guild_id == cfg.guild_id)
    )

    if user_id is not None:
        base = base.where(RuleEvaluation.user_id == user_id)
        count_base = count_base.where(RuleEvaluation.user_id == user_id)
    if snapshot_id is not None:
        base = base.where(RuleEvaluation.snapshot_id == snapshot_id)
        count_base = count_base.where(RuleEvaluation.snapshot_id == snapshot_id)

    total = session.scalar(count_base) or 0
    rows = list(
        session.scalars(
            base.order_by(RuleEvaluation.evaluated_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "evaluations": [
            {
                "id": e.id,
                "user_id": str(e.user_id) if e.user_id else None,
                "event_lake_id": str(e.event_lake_id) if e.event_lake_id else None,
                "snapshot_id": e.snapshot_id,
                "matched_rules": e.matched_rules,
                "outcomes_applied": e.outcomes_applied,
                "context_snapshot": e.context_snapshot,
                "evaluated_at": e.evaluated_at.isoformat() if e.evaluated_at else None,
            }
            for e in rows
        ],
    }


# ---------------------------------------------------------------------------
# Projection Status
# ---------------------------------------------------------------------------


@router.get("/projections/status")
def projection_status(
    admin: dict = Depends(rate_limited_admin),
    session: Session = Depends(get_session),
    cfg: SynapseConfig = Depends(get_config),
):
    """Return projection worker checkpoint status and lag."""
    checkpoints = list(session.scalars(select(ProjectionCheckpoint)))

    # Get latest evaluation ID
    latest_eval_id = (
        session.scalar(
            select(sa_func.max(RuleEvaluation.id)).where(RuleEvaluation.guild_id == cfg.guild_id)
        )
        or 0
    )

    total_evals = (
        session.scalar(
            select(sa_func.count())
            .select_from(RuleEvaluation)
            .where(RuleEvaluation.guild_id == cfg.guild_id)
        )
        or 0
    )

    workers = []
    for cp in checkpoints:
        lag = latest_eval_id - cp.last_processed_evaluation_id
        workers.append(
            {
                "worker_id": cp.worker_id,
                "last_processed_id": cp.last_processed_evaluation_id,
                "updated_at": cp.updated_at.isoformat() if cp.updated_at else None,
                "lag": max(0, lag),
            }
        )

    return {
        "latest_evaluation_id": latest_eval_id,
        "total_evaluations": total_evals,
        "workers": workers,
    }


# ---------------------------------------------------------------------------
# Individual Rule CRUD (Moved to end to avoid path collisions)
# ---------------------------------------------------------------------------


@router.get("/{rule_id}")
def get_rule(
    rule_id: int,
    admin: dict = Depends(rate_limited_admin),
    engine: Engine = Depends(get_engine),
):
    """Get a single reward rule by ID."""
    rule = admin_service.get_reward_rule(engine, rule_id)
    if rule is None:
        raise HTTPException(404, "Rule not found.")
    return _rule_dict(rule)


@router.patch("/{rule_id}")
def update_rule(
    rule_id: int,
    body: RuleUpdate,
    admin: dict = Depends(rate_limited_admin),
    engine: Engine = Depends(get_engine),
):
    """Update mutable fields on a reward rule."""
    kwargs: dict[str, Any] = {}
    if body.name is not None:
        kwargs["name"] = body.name
    if body.predicates is not None:
        kwargs["predicates"] = body.predicates
    if body.outcomes is not None:
        kwargs["outcomes"] = body.outcomes
    if body.priority is not None:
        kwargs["priority"] = body.priority
    if body.is_active is not None:
        kwargs["is_active"] = body.is_active
    if not kwargs:
        raise HTTPException(400, "No fields to update.")
    rule = admin_service.update_reward_rule(
        engine,
        rule_id,
        actor_id=int(admin["sub"]),
        **kwargs,
    )
    if rule is None:
        raise HTTPException(404, "Rule not found.")
    return _rule_dict(rule)


@router.delete("/{rule_id}", status_code=200)
def delete_rule(
    rule_id: int,
    admin: dict = Depends(rate_limited_admin),
    engine: Engine = Depends(get_engine),
):
    """Delete a reward rule."""
    deleted = admin_service.delete_reward_rule(
        engine,
        rule_id,
        actor_id=int(admin["sub"]),
    )
    if not deleted:
        raise HTTPException(404, "Rule not found.")
    return {"deleted": True}
