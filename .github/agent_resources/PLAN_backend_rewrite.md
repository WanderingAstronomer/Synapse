# Plan: Backend Rewrite (Raw SQL, Historical Ingestion)

## Problem Statement
The current backend relies heavily on `SQLAlchemy` (ORM) and `Alembic` (Migrations), which adds complexity and hides performance characteristics. Additionally, the ingestion strategy relies solely on live Gateway events, leading to data loss during downtime. The user desires a simpler, raw-SQL approach using `psycopg` (v3) and a robust historical backfill mechanism.

## Context
- **Current Stack**: Python 3.12, `discord.py`, `SQLAlchemy` 2.0, `Alembic`.
- **Target Stack**: Python 3.12, `discord.py`, `psycopg` 3 (async), Manual Schema Management.
- **Ingestion**: Move from strictly live to **Hybrid** (Live + Historical Backfill).

## Goals
1.  **Remove ORM Dependency**: Replace SQLAlchemy/Alembic with raw `psycopg` and manual SQL files.
2.  **Implement Async Database Layer**: Use `psycopg_pool.AsyncConnectionPool` for non-blocking DB access.
3.  **Implement Historical Backfill**: Create a service to fetch message history on startup/schedule to fill gaps.
4.  **Preserve Data Schema**: Replicate the existing schema in raw SQL to ensure compatibility with existing data.

## Proposed Architecture

### 1. Database Connection (`synapse/database/connection.py`)
Replace `synapse/database/engine.py`.
-   Use `psycopg_pool.AsyncConnectionPool`.
-   Provide context managers for acquiring connections/cursors.
-   Handle connection lifecycle (startup/shutdown).

### 2. Schema Management (`synapse/database/schema.sql`)
-   Manual SQL file containing `CREATE TABLE IF NOT EXISTS` for all entities.
-   A simple migration runner `synapse/database/migrate.py` or just running the file on startup (idempotent).

### 3. Backfill Service (`synapse/services/backfill.py`)
-   On startup, for each tracked channel:
    -   Find the last stored message ID in `event_lake`.
    -   Fetch history from Discord (`channel.history(after=last_stored_id)`).
    -   Check for gaps (comparing message IDs).
    -   Insert missing messages into `event_lake`.
    -   **Idempotency**: Ensure duplicated events are handled gracefully (Postgres `ON CONFLICT DO NOTHING`).

### 4. Service Layer Refactor
-   Update `EventLakeWriter`, `RewardService`, etc., to use the new `AsyncConnectionPool`.
-   Rewrite ORM queries as raw SQL.

## Phases

### Phase 1: Infrastructure & Schema [IN PROGRESS]
-   [ ] Update `pyproject.toml` (Add `psycopg`, remove `sqlalchemy`, `alembic`).
-   [ ] Create `synapse/database/connection.py` (Async Pool).
-   [ ] Reverse-engineer `synapse/database/models.py` into `synapse/database/schema.sql`.
-   [ ] Create `synapse/database/schema.py` (Schema intializer implementation).

### Phase 2: Core Services Migration
-   [ ] Refactor `EventLakeWriter` to use raw SQL.
-   [ ] Refactor `AdminService` / `RewardService` (if needed for initial proof).
-   [ ] Verify basic event flow.

### Phase 3: Historical Backfill
-   [ ] Create `synapse/services/backfill.py`.
-   [ ] Wire into `SynapseBot` startup.
-   [ ] Test with a gap in data.

## Risks
-   **Schema Drift**: Manual SQL maintenance requires discipline.
-   **Type Safety**: Losing Pydantic/SQLAlchemy models means we must be careful with types from `row` results.
-   **Backfill Limits**: Discord API has rate limits. Backfill must be throttled and respect them.
