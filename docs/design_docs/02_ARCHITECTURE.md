# 02 — System Architecture

> *Four services, one database, three pillars, minimal ops burden.*

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
           │ Gateway Events (ephemeral — disappear if not captured)
           ▼
┌───────────────────────────┐
│  Service 1: BOT           │
│  (discord.py)             │
│                           │
│  - Captures gateway events│
│  - Writes to Event Lake   │  ← NEW in v4.0
│  - Runs Rules Engine      │  ← NEW in v4.0 (replaces Reward Engine)
│  - Posts embeds           │
└────────┬──────────────────┘
         │
         ▼
┌────────────────────────────────────┐
│  Service 2: API                    │
│  (FastAPI + uvicorn on :8000)      │
│                                    │
│  - REST endpoints (/api/*)         │
│  - Discord OAuth → JWT auth        │
│  - Admin CRUD (audit-logged)       │
│  - Rule + Currency + Module mgmt   │  ← NEW in v4.0
│  - Public analytics queries        │
└────────┬───────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────────────────┐
│  Service 3: DASHBOARD  (SvelteKit on :3000)                      │
│  - Public pages (overview, leaderboard, activity, milestones)    │
│  - Admin pages (rules, currencies, modules, regions, audit)      │  ← expanded in v4.0
│  - Talks to API only (never touches DB directly)                 │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│  Service 4: DATABASE  (PostgreSQL 16)                            │
│  - Event Lake (raw captured events)                              │  ← NEW in v4.0
│  - Ledger (currencies, wallets, transactions)                    │  ← NEW in v4.0
│  - Rules (configurable trigger/condition/effect)                 │  ← NEW in v4.0
│  - Milestones, Regions, Settings, Modules, Taxonomy              │
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

## 2.2 The Three Pillars (v4.0)

The v4.0 architecture adds three foundational subsystems that sit between
the raw Discord events and the user-facing features:

```
Discord Gateway ──→ Event Lake ──→ Rules Engine ──→ Ledger ──→ Dashboard
   (ephemeral)      (captured)     (configurable)   (audited)   (visible)
```

### Pillar 1: Event Lake (Data In)

The Event Lake captures ephemeral Discord gateway events that would
otherwise be lost.  It is an append-only table storing normalized event
payloads.  The bot is the sole writer; the API and Rules Engine are readers.

See [03B_DATA_LAKE.md](03B_DATA_LAKE.md) for the full design.

**Key design principle:** Only store data that disappears.  Discord's REST
API can fetch static/historical data (member lists, channel info, roles)
on demand — there's no need to duplicate it.  The Event Lake focuses on
the stream: messages sent, reactions added, voice sessions started, etc.

### Pillar 2: Ledger (Currency)

The Ledger replaces hardcoded `users.xp` and `users.gold` columns with
a configurable currency system: admin-defined **Currencies**, per-user
**Wallets**, and append-only **Transactions**.

See [03_CONFIGURABLE_ECONOMY.md](03_CONFIGURABLE_ECONOMY.md).

### Pillar 3: Rules Engine (Decisions)

The Rules Engine replaces the hardcoded Reward Engine pipeline with
configurable trigger/condition/effect rules stored as JSON in the database.

See [05_RULES_ENGINE.md](05_RULES_ENGINE.md).

---

## 2.3 Data Flow: The Event Pipeline

Every interaction in Discord follows this path:

```
1. Discord Gateway Event
       │
       ▼
2. [Bot: Event Capture]
   Cog receives on_message / on_reaction_add / on_voice_state_update
       │
       ▼
3. [Bot: Event Lake Writer]
   Normalizes raw discord.py objects into an Event Lake entry:
     {
       user_id: 123,
       event_type: "message_create",
       channel_id: 456,
       guild_id: 789,
       payload: { length: 312, has_code_block: true, ... },
       source_id: "discord_snowflake_abc",
       timestamp: "2025-01-15T14:30:00Z"
     }
   INSERT into event_lake (idempotent via source_id)
       │
       ▼
4. [Bot: Rules Engine]
   a. Load enabled rules (cached, PG NOTIFY refresh)
   b. For each rule where trigger matches this event:
      - Evaluate all conditions (zone filter, caps, anti-gaming)
      - If conditions pass: execute effects
   c. Effects may include:
      - Ledger transactions (credit XP, Stars, Gold, etc.)
      - Milestone checks (query wallets + event counts)
      - Announcements (level-up, milestone earned)
      - Role assignments
   d. All ledger writes batched in one DB transaction
       │
       ▼
5. [Database: State Update]
   a. Event Lake entry persisted (step 3)
   b. Wallet balances updated via transactions
   c. If milestone triggered → INSERT into user_milestones
   d. If rule logs → INSERT into admin_log
       │
       ▼
6. [Bot: Response]
   a. If level-up     → Post celebratory embed in channel
   b. If milestone    → Post milestone embed in announcement channel
   c. Otherwise       → Silent (no spam)
```

---

## 2.4 Service Boundaries

### Bot Runtime Boundary

The bot owns **event capture** and **rule evaluation**.  All Discord
gateway events are normalized into Event Lake entries, then processed
by the Rules Engine.  The bot writes to the Event Lake, Ledger (wallets/
transactions), and milestones tables.

The bot is also the sole consumer of the Discord gateway connection.
It holds two privileged intents: **MESSAGE_CONTENT** (quality analysis
of message text without storing it) and **GUILD_MEMBERS** (join/leave
tracking, member cache population).  **GUILD_PRESENCES** is explicitly
disabled — it is the highest-bandwidth intent and provides no engagement
signal.  See [03B_DATA_LAKE.md §3B.2](03B_DATA_LAKE.md) for the full
intent matrix and verification requirements.

### API → Database Communication

The FastAPI service is the **sole gateway** between the web frontend and the
database.  It exposes typed REST endpoints under `/api/*` for both public
analytics and authenticated admin operations.

All admin config mutations (rule CRUD, currency definitions, region changes,
manual awards, module toggles, taxonomy edits, season rolls) are
**audit-logged** via the shared service layer.

### Dashboard → API Communication

The SvelteKit dashboard **never accesses PostgreSQL directly**.  All data
flows through the FastAPI REST endpoints.  Authentication is handled via
Discord OAuth2 → JWT tokens issued by the API.

### Module System

v4.0 introduces **Modules** — toggleable feature groups that control which
subsystems are active for a given deployment:

| Module | Controls | Default |
|--------|----------|---------|
| Economy | Currencies, wallets, transactions, leaderboard | ON |
| Milestones | Milestone templates, earn tracking, gallery | ON |
| Analytics | Event Lake capture, activity charts, heatmaps | ON |
| Announcements | Level-up/milestone embeds, activity ticker | ON |
| Seasons | Seasonal currency resets, season snapshots | OFF |

Modules are not code-level plugins — they are **feature flags** stored in
the `modules` table.  When a module is OFF, its related rules are skipped,
its API endpoints return 404, and its dashboard pages are hidden.

---

## 2.5 The Cog System (Bot Modularity)

The bot uses discord.py's **Cog** (extension) pattern.  Each Cog is a
self-contained module that can be loaded, unloaded, or hot-reloaded.

```
synapse/bot/cogs/
├── social.py        # on_message → Event Lake + Rules Engine
├── reactions.py     # on_reaction_add/remove → Event Lake + Rules Engine
├── voice.py         # on_voice_state_update → Event Lake + derived events
├── threads.py       # on_thread_create → Event Lake + Rules Engine
├── meta.py          # /profile, /leaderboard (reads from wallets)
└── admin.py         # /award, /create-milestone, /grant-milestone
```

**Plugin Convention:** The Rules Engine doesn't care where events come from —
it processes Event Lake entries.  Future integrations (GitHub webhooks,
external APIs) add new event sources that write to the Event Lake without
changing the Rules Engine or core cogs.

---

## 2.6 Technology Stack Summary

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

> **Decision D02-08:** Three-Pillar Data Architecture (v4.0)
> - **Status:** Accepted (New in v4.0)
> - **Context:** The v3.0 bot ran a hardcoded Reward Engine pipeline.
>   All currency names, anti-gaming logic, and quality modifiers were
>   Python code.  This prevented non-developers from configuring behavior.
> - **Choice:** Introduce three foundational subsystems — Event Lake
>   (data capture), Ledger (configurable currencies), and Rules Engine
>   (configurable logic) — that decouple "what happened" from "what to
>   do about it."
> - **Consequences:** Community operators can configure all behavior through
>   the dashboard.  The bot becomes a data vacuum + rule evaluator rather
>   than a reward calculator.

> **Decision D02-09:** Module System as Feature Flags (v4.0)
> - **Status:** Accepted (New in v4.0)
> - **Context:** Not every community wants every feature.  A study group
>   may want analytics but no economy.
> - **Choice:** Introduce a `modules` table with boolean toggles.  Disabled
>   modules skip their rules, hide their API endpoints, and hide their
>   dashboard pages.
> - **Consequences:** Lightweight feature toggling without code-level plugin
>   architecture.  Simple enough for a single-maintainer project.

> **Decision D02-10:** Gateway Intent Configuration (v4.0)
> - **Status:** Accepted (New in v4.0)
> - **Context:** Discord v10 requires explicit opt-in to event categories
>   via Gateway Intents.  Privileged intents (MESSAGE_CONTENT, GUILD_MEMBERS,
>   GUILD_PRESENCES) require justification and approval at 75+ servers.
> - **Choice:** Enable 4 standard intents (GUILDS, GUILD_MESSAGES,
>   GUILD_MESSAGE_REACTIONS, GUILD_VOICE_STATES) and 2 privileged intents
>   (MESSAGE_CONTENT, GUILD_MEMBERS).  Skip GUILD_PRESENCES entirely.
> - **Consequences:** Full coverage of engagement events (messages, reactions,
>   voice, threads, membership).  No online/offline tracking.  Two intents
>   to justify at verification instead of three.
>   See [03B_DATA_LAKE.md](03B_DATA_LAKE.md) for details.
