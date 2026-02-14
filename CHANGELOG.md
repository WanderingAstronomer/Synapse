# Changelog

All notable changes to Synapse are documented here.

## [Unreleased]

### Security & Reliability

- **JWT secret hardening** — Removed hardcoded fallback secret. API startup now validates: minimum 32 characters, rejects known-weak values (`change-me`, `secret`, etc.), and refuses to start with missing or blank secrets.
- **Admin mutation rate limiting** — Sliding-window throttle: 30 mutations/minute per admin. Returns `429` with `Retry-After` and `X-RateLimit-*` response headers. Only counts successful mutations.
- **NOTIFY SQL injection prevention** — `send_notify()` validates table names against a frozen allowlist before constructing the SQL string.
- **PG LISTEN/NOTIFY reconnect** — Infinite reconnect loop with exponential backoff (1s–60s) and random jitter. Listener health exposed via `ConfigCache.listener_healthy` property.
- **Replaced python-jose with PyJWT** — Switched JWT library to `PyJWT[crypto]` for a smaller dependency footprint.
- **Removed unused requests dependency** — Only `httpx` is used for HTTP calls.

### Seedless Bootstrap

- Deleted `synapse/services/seed.py` and `seeds/` directory. The bot no longer seeds data on startup.
- Added `setup_service.py` — First-run bootstrap reads the live Discord guild structure (categories, channels) and creates categories, channel mappings, a default season, and 18 default settings.
- Guild snapshot written to the `settings` table on every bot connect for API access to channel metadata.
- Setup API endpoints: `GET /api/admin/setup/status` and `POST /api/admin/setup/bootstrap`.
- Dashboard setup wizard at `/admin/setup` — admin layout auto-redirects here if the guild hasn't been bootstrapped.
- Bot heartbeat (`save_bot_heartbeat` / `get_bot_heartbeat`) for dashboard online status display.

### Dashboard

- Admin layout auth guard with setup-gate redirect.
- API proxy (`/api/[...path]` → FastAPI backend) for CORS-free production deployment.
- Bot and API health indicators in the sidebar (polled every 30s).
- Name resolution store (`names.ts`) with 50ms batched snowflake ID → name lookups.
- Version mismatch handling — forces full page reload when SvelteKit detects stale JS chunks after a rebuild.

### Testing

- Expanded test suite to 12 files (~3,200 lines).
- JWT startup validation tests (missing, blank, short, weak secrets).
- Admin rate limit tests (sliding window, 429 responses, header validation).
- NOTIFY table-name allowlist tests.
- Cache listener health and reconnect tests.
- FastAPI route auth guard integration tests.
- In-memory SQLite fixtures with JSONB→TEXT dialect shim.

### Documentation

- Rebuilt all documentation from scratch based on the current state of the codebase.

## [1.0.0] — 2026-02-12

Initial release.

### Core Systems

- Three-currency economy: XP (progression/leveling), Stars (seasonal recognition), Gold (spendable).
- Category-based channel groupings with per-event-type XP and Star multipliers.
- Quality-weighted reward engine: message length, code blocks, links, attachments, emoji spam penalty.
- Anti-gaming: self-reaction filter, per-reactor-per-author pair cap (3/day), diminishing returns, unique-reactor weighting, velocity cap, message cooldown.
- Exponential leveling formula: `level_base × level_factor^level` (defaults 100, 1.25). Gold bonus on level-up.
- Achievement system with four trigger types: `counter_threshold`, `star_threshold`, `xp_milestone`, `custom`. Five rarity tiers.
- Seasonal stats tracking (per-user per-season counters for messages, reactions, threads, voice).

### Event Lake

- Append-only capture of 9 Discord gateway event types: message_create, reaction_add, reaction_remove, thread_create, voice_join, voice_leave, voice_move, member_join, member_leave.
- Idempotent inserts with source_id deduplication.
- Pre-computed event counters by (user, type, category, period) for O(1) reads.
- Per-source toggles via admin dashboard.
- Privacy-safe: message content never persisted, only metadata.
- Retention cleanup (daily, default 90 days, batch 5,000).
- Counter reconciliation (weekly, validates lifetime counters vs raw events).
- Backfill utility for migrating legacy activity_log data to event counters.
- Voice session tracking with AFK channel detection.

