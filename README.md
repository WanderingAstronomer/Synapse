# Synapse

A modular community operating system for Discord. Captures activity, drives engagement through a configurable economy, and surfaces insights through a real-time dashboard.

## Architecture

```
┌─────────────┐      ┌──────────────┐      ┌─────────────────┐
│  Discord    │◄────►│  Synapse Bot │◄────►│  PostgreSQL 16  │
│  Gateway    │      │  (discord.py)│      │  (JSONB, LISTEN │
└─────────────┘      └──────┬───────┘      │   /NOTIFY)      │
                            │              └──────┬──────────┘
                     ┌──────┴───────┐             │
                     │  FastAPI     │◄────────────┘
                     │  REST API    │
                     └──────┬───────┘
                            │
                     ┌──────┴───────┐
                     │  SvelteKit   │
                     │  Dashboard   │
                     └──────────────┘
```

Four services in Docker Compose:

| Service | Runtime | Port | Purpose |
|---------|---------|------|---------|
| **db** | PostgreSQL 16 Alpine | 5432 | Persistent game state and configuration |
| **bot** | Python 3.12 (discord.py) | — | Discord event processor and command handler |
| **api** | Python 3.12 (FastAPI + Uvicorn) | 8000 | REST API for dashboard and admin operations |
| **dashboard** | SvelteKit 2 (Node adapter) | 3000 | Public analytics and admin panel |

## Tech Stack

**Backend:** Python 3.12, discord.py, FastAPI, Uvicorn, SQLAlchemy 2.0, Alembic, PyJWT, httpx, psycopg2  
**Frontend:** SvelteKit 2 (Svelte 5), TypeScript, Tailwind CSS, Chart.js, Vite  
**Infrastructure:** Docker (multi-stage builds), Docker Compose, PostgreSQL 16, uv (package manager)  
**Quality:** pytest, Ruff (linting + formatting), mypy, svelte-check

## Quick Start

### Prerequisites

