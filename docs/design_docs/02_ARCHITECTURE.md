# 02 — System Architecture

> *Four services, one database, minimal ops burden.*

---

## 2.1 High-Level Topology

Synapse runs as **four services** that share a single PostgreSQL database.
This keeps separation of concerns while enabling a modern web experience
for a solo maintainer.

```
┌──────────────────────────────────────────────────────────────────────┐
│                        Discord Server                                │
│   Members chat, react, join voice, use slash commands                │
└──────────┬───────────────────────────────────────────────────────────┘
           │ Events (on_message, on_reaction_add, etc.)           
           ▼                                                      
┌──────────────────────┐                                          
│  Service 1: BOT      │                                          
│  (discord.py)        │                                          
│                      │                                          
│  - Listens to events │                                          
│  - Normalizes to     │                                          
│    SynapseEvent      │                                          
│  - Runs Reward       │                                         
│    Engine module     │                                          
│  - Posts embeds      │                                          
└────────┬─────────────┘                                          
         │                                                        
         ▼                                                        
┌────────────────────────────────────┐                                          
│  Service 2: API                    │                                                 
│  (FastAPI + uvicorn on :8000)      │                            
│                                    │                             
│  - REST endpoints (/api/*)         │                             
│  - Discord OAuth → JWT auth        │                            
│  - Admin CRUD (audit-logged)       │                             
│  - Public analytics queries        │                             
└────────┬───────────────────────────┘                                          
         │                                                         
         ▼                                                         
┌──────────────────────────────────────────────────────────────────┐
│  Service 3: DASHBOARD  (SvelteKit on :3000)                      │
│  - Public pages (overview, leaderboard, activity, achievements)  │
│  - Admin pages (zones, achievements, awards, settings, audit)    │
│  - Talks to API only (never touches DB directly)                 │
└──────────────────────────────────────────────────────────────────┘
                                                                    
┌──────────────────────────────────────────────────────────────────┐
│  Service 4: DATABASE  (PostgreSQL 16)                            │
│  - Users, Zones, Achievements, ActivityLog, Settings, Quests     │
│  - All configuration lives here (not in YAML at production)      │
└──────────────────────────────────────────────────────────────────┘
```

### Why Four Services?

| Service | Responsibility | Scaling Profile |
|---------|---------------|-----------------|
| **Bot** | Event ingestion, Discord I/O | Single instance (Discord gateway limit) |
| **API** | REST endpoints, auth, admin CRUD | Stateless, horizontally scalable |
| **Dashboard** | Web UI (SvelteKit SSR + SPA) | Stateless, horizontally scalable |
| **Database** | State persistence | Vertically scalable (managed PG) |

---

## 2.2 Data Flow: The Event Pipeline

Every interaction in Discord follows this path:

```
1. Discord Event
       │
       ▼
2. [Bot: Event Listener]
   Cog receives on_message / on_reaction_add / on_voice_state_update
       │
       ▼
3. [Bot: Event Normalizer]
   Converts raw discord.py objects into a SynapseEvent dataclass:
     SynapseEvent(
       user_id=123,
       event_type=InteractionType.MESSAGE,
       channel_id=456,
       zone_id=None,       # resolved by Reward Engine
       metadata={"length": 312, "has_code_block": True},
       timestamp=datetime.now(UTC)
     )
       │
       ▼
4. [Bot: Reward Engine Module]
   a. Zone Classification  — Which zone does this channel belong to?
   b. Multiplier Lookup    — What are the XP/Star multipliers for this zone+event type?
   c. Quality Analysis     — Message length, code blocks, link enrichment, LLM score?
   d. XP Calculation       — base_xp × zone_multiplier × quality_modifier
   e. Star Calculation     — base_stars × zone_star_multiplier
   f. Achievement Check    — Does this push any counter past a threshold?
       │
       ▼
5. [Database: State Update]
   a. UPDATE users SET xp = xp + ?, stars = stars + ?
   b. INSERT INTO activity_log (...) ON CONFLICT (source_system, source_event_id)
      DO NOTHING — idempotent insert prevents double-credit (D04-07)
   c. UPDATE user_stats SET messages_sent = messages_sent + 1
   d. If achievement triggered → INSERT INTO user_achievements
       │
       ▼
6. [Bot: Response]
   a. If level-up    → Post celebratory embed in channel
   b. If achievement → Post achievement embed in announcement channel
   c. Otherwise      → Silent (no spam)
```

---

## 2.3 Service Boundaries

### Bot Runtime Boundary

The bot owns event ingestion and reward calculation.  All Discord events are
normalized into `SynapseEvent`, passed through the reward module, and then
persisted to PostgreSQL.

### API → Database Communication

The FastAPI service is the **sole gateway** between the web frontend and the
database.  It exposes typed REST endpoints under `/api/*` for both public
analytics and authenticated admin operations.

All admin config mutations (zone CRUD, multiplier changes, manual awards,
season rolls) are **audit-logged** via the shared service layer.  Every write
inserts a row into `admin_log` with before/after snapshots before committing
the config change.  See D02-05 and D04-06.

### Dashboard → API Communication

The SvelteKit dashboard **never accesses PostgreSQL directly**.  All data
flows through the FastAPI REST endpoints.  Authentication is handled via
Discord OAuth2 → JWT tokens issued by the API.

---

## 2.4 The Cog System (Bot Modularity)

