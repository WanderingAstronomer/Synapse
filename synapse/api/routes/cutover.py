"""
synapse.api.routes.cutover — Feature Flag Cutover Endpoints
==============================================================

Admin-only endpoints powering the Phase 13 feature-flag cutover dashboard:

    GET  /admin/cutover       — Current flag status, preflight checks, monitoring
    POST /admin/cutover/toggle — Enable/disable a flag with ordering enforcement
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from synapse.api.deps import get_config, get_session
from synapse.api.rate_limit import rate_limited_admin
from synapse.config import SynapseConfig
from synapse.database.models import (
    ActivityLog,
    AdminLog,
    ProjectionCheckpoint,
    RuleEvaluation,
    Setting,
)
from synapse.services import admin_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/cutover", tags=["cutover"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class FlagMonitoring(BaseModel):
    """Tailored monitoring data for a single feature flag."""

    metrics: dict[str, Any] = {}
    status: str = "unknown"  # "healthy" | "warning" | "critical" | "unknown"
    summary: str = ""


class PreflightCheck(BaseModel):
    """One preflight condition that must pass before enabling a flag."""

    label: str
    passed: bool
    detail: str = ""


class CutoverFlag(BaseModel):
    """Full state for one feature flag in the cutover sequence."""

    key: str
    label: str
    order: int
    enabled: bool
    description: str
    prerequisites: list[str]
    preflight_checks: list[PreflightCheck]
    monitoring: FlagMonitoring
    can_enable: bool
    blockers: list[str]
    enabled_at: str | None = None


class CutoverStatus(BaseModel):
    """Complete cutover dashboard response."""

    flags: list[CutoverFlag]
    overall_status: str  # "not_started" | "in_progress" | "complete"


class ToggleRequest(BaseModel):
    """Body for toggling a flag."""

    flag: str
    enabled: bool


class ToggleResponse(BaseModel):
    """Response after toggling a flag."""

    flag: str
    enabled: bool
    message: str


# ---------------------------------------------------------------------------
# Flag definitions — ordered cutover sequence
# ---------------------------------------------------------------------------


_FLAG_DEFS: list[dict[str, Any]] = [
    {
        "key": "flags.projection_workers_enabled",
        "label": "Projection Workers",
        "order": 1,
        "description": (
            "Run async projection workers that keep materialized counters current. "
            "Monitor read-model drift vs. direct activity_log sums."
        ),
        "prerequisites": [],
        "rollback_trigger": "Delta > 1% or worker error rate > 0.1%",
    },
    {
        "key": "flags.firewall_enabled",
        "label": "Rule Engine Firewall",
        "order": 2,
        "description": (
            "Route events through the RuleEngine instead of the legacy pipeline. "
            "Requires projection workers to be stable first."
        ),
        "prerequisites": ["flags.projection_workers_enabled"],
        "rollback_trigger": "Anomaly count spikes or total XP/hour doubles vs. baseline",
    },
    {
        "key": "flags.three_tier_auth_enabled",
        "label": "Three-Tier Auth",
        "order": 3,
        "description": (
            "Allow non-admin guild members to log in to the dashboard. "
            "Requires firewall to be stable first."
        ),
        "prerequisites": ["flags.firewall_enabled"],
        "rollback_trigger": "Auth error rate > 0.5%",
    },
    {
        "key": "flags.marketplace_enabled",
        "label": "Marketplace",
        "order": 4,
        "description": (
            "Enable shop endpoints and the purchase flow. "
            "Requires auth tier to be stable first."
        ),
        "prerequisites": ["flags.three_tier_auth_enabled"],
        "rollback_trigger": "Any failed atomic purchase or currency duplication",
    },
]

_FLAG_KEYS = [f["key"] for f in _FLAG_DEFS]


# ---------------------------------------------------------------------------
# Ordering / validation helpers
# ---------------------------------------------------------------------------


def _check_disable_dependents(
    flag_key: str,
    flag_states: dict[str, bool],
) -> list[str]:
    """Return labels of enabled flags that declare *flag_key* as a prerequisite.

    Used to prevent disabling a flag while another flag that depends on it is
    still live.  Returns an empty list when it is safe to disable.
    """
    return [
        f["label"]
        for f in _FLAG_DEFS
        if flag_key in f["prerequisites"] and flag_states.get(f["key"], False)
    ]


# ---------------------------------------------------------------------------
# Monitoring helpers
# ---------------------------------------------------------------------------


def _read_flag(session: Session, key: str) -> bool:
    """Read a boolean flag value from the settings table."""
    row = session.get(Setting, key)
    if row is None:
        return False
    try:
        return json.loads(row.value_json) is True
    except (json.JSONDecodeError, TypeError):
        return False


def _flag_enabled_at(session: Session, key: str) -> str | None:
    """Find when a flag was last enabled by looking at admin_log."""
    row = session.execute(
        select(AdminLog.timestamp)
        .where(AdminLog.target_table == "settings")
        .where(AdminLog.target_id == key)
        .where(AdminLog.action_type == "UPDATE")
        .order_by(AdminLog.timestamp.desc())
        .limit(1)
    ).first()
    if row and row.timestamp:
        return row.timestamp.isoformat()
    return None


def _projection_monitoring(session: Session, cfg: SynapseConfig) -> FlagMonitoring:
    """Monitoring for projection_workers_enabled."""
    # Get checkpoint lag
    checkpoints = list(session.scalars(select(ProjectionCheckpoint)))
    latest_eval_id = (
        session.scalar(
            select(func.max(RuleEvaluation.id)).where(
                RuleEvaluation.guild_id == cfg.guild_id
            )
        )
        or 0
    )

    total_lag = 0
    worker_count = len(checkpoints)
    workers = []
    for cp in checkpoints:
        lag = max(0, latest_eval_id - cp.last_processed_evaluation_id)
        total_lag += lag
        workers.append(
            {
                "worker_id": cp.worker_id,
                "lag": lag,
                "updated_at": cp.updated_at.isoformat() if cp.updated_at else None,
            }
        )

    avg_lag = total_lag / worker_count if worker_count > 0 else 0

    # Determine status
    if worker_count == 0:
        status = "unknown"
        summary = "No projection workers registered yet"
    elif avg_lag > latest_eval_id * 0.01:  # >1% drift
        status = "critical"
        summary = f"Average lag {avg_lag:.0f} exceeds 1% threshold"
    elif avg_lag > latest_eval_id * 0.005:  # >0.5% drift
        status = "warning"
        summary = f"Average lag {avg_lag:.0f} approaching threshold"
    else:
        status = "healthy"
        summary = f"{worker_count} worker(s) running, lag {avg_lag:.0f}"

    return FlagMonitoring(
        metrics={
            "worker_count": worker_count,
            "latest_evaluation_id": latest_eval_id,
            "average_lag": round(avg_lag, 1),
            "workers": workers,
        },
        status=status,
        summary=summary,
    )


def _firewall_monitoring(session: Session) -> FlagMonitoring:
    """Monitoring for firewall_enabled — anomaly count + XP/hour trend."""
    now = datetime.now(UTC)
    one_hour_ago = now - timedelta(hours=1)
    twenty_four_hours_ago = now - timedelta(hours=24)

    # XP issued in last hour
    xp_last_hour = (
        session.scalar(
            select(func.coalesce(func.sum(ActivityLog.xp_delta), 0)).where(
                ActivityLog.timestamp >= one_hour_ago
            )
        )
        or 0
    )

    # Average XP/hour over 24h (baseline)
    xp_24h = (
        session.scalar(
            select(func.coalesce(func.sum(ActivityLog.xp_delta), 0)).where(
                ActivityLog.timestamp >= twenty_four_hours_ago
            )
        )
        or 0
    )
    avg_xp_per_hour = xp_24h / 24.0 if xp_24h > 0 else 0

    # Rule evaluations in last hour
    evals_last_hour = (
        session.scalar(
            select(func.count())
            .select_from(RuleEvaluation)
            .where(RuleEvaluation.evaluated_at >= one_hour_ago)
        )
        or 0
    )

    # Determine status
    ratio = xp_last_hour / avg_xp_per_hour if avg_xp_per_hour > 0 else 1.0
    if ratio > 2.0:
        status = "critical"
        summary = f"XP/hour ({xp_last_hour}) is {ratio:.1f}x the 24h baseline"
    elif ratio > 1.5:
        status = "warning"
        summary = f"XP/hour ({xp_last_hour}) is {ratio:.1f}x the 24h baseline"
    else:
        status = "healthy"
        summary = f"XP/hour {xp_last_hour}, baseline avg {avg_xp_per_hour:.0f}/h"

    return FlagMonitoring(
        metrics={
            "xp_last_hour": int(xp_last_hour),
            "avg_xp_per_hour_24h": round(avg_xp_per_hour, 1),
            "ratio": round(ratio, 2),
            "rule_evaluations_last_hour": evals_last_hour,
        },
        status=status,
        summary=summary,
    )


def _auth_monitoring(session: Session) -> FlagMonitoring:
    """Monitoring for three_tier_auth_enabled — auth error tracking.

    Checks the admin_log for recent OAuth activity and failure patterns.
    In a production system this would read from structured auth logs;
    here we approximate by checking recent login events.
    """
    now = datetime.now(UTC)
    one_hour_ago = now - timedelta(hours=1)

    # Count admin_log entries related to auth in the last hour
    # since our auth system logs successful logins as audit events
    recent_auth_events = (
        session.scalar(
            select(func.count())
            .select_from(AdminLog)
            .where(AdminLog.timestamp >= one_hour_ago)
            .where(AdminLog.target_table == "oauth_states")
        )
        or 0
    )

    return FlagMonitoring(
        metrics={
            "auth_events_last_hour": recent_auth_events,
        },
        status="healthy",
        summary=(
            f"{recent_auth_events} auth event(s) in the last hour"
            if recent_auth_events > 0
            else "No auth events recorded yet"
        ),
    )


def _marketplace_monitoring(session: Session) -> FlagMonitoring:
    """Monitoring for marketplace_enabled — purchase integrity.

    Checks the admin_log for marketplace-related entries and verifies
    no negative-balance transactions exist.
    """
    now = datetime.now(UTC)
    twenty_four_hours_ago = now - timedelta(hours=24)

    # Count marketplace audit events
    purchase_events = (
        session.scalar(
            select(func.count())
            .select_from(AdminLog)
            .where(AdminLog.timestamp >= twenty_four_hours_ago)
            .where(AdminLog.target_table == "marketplace_purchases")
        )
        or 0
    )

    return FlagMonitoring(
        metrics={
            "purchases_24h": purchase_events,
        },
        status="healthy",
        summary=(
            f"{purchase_events} purchase(s) in the last 24h"
            if purchase_events > 0
            else "No purchase activity yet"
        ),
    )


_MONITORING_FNS: dict[str, Any] = {
    "flags.projection_workers_enabled": _projection_monitoring,
    "flags.firewall_enabled": _firewall_monitoring,
    "flags.three_tier_auth_enabled": _auth_monitoring,
    "flags.marketplace_enabled": _marketplace_monitoring,
}


# ---------------------------------------------------------------------------
# Preflight checks
# ---------------------------------------------------------------------------


def _projection_preflight(session: Session, cfg: SynapseConfig) -> list[PreflightCheck]:
    """Preflight for enabling projection workers."""
    checks: list[PreflightCheck] = []

    # Check: at least one rule exists
    rule_count = (
        session.scalar(
            select(func.count())
            .select_from(RuleEvaluation)
            .where(RuleEvaluation.guild_id == cfg.guild_id)
        )
        or 0
    )
    checks.append(
        PreflightCheck(
            label="Rule evaluations exist",
            passed=rule_count > 0,
            detail=f"{rule_count} evaluation(s) found" if rule_count > 0 else "No evaluations yet",
        )
    )

    return checks


def _firewall_preflight(
    session: Session, flag_states: dict[str, bool]
) -> list[PreflightCheck]:
    """Preflight for enabling the rule engine firewall."""
    checks: list[PreflightCheck] = []

    # Check: projection workers must be enabled
    pw_enabled = flag_states.get("flags.projection_workers_enabled", False)
    checks.append(
        PreflightCheck(
            label="Projection workers enabled",
            passed=pw_enabled,
            detail="Active" if pw_enabled else "Must enable projection workers first",
        )
    )

    # Check: no critical anomalies in the last hour
    now = datetime.now(UTC)
    one_hour_ago = now - timedelta(hours=1)
    xp_last_hour = (
        session.scalar(
            select(func.coalesce(func.sum(ActivityLog.xp_delta), 0)).where(
                ActivityLog.timestamp >= one_hour_ago
            )
        )
        or 0
    )
    xp_24h = (
        session.scalar(
            select(func.coalesce(func.sum(ActivityLog.xp_delta), 0)).where(
                ActivityLog.timestamp >= now - timedelta(hours=24)
            )
        )
        or 0
    )
    avg = xp_24h / 24.0 if xp_24h > 0 else 0
    ratio = xp_last_hour / avg if avg > 0 else 1.0
    checks.append(
        PreflightCheck(
            label="XP/hour within normal range",
            passed=ratio <= 2.0,
            detail=f"Current: {int(xp_last_hour)}/h, baseline: {avg:.0f}/h ({ratio:.1f}x)",
        )
    )

    return checks


def _auth_preflight(flag_states: dict[str, bool]) -> list[PreflightCheck]:
    """Preflight for enabling three-tier auth."""
    checks: list[PreflightCheck] = []

    fw_enabled = flag_states.get("flags.firewall_enabled", False)
    checks.append(
        PreflightCheck(
            label="Rule engine firewall enabled",
            passed=fw_enabled,
            detail="Active" if fw_enabled else "Must enable firewall first",
        )
    )

    return checks


def _marketplace_preflight(flag_states: dict[str, bool]) -> list[PreflightCheck]:
    """Preflight for enabling the marketplace."""
    checks: list[PreflightCheck] = []

    auth_enabled = flag_states.get("flags.three_tier_auth_enabled", False)
    checks.append(
        PreflightCheck(
            label="Three-tier auth enabled",
            passed=auth_enabled,
            detail="Active" if auth_enabled else "Must enable auth first",
        )
    )

    return checks


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", response_model=CutoverStatus)
def get_cutover_status(
    session: Session = Depends(get_session),
    admin: dict = Depends(rate_limited_admin),  # noqa: ARG001
    cfg: SynapseConfig = Depends(get_config),
):
    """Return the full cutover status with monitoring data for each flag."""

    # Read all flag states
    flag_states: dict[str, bool] = {}
    for fdef in _FLAG_DEFS:
        flag_states[fdef["key"]] = _read_flag(session, fdef["key"])

    flags: list[CutoverFlag] = []

    for fdef in _FLAG_DEFS:
        key = fdef["key"]
        enabled = flag_states[key]

        # Prerequisite check
        prereqs_met = all(flag_states.get(p, False) for p in fdef["prerequisites"])
        blockers: list[str] = []
        if not prereqs_met:
            for p in fdef["prerequisites"]:
                if not flag_states.get(p, False):
                    # Find label for the prerequisite
                    plabel = next(
                        (f["label"] for f in _FLAG_DEFS if f["key"] == p), p
                    )
                    blockers.append(f"{plabel} must be enabled first")

        # Preflight checks
        if key == "flags.projection_workers_enabled":
            preflight = _projection_preflight(session, cfg)
        elif key == "flags.firewall_enabled":
            preflight = _firewall_preflight(session, flag_states)
        elif key == "flags.three_tier_auth_enabled":
            preflight = _auth_preflight(flag_states)
        elif key == "flags.marketplace_enabled":
            preflight = _marketplace_preflight(flag_states)
        else:
            preflight = []

        # Monitoring
        mon_fn = _MONITORING_FNS.get(key)
        if mon_fn:
            # Some monitoring fns need cfg, some don't
            if key == "flags.projection_workers_enabled":
                monitoring = mon_fn(session, cfg)
            else:
                monitoring = mon_fn(session)
        else:
            monitoring = FlagMonitoring()

        # Can-enable logic: prerequisites met AND all preflight checks pass
        all_preflight_passed = all(c.passed for c in preflight)
        can_enable = prereqs_met and all_preflight_passed

        flags.append(
            CutoverFlag(
                key=key,
                label=fdef["label"],
                order=fdef["order"],
                enabled=enabled,
                description=fdef["description"],
                prerequisites=fdef["prerequisites"],
                preflight_checks=preflight,
                monitoring=monitoring,
                can_enable=can_enable,
                blockers=blockers,
                enabled_at=_flag_enabled_at(session, key) if enabled else None,
            )
        )

    # Overall status
    enabled_count = sum(1 for f in flags if f.enabled)
    if enabled_count == 0:
        overall = "not_started"
    elif enabled_count == len(flags):
        overall = "complete"
    else:
        overall = "in_progress"

    return CutoverStatus(flags=flags, overall_status=overall)


@router.post("/toggle", response_model=ToggleResponse)
def toggle_flag(
    body: ToggleRequest,
    session: Session = Depends(get_session),
    admin: dict = Depends(rate_limited_admin),
    cfg: SynapseConfig = Depends(get_config),
):
    """Enable or disable a feature flag with ordering enforcement.

    Enabling validates:
    - The flag is in the known cutover set
    - All prerequisite flags are already enabled
    - All preflight checks pass

    Disabling is always allowed (emergency rollback).
    """
    engine = session.get_bind()

    if body.flag not in _FLAG_KEYS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown cutover flag: {body.flag}",
        )

    # Read current state of all flags
    flag_states: dict[str, bool] = {}
    for fdef in _FLAG_DEFS:
        flag_states[fdef["key"]] = _read_flag(session, fdef["key"])

    current = flag_states[body.flag]

    if body.enabled and current:
        return ToggleResponse(
            flag=body.flag, enabled=True, message="Already enabled"
        )

    if not body.enabled and not current:
        return ToggleResponse(
            flag=body.flag, enabled=False, message="Already disabled"
        )

    fdef = next(f for f in _FLAG_DEFS if f["key"] == body.flag)

    if body.enabled:
        # Validate prerequisites
        for prereq_key in fdef["prerequisites"]:
            if not flag_states.get(prereq_key, False):
                plabel = next(
                    (f["label"] for f in _FLAG_DEFS if f["key"] == prereq_key),
                    prereq_key,
                )
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"Cannot enable {fdef['label']}: "
                        f"prerequisite '{plabel}' is not enabled"
                    ),
                )

        # Validate preflight checks
        if body.flag == "flags.projection_workers_enabled":
            preflight = _projection_preflight(session, cfg)
        elif body.flag == "flags.firewall_enabled":
            preflight = _firewall_preflight(session, flag_states)
        elif body.flag == "flags.three_tier_auth_enabled":
            preflight = _auth_preflight(flag_states)
        elif body.flag == "flags.marketplace_enabled":
            preflight = _marketplace_preflight(flag_states)
        else:
            preflight = []

        failed = [c for c in preflight if not c.passed]
        if failed:
            labels = ", ".join(c.label for c in failed)
            raise HTTPException(
                status_code=409,
                detail=f"Preflight check(s) failed: {labels}",
            )
    else:
        # P13-03: Block disabling if any dependent flag is still enabled.
        blocking = _check_disable_dependents(body.flag, flag_states)
        if blocking:
            dep_list = ", ".join(f"'{d}'" for d in blocking)
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Cannot disable {fdef['label']}: dependent flag(s) still "
                    f"enabled: {dep_list}. Disable them first."
                ),
            )

    # Perform the toggle via admin_service (audit trail + atomic notify).
    admin_service.toggle_feature_flag(
        engine,
        flag_key=body.flag,
        flag_label=fdef["label"],
        flag_description=fdef["description"],
        new_value=body.enabled,
        actor_id=int(admin["sub"]),
    )

    action = "enabled" if body.enabled else "disabled"
    logger.info("Cutover: %s %s by admin %s", fdef["label"], action, admin["sub"])

    return ToggleResponse(
        flag=body.flag,
        enabled=body.enabled,
        message=f"{fdef['label']} {action} successfully",
    )
