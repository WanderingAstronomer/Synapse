# Copilot Instructions — Synapse

## Philosophy

**Move carefully and Socratically.** Before writing code, understand context. Before changing a pattern, understand why it exists. Ask clarifying questions when requirements are ambiguous. Propose a plan before executing multi-step changes. Prefer small, verifiable increments over sprawling rewrites.

When uncertain about intent, present 2–3 options with tradeoffs rather than guessing. When a change touches shared infrastructure (models, cache, engine), trace all downstream consumers before editing.

---

## Project Overview

Synapse is a modular community operating system for Discord. Four services share a single PostgreSQL 16 database:

| Service       | Stack                         | Entry Point                                  |
|---------------|-------------------------------|----------------------------------------------|
| **Bot**       | Python 3.12, discord.py       | `synapse/bot/__main__.py`                    |
| **API**       | Python 3.12, FastAPI, Uvicorn | `synapse/api/main.py`                        |
| **Dashboard** | SvelteKit 2, Svelte 5, TS     | `dashboard/src/routes/`                      |
| **Database**  | PostgreSQL 16 Alpine          | `synapse/database/models.py`, Alembic        |

Infrastructure: Docker Compose, `uv` (package manager), Alembic (migrations).

---

## Repository Layout

```
synapse/
  config.py          — YAML infrastructure config (SynapseConfig dataclass)
  constants.py       — Presentations constants, leveling formula
  database/
    models.py        — SQLAlchemy 2.0 ORM models (Base, enums, all tables)
    engine.py        — Engine factory, init_db(), run_db() async bridge
  engine/
    events.py        — SynapseEvent dataclass, BASE_XP/BASE_STARS dicts
    reward.py        — Pure calculation pipeline (no I/O)
    anti_gaming.py   — Sliding-window anti-abuse tracker
    quality.py       — Message quality scoring
    achievements.py  — Achievement trigger evaluation
    cache.py         — ConfigCache + PG LISTEN/NOTIFY invalidation
  services/
    reward_service.py       — Event persistence + reward application (DB I/O)
    admin_service.py        — Audited admin mutations (before/after JSONB)
    announcement_service.py — Throttled Discord embed posting
    channel_service.py      — Channel sync logic
    ...
  bot/
    core.py          — SynapseBot subclass (shared state: cfg, engine, cache)
    cogs/            — One file per event domain (reactions, social, voice, etc.)
  api/
    deps.py          — FastAPI DI (JWT validation, DB sessions, config)
    auth.py          — Discord OAuth flow
    rate_limit.py    — Per-admin mutation rate limiter
    routes/          — admin.py, public.py, event_lake.py, layouts.py
dashboard/           — SvelteKit 2 frontend (separate Node build)
tests/               — pytest suite (SQLite in-memory, no Docker needed)
alembic/             — Migration scripts
docs/                — Prose architecture docs (ARCHITECTURE.md, etc.)
```

---

## Critical Patterns — Understand Before Changing

### 1. Async Bridge (`run_db`)

Discord.py runs on asyncio. SQLAlchemy + psycopg2 is synchronous. The bridge is `run_db()` in `synapse/database/engine.py`:

```python
result = await run_db(sync_function, engine, arg1, arg2)
```

It uses `asyncio.to_thread()` internally. **Never call synchronous DB functions directly from async cog code.** Always go through `run_db`.

### 2. Pure Engine vs. Service Layer

The **engine** (`synapse/engine/`) is pure calculation — no database I/O, no Discord I/O. It takes data in, returns results.

The **service layer** (`synapse/services/`) handles persistence, side effects, and coordination. It calls engine functions, then writes results to the DB.

**Do not add DB access to engine modules.** Keep the pipeline testable without a database.

### 3. ConfigCache + LISTEN/NOTIFY

`ConfigCache` holds categories, multipliers, achievements, and settings in memory. When admin mutates config via the API:

1. `admin_service` writes change + audit log
2. `send_notify(engine, table_name)` fires PG NOTIFY
3. Bot's listener thread receives notification, reloads that partition
4. Sub-second propagation

Table names are validated against `ALLOWED_NOTIFY_TABLES` (frozen set in `cache.py`). If you add a new cached table, you must add it to this allowlist.

### 4. Idempotent Event Processing

`activity_log` has a partial unique index on `(source_system, source_event_id)` where `source_event_id IS NOT NULL`. Each cog generates deterministic IDs like `msg_{message_id}`, `rxn_given_{msg}_{user}_{emoji}`. Duplicate inserts are caught via SAVEPOINT + `IntegrityError`. **Preserve this pattern in any new event type.**

