"""
synapse.api.routes.event_lake — Event Lake Admin Endpoints
============================================================

JWT-protected admin routes for:
    - Paginated event reads with filters  (Task #14)
    - Data Sources toggle CRUD            (Task #15)
    - Event volume / health metrics       (Task #16)
    - Retention cleanup trigger           (Task #11 companion)
    - Counter reconciliation trigger      (Task #12 companion)
    - Activity-log backfill trigger       (Task #13 companion)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from synapse.api.deps import get_current_admin, get_engine, get_session, get_setting
from synapse.database.models import EventCounter, EventLake
from synapse.services.event_lake_writer import EventType

router = APIRouter(prefix="/admin/event-lake", tags=["event-lake"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------
class EventRow(BaseModel):
    """Single event from the Event Lake."""
    id: int
    guild_id: str
    user_id: str
    event_type: str
    channel_id: str | None
    target_id: str | None
    payload: dict[str, Any]
    source_id: str | None
    timestamp: str


class EventListResponse(BaseModel):
    """Paginated list of events."""
    total: int
    page: int
    page_size: int
    events: list[EventRow]


class DataSourceConfig(BaseModel):
    """Per–event-type toggle and metadata."""
    event_type: str
    enabled: bool
    label: str
    description: str


class DataSourceToggle(BaseModel):
    """Toggle request body."""
    event_type: str
    enabled: bool


class VolumePoint(BaseModel):
    """Single data point in the volume time-series."""
    date: str
    event_type: str
    count: int


class HealthResponse(BaseModel):
    """Event Lake health / size dashboard."""
    total_events: int
    total_counters: int
    oldest_event: str | None
    newest_event: str | None
    table_size_bytes: int
    events_today: int
    events_7d: int
    volume_by_type: dict[str, int]
    daily_volume: list[VolumePoint]


class RetentionResult(BaseModel):
    events_deleted: int
    counters_deleted: int


class ReconciliationResult(BaseModel):
    checked: int
    corrected: int
    corrections: list[dict[str, Any]]
    timestamp: str


class BackfillResult(BaseModel):
    rows_read: int
    counters_upserted: int
    skipped_types: list[str]
    dry_run: bool
    timestamp: str


class StorageEstimate(BaseModel):
    """§3B.5-style storage estimate."""
    avg_row_bytes: int
    total_rows: int
    estimated_bytes: int
    estimated_mb: float
    estimated_gb: float
    daily_rate: float
    days_of_data: int
    projected_90d_mb: float


# ---------------------------------------------------------------------------
# Canonical data source definitions (§3B.4 + §3B.8)
# ---------------------------------------------------------------------------
DATA_SOURCES: list[dict[str, str]] = [
    {"event_type": EventType.MESSAGE_CREATE,  "label": "Messages",         "description": "Message creation events — privacy-safe metadata only (no content)."},
    {"event_type": EventType.REACTION_ADD,    "label": "Reactions (add)",   "description": "Emoji reactions added to messages."},
    {"event_type": EventType.REACTION_REMOVE, "label": "Reactions (remove)","description": "Emoji reactions removed from messages."},
    {"event_type": EventType.THREAD_CREATE,   "label": "Thread Creation",  "description": "New threads created in the server."},
    {"event_type": EventType.VOICE_JOIN,      "label": "Voice Join",       "description": "Members joining a voice channel."},
    {"event_type": EventType.VOICE_LEAVE,     "label": "Voice Leave",      "description": "Members leaving a voice channel (includes duration)."},
    {"event_type": EventType.VOICE_MOVE,      "label": "Voice Move",       "description": "Members moving between voice channels."},
    {"event_type": EventType.MEMBER_JOIN,     "label": "Member Join",      "description": "New members joining the server."},
    {"event_type": EventType.MEMBER_LEAVE,    "label": "Member Leave",     "description": "Members leaving / being removed from the server."},
]

# Settings key pattern for per-type toggles
_TOGGLE_KEY = "event_lake.source.{event_type}.enabled"


# =========================================================================
# 1.  Paginated Event Read  (Task #14)
# =========================================================================
@router.get("/events", response_model=EventListResponse)
def list_events(
    session: Session = Depends(get_session),
    admin: dict = Depends(get_current_admin),  # noqa: ARG001
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    event_type: str | None = Query(None, description="Filter by event_type"),
    user_id: int | None = Query(None, description="Filter by user_id"),
    channel_id: int | None = Query(None, description="Filter by channel_id"),
    since: str | None = Query(None, description="ISO datetime lower bound"),
    until: str | None = Query(None, description="ISO datetime upper bound"),
):
    """Return a paginated, filterable list of Event Lake rows."""
    q = select(EventLake).order_by(EventLake.timestamp.desc())
    count_q = select(func.count()).select_from(EventLake)

    if event_type:
        q = q.where(EventLake.event_type == event_type)
        count_q = count_q.where(EventLake.event_type == event_type)
    if user_id:
        q = q.where(EventLake.user_id == user_id)
        count_q = count_q.where(EventLake.user_id == user_id)
    if channel_id:
        q = q.where(EventLake.channel_id == channel_id)
        count_q = count_q.where(EventLake.channel_id == channel_id)
    if since:
        q = q.where(EventLake.timestamp >= since)
        count_q = count_q.where(EventLake.timestamp >= since)
    if until:
        q = q.where(EventLake.timestamp <= until)
        count_q = count_q.where(EventLake.timestamp <= until)

    total = session.scalar(count_q) or 0
    rows = session.scalars(q.offset((page - 1) * page_size).limit(page_size)).all()

    events = [
        EventRow(
            id=r.id,
            guild_id=str(r.guild_id),
            user_id=str(r.user_id),
            event_type=r.event_type,
            channel_id=str(r.channel_id) if r.channel_id else None,
            target_id=str(r.target_id) if r.target_id else None,
            payload=r.payload or {},
            source_id=r.source_id,
            timestamp=r.timestamp.isoformat() if r.timestamp else "",
        )
        for r in rows
    ]

    return EventListResponse(total=total, page=page, page_size=page_size, events=events)


# =========================================================================
# 2.  Data Sources Toggle  (Task #15)
# =========================================================================
@router.get("/data-sources", response_model=list[DataSourceConfig])
def list_data_sources(
    session: Session = Depends(get_session),
    admin: dict = Depends(get_current_admin),  # noqa: ARG001
):
    """Return all data source types with their enabled/disabled state."""
    sources: list[DataSourceConfig] = []
    for ds in DATA_SOURCES:
        key = _TOGGLE_KEY.format(event_type=ds["event_type"])
        enabled = get_setting(session, key, default=True)
        # Coerce to bool (might come back as string "true"/"false")
        if isinstance(enabled, str):
            enabled = enabled.lower() not in ("false", "0", "no")
        sources.append(
            DataSourceConfig(
                event_type=ds["event_type"],
                enabled=bool(enabled),
                label=ds["label"],
                description=ds["description"],
            )
        )
    return sources


@router.put("/data-sources", response_model=dict[str, int])
def toggle_data_sources(
    toggles: list[DataSourceToggle],
    session: Session = Depends(get_session),
    engine: Engine = Depends(get_engine),
    admin: dict = Depends(get_current_admin),
):
    """Enable or disable one or more data source types."""
    from synapse.services import settings_service

    valid_types = {ds["event_type"] for ds in DATA_SOURCES}
    updated = 0
    for t in toggles:
        if t.event_type not in valid_types:
            raise HTTPException(400, f"Unknown event type: {t.event_type}")
        key = _TOGGLE_KEY.format(event_type=t.event_type)
        settings_service.upsert_setting(
            engine, key=key, value=t.enabled,
            category="event_lake", description=f"Enable {t.event_type} data source",
        )
        updated += 1

    return {"updated": updated}


# =========================================================================
# 3.  Event Volume & Health Metrics  (Task #16)
# =========================================================================
@router.get("/health", response_model=HealthResponse)
def event_lake_health(
    session: Session = Depends(get_session),
    admin: dict = Depends(get_current_admin),  # noqa: ARG001
    days: int = Query(30, ge=1, le=365, description="Days of daily volume history"),
):
    """Return Event Lake health stats for the admin dashboard."""
    from synapse.services.retention_service import get_retention_stats

    engine = session.get_bind()
    stats = get_retention_stats(engine)

    # Events today
    today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    events_today = session.scalar(
        select(func.count()).select_from(EventLake)
        .where(EventLake.timestamp >= today_start)
    ) or 0

    # Events last 7 days
    seven_days_ago = datetime.now(UTC) - timedelta(days=7)
    events_7d = session.scalar(
        select(func.count()).select_from(EventLake)
        .where(EventLake.timestamp >= seven_days_ago)
    ) or 0

    # Volume by type (all time)
    type_q = (
        select(EventLake.event_type, func.count().label("cnt"))
        .group_by(EventLake.event_type)
    )
    volume_by_type = {row.event_type: row.cnt for row in session.execute(type_q)}

    # Daily volume time-series (last N days)
    cutoff = datetime.now(UTC) - timedelta(days=days)
    daily_q = (
        select(
            func.date_trunc("day", EventLake.timestamp).label("day"),
            EventLake.event_type,
            func.count().label("cnt"),
        )
        .where(EventLake.timestamp >= cutoff)
        .group_by("day", EventLake.event_type)
        .order_by("day")
    )
    daily_volume = [
        VolumePoint(
            date=row.day.strftime("%Y-%m-%d") if row.day else "",
            event_type=row.event_type,
            count=row.cnt,
        )
        for row in session.execute(daily_q)
    ]

    return HealthResponse(
        total_events=stats["total_events"],
        total_counters=stats["total_counters"],
        oldest_event=stats["oldest_event"],
        newest_event=stats["newest_event"],
        table_size_bytes=stats["table_size_bytes"],
        events_today=events_today,
        events_7d=events_7d,
        volume_by_type=volume_by_type,
        daily_volume=daily_volume,
    )


# =========================================================================
# 4.  Storage Estimate Calculator  (Task #19)
# =========================================================================
@router.get("/storage-estimate", response_model=StorageEstimate)
def storage_estimate(
    session: Session = Depends(get_session),
    admin: dict = Depends(get_current_admin),  # noqa: ARG001
):
    """Return a storage estimate based on current data volume.

    Reference: §3B.5 — ~340 bytes per row average.
    """
    AVG_ROW_BYTES = 340  # from design doc estimates

    total_rows = session.scalar(
        select(func.count()).select_from(EventLake)
    ) or 0

    estimated_bytes = total_rows * AVG_ROW_BYTES

    # Calculate days of data for daily rate projection
    oldest = session.scalar(select(func.min(EventLake.timestamp)))
    newest = session.scalar(select(func.max(EventLake.timestamp)))

    if oldest and newest and oldest != newest:
        days_of_data = max((newest - oldest).days, 1)
    else:
        days_of_data = 1

    daily_rate = total_rows / days_of_data
    projected_90d_bytes = daily_rate * 90 * AVG_ROW_BYTES

    return StorageEstimate(
        avg_row_bytes=AVG_ROW_BYTES,
        total_rows=total_rows,
        estimated_bytes=estimated_bytes,
        estimated_mb=round(estimated_bytes / (1024 * 1024), 2),
        estimated_gb=round(estimated_bytes / (1024 ** 3), 4),
        daily_rate=round(daily_rate, 1),
        days_of_data=days_of_data,
        projected_90d_mb=round(projected_90d_bytes / (1024 * 1024), 2),
    )


# =========================================================================
# 5.  Admin Operations (retention, reconciliation, backfill triggers)
# =========================================================================
@router.post("/retention/run", response_model=RetentionResult)
def trigger_retention(
    engine: Engine = Depends(get_engine),
    admin: dict = Depends(get_current_admin),  # noqa: ARG001
    retention_days: int = Query(90, ge=1, le=730),
):
    """Manually trigger Event Lake retention cleanup."""
    from synapse.services.retention_service import run_retention_cleanup

    result = run_retention_cleanup(engine, retention_days=retention_days)
    return RetentionResult(**result)


@router.post("/reconciliation/run", response_model=ReconciliationResult)
def trigger_reconciliation(
    engine: Engine = Depends(get_engine),
    admin: dict = Depends(get_current_admin),  # noqa: ARG001
):
    """Manually trigger counter reconciliation."""
    from synapse.services.reconciliation_service import reconcile_counters

    return ReconciliationResult(**reconcile_counters(engine))


@router.post("/backfill/run", response_model=BackfillResult)
def trigger_backfill(
    engine: Engine = Depends(get_engine),
    admin: dict = Depends(get_current_admin),  # noqa: ARG001
    dry_run: bool = Query(False, description="Preview without writing"),
):
    """Trigger activity_log → event_counters backfill."""
    from synapse.services.backfill_service import backfill_counters_from_activity_log

    return BackfillResult(**backfill_counters_from_activity_log(engine, dry_run=dry_run))


# =========================================================================
# 6.  Counter Lookup  (for admin inspection)
# =========================================================================
@router.get("/counters")
def list_counters(
    session: Session = Depends(get_session),
    admin: dict = Depends(get_current_admin),  # noqa: ARG001
    user_id: int | None = Query(None),
    event_type: str | None = Query(None),
    period: str = Query("lifetime"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    """Browse event counters."""
    q = select(EventCounter).order_by(EventCounter.count.desc())
    if user_id:
        q = q.where(EventCounter.user_id == user_id)
    if event_type:
        q = q.where(EventCounter.event_type == event_type)
    q = q.where(EventCounter.period == period)

    total = session.scalar(
        select(func.count()).select_from(
            q.subquery()
        )
    ) or 0

    rows = session.scalars(q.offset((page - 1) * page_size).limit(page_size)).all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "counters": [
            {
                "user_id": str(c.user_id),
                "event_type": c.event_type,
                "zone_id": c.zone_id,
                "period": c.period,
                "count": c.count,
            }
            for c in rows
        ],
    }
