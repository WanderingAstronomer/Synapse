# Architecture

## System Topology

Synapse runs as four services sharing a single PostgreSQL database:

```
┌──────────────────────────────────────────────────────────────────────┐
│                        Discord Server                                │
│   Members chat, react, join voice, create threads, use commands      │
└──────────┬───────────────────────────────────────────────────────────┘
           │ Gateway Events
           ▼
┌───────────────────────────┐
│  Service 1: BOT           │
│  (discord.py on asyncio)  │
│                           │
│  - Captures gateway events│
│  - Writes to Event Lake   │
│  - Runs reward pipeline   │
│  - Posts announcements    │
│  - Slash command handler  │
└────────┬──────────────────┘
         │ SQLAlchemy (sync via run_db)
         ▼
┌────────────────────────────────────┐
│  Service 2: API                    │
│  (FastAPI + Uvicorn on :8000)      │
│                                    │
│  - REST endpoints (/api/*)         │
│  - Discord OAuth → JWT auth        │
│  - Admin CRUD (audit-logged)       │
│  - Public analytics queries        │
└────────┬───────────────────────────┘
         │ API proxy (/api/[...path])
         ▼
┌──────────────────────────────────────────────────────────────────┐
│  Service 3: DASHBOARD  (SvelteKit on :3000)                      │
│  - Public pages (overview, leaderboard, activity, achievements)  │
│  - Admin pages (zones, achievements, awards, settings, audit,    │
│    logs, data-sources, setup)                                    │
│  - Talks to API only (never touches DB directly)                 │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│  Service 4: DATABASE  (PostgreSQL 16)                            │
│  - 15 tables (see DATABASE.md)                                   │
│  - JSONB for flexible metadata and config                        │
│  - LISTEN/NOTIFY for cache invalidation                          │
│  - Partial unique indexes for idempotency                        │
└──────────────────────────────────────────────────────────────────┘
```

## Service Boundaries

### Bot (`python -m synapse.bot`)

Entry point: `synapse/bot/__main__.py`. Startup sequence:

1. Load `.env` via python-dotenv
2. Validate `DISCORD_TOKEN`
3. Load `config.yaml` → `SynapseConfig`
4. Create SQLAlchemy engine + `init_db()` (CREATE TABLE IF NOT EXISTS)
5. Build `ConfigCache` and warm from DB
6. Start PG LISTEN/NOTIFY background thread
7. Install log ring buffer handler
8. Create `SynapseBot` and run blocking event loop

The bot carries shared state: `bot.cfg` (config), `bot.engine` (DB engine), `bot.cache` (ConfigCache), `bot.lake_writer` (EventLakeWriter). Cogs access these via `self.bot.*`.

### API (`uvicorn synapse.api.main:app`)

FastAPI application with lifespan context manager. On startup:

1. Load `.env`
2. Create DB engine (LRU-cached singleton)
3. Install log ring buffer handler
4. Validate JWT_SECRET (rejects missing, blank, short, weak values — will not start if insecure)

Mounts four routers under `/api`: auth, public, admin, event_lake. Middleware: CORS, admin rate limiting.

### Dashboard (`SvelteKit on :3000`)

Client-side SPA (SSR disabled). Built-in API proxy at `/api/[...path]` forwards all requests to the FastAPI backend, avoiding CORS issues.

### Database

PostgreSQL 16 Alpine. No application logic — purely a data store. The bot and API both connect via SQLAlchemy. LISTEN/NOTIFY used for cache invalidation (five channels: zones, zone_channels, zone_multipliers, achievement_templates, settings).

## Key Patterns

### Async Bridge

Discord bots run on asyncio. SQLAlchemy + psycopg2 is synchronous. The `run_db()` function bridges these:

```python
result = await run_db(sync_db_function, engine, arg1, arg2)
```

Under the hood: `asyncio.to_thread()` ships the sync function to a thread pool. The event loop is never blocked.

### ConfigCache + LISTEN/NOTIFY

`ConfigCache` holds zones, multipliers, achievements, and settings in memory. When an admin mutates config via the API, the service layer calls `send_notify(engine, table_name)`. The bot's listener thread receives the notification and reloads the affected partition. Propagation time: sub-second.

The listener uses raw psycopg2 with `select()` polling. Reconnection uses exponential backoff (1s–60s) with random jitter.

Table names are validated against a frozen allowlist before SQL construction (`ALLOWED_NOTIFY_TABLES`).

### Idempotent Event Processing

The `activity_log` table has a partial unique index on `(source_system, source_event_id)` where `source_event_id IS NOT NULL`. Each event-producing cog generates a deterministic `source_event_id` (e.g., `msg_{message_id}`, `rxn_given_{msg}_{user}_{emoji}`). Duplicate inserts are caught via SAVEPOINT + IntegrityError.

Events without natural unique keys (e.g., voice ticks) always insert.

### Audit Trail

Every admin mutation in the API goes through `admin_service.py`, which:

1. Reads the "before" state
2. Applies the change
3. Writes an `admin_log` row with before/after JSONB snapshots, actor ID, optional IP and reason
4. Fires `send_notify()` for cache invalidation
5. Commits

### Announcement Throttle

Per-channel sliding window: max 3 embeds per 60 seconds. Excess embeds are queued and drained by a background asyncio task (~10s interval). Announcements respect per-user preferences (level-ups, achievements, awards — all opt-out).

## Data Flow

### Reward Pipeline (per event)

```
1. Cog receives Discord event
2. Write to Event Lake (idempotent, counter update)
3. Build SynapseEvent with metadata
4. reward_service.process_event():
   a. Classify zone (channel → zone lookup via cache)
   b. Look up zone multipliers
   c. Calculate quality modifier (MESSAGE only)
   d. Apply anti-gaming checks
   e. Apply XP caps
   f. Persist to activity_log (idempotent)
   g. Update user (XP, level, gold)
   h. Update user_stats (season counters)
   i. Check achievement triggers
   j. Apply achievement rewards if earned
5. Announce results (throttle-gated, preference-gated)
```

### Admin Config Change

```
1. Admin makes change in dashboard
2. Dashboard sends API request with JWT
3. API validates JWT + admin role
4. Rate limiter checks window (30 mutations/min)
5. admin_service writes change with audit log
6. send_notify() fires PG NOTIFY
7. Bot's ConfigCache listener receives, reloads partition
8. Next event uses updated config (sub-second)
```