### 5. Admin Audit Trail

Every admin mutation goes through `admin_service.py` following: read before → apply change → write `admin_log` (before/after JSONB) → NOTIFY → commit. **Never bypass this for admin writes.**

### 6. Channel-First Multiplier Resolution

Multipliers resolve in this order (first match wins):

1. `ChannelOverride(channel_id, event_type)` — exact
2. `ChannelOverride(channel_id, '*')` — wildcard
3. `ChannelTypeDefault(channel.type, event_type)` — type default
4. `ChannelTypeDefault(channel.type, '*')` — type wildcard
5. `(1.0, 1.0)` — system default

---

## Code Style & Conventions

### Python

- **Python 3.12+** — use `X | Y` union syntax, StrEnum, slots dataclasses
- **Formatter/Linter:** Ruff (`line-length = 99`, rules: E, F, I, N, W, UP)
- **Type checker:** mypy (strict-ish)
- **Imports:** `from __future__ import annotations` at the top of every module
- **Docstrings:** NumPy-style for public functions (Parameters / Returns / Raises sections). Module-level docstrings use `===` underline style
- **Section separators:** `# ---------------------------------------------------------------------------` with centered labels
- **Logging:** `logger = logging.getLogger(__name__)` per module, no print statements
- **Dataclasses:** Use `frozen=True, slots=True` for value objects (`SynapseConfig`, `SynapseEvent`)
- **Enums:** `StrEnum` for anything serialized (`InteractionType`)
- **TYPE_CHECKING guards:** Heavy objects imported only under `if TYPE_CHECKING:` (Engine, ConfigCache, SynapseBot)

### SQLAlchemy

- **SQLAlchemy 2.0 style:** `Mapped[T]`, `mapped_column()`, `DeclarativeBase`
- **No raw SQL except** `send_notify()` (validated against allowlist)
- **JSONB** for flexible metadata columns
- **Partial unique indexes** for idempotency constraints

### Testing

- **Framework:** pytest with fixtures in `conftest.py`
- **Database:** In-memory SQLite with JSONB → TEXT compilation hack (no Docker needed)
- **Run:** `uv run pytest tests/ -v`
- **Fixtures:** `db_engine`, `db_session` (auto-rollback), `admin_token`, `auth_headers`
- Tests should be self-contained — no cross-test state, no external services

### Frontend (Dashboard)

- **SvelteKit 2**, Svelte 5, TypeScript, Tailwind CSS
- **SSR disabled** — client-side SPA
- **API proxy:** `/api/[...path]` routes forward to FastAPI backend
- Dashboard never accesses the database directly

---

## Defensive Engineering Standards

The following constraints address systemic weaknesses in AI-generated code — particularly around concurrency, database safety, security, and operational resilience. These are not suggestions; they are architectural invariants for this project.

### Concurrency & Event Loop Safety

This project runs on asyncio (discord.py + FastAPI). The event loop is single-threaded. One blocking call freezes the entire server for all users.

- **No blocking I/O in `async def` functions.** This is a P0 failure mode. Mandatory replacements:
  - `time.sleep()` → `await asyncio.sleep()`
  - `requests` → `httpx` (async client) or `aiohttp`
  - Synchronous file I/O → `aiofiles` or `asyncio.to_thread()`
  - `subprocess.run()` → `asyncio.create_subprocess_exec()`
  - Synchronous DB calls → `await run_db(sync_fn, engine, ...)` (already established in this project)
- **Bound concurrent work.** Never call `asyncio.gather()` on an unbounded list of tasks — this causes thundering herd effects. Use `asyncio.Semaphore` to cap concurrency:
  ```python
  sem = asyncio.Semaphore(10)
  async def limited(task):
      async with sem:
          return await task
  results = await asyncio.gather(*(limited(t) for t in tasks))
  ```
- **GIL awareness.** Python threads do not provide CPU parallelism. For CPU-bound work (JSON serialization of large payloads, cryptographic operations), use `asyncio.to_thread()` or `ProcessPoolExecutor` — never raw `threading.Thread`.

### Database Safety

PostgreSQL under concurrent load requires disciplined query patterns. AI-generated SQL is often functionally correct but operationally destructive.

- **No check-then-act patterns for stateful mutations.** This is a race condition under concurrent requests:
  ```python
  # WRONG — race window between check and update
  if user.balance >= amount:
      user.balance -= amount

  # RIGHT — atomic SQL with guard clause
  # UPDATE users SET balance = balance - :amt WHERE id = :id AND balance >= :amt
  ```
  Use atomic `UPDATE ... WHERE` guards, `SELECT ... FOR UPDATE`, or database-level constraints. Rely on the database to enforce invariants, not application-level if-checks.