- Docker and Docker Compose
- A Discord bot token ([Developer Portal](https://discord.com/developers/applications))
- Two privileged intents enabled: **Message Content** and **Server Members**

### Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/WanderingAstronomer/Synapse.git
   cd Synapse
   ```

2. Copy the environment file and fill in your secrets:
   ```bash
   cp .env.example .env
   ```

   Required variables:
   | Variable | Description |
   |----------|-------------|
   | `DISCORD_TOKEN` | Bot token from Discord Developer Portal |
   | `DATABASE_URL` | PostgreSQL connection string (auto-set in Docker) |
   | `JWT_SECRET` | Min 32-char secret for admin JWT signing |
   | `DISCORD_CLIENT_ID` | OAuth2 client ID for dashboard login |
   | `DISCORD_CLIENT_SECRET` | OAuth2 client secret |
   | `DISCORD_REDIRECT_URI` | OAuth2 callback URL |
   | `FRONTEND_URL` | Dashboard base URL |

3. Edit `config.yaml` with your community info:
   ```yaml
   community_name: "My Community"
   community_motto: "Our tagline"
   bot_prefix: "!"
   guild_id: 123456789              # Your Discord server ID
   dashboard_port: 3000
   admin_role_id: 123456789         # Discord role ID for admin access
   announce_channel_id: null        # Optional: override announcement channel
   ```

4. Start the stack:
   ```bash
   docker compose up -d --build
   ```

5. Open the dashboard at `http://localhost:3000` and log in with Discord OAuth to run the first-time bootstrap wizard at `/admin/setup`.

### Running Without Docker

```bash
# Install dependencies
uv sync

# Start PostgreSQL separately, set DATABASE_URL in .env

# Run the bot
uv run python -m synapse.bot

# Run the API (separate terminal)
uv run uvicorn synapse.api.main:app --host 0.0.0.0 --port 8000

# Run the dashboard (separate terminal)
cd dashboard && npm install && npm run dev
```

## Economy System

Three default currencies, all configurable via the admin dashboard:

| Currency | Default Name | Purpose |
|----------|-------------|---------|
| **XP** | XP | Progression — drives leveling via exponential formula: `base × factor^level` |
| **Stars** | Stars | Seasonal recognition — tracked per-season and lifetime |
| **Gold** | Gold | Spendable currency — awarded on level-up, spent via `/buy-coffee` |

All currency names, rates, and behaviors are stored in the `settings` database table and editable from the admin dashboard without redeploying.

### Leveling Formula

```
XP required for level N = level_base × (level_factor ^ N)
```

Defaults: `level_base = 100`, `level_factor = 1.25`. Both configurable.

## Zones

Channels are grouped into **Zones** (mapped from Discord categories during bootstrap). Each zone has per-event-type multipliers for XP and Stars, editable in the admin dashboard. Unmapped channels fall back to a "general" zone or the first available zone.

## Event Pipeline

```
Discord Event → Event Lake Write → SynapseEvent → Zone Classification
→ Multiplier Lookup → Quality Modifier → Anti-Gaming Checks → XP Cap
→ Idempotent Persist → Stat Update → Achievement Check → Level-Up Check
→ Announcement (throttle-gated, preference-gated)
```

### Tracked Event Types

| Event | Source | Rewards |
|-------|--------|---------|
| `MESSAGE` | `on_message` | XP + Stars (cooldown-gated per user/channel) |
| `REACTION_GIVEN` | `on_raw_reaction_add` | XP + Stars for reactor |
| `REACTION_RECEIVED` | `on_raw_reaction_add` | XP + Stars for message author (anti-gaming protected) |
| `THREAD_CREATE` | `on_thread_create` | XP + Stars |
| `VOICE_TICK` | Background task (10 min) | XP + Stars (idle-detection: muted+deafened users skipped) |
| `MANUAL_AWARD` | `/award` command | Admin-specified XP/Gold |
| `LEVEL_UP` | Automatic on level threshold | Gold bonus |
| `ACHIEVEMENT_EARNED` | Automatic on trigger | Template-defined XP/Gold |

### Quality Modifiers (MESSAGE only)

Applied multiplicatively to XP. All thresholds configurable:

| Condition | Modifier |
|-----------|----------|
| Content > 500 chars | ×1.5 |
| Content > 200 chars | ×1.2 |
| Contains code block | ×1.4 |
| Contains link | ×1.25 |
| Contains attachment | ×1.1 |
| Emoji count > 5 | ×0.5 |

Floor: 0.1 (no event produces zero XP).

### Anti-Gaming Measures

- **Self-reaction filter:** Zero rewards for reacting to your own messages
- **Pair cap:** Max 3 reactions per reactor→author pair per 24h sliding window
- **Diminishing returns:** Factor `1/(1+count)` on repeated reactor→author interactions
- **Unique-reactor weighting:** Star scaling based on distinct reactors
- **Velocity cap:** XP capped to 5 for messages with >10 reactors and <5min age
- **Message cooldown:** Per-user per-channel cooldown (default 30s) on MESSAGE rewards

## Event Lake

Append-only capture of all ephemeral Discord gateway events. The bot writes every event regardless of whether any reward rule acts on it.

### Captured Event Types

`message_create`, `reaction_add`, `reaction_remove`, `thread_create`, `voice_join`, `voice_leave`, `voice_move`, `member_join`, `member_leave`

Each data source can be toggled on/off from the admin dashboard. Message content is **never** persisted — only metadata (length, has_code, has_link, etc.).

### Pre-Computed Counters

`event_counters` table maintains pre-aggregated counts by `(user_id, event_type, zone_id, period)` for O(1) reads. Periods: `lifetime`, `season`, `day:YYYY-MM-DD`.

### Maintenance

- **Retention cleanup:** Daily background task deletes events older than `event_lake_retention_days` (default 90). Batch size: 5,000 rows.
- **Reconciliation:** Weekly background task validates lifetime counters against raw Event Lake data and corrects drift.
- **Backfill:** One-shot utility to migrate legacy `activity_log` data into `event_counters`.

## Achievements

Admin-defined recognition templates with four trigger types:

| Type | Trigger |
|------|---------|
| `counter_threshold` | Stat field (messages_sent, reactions_given, etc.) reaches a value |
| `star_threshold` | Season or lifetime stars reach a value |
| `xp_milestone` | Total XP reaches a value |
| `custom` | Manual grant by admin only |

Five rarity tiers: Common, Uncommon, Rare, Epic, Legendary — each with distinct colors and emoji.

Achievements are checked automatically after every reward event. Earned achievements grant template-defined XP and Gold bonuses.

## Bot Commands

### User Commands

| Command | Parameters | Description |
|---------|-----------|-------------|
| `/profile` | `[member]` | View your (or another member's) profile: level, XP, gold, rank, stats, achievements, GitHub link |
| `/leaderboard` | `[sort_by: XP\|Stars]` | Top members leaderboard (size from settings, default 25) |
| `/link-github` | `<username>` | Associate your GitHub account |
| `/preferences` | `<setting> <on\|off>` | Toggle announcement visibility (level-ups, achievements, awards) |
| `/buy-coffee` | — | Spend gold (cost from `coffee_gold_cost` setting, default 50) |

### Admin Commands

| Command | Parameters | Description |
|---------|-----------|-------------|
| `/award` | `<member> [xp] [gold] [reason]` | Manual XP/Gold award |
| `/create-achievement` | `<name> <description> [type] [field] [value] [xp_reward] [gold_reward] [rarity]` | Create achievement template |
| `/grant-achievement` | `<member> <achievement_id>` | Grant achievement to a member |
| `/season` | `<name> [duration_days]` | Create new season (deactivates current, default 120 days) |

Admin commands require the Discord role matching `admin_role_id` in `config.yaml`.

## REST API

Base URL: `/api`

### Public Endpoints (No Auth)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness probe |
| GET | `/health/bot` | Bot heartbeat status |
| GET | `/metrics` | Overview: total users, total XP, 7-day actives, top level, achievements earned |
| GET | `/leaderboard/{currency}` | Paginated leaderboard (xp, gold, or level) |
| GET | `/activity` | Event feed + daily aggregation for charts |
| GET | `/achievements` | Active templates with earner counts |
| GET | `/achievements/recent` | Recently earned achievements |
| GET | `/settings/public` | Public dashboard settings (title, currency names, etc.) |

### Auth Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/auth/login` | Redirect to Discord OAuth2 |
| GET | `/auth/callback` | OAuth2 code exchange, admin role check, JWT issuance |
| GET | `/auth/me` | Current admin info |

### Admin Endpoints (JWT Required)

| Method | Path | Description |
|--------|------|-------------|
| GET/POST/PATCH | `/admin/zones` | Zone CRUD |
| GET/POST/PATCH | `/admin/achievements` | Achievement template CRUD |
| POST | `/admin/awards/xp-gold` | Manual XP/Gold award |
| POST | `/admin/awards/achievement` | Grant achievement |
| GET | `/admin/users` | User search (for admin dropdowns) |
| GET/PUT | `/admin/settings` | Settings CRUD |
| GET | `/admin/audit` | Paginated audit log |
| GET/POST | `/admin/setup/*` | First-run bootstrap |
| GET/PUT | `/admin/logs` | Live log viewer + level control |
| POST | `/admin/resolve-names` | Snowflake ID → name resolution |

### Event Lake Admin Endpoints (JWT Required)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/admin/event-lake/events` | Paginated, filterable event browser |
| GET/PUT | `/admin/event-lake/data-sources` | Toggle data source capture |
| GET | `/admin/event-lake/health` | Volume metrics, storage, daily trends |
| GET | `/admin/event-lake/storage-estimate` | Storage projection |
| POST | `/admin/event-lake/retention/run` | Trigger retention cleanup |
| POST | `/admin/event-lake/reconciliation/run` | Trigger counter reconciliation |
| POST | `/admin/event-lake/backfill/run` | Trigger activity_log backfill |
| GET | `/admin/event-lake/counters` | Browse pre-computed counters |

### Security

- **Authentication:** Discord OAuth2 → JWT (HS256, 12-hour expiry)
- **Admin gating:** JWT validated on every admin request; user must have `admin_role_id` in their Discord guild roles
- **JWT secret validation:** API startup rejects missing, blank, short (<32 chars), and known-weak secrets
- **Rate limiting:** 30 admin mutations/minute per admin (sliding window), 429 with `Retry-After` header
- **CORS:** Configured for localhost development origins

## Dashboard

### Public Pages

| Route | Description |
|-------|-------------|
| `/` | Overview — hero metrics, activity ticker, champion spotlight, recent achievements |
| `/leaderboard` | Full paginated leaderboard |
| `/activity` | Activity feed with daily charts |
| `/achievements` | Achievement gallery with earn percentages |

### Admin Pages

| Route | Description |
|-------|-------------|
| `/admin/setup` | First-run bootstrap wizard |
| `/admin/zones` | Zone management (channels, multipliers) |
| `/admin/achievements` | Achievement template builder |
| `/admin/awards` | Manual XP/Gold/Achievement awards |
| `/admin/settings` | Dashboard and economy settings editor |
| `/admin/audit` | Admin audit log viewer |
| `/admin/logs` | Live log viewer with level control |
| `/admin/data-sources` | Event Lake data source toggles |

The dashboard runs as a client-side SPA (SSR disabled). Admin pages are gated by JWT auth and auto-redirect to the setup wizard if the guild hasn't been bootstrapped. A built-in API proxy (`/api/[...path]` → FastAPI backend) avoids CORS issues in production.

## Database

PostgreSQL 16 with 15 tables:

| Table | Purpose |
|-------|---------|
| `users` | Discord member profiles (snowflake PK, XP, level, gold) |
| `user_stats` | Per-season engagement counters (messages, reactions, threads, voice) |
| `seasons` | Competitive time windows |
| `activity_log` | Append-only event journal with idempotent insert |
| `zones` | Channel groupings |
| `zone_channels` | Zone ↔ channel mapping |
| `zone_multipliers` | Per-zone, per-event-type XP/Star weights |
| `achievement_templates` | Admin-defined recognition with rarity and rewards |
| `user_achievements` | Earned badges with timestamps |
| `quests` | Gamified tasks (schema present, UI deferred) |
| `admin_log` | Append-only audit trail with before/after JSONB snapshots |
| `user_preferences` | Per-user announcement opt-outs |
| `settings` | Key-value configuration store (JSON values, categorized) |
| `event_lake` | Append-only ephemeral event capture with JSONB payloads |
| `event_counters` | Pre-computed aggregation cache by user/type/zone/period |

### Key Patterns

- **Idempotent insert:** Partial unique index on `(source_system, source_event_id)` prevents duplicate event processing
- **LISTEN/NOTIFY:** Cache invalidation via PostgreSQL notifications — admin changes propagate to the bot's in-memory `ConfigCache` within seconds
- **Async bridge:** `await run_db(sync_fn, *args)` ships synchronous SQLAlchemy calls to `asyncio.to_thread()` so the bot event loop is never blocked

## Background Tasks

| Task | Interval | Description |
|------|----------|-------------|
| `heartbeat_loop` | 30 seconds | Writes bot heartbeat for dashboard health display |
| `voice_tick_loop` | 10 minutes | Awards XP/Stars to non-idle voice participants (max 6 ticks/hour) |
| `retention_loop` | 24 hours | Cleans Event Lake rows older than retention threshold |
| `reconciliation_loop` | 7 days | Validates lifetime counters against raw events |
| Announcement drain | ~10 seconds | Sends queued embeds from throttle overflow |

## Configuration

All gameplay tuning is stored in the `settings` database table, editable from the admin dashboard. `config.yaml` contains only infrastructure/identity settings.

### Default Settings (written during bootstrap)

| Category | Settings |
|----------|----------|
| **Economy** | `xp_base_message` (15), `xp_base_reaction_given` (5), `xp_base_reaction_received` (8), `xp_base_thread` (20), `xp_base_voice_tick` (10), `gold_per_level_up` (50), `coffee_gold_cost` (50) |
| **Leveling** | `level_base` (100), `level_factor` (1.25) |
| **Anti-Gaming** | `cooldown_seconds` (30), `max_reactions_per_pair_per_day` (3), `xp_cap_reaction_burst` (5) |
| **Quality** | `quality_length_medium` (200), `quality_length_long` (500), `quality_multiplier_long` (1.5), `quality_multiplier_code` (1.4) |
| **Display** | `currency_name_primary` (XP), `currency_name_secondary` (Gold), `leaderboard_size` (25) |
| **Announcements** | `announce_level_ups` (true), `announce_achievements` (true) |
| **Event Lake** | `event_lake_retention_days` (90), `voice_tick_minutes` (10) |

## Project Structure

```
synapse/
├── config.py              # YAML config loader (infrastructure only)
├── constants.py           # Rarity maps, leveling formula
├── bot/
│   ├── __main__.py        # Entry point: python -m synapse.bot
│   ├── core.py            # SynapseBot class, cog loader, lifecycle hooks
│   └── cogs/
│       ├── social.py      # on_message → reward pipeline
│       ├── reactions.py   # on_raw_reaction_add/remove → rewards + lake
│       ├── voice.py       # Voice state tracking + 10min tick loop
│       ├── threads.py     # on_thread_create → rewards
│       ├── membership.py  # on_member_join/remove → lake capture only
│       ├── meta.py        # /profile, /leaderboard, /link-github, etc.
│       ├── admin.py       # /award, /create-achievement, etc.
│       └── tasks.py       # Heartbeat, retention, reconciliation loops
├── database/
│   ├── engine.py          # Engine creation, session helper, async bridge
│   └── models.py          # 15 SQLAlchemy ORM models
├── engine/
│   ├── events.py          # SynapseEvent dataclass, base XP/Star tables
│   ├── reward.py          # Pure calculation pipeline (no I/O)
│   ├── quality.py         # Message quality modifiers
│   ├── anti_gaming.py     # Pair caps, diminishing returns, velocity limits
│   ├── achievements.py    # Achievement trigger checking
│   └── cache.py           # In-memory ConfigCache + PG LISTEN/NOTIFY
├── services/
│   ├── reward_service.py       # Calculate → persist → stats → achievements
│   ├── announcement_service.py # Preference-gated, throttle-safe announcements
│   ├── event_lake_writer.py    # Event Lake writes with counter updates
│   ├── admin_service.py        # Zone/achievement/season CRUD + audit logging
│   ├── settings_service.py     # Settings read/write with NOTIFY
│   ├── channel_service.py      # Guild channel → zone auto-mapping
│   ├── setup_service.py        # First-run bootstrap, guild snapshots
│   ├── retention_service.py    # Event Lake cleanup
│   ├── reconciliation_service.py # Counter drift correction
│   ├── backfill_service.py     # Legacy activity_log migration
│   ├── embeds.py               # Discord embed builders
│   ├── throttle.py             # Announcement rate limiter
│   └── log_buffer.py           # In-memory ring buffer for live logs
└── api/
    ├── main.py            # FastAPI app setup
    ├── auth.py            # Discord OAuth2 → JWT
    ├── deps.py            # Dependency injection, JWT validation
    ├── rate_limit.py      # Per-admin mutation rate limiting
    └── routes/
        ├── public.py      # Read-only public endpoints
        ├── admin.py       # Admin CRUD endpoints
        └── event_lake.py  # Event Lake management endpoints

dashboard/
├── src/
│   ├── routes/            # SvelteKit pages (4 public + 8 admin)
│   └── lib/
│       ├── api.ts         # Typed API client
│       ├── utils.ts       # Formatting helpers
│       ├── stores/        # auth, currency, flash, names
│       └── components/    # 10 reusable Svelte components

tests/                     # 12 test files, ~3,200 lines, in-memory SQLite
alembic/                   # Database migrations
```

## Development

### Running Tests

```bash
uv run pytest tests/ -v
```

Tests use in-memory SQLite (with a JSONB→TEXT shim) for full isolation — no PostgreSQL required.

### Linting

```bash
uv run ruff check synapse/ tests/
uv run ruff format synapse/ tests/
uv run mypy synapse/
```

### Database Migrations

```bash
# Generate a migration after model changes
uv run alembic revision --autogenerate -m "description"

# Apply migrations
uv run alembic upgrade head
```

## License

See repository for license details.
