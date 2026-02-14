# Deployment

## Docker Compose (Recommended)

Four services on a shared `synapse-net` bridge network:

```bash
docker compose up -d --build
```

### Services

| Service | Container | Image | Port | Command |
|---------|-----------|-------|------|---------|
| **db** | synapse-db | postgres:16-alpine | 5432 | Default PostgreSQL |
| **bot** | synapse-bot | Built from `./Dockerfile` | — | `python -m synapse.bot` |
| **api** | synapse-api | Built from `./Dockerfile` | 8000 | `uvicorn synapse.api.main:app` |
| **dashboard** | synapse-dashboard | Built from `./dashboard/Dockerfile` | 3000 | Node.js (SvelteKit) |

### Dependency Chain

```
db (healthy) → bot
db (healthy) → api (healthy) → dashboard
```

All services have healthchecks:
- **db:** `pg_isready -U synapse` (5s interval)
- **bot:** `python -c 'import synapse.bot'` (30s interval, 15s start period)
- **api:** HTTP GET to `/api/health` (15s interval, 10s start period)
- **dashboard:** `fetch('http://localhost:3000')` (15s interval, 15s start period)

### Volumes

- `pgdata` — Persistent PostgreSQL data directory

### Docker Compose Watch (Dev)

The bot and API services use `develop.watch` for live-reload:
- File syncs: `./synapse` → `/app/synapse`, `./config.yaml` → `/app/config.yaml`
- Rebuild trigger: `pyproject.toml` changes

```bash
docker compose watch
```

## Dockerfile

Multi-stage build using Python 3.12-slim:

**Stage 1 (builder):**
1. Copies `uv` binary from official image
2. `uv sync --locked --no-install-project --no-dev` — installs dependencies (cached aggressively)
3. Copies full source and installs the project

**Stage 2 (runtime):**
1. Copies `.venv` from builder
2. Copies uv-managed Python interpreter
3. Copies application code
4. Default CMD: `python -m synapse.bot` (overridden per service in compose)

The dashboard has its own `dashboard/Dockerfile` for the SvelteKit Node adapter build.

## Environment Variables

### Required

| Variable | Description | Example |
|----------|-------------|---------|
| `DISCORD_TOKEN` | Bot token from Discord Developer Portal | `MTIz...` |
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+psycopg2://synapse:synapse@db:5432/synapse` |
| `JWT_SECRET` | Min 32-character secret for JWT signing | `your-secure-random-string-here-min-32-chars` |
| `DISCORD_CLIENT_ID` | OAuth2 application client ID | `123456789012345678` |
| `DISCORD_CLIENT_SECRET` | OAuth2 application client secret | `abcdef...` |
| `DISCORD_REDIRECT_URI` | OAuth2 callback URL | `http://localhost:3000/auth/callback` |
| `FRONTEND_URL` | Dashboard base URL for OAuth redirects | `http://localhost:3000` |

### Optional

| Variable | Default | Description |
|----------|---------|-------------|
| `DEV_GUILD_ID` | — | If set, syncs slash commands to this guild only (faster for dev) |
| `API_BASE_URL` | `http://localhost:8000/api` | Dashboard env: API backend URL for proxy |
| `CORS_ALLOW_ORIGINS` | — | API env: comma-separated CORS allowlist (falls back to `FRONTEND_URL`) |
| `ORIGIN` | — | Dashboard env: SvelteKit origin for CSRF |
| `BODY_SIZE_LIMIT` | — | Dashboard env: request body size limit |

### Docker Compose Overrides

The compose file sets these automatically:
- `DATABASE_URL` → `postgresql+psycopg2://synapse:synapse@db:5432/synapse`
- `JWT_SECRET` → reads from `.env` (with a dev fallback)
- `DISCORD_REDIRECT_URI` → `http://localhost:3000/auth/callback`
- `FRONTEND_URL` → `http://localhost:3000`
- `API_BASE_URL` → `http://api:8000/api` (dashboard → API via Docker network)

## config.yaml

Infrastructure and identity settings only. All gameplay tuning is in the database.

```yaml
community_name: "My Community"      # Displayed in embeds and dashboard
community_motto: "Our tagline"       # Displayed in bot description
bot_prefix: "!"                      # Legacy prefix (slash commands are primary)
guild_id: 123456789                  # Primary Discord server snowflake
dashboard_port: 3000                 # Dashboard port (informational)
admin_role_id: 123456789             # Discord role required for admin access
announce_channel_id: null            # Optional: override announcement channel
```

## Discord Bot Setup

1. Create application at [Discord Developer Portal](https://discord.com/developers/applications)
2. Create a bot user and copy the token
3. Enable privileged intents:
   - **Message Content Intent** — Required for quality analysis
   - **Server Members Intent** — Required for join/leave tracking
4. Generate invite URL with permissions:
   - Read Messages, Send Messages, Embed Links, Add Reactions
   - Manage Channels (for auto-creating `#synapse-achievements`)
   - Read Message History (for reaction tracking on older messages)
5. Invite the bot to your server

## First-Run Bootstrap

After starting all services:

1. Open `http://localhost:3000`
2. Click Login and authorize with Discord OAuth2
3. You must have the `admin_role_id` role in the Discord server
4. Navigate to `/admin/setup` (auto-redirect if not bootstrapped)
5. Click Bootstrap — this creates:
   - Categories from Discord server categories
   - Channel → category mappings
   - Default season (120 days)
   - 18+ default settings (economy, anti-gaming, quality, display, announcements)

## Database

### Connection

PostgreSQL 16. Connection pool: 5 persistent + 10 overflow, with `pool_pre_ping=True` for auto-reconnect.

### Schema Initialization

On bot startup, `init_db(engine)` calls `Base.metadata.create_all()` — safe to run repeatedly.

### Migrations

Alembic for additive schema changes:

```bash
# Set DATABASE_URL in .env, then:
uv run alembic revision --autogenerate -m "description"
uv run alembic upgrade head
```

Configuration in `alembic/env.py` reads `DATABASE_URL` from the environment and uses `Base.metadata` for autogeneration.

## Running Without Docker

```bash
# 1. Install Python dependencies
uv sync

# 2. Start PostgreSQL and set DATABASE_URL in .env

# 3. Run the bot
uv run python -m synapse.bot

# 4. Run the API (separate terminal)
uv run uvicorn synapse.api.main:app --host 0.0.0.0 --port 8000

# 5. Run the dashboard (separate terminal)
cd dashboard
npm install
npm run dev
```

## CORS

The API allows requests from:
- `http://localhost:5173` (SvelteKit dev server)
- `http://localhost:3000` (dashboard production/preview)
- `http://dashboard:3000` (Docker internal network)

In production with the API proxy, CORS is not needed — the dashboard proxies all API calls through its own origin.

## Logging

Python logging with format: `HH:MM:SS │ LEVEL │ logger │ message`.

An in-memory ring buffer (2,000 entries) captures all logs for the admin live log viewer. Level can be changed at runtime via `PUT /api/admin/logs/level`.

Logs are lost on restart by design — no filesystem persistence.
