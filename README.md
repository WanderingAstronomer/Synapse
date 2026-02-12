# 🧠 Project Synapse

**A gamified engagement framework for university clubs** — bridges Discord activity to meaningful recognition through XP, Stars, Gold, achievements, and seasonal progression.

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

**Four services** in Docker Compose:
- **db** — PostgreSQL 16
- **bot** — Discord bot (`python -m synapse.bot`)
- **api** — FastAPI REST layer (`uvicorn synapse.api.main:app`)
- **dashboard** — SvelteKit frontend (public Club Pulse + admin panel)

## Dual Economy

| Currency | Earning | Purpose |
|----------|---------|---------|
| **XP** | Weighted by zone multipliers + quality modifiers | Progression (levels, rank) |
| **Stars** ⭐ | Flat per event type | Social recognition (achievements, seasonal) |
| **Gold** 🪙 | Level-up bonus (50/level) | Spendable (minimal sink via `/buy-coffee`) |

## Zones & Multipliers

Channels are grouped into **Zones** (e.g., programming, cybersecurity, general, memes). Each zone has per-event-type XP and Star multipliers stored in PostgreSQL, editable in the admin dashboard.

## Event Pipeline

```
Discord Event → SynapseEvent → Zone Classification → Quality Modifier
→ Anti-Gaming → Multiplier Application → XP Cap → Idempotent Persist
→ Stat Update → Achievement Check → Level-Up Check
```

**Anti-gaming measures**: self-reaction filter, unique-reactor weighting, per-user per-target caps, diminishing returns, reaction velocity cap.

## Achievements

Four trigger types:
- `counter_threshold` — Stat field reaches a value (e.g., 100 messages)
- `star_threshold` — Season or lifetime stars reach a value
- `xp_milestone` — XP reaches a value
- `custom` — Admin-granted only

11 seed achievements included (First Steps, Rising Star, Chatterbox, etc.)

## Bot Commands

| Command | Access | Description |
|---------|--------|-------------|
| `/profile [member]` | Everyone | XP, level, gold, stars, achievements, rank |
| `/leaderboard [xp\|stars]` | Everyone | Top members by XP or Stars |
| `/link-github <username>` | Everyone | Associate GitHub account |
| `/preferences <setting> <on\|off>` | Everyone | Toggle announcement preferences (level-ups, achievements, awards) |
| `/buy-coffee` | Everyone | Spend gold (minimal gold sink) |
| `/award <member> [xp] [gold] [reason]` | Admin | Manual XP/Gold award |
| `/create-achievement ...` | Admin | Create new achievement template |
| `/grant-achievement <member> <id>` | Admin | Grant achievement to user |
| `/season <name> [days]` | Admin | Create new season (rolls over) |

## Dashboard

### Club Pulse (Public)
- **Overview** — Hero banner with live metrics (total members, XP, active users, top level)
- **Leaderboard** — Paginated XP / Gold / Level tabs with Discord avatars and progress bars
- **Activity** — Chart.js stacked bar chart (daily event breakdown), filterable event feed
- **Achievements** — Card grid with rarity glow effects, category/rarity filters, recent earners

### Admin Panel (JWT-gated via Discord OAuth)
- Discord OAuth2 → FastAPI issues JWT → SvelteKit stores token
- Admin role check (requires `admin_role_id` from config)
- **Zones** — Create/edit zones with channel IDs and multipliers
- **Achievements** — Full builder with all fields, table view, toggle active
- **Awards** — User search, XP/Gold grant, achievement grant
- **Settings** — Category-filtered inline editor with bulk save
- **Audit Log** — Expandable entries with before/after JSON snapshots

Rate limited: 30 mutations/minute per admin session.

## Setup