- **Batch large write operations.** Never issue unbounded `DELETE FROM table WHERE ...` on large tables — this acquires a table-level lock and blocks all other queries. Batch deletes in chunks (e.g., 1000 rows per transaction) with brief pauses between batches.
- **Consider index impact.** When adding queries against large tables (`activity_log`, `event_lake`), verify that appropriate indexes exist. Flag potential full-table scans. Prefer partial indexes for filtered queries.
- **Idempotency via database constraints.** This project enforces idempotency through partial unique indexes on `(source_system, source_event_id)`, not application-level deduplication. Preserve this pattern — the database is the source of truth for uniqueness.

### Security Hardening

- **No placeholder security functions.** Never generate stub implementations like `def sanitize(x): pass` or `def verify_token(): return True`. If a security function is needed, implement it fully using established libraries, or mark it with an explicit `# TODO: IMPLEMENT — SECURITY GAP` that will be caught in review. Silent stubs create an illusion of protection.
- **Parameterized queries only.** Never use f-strings, `.format()`, or string concatenation to build SQL. This project uses SQLAlchemy ORM for all queries except `send_notify()`, which validates table names against `ALLOWED_NOTIFY_TABLES`. Maintain this pattern.
- **Sanitize before logging.** Strip or escape newlines (`\n`, `\r`) in user-controlled data before passing to `logger.*()` calls. Log injection (CWE-117) enables log forgery and can confuse monitoring tools.
- **Dependency hygiene.** Only suggest well-known, established packages. AI can hallucinate package names that look plausible but don't exist (or worse, are registered by attackers — "slopsquatting"). When suggesting a new dependency:
  - Verify the exact `pip install` name matches the real package
  - Prefer standard library alternatives when reasonable
  - When in doubt, add a comment: `# VERIFY: package existence and security`

### Operational Resilience

- **Finite retry bounds.** All retry logic must have a hard `max_retries` (typically 3–5) with exponential backoff and jitter. Never generate open-ended retry loops — these consume resources indefinitely on persistent failures.
  ```python
  for attempt in range(max_retries):
      try:
          result = await call_external_service()
          break
      except TransientError:
          wait = (2 ** attempt) + random.uniform(0, 1)
          await asyncio.sleep(wait)
  else:
      raise ExhaustedRetriesError(...)
  ```
- **Hard bounds on loops and recursion.** Every `while` loop must have a maximum iteration counter. Every recursive function must have a depth limit. Unbounded loops are a crash vector.
- **Timeouts on external calls.** Every HTTP request, database query, or subprocess invocation must have an explicit timeout parameter. No call to the outside world should be allowed to hang forever.
- **Preserve config limits.** When editing configuration files (YAML, JSON, Docker), never remove numeric limits, size caps, or rate thresholds without understanding and documenting why they exist. These are safety nets, not arbitrary values.

### Destructive Operation Safety

- **Default to read-only.** When asked to "optimize", "clean up", or "refactor" data or schemas, default to analysis and dry-run output. Do not execute destructive operations (DELETE, DROP, TRUNCATE, data migrations) without explicit user confirmation.
- **Explain blast radius.** Before executing any operation that modifies or removes data, explain what will be affected and how many rows/records are involved. Surface the consequences before acting.
- **Backups before migrations.** When generating schema changes or data migrations, remind about backup procedures. Schema changes are one-way — Alembic `downgrade` is not always reliable.

---

## How to Approach Changes

### Adding a new event type

1. Add the variant to `InteractionType` (StrEnum in `models.py`)
2. Add base XP/Stars in `BASE_XP` and `BASE_STARS` dicts (`engine/events.py`)
3. Create a deterministic `source_event_id` format for idempotency
4. Write the cog listener in `bot/cogs/`
5. Wire through `reward_service.process_event()`
6. Add a test in `tests/`
7. Create an Alembic migration if the enum changed in Postgres

### Adding a new cached config table

1. Add the SQLAlchemy model in `models.py`
2. Add the table name to `ALLOWED_NOTIFY_TABLES` in `cache.py`
3. Add load/reload logic in `ConfigCache`
4. Wire `send_notify()` in the admin service mutation
5. Test cache invalidation

### Adding a new API route

1. Add to the appropriate router in `synapse/api/routes/`
2. Admin routes must go through `admin_service` (audit trail)
3. Use FastAPI dependency injection from `deps.py`
4. Admin mutations are rate-limited — verify the middleware applies

### Database schema changes

