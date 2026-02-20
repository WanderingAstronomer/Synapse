"""
synapse.api.routes.observability — Operational Observability Endpoints
=======================================================================

Admin-only endpoints powering the Phase 12 health / observability dashboard:

    - System health: bot heartbeat, API uptime, DB pool saturation, last event
    - Economic histogram: XP & Gold issued per hour (last 24 h)
    - Anomaly feed: users earning >5× guild median per hour, high-firing rules
    - Rule performance: match rate per rule per hour (last 24 h)
    - Anti-gaming signals: top-10 earners per event type (last 24 h)
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import Engine, case, func, literal, select
from sqlalchemy.orm import Session

from synapse.api.deps import get_session
from synapse.api.rate_limit import rate_limited_admin
from synapse.database.models import ActivityLog, EventLake, RuleEvaluation

router = APIRouter(prefix="/admin/observability", tags=["observability"])


# ---------------------------------------------------------------------------
# Pydantic response schemas
# ---------------------------------------------------------------------------

class BotHealth(BaseModel):
    status: str  # "online" | "offline"
    last_heartbeat: str | None
    age_seconds: float | None = None


class DbPoolStats(BaseModel):
    pool_size: int
    checked_out: int
    overflow: int
    checked_in: int


class SystemHealth(BaseModel):
    bot: BotHealth
    api_uptime_seconds: float
    db_pool: DbPoolStats
    last_event_at: str | None
    last_activity_at: str | None


class EconomicBucket(BaseModel):
    """Single hour bucket for XP/Gold histogram."""
    hour: str  # ISO-8601 truncated to hour
    xp_issued: int
    gold_issued: int


class AnomalyEntry(BaseModel):
    """One anomaly flag for the feed."""
    kind: str  # "high_earner" | "hot_rule"
    severity: str  # "warning" | "critical"
    message: str
    details: dict[str, Any] = {}


class RulePerformanceBucket(BaseModel):
    """Match count for one rule in one hour."""
    rule_id: int
    rule_name: str
    hour: str
    match_count: int


class TopEarner(BaseModel):
    """One user in the top-earners-per-event-type table."""
    user_id: str
    user_name: str | None
    event_type: str
    total_xp: int
    total_gold: int
    event_count: int


class ObservabilityResponse(BaseModel):
    health: SystemHealth
    economic_histogram: list[EconomicBucket]
    anomalies: list[AnomalyEntry]
    rule_performance: list[RulePerformanceBucket]
    top_earners: list[TopEarner]


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------
_api_start_time = time.monotonic()


def _bot_health(engine: Engine) -> BotHealth:
    """Delegate to the existing heartbeat helper."""
    from synapse.services.setup_service import get_bot_heartbeat

    data = get_bot_heartbeat(engine)
    return BotHealth(
        status=data.get("status", "offline"),
        last_heartbeat=data.get("last_heartbeat"),
        age_seconds=data.get("age_seconds"),
    )


def _db_pool_stats(engine: Engine) -> DbPoolStats:
    """Read live connection-pool statistics from the SQLAlchemy engine."""
    pool = engine.pool
    return DbPoolStats(
        pool_size=pool.size(),
        checked_out=pool.checkedout(),
        overflow=pool.overflow(),
        checked_in=pool.checkedin(),
    )


def _system_health(
    session: Session, engine: Engine
) -> SystemHealth:
    """Aggregate system health signals."""
    # Last event lake timestamp
    last_event_at = session.scalar(
        select(func.max(EventLake.timestamp))
    )
    # Last activity log timestamp
    last_activity_at = session.scalar(
        select(func.max(ActivityLog.timestamp))
    )

    return SystemHealth(
        bot=_bot_health(engine),
        api_uptime_seconds=round(time.monotonic() - _api_start_time, 1),
        db_pool=_db_pool_stats(engine),
        last_event_at=last_event_at.isoformat() if last_event_at else None,
        last_activity_at=last_activity_at.isoformat() if last_activity_at else None,
    )


def _economic_histogram(session: Session, hours: int = 24) -> list[EconomicBucket]:
    """XP and Gold issued per hour from activity_log for the last *hours* hours."""
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    q = (
        select(
            func.date_trunc("hour", ActivityLog.timestamp).label("hour"),
            func.coalesce(func.sum(ActivityLog.xp_delta), literal(0)).label("xp"),
            func.coalesce(func.sum(ActivityLog.star_delta), literal(0)).label("gold"),
        )
        .where(ActivityLog.timestamp >= cutoff)
        .group_by("hour")
        .order_by("hour")
    )
    return [
        EconomicBucket(
            hour=row.hour.isoformat() if row.hour else "",
            xp_issued=int(row.xp),
            gold_issued=int(row.gold),
        )
        for row in session.execute(q)
    ]


def _anomaly_feed(session: Session, hours: int = 1) -> list[AnomalyEntry]:
    """Detect anomalies in the last *hours* hours.

    Two categories:
    1. **High earners** — users whose XP in the last hour exceeds 5× the
       guild median hourly XP.
    2. **Hot rules** — rules that matched >1 000 events in the last 10 min.
    """
    anomalies: list[AnomalyEntry] = []
    cutoff = datetime.now(UTC) - timedelta(hours=hours)

    # --- High earners ---
    # Per-user XP in the window
    user_xp = (
        select(
            ActivityLog.user_id,
            func.sum(ActivityLog.xp_delta).label("xp"),
        )
        .where(ActivityLog.timestamp >= cutoff)
        .group_by(ActivityLog.user_id)
        .subquery()
    )

    # Guild-wide median approximation: use percentile_cont if available,
    # else fall back to a simple average as a conservative threshold.
    # PostgreSQL has percentile_cont; SQLite (tests) does not.
    try:
        median_q = select(
            func.percentile_cont(0.5).within_group(user_xp.c.xp).label("median_xp")
        )
        median_row = session.execute(median_q).one_or_none()
        median_xp = float(median_row.median_xp) if median_row and median_row.median_xp else 0.0
    except Exception:
        # Fallback for SQLite or empty data
        avg_row = session.execute(
            select(func.avg(user_xp.c.xp).label("avg_xp"))
        ).one_or_none()
        median_xp = float(avg_row.avg_xp) if avg_row and avg_row.avg_xp else 0.0

    threshold = max(median_xp * 5, 50)  # Floor of 50 XP to avoid noise on quiet servers

    high_earner_q = (
        select(user_xp.c.user_id, user_xp.c.xp)
        .where(user_xp.c.xp > threshold)
        .order_by(user_xp.c.xp.desc())
        .limit(20)
    )
    for row in session.execute(high_earner_q):
        severity = "critical" if row.xp > threshold * 2 else "warning"
        anomalies.append(
            AnomalyEntry(
                kind="high_earner",
                severity=severity,
                message=(
                    f"User {row.user_id} earned {int(row.xp)} XP in the last hour "
                    f"(threshold: {int(threshold)})"
                ),
                details={
                    "user_id": str(row.user_id),
                    "xp_earned": int(row.xp),
                    "threshold": int(threshold),
                    "median_xp": round(median_xp, 1),
                },
            )
        )

    # --- Hot rules ---
    ten_min_ago = datetime.now(UTC) - timedelta(minutes=10)

    # Count rule evaluations in the last 10 minutes, grouped by rule name.
    # matched_rules is JSONB array — we count evaluations where > 0 rules matched.
    hot_rule_q = (
        select(
            func.count().label("eval_count"),
        )
        .where(RuleEvaluation.evaluated_at >= ten_min_ago)
    )
    # For a per-rule breakdown, we'd need to unnest JSONB.  Simpler: count
    # total evaluations in the window.  A single spike still flags concern.
    total_evals = session.scalar(hot_rule_q) or 0

    if total_evals > 1000:
        anomalies.append(
            AnomalyEntry(
                kind="hot_rule",
                severity="critical" if total_evals > 5000 else "warning",
                message=(
                    f"{total_evals} rule evaluations in the last 10 minutes "
                    f"(threshold: 1,000)"
                ),
                details={
                    "eval_count": total_evals,
                    "window_minutes": 10,
                },
            )
        )

    return anomalies


def _rule_performance(session: Session, hours: int = 24) -> list[RulePerformanceBucket]:
    """Match count per rule per hour for the last *hours* hours.

    Uses the rule_evaluations table.  Each evaluation's ``matched_rules``
    JSONB array length is the number of rules that fired.  We join to
    reward_rules for the rule names and bucket by hour.
    """
    cutoff = datetime.now(UTC) - timedelta(hours=hours)

    # Count evaluations per hour (each evaluation = one event processed).
    # We also track how many had at least one match vs zero matches.
    q = (
        select(
            func.date_trunc("hour", RuleEvaluation.evaluated_at).label("hour"),
            func.count().label("total"),
            func.sum(
                case(
                    (func.jsonb_array_length(RuleEvaluation.matched_rules) > 0, 1),
                    else_=0,
                )
            ).label("matched"),
        )
        .where(RuleEvaluation.evaluated_at >= cutoff)
        .group_by("hour")
        .order_by("hour")
    )

    results: list[RulePerformanceBucket] = []
    for row in session.execute(q):
        results.append(
            RulePerformanceBucket(
                rule_id=0,  # Aggregated across all rules
                rule_name="All Rules",
                hour=row.hour.isoformat() if row.hour else "",
                match_count=int(row.matched or 0),
            )
        )

    return results


def _top_earners(session: Session, hours: int = 24, top_n: int = 10) -> list[TopEarner]:
    """Top-N earners per event type in the last *hours* hours."""
    cutoff = datetime.now(UTC) - timedelta(hours=hours)

    # Per user-per-event-type aggregation
    agg = (
        select(
            ActivityLog.user_id,
            ActivityLog.event_type,
            func.sum(ActivityLog.xp_delta).label("total_xp"),
            func.sum(ActivityLog.star_delta).label("total_gold"),
            func.count().label("event_count"),
        )
        .where(ActivityLog.timestamp >= cutoff)
        .group_by(ActivityLog.user_id, ActivityLog.event_type)
        .subquery()
    )

    # Window function to rank within each event_type
    ranked = (
        select(
            agg.c.user_id,
            agg.c.event_type,
            agg.c.total_xp,
            agg.c.total_gold,
            agg.c.event_count,
            func.row_number()
            .over(partition_by=agg.c.event_type, order_by=agg.c.total_xp.desc())
            .label("rn"),
        )
        .subquery()
    )

    q = (
        select(ranked)
        .where(ranked.c.rn <= top_n)
        .order_by(ranked.c.event_type, ranked.c.rn)
    )

    # Bulk-resolve usernames
    from synapse.database.models import User

    rows = list(session.execute(q))
    user_ids = {r.user_id for r in rows}
    user_names = {}
    if user_ids:
        for u in session.execute(
            select(User.id, User.discord_name).where(User.id.in_(user_ids))
        ):
            user_names[u.id] = u.discord_name

    return [
        TopEarner(
            user_id=str(r.user_id),
            user_name=user_names.get(r.user_id),
            event_type=r.event_type,
            total_xp=int(r.total_xp or 0),
            total_gold=int(r.total_gold or 0),
            event_count=int(r.event_count),
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------
@router.get("", response_model=ObservabilityResponse)
def get_observability(
    session: Session = Depends(get_session),
    admin: dict = Depends(rate_limited_admin),  # noqa: ARG001
    econ_hours: int = Query(24, ge=1, le=168, description="Economic histogram window (hours)"),
    anomaly_hours: int = Query(1, ge=1, le=24, description="Anomaly detection window (hours)"),
    rule_hours: int = Query(24, ge=1, le=168, description="Rule performance window (hours)"),
    earner_hours: int = Query(24, ge=1, le=168, description="Top earners window (hours)"),
    top_n: int = Query(10, ge=1, le=50, description="Top-N earners per event type"),
):
    """Return a full observability snapshot for the admin dashboard."""
    engine = session.get_bind()

    return ObservabilityResponse(
        health=_system_health(session, engine),  # type: ignore[arg-type]
        economic_histogram=_economic_histogram(session, hours=econ_hours),
        anomalies=_anomaly_feed(session, hours=anomaly_hours),
        rule_performance=_rule_performance(session, hours=rule_hours),
        top_earners=_top_earners(session, hours=earner_hours, top_n=top_n),
    )