### Prerequisites
- Python 3.12+
- PostgreSQL 16
- [uv](https://docs.astral.sh/uv/) package manager
- Discord bot token

### Environment Variables

```bash
# .env
DISCORD_TOKEN=your-bot-token
DATABASE_URL=postgresql://synapse:synapse@localhost:5432/synapse

# Dashboard admin auth
DISCORD_CLIENT_ID=your-oauth-app-id
DISCORD_CLIENT_SECRET=your-oauth-secret
DISCORD_REDIRECT_URI=http://localhost:5173/auth/callback
JWT_SECRET=your-random-secret    # openssl rand -hex 32
FRONTEND_URL=http://localhost:5173

DEV_GUILD_ID=your-guild-id  # For instant slash command sync
```

### Local Development

```bash
# Install Python dependencies
uv sync

# Install Node dependencies (dashboard)
cd dashboard && npm install && cd ..

# Start PostgreSQL (via Docker or local)
docker compose up -d db

# Run the bot
uv run python -m synapse.bot

# Run the API (separate terminal)
uv run uvicorn synapse.api.main:app --reload --port 8000

# Run the dashboard (separate terminal)
cd dashboard && npm run dev

# Run tests
uv run pytest tests/ -v
```

### Docker Compose (Full Stack)

```bash
docker compose up --build
```

### Configuration

Edit `config.yaml` for club-specific settings:

```yaml
club_name: "Your Club"
guild_id: 123456789          # Your Discord server ID
admin_role_id: 987654321     # Admin role ID
cooldown_seconds: 60
level_base: 100
level_factor: 1.25
gold_per_level_up: 50
```

## Project Structure

```
synapse/
├── api/
│   ├── main.py              # FastAPI app (CORS, lifespan, router mounting)
│   ├── deps.py              # Dependency injection (engine, config, session, JWT auth)
│   ├── auth.py              # Discord OAuth2 flow + JWT issuance
│   └── routes/
│       ├── public.py        # Public endpoints (metrics, leaderboard, activity, achievements)
│       └── admin.py         # Admin CRUD (zones, achievements, awards, settings, audit)
├── bot/
│   ├── __main__.py          # Entry point
│   ├── core.py              # SynapseBot class + extension loader
│   └── cogs/
│       ├── social.py        # on_message XP/Star pipeline
│       ├── reactions.py     # on_reaction XP/Star pipeline
│       ├── voice.py         # Voice tick + thread creation
│       ├── meta.py          # /profile, /leaderboard, /preferences, /buy-coffee
│       └── admin.py         # /award, /create-achievement, /grant-achievement
├── database/
│   ├── engine.py            # SQLAlchemy engine + async bridge
│   └── models.py            # 12 tables (SQLAlchemy 2.0 Mapped)
├── engine/
│   ├── events.py            # SynapseEvent dataclass + base XP/Stars
│   ├── reward.py            # Pure reward calculation pipeline
│   ├── achievements.py      # Achievement check logic
│   └── cache.py             # In-memory config cache + PG LISTEN/NOTIFY
├── services/
│   ├── reward_service.py    # Event persistence + reward application
│   ├── admin_service.py     # Audit-logged admin mutations
│   └── seed.py              # Default data seeder
└── config.py                # YAML config loader

dashboard/                   # SvelteKit frontend (separate Node project)
├── src/
│   ├── lib/
│   │   ├── api.ts           # Typed fetch client for all API endpoints
│   │   ├── utils.ts         # Formatters, time helpers, event colors
│   │   ├── stores/          # Svelte stores (auth, flash notifications)
│   │   └── components/      # Reusable UI (HeroHeader, Sidebar, MetricCard, etc.)
│   └── routes/
│       ├── +page.svelte             # Overview (metrics, top members, recent achievements)
│       ├── leaderboard/+page.svelte # Paginated XP/Gold/Level leaderboard
│       ├── activity/+page.svelte    # Chart.js daily chart + event feed
│       ├── achievements/+page.svelte # Achievement card grid with filters
│       ├── auth/callback/+page.svelte # OAuth token handler
│       └── admin/                   # Auth-guarded admin pages
│           ├── zones/+page.svelte
│           ├── achievements/+page.svelte
│           ├── awards/+page.svelte
│           ├── settings/+page.svelte
│           └── audit/+page.svelte
├── tailwind.config.js       # Custom brand colors, animations
├── package.json             # SvelteKit 2, Svelte 5, Tailwind, Chart.js
└── Dockerfile               # Multi-stage Node build for production
```

## Implemented vs Deferred

### ✅ Implemented
- Full dual economy (XP + Stars + Gold)
- Zone-based multipliers with per-event-type granularity
- Quality-weighted message XP (length, code, links, attachments)
- Anti-gaming suite (self-reaction filter, unique-reactor weighting, diminishing returns)
- Idempotent event persistence (ON CONFLICT DO NOTHING)
- PG LISTEN/NOTIFY cache invalidation (no Redis)
- Achievement system (4 trigger types, 11 seed achievements)
- Seasonal stats with season rollover
- FastAPI REST API with typed endpoints
- SvelteKit dashboard with Tailwind CSS + Chart.js
- Discord OAuth → JWT admin authentication with role check
- Audit-logged admin mutations with before/after snapshots
- Rate-limited admin panel (30 mutations/min)
- Voice channel XP with anti-idle
- Thread creation tracking
- Discord avatar integration (CDN URL construction)

### 🔮 Deferred
- **GitHub Neural Bridge** — GitHub webhook → XP attribution (requires webhook infra)
- **LLM Quality Modifier** — AI-based content quality scoring (stub present)
- **Quests** — Table exists, UI deferred to P2
- **Alembic Migrations** — Using `create_all` for dev; add before production
- **Custom Badge Images** — `badge_image_url` column exists, rendering deferred
- **DM Notifications** — Preference column exists, delivery deferred

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Bot | discord.py 2.6+ |
| Database | PostgreSQL 16 (JSONB, partial indexes, LISTEN/NOTIFY) |
| ORM | SQLAlchemy 2.0 (Mapped[] style, sync + asyncio.to_thread) |
| API | FastAPI + uvicorn |
| Frontend | SvelteKit 2 + Svelte 5 + Tailwind CSS 3.4 + Chart.js 4 |
| Auth | Discord OAuth2 → FastAPI JWT (HS256 via python-jose) |
| Runtime | Python 3.12+, Node.js 22 |
| Package Managers | uv (Python), npm (Node) |
| Container | Docker Compose (4 services: db, bot, api, dashboard) |

## License

MIT