### Bot

- 8 cogs: Social, Reactions, Voice, Threads, Membership, Meta, Admin, PeriodicTasks.
- 5 user commands: `/profile`, `/leaderboard`, `/link-github`, `/preferences`, `/buy-coffee`.
- 4 admin commands: `/award`, `/create-achievement`, `/grant-achievement`, `/season`.
- Event listeners: `on_message`, `on_raw_reaction_add`, `on_raw_reaction_remove`, `on_voice_state_update`, `on_thread_create`, `on_member_join`, `on_member_remove`.
- Background tasks: heartbeat (30s), voice tick (10min), retention (24h), reconciliation (7d).
- Announcement service with per-user preference gating, per-channel throttling (3/min), and async drain queue.
- Auto-creates `#synapse-achievements` channel on startup.
- Auto-discovers guild channels and maps to categories by Discord category name.
- In-memory `ConfigCache` with PG LISTEN/NOTIFY for near-instant invalidation.

### API (FastAPI)

- 8 public endpoints: health, bot heartbeat, metrics, leaderboard, activity, achievements, recent achievements, public settings.
- 3 auth endpoints: OAuth2 login redirect, callback (code exchange + admin role check + JWT issuance), current admin info.
- 17 admin endpoints: category CRUD, achievement CRUD, manual awards, user search, settings CRUD, audit log, setup/bootstrap, live logs, name resolution.
- 9 Event Lake admin endpoints: event browser, data source toggles, health metrics, storage estimate, retention/reconciliation/backfill triggers, counter browser.
- Discord OAuth2 → JWT (HS256, 12h expiry) authentication.
- Admin rate limiting middleware (30 mutations/minute per admin).
- CORS middleware for development origins.
- In-memory ring buffer log handler for live log streaming.

### Dashboard (SvelteKit)

- 4 public pages: overview (hero metrics, activity ticker, champion spotlight), leaderboard, activity feed with charts, achievement gallery.
- 8 admin pages: setup wizard, categories, achievements, awards, settings, audit log, live logs, data source toggles.
- Client-side SPA (SSR disabled) with Svelte 5, TypeScript, Tailwind CSS.
- 10 reusable components: Avatar, ConfirmModal, EmptyState, FlashMessage, HeroHeader, MetricCard, ProgressBar, RarityBadge, Sidebar, SynapseLoader.
- 4 stores: auth (JWT state), currency (configurable labels), flash (toasts), names (batched ID resolution).
- Chart.js integration for activity visualization.

### Database (PostgreSQL 16)

- 15 tables: users, user_stats, seasons, activity_log, categories, category_channels, category_multipliers, achievement_templates, user_achievements, quests, admin_log, user_preferences, settings, event_lake, event_counters.
- JSONB columns for flexible metadata and configuration.
- Partial unique indexes for idempotent event insertion.
- PG LISTEN/NOTIFY for cache invalidation.
- Composite indexes for query performance.
- Async bridge pattern: `run_db()` ships sync SQLAlchemy calls to thread pool.

### Infrastructure

- Docker Compose with 4 services (db, bot, api, dashboard) on shared network.
- Multi-stage Dockerfile: builder (uv + dependency install) → runtime (minimal Python 3.12-slim).
- Healthchecks on all services.
- uv package manager for Python dependencies.
- Alembic for database migrations.
- pytest test suite with in-memory SQLite.
- Ruff for linting and formatting, mypy for type checking.

### Deferred

- Quest system UI (schema exists, no dashboard/command interface).
- GitHub Neural Bridge integration.
- LLM quality modifier (`llm_quality_modifier()` returns 1.0 — placeholder).
- Custom badge image uploads.
- DM notification delivery.
- Redis session store for multi-instance OAuth state.