The bot uses discord.py's **Cog** (extension) pattern.  Each Cog is a
self-contained module that can be loaded, unloaded, or hot-reloaded.

```
synapse/bot/cogs/
├── social.py        # on_message → XP engine (core, always loaded)
├── reactions.py     # on_reaction_add/remove → star engine
├── voice.py         # on_voice_state_update → presence tracking
├── threads.py       # on_thread_create → thread tracking
├── meta.py          # /profile, /link-github, /leaderboard
└── admin.py         # /award, /create-achievement, /grant-achievement
```

**Plugin Convention:** The Reward Engine doesn't care where events come from —
it only sees `SynapseEvent` objects.  Future integrations (GitHub webhooks,
TryHackMe) add new cogs that emit `SynapseEvent` without changing the core.

---

## 2.5 Technology Stack Summary

| Layer | Technology | Justification |
|-------|-----------|---------------|
| Language (Backend) | Python 3.12+ | Team familiarity, discord.py ecosystem |
| Language (Frontend) | TypeScript / Svelte 5 | Type safety, modern reactivity, small bundle |
| Package Managers | uv (Python), npm (Node) | Deterministic lockfiles, fast installs |
| Bot Framework | discord.py 2.6+ | Mature, Cog system, hybrid commands |
| API Framework | FastAPI + uvicorn | Async, auto-docs, type-validated requests |
| Frontend Framework | SvelteKit 2 + Tailwind CSS 3.4 | SSR, file-based routing, utility CSS |
| Charts | Chart.js 4 | Lightweight, canvas-based, responsive |
| Auth | Discord OAuth2 → JWT (HS256 via python-jose) | Stateless, no session store required |
| ORM | SQLAlchemy 2.0 | Modern Mapped[] style, type-safe, migration-ready |
| Database | PostgreSQL 16 | ACID, JSON columns, full-text search, Azure-native |
| Containerization | Docker + Compose | Reproducible local dev, matches Azure App Service |
| Cloud Target | Microsoft Azure | App Service + Flexible PG Server + Container Registry |

---

## Decisions

> **Decision D02-01:** Separate API Service
> - **Status:** Superseded → Reinstated (v3.0)
> - **Context:** Originally accepted in v2.0, then dropped in v2.1 as
>   unnecessary for Streamlit-only architecture.  Reinstated in v3.0
>   when Streamlit was replaced by SvelteKit, which requires a proper
>   API backend.
> - **Choice:** FastAPI + uvicorn serves all REST endpoints on port 8000.
>   The SvelteKit frontend communicates exclusively through these endpoints.
> - **Consequences:** Clean separation between frontend and backend.  API
>   can be versioned, tested, and scaled independently.

> **Decision D02-02:** Synchronous SQLAlchemy + asyncio.to_thread()
> - **Status:** Accepted
> - **Context:** discord.py is async.  SQLAlchemy + psycopg2 is sync.
> - **Choice:** Use `asyncio.to_thread()` to offload DB calls instead of
>   adopting async SQLAlchemy + asyncpg.
> - **Consequences:** Simpler code, easier for novices to learn, battle-tested
>   psycopg2 driver.  Acceptable performance for <10k members.

> **Decision D02-03:** Dashboard Is Read-Only
> - **Status:** Superseded
> - **Context:** Originally limited the dashboard to read-only.  Later
>   expanded to allow authenticated admin writes in Streamlit.  Now the
>   SvelteKit frontend performs all writes through the FastAPI API.
> - **Choice:** Replaced by API-mediated admin writes (D02-07).
> - **Consequences:** All mutations flow through FastAPI with JWT auth.

> **Decision D02-04:** Three-Service Runtime Topology
> - **Status:** Superseded by D02-07
> - **Context:** A dedicated API container was not deemed necessary when
>   Streamlit could access the database directly.
> - **Choice:** Replaced by four-service topology in v3.0.
> - **Consequences:** See D02-07.

> **Decision D02-05:** Admin Writes Are Audit-Logged at the Service Layer
> - **Status:** Accepted
> - **Context:** Admin mutations need an audit trail regardless of which
>   frontend initiates them.
> - **Choice:** The shared service module inserts an `admin_log` row
>   (before/after JSONB snapshots) in the same transaction as every config
>   mutation.
> - **Consequences:** Full mutation history.  Now invoked by FastAPI route
>   handlers instead of Streamlit pages.

> **Decision D02-06:** Idempotent Event Persistence
> - **Status:** Accepted
> - **Context:** Bot retries and webhook replays can duplicate events.
> - **Choice:** `activity_log` inserts use `ON CONFLICT DO NOTHING` on
>   `(source_system, source_event_id)`.  Events without a natural key
>   (e.g., voice ticks) leave `source_event_id` NULL.
> - **Consequences:** At-least-once delivery becomes exactly-once crediting
>   with zero application-side dedup logic.

> **Decision D02-07:** Four-Service Runtime Topology (v3.0)
> - **Status:** Accepted
> - **Context:** Streamlit was replaced by SvelteKit + FastAPI.  The
>   frontend can no longer access the database directly; it needs a
>   proper API layer.
> - **Choice:** Run `db`, `bot`, `api` (FastAPI on :8000), and `dashboard`
>   (SvelteKit on :3000) as four Docker Compose services.
> - **Consequences:** Clean frontend/backend separation.  API handles auth,
>   validation, and audit logging.  Dashboard is a pure static/SSR client.
>   Slightly more services to manage, but each is independently deployable.