1. Modify `models.py`
2. Generate migration: `uv run alembic revision --autogenerate -m "description"`
3. Review the generated migration — autogenerate is not infallible
4. Test with `uv run pytest tests/ -v` (SQLite compat)
5. Apply: `uv run alembic upgrade head`

---

## Agent Workflow — Plan, Track, Cache

For any non-trivial change (multi-file, multi-phase, or touching shared infrastructure), follow the **Plan → Track → Execute** workflow using the templates in `.github/agent_resources/`.

### When to Use the Full Workflow

Use the planning + tracking documents when:
- The change spans **3+ files** or **2+ phases**
- It touches shared infrastructure (models, cache, engine, service layer)
- Requirements are ambiguous and need structured breakdown
- The user explicitly asks for a phased rollout

Skip the documents for single-file fixes, simple additions, or one-step tasks.

### Step-by-Step

1. **Plan first.** Copy `PLANNING_TEMPLATE.md` → `PLAN_<feature>.md`. Fill out the problem statement, gather context (cite files and symbols), evaluate design options, and define rollout phases with success criteria. Present the plan for review before writing code.

2. **Track as you go.** Copy `WORK_TRACKER_TEMPLATE.md` → `TRACKER_<feature>.md`. Mirror the phases from the plan. Update task status (`⬜ → 🔄 → ✅`) after each task — not in batches. Append to the completion log at the end of each phase.

3. **Verify between phases.** Tests must pass at the end of every phase. Do not start Phase N+1 until Phase N is verified. Record the verification result in the tracker.

4. **Clean up.** Once the work is merged, delete the plan and tracker from `agent_resources/`. Templates stay.

### Caching Lookups

When you discover information that would be expensive to re-derive (e.g. a map of all model columns, a list of event handler → service function wiring, multiplier resolution paths), write it to a `CACHE_<topic>.md` file in `.github/agent_resources/`. Check for existing cache files before doing deep lookups. Cache files are disposable scratch — they are not committed and can be deleted at any time.

### Ad-hoc Scripts

Utility scripts (data backfills, one-off migrations, diagnostic queries) go in `.github/agent_resources/` as `script_<purpose>.py`. These are not part of the application — they are temporary tools. Delete after use.

### File Naming Conventions

| Kind | Pattern | Example |
|------|---------|---------|
| Planning doc | `PLAN_<feature>.md` | `PLAN_voice_rewards.md` |
| Work tracker | `TRACKER_<feature>.md` | `TRACKER_voice_rewards.md` |
| Cached lookup | `CACHE_<topic>.md` | `CACHE_model_columns.md` |
| Ad-hoc script | `script_<purpose>.py` | `script_backfill_stats.py` |
| Templates | `*_TEMPLATE.md` | _(do not rename)_ |

---

## Commands

| Task | Command |
|------|---------|
| Install deps | `uv sync --group dev` |
| Run tests | `uv run pytest tests/ -v` |
| Lint | `uv run ruff check .` |
| Format | `uv run ruff format .` |
| Type check | `uv run mypy synapse/` |
| Start stack | `docker compose up -d --build` |
| Stop stack | `docker compose down` |
| View logs | `docker compose logs -f --tail=200` |
| New migration | `uv run alembic revision --autogenerate -m "msg"` |
| Apply migrations | `uv run alembic upgrade head` |

---

## Guardrails

- **Never block the asyncio event loop** with synchronous DB calls — use `run_db()`
- **Never bypass `admin_service`** for admin mutations — the audit trail is non-negotiable
- **Never add DB I/O to `synapse/engine/`** — keep the calculation pipeline pure
- **Never construct SQL from user input** — `ALLOWED_NOTIFY_TABLES` exists for a reason
- **Never use `asyncio.gather()` on unbounded task lists** — cap with `asyncio.Semaphore`
- **Never generate stub security functions** — implement fully or flag as `# TODO: SECURITY GAP`
- **Never issue unbounded DELETE/UPDATE on large tables** — batch to avoid table locks
- **Never use check-then-act for concurrent state** — use atomic SQL or `SELECT FOR UPDATE`
- **Never suggest unverified third-party packages** — confirm exact package names exist
- **Never write open-ended retry loops** — hard `max_retries` + exponential backoff + jitter
- **Never remove config limits** without understanding and documenting why they exist
- **Always generate an Alembic migration** for schema changes — don't rely on `create_all`
- **Always preserve idempotency** — new event types need a deterministic `source_event_id`
- **Always set explicit timeouts** on HTTP requests, DB queries, and subprocess calls
- **Always run tests** (`uv run pytest tests/ -v`) before considering a change complete
- **Always use `from __future__ import annotations`** at the top of new Python files
