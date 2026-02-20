# Architecture

Synapse is a modular Discord operating system with four runtime surfaces backed
by one PostgreSQL database:

- **Bot** (`synapse/bot/`): Discord event ingestion and community-facing actions.
- **API** (`synapse/api/`): Authenticated admin/member control plane.
- **Dashboard** (`dashboard/`): Client SPA consuming API routes.
- **Database** (`synapse/database/` + Alembic): Source of truth for state and
	idempotency guarantees.

## Core Boundaries

### 1) Engine Is Pure, Services Do I/O

- `synapse/engine/` modules perform deterministic computation only.
- `synapse/services/` modules coordinate DB writes and side effects.
- Engine code must not open DB sessions or call Discord/network APIs.

### 2) Async Bridge Contract

- Bot code runs in asyncio and must not execute synchronous DB calls directly.
- Synchronous SQLAlchemy operations from async contexts must use
	`await run_db(sync_fn, engine, ...)`.

### 3) Cache Invalidation & Event Contract

- Config cache invalidation uses `config_changed` + table payload.
- Cross-service domain events use `synapse_events` JSON payloads with a required
	`type` key.
- Producers should use centralized helpers in `synapse.engine.cache`
	(`notify_before_commit` and `send_event_notify`) rather than bespoke channels.

## Data Flow

1. Bot ingests Discord interaction and normalizes to `SynapseEvent`.
2. Reward/rule engines compute outcomes with cache-backed settings.
3. Services persist state updates and append event-lake/audit records.
4. API and bot consume persisted state; announcements and projections are
	 dispatched asynchronously.

## Reliability & Consistency

### Idempotency

- External event dedup relies on DB constraints (for example,
	`(source_system, source_event_id)` uniqueness semantics).
- Event IDs must be deterministic per source event.

### Transaction Safety

- Mutations should prefer atomic SQL (`UPDATE ... WHERE guard`) over
	check-then-act.
- Admin mutations should always pass through `admin_service` so before/after
	audit entries are guaranteed.

### Retry & Backoff

- Retry loops must be bounded and use exponential backoff with jitter.
- Long-running polling remains fallback behavior; primary delivery should use
	event notifications where available.

## Observability

- **Health:** bot startup hooks, cache listener health, projection worker state.
- **Economic:** reward issuance, marketplace purchases, season rollovers.
- **Anomaly:** anti-gaming penalties, permission failures, listener reconnects.

## Change Checklist (Architecture Alignment)

Before merging shared-infrastructure changes:

1. Confirm engine/service boundary is preserved.
2. Confirm async code uses `run_db` for sync DB work.
3. Confirm notifications use centralized helpers and allowed channels.
4. Confirm idempotency and audit trails remain database-backed.
5. Confirm tests cover both success and duplicate/retry paths.
