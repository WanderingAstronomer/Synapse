"""
synapse.services.projection_service — Projection Pipeline Worker
================================================================

Reads ``rule_evaluations`` rows and applies their ``outcomes_applied``
to the User Read Model (``users.xp``, ``users.gold``).

Architecture
------------
This service provides:

1. **ProjectionWorker** — an ``asyncio.Task``-based worker that polls
   ``rule_evaluations`` on a configurable interval and applies batches
   to the Read Model.  Gated behind ``flags.projection_workers_enabled``
   (default ``false``).

2. **_process_batch** — the synchronous core called via ``run_db()``.
   Reads up to ``BATCH_SIZE`` evaluations after the stored checkpoint,
   applies outcomes, and advances the checkpoint in a **single atomic
   transaction**.  Exactly-once semantics: if the commit fails, neither
   the Read Model writes nor the checkpoint advance.

3. **replay_projection** — dry-run aggregate; never writes, returns a
   summary dict.  Used for manual parity checks against current state.

Feature-flag lifecycle
----------------------
The worker starts its asyncio task unconditionally on ``on_ready`` but
immediately sleeps when the flag is ``false``.  Enabling the flag in the
``settings`` table takes effect within ``POLL_INTERVAL_SEC`` without a
restart.

Guardrails
----------
- Batch size capped at ``BATCH_SIZE = 100`` — avoids table-level locks.
- Loop bound at ``MAX_LOOP_ITERATIONS = 1_000_000`` — prevents unbounded
  loops in unexpected edge cases (≈57 days at 5 s/iteration).
- Explicit ``asyncio.sleep`` between polls — never blocks the event loop.
- All DB work goes through ``run_db()`` (``asyncio.to_thread``).
- ``stop()`` is idempotent and graceful — sets an asyncio.Event; the run
  loop checks it each iteration before sleeping.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from synapse.database.engine import run_db
from synapse.database.models import ProjectionCheckpoint, RuleEvaluation, User
from synapse.services.reward_service import get_active_season, get_or_create_stats

if TYPE_CHECKING:
    from sqlalchemy import Engine

    from synapse.engine.cache import ConfigCache

logger = logging.getLogger(__name__)

__all__ = [
    "ProjectionWorker",
    "replay_projection",
    "start_projection_worker",
    "stop_projection_worker",
]

# ---------------------------------------------------------------------------
# Configuration constants
# ---------------------------------------------------------------------------

WORKER_ID = "xp_gold"
BATCH_SIZE = 100
POLL_INTERVAL_SEC = 5.0
MAX_LOOP_ITERATIONS = 1_000_000  # hard bound: ~57 days at 5 s/iteration


# ---------------------------------------------------------------------------
# Synchronous batch processor (called via run_db)
# ---------------------------------------------------------------------------


def _apply_outcomes(
    session: Session,
    user: User,
    outcomes: dict[str, Any],
    guild_id: int,
) -> None:
    """Apply a single evaluation's outcomes to the User read model.

    Parameters
    ----------
    session : Session
        Active SQLAlchemy session (mid-transaction).
    user : User
        The user row to mutate in place.
    outcomes : dict
        ``outcomes_applied`` dict from ``RuleEvaluation``, e.g.
        ``{"xp": 15, "gold": 0}``.
    guild_id : int
        Required to look up the active season.
    """
    xp_delta = int(outcomes.get("xp", 0))
    gold_delta = int(outcomes.get("gold", 0))

    if xp_delta:
        user.xp += xp_delta

    if gold_delta:
        user.gold += gold_delta


def _process_batch(
    engine: Engine,
    worker_id: str,
    batch_size: int,
    guild_id: int,
) -> int:
    """Read up to ``batch_size`` pending evaluations and apply them.

    The checkpoint advance and all Read Model writes share a single
    transaction: exactly-once semantics without a separate applied log.

    Parameters
    ----------
    engine : Engine
        SQLAlchemy engine (synchronous).
    worker_id : str
        Identifies the ``projection_checkpoints`` row for this worker.
    batch_size : int
        Maximum evaluations to process per invocation.
    guild_id : int
        Guild scope for season lookups.

    Returns
    -------
    int
        Number of evaluations processed (0 means queue is empty).
    """
    with Session(engine) as session:
        # Load or initialise checkpoint
        checkpoint = session.get(ProjectionCheckpoint, worker_id)
        if checkpoint is None:
            checkpoint = ProjectionCheckpoint(
                worker_id=worker_id,
                last_processed_evaluation_id=0,
            )
            session.add(checkpoint)
            session.flush()

        last_id = checkpoint.last_processed_evaluation_id

        # Fetch the next batch — only rows with a known user (nullable user_id
        # rows are unapplyable and must be skipped silently)
        evals = session.scalars(
            select(RuleEvaluation)
            .where(
                RuleEvaluation.id > last_id,
                RuleEvaluation.user_id.is_not(None),
            )
            .order_by(RuleEvaluation.id.asc())
            .limit(batch_size)
        ).all()

        if not evals:
            session.commit()
            return 0

        # Cache user rows to avoid redundant SELECTs within the same batch
        user_cache: dict[int, User] = {}

        for evaluation in evals:
            uid = evaluation.user_id
            assert uid is not None  # guaranteed by the query filter above

            if uid not in user_cache:
                user = session.get(User, uid)
                if user is None:
                    logger.warning(
                        "Projection: user %s referenced by evaluation %s not found — skipping",
                        uid,
                        evaluation.id,
                    )
                    continue
                user_cache[uid] = user

            outcomes = evaluation.outcomes_applied or {}
            if not any(outcomes.get(k, 0) for k in ("xp", "gold")):
                continue  # No-op evaluation — advance checkpoint but skip writes

            try:
                _apply_outcomes(
                    session,
                    user_cache[uid],
                    outcomes,
                    evaluation.guild_id,
                )
            except Exception:
                logger.error(
                    "Projection: failed to apply evaluation %s for user %s",
                    evaluation.id,
                    uid,
                    exc_info=True,
                )
                # Abort the entire batch — checkpoint does not advance.
                # Will be retried on the next poll cycle.
                session.rollback()
                return 0

        # Atomic: advance checkpoint in the same commit as the writes
        checkpoint.last_processed_evaluation_id = evals[-1].id
        session.commit()

        logger.debug(
            "Projection batch: processed %d evaluations (ids %d–%d)",
            len(evals),
            evals[0].id,
            evals[-1].id,
        )
        return len(evals)


# ---------------------------------------------------------------------------
# Dry-run replay (no writes)
# ---------------------------------------------------------------------------


def replay_projection(
    engine: Engine,
    from_id: int = 0,
    max_rows: int = 10_000,
) -> dict[str, Any]:
    """Aggregate projection outcomes without writing anything.

    Useful for comparing what the projection pipeline *would* produce
    against the current ``users`` / ``user_stats`` Read Model state.

    Parameters
    ----------
    engine : Engine
        SQLAlchemy engine (synchronous).
    from_id : int
        Start aggregating from evaluations with ``id > from_id``.
    max_rows : int
        Safety cap on how many rows to read (default 10 000).

    Returns
    -------
    dict
        ``{"rows_read": int, "by_user": {user_id: {"xp": int, "gold": int}}}``
    """
    with Session(engine) as session:
        evals = session.scalars(
            select(RuleEvaluation)
            .where(
                RuleEvaluation.id > from_id,
                RuleEvaluation.user_id.is_not(None),
            )
            .order_by(RuleEvaluation.id.asc())
            .limit(max_rows)
        ).all()

    by_user: dict[int, dict[str, int]] = {}
    for ev in evals:
        uid = ev.user_id
        assert uid is not None
        entry = by_user.setdefault(uid, {"xp": 0, "gold": 0})
        outcomes = ev.outcomes_applied or {}
        entry["xp"] += int(outcomes.get("xp", 0))
        entry["gold"] += int(outcomes.get("gold", 0))

    return {"rows_read": len(evals), "by_user": by_user}


# ---------------------------------------------------------------------------
# ProjectionWorker — asyncio task wrapper
# ---------------------------------------------------------------------------


class ProjectionWorker:
    """Async wrapper that polls ``_process_batch`` on a configurable interval.

    Designed to be a singleton per bot process.  Start via
    ``worker.start(engine, cache, guild_id)`` from ``on_ready``; stop via
    ``await worker.stop()`` from ``bot.close()``.

    The worker checks ``flags.projection_workers_enabled`` on every iteration,
    so the feature flag takes effect within ``POLL_INTERVAL_SEC`` without a
    restart.
    """

    def __init__(self) -> None:
        self._stop_event: asyncio.Event = asyncio.Event()
        self._task: asyncio.Task | None = None

    def start(
        self,
        engine: Engine,
        cache: ConfigCache,
        guild_id: int,
    ) -> None:
        """Spawn the background task.  Call from ``on_ready``."""
        if self._task is not None and not self._task.done():
            logger.warning("ProjectionWorker.start() called while already running — ignored")
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(
            self._run(engine, cache, guild_id),
            name="projection_worker",
        )
        logger.info("ProjectionWorker started (guild=%s)", guild_id)

    async def stop(self) -> None:
        """Signal the worker to stop and wait for it to finish."""
        self._stop_event.set()
        if self._task is not None and not self._task.done():
            try:
                await asyncio.wait_for(self._task, timeout=10.0)
            except (TimeoutError, asyncio.CancelledError):
                logger.warning("ProjectionWorker did not finish within 10s; cancelling")
                self._task.cancel()
        self._task = None
        logger.info("ProjectionWorker stopped")

    async def _run(
        self,
        engine: Engine,
        cache: ConfigCache,
        guild_id: int,
    ) -> None:
        """Main loop.  Bounded by MAX_LOOP_ITERATIONS."""
        for _ in range(MAX_LOOP_ITERATIONS):
            if self._stop_event.is_set():
                break

            enabled = cache.get_bool("flags.projection_workers_enabled", default=False)

            if enabled:
                try:
                    processed = await run_db(
                        _process_batch, engine, WORKER_ID, BATCH_SIZE, guild_id
                    )
                except Exception:
                    logger.error(
                        "ProjectionWorker: _process_batch raised unexpectedly",
                        exc_info=True,
                    )
                    processed = 0

                # If we filled the batch, poll immediately (catch-up mode).
                # Otherwise, sleep before next poll.
                if processed < BATCH_SIZE:
                    await asyncio.sleep(POLL_INTERVAL_SEC)
            else:
                # Flag off — nothing to do; sleep a full interval
                await asyncio.sleep(POLL_INTERVAL_SEC)

        if not self._stop_event.is_set():
            logger.warning(
                "ProjectionWorker: MAX_LOOP_ITERATIONS (%d) reached — worker exiting",
                MAX_LOOP_ITERATIONS,
            )


# Module-level singleton
_worker = ProjectionWorker()


def start_projection_worker(
    engine: Engine,
    cache: ConfigCache,
    guild_id: int,
) -> None:
    """Start the module-level projection worker singleton."""
    _worker.start(engine, cache, guild_id)


async def stop_projection_worker() -> None:
    """Stop the module-level projection worker singleton."""
    await _worker.stop()
