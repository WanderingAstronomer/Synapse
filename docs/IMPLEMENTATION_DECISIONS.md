# Implementation Decision Log

> Living document maintained during Project Synapse implementation.
> Updated at each major milestone.

---

## Initial Gap Analysis (2026-02-11)

### Current State (P0)
The existing codebase implements the Phase 0 foundation:
- Basic `User`, `Quest`, `ActivityLog` models (SQLAlchemy 2.0 Mapped style)
- Simple `social.py` cog with flat XP-per-message and cooldown
- `meta.py` cog with `/profile` and `/link-github`
- Streamlit dashboard with leaderboard, activity chart, quest management
- Docker Compose with db/bot/dashboard topology
- `config.yaml` loader

### Gaps vs. Design Documents

| Gap | Source Doc | Severity |
|-----|-----------|----------|
| No `zones`, `zone_channels`, `zone_multipliers` tables | 04 §4.3 | Critical |
| No `seasons` table | 04 §4.3 | Critical |
| No `user_stats` table (per-season counters) | 04 §4.3 | Critical |
| No `achievement_templates` / `user_achievements` tables | 04 §4.3 | Critical |
| No `admin_log` audit table | 04 §4.3 | Critical |
| No `user_preferences` table | 04 §4.3 | High |
| `activity_log` missing: season_id, zone_id, source_system, source_event_id, star_delta, metadata JSONB | 04 §4.3, §4.6 | Critical |
| `quests` missing: guild_id, gold_reward | 04 §4.3 | Medium |
| `ActionType` enum is P0-only; needs `InteractionType` per spec | 05 §5.2 | Critical |
| No `SynapseEvent` dataclass | 05 §5.2 | Critical |
| No Reward Engine pipeline (zone classify → multiply → quality → anti-gaming → cap) | 05 §5.4-5.8 | Critical |
| No `RewardResult` output structure | 05 §5.10 | Critical |
| No zone classification or multiplier lookup | 05 §5.4-5.5 | Critical |
| No quality modifiers for messages | 05 §5.6 | Critical |
| No anti-gaming checks (unique-reactor, per-user caps, diminishing returns) | 05 §5.7 | Critical |
| No reaction handling cog | 02 §2.4 | Critical |
| No voice tracking cog | 02 §2.4 | Critical |
| No admin bot commands (/award, /grant-achievement) | 06 §6.6 | High |
| No PG LISTEN/NOTIFY cache invalidation | 05 §5.12 | Critical |
| No shared service layer for admin mutations | 07 §7.9 | Critical |
| No idempotent event persistence (ON CONFLICT DO NOTHING) | 04 §4.3, D04-07 | Critical |
| No Discord OAuth for admin dashboard | 07 §7.8 | High |
| No Club Pulse public pages (achievement gallery, full leaderboard) | 07 §7.7 | High |
| No admin CRUD pages (zones, achievements, manual awards) | 07 §7.4-7.6 | High |
| No seed script for default zones/multipliers/achievements | 04 D04-01 | Medium |
| No tests | — | High |
| LLM quality assessment slot not present (deferred but needs stub) | 05 §5.9, D05-02 | Low |

---

## Decisions

### D-IMPL-01: Drop-and-Recreate Schema During Development
- **Date:** 2026-02-11
- **Topic:** Schema migration strategy
- **Decision:** Agreement with D04-03
- **Evidence:** 04 §4.5 specifies `Base.metadata.create_all()` for development
- **Consequences:** Existing P0 data in dev environments will be lost. Acceptable per spec.
- **Follow-up:** Alembic introduction deferred per D09-02

### D-IMPL-02: Expand ActivityLog In-Place Rather Than Create New Table
- **Date:** 2026-02-11
- **Topic:** ActivityLog evolution from P0 to P1
- **Decision:** Agreement — replace the P0 `ActionType` enum and `detail` column with the full P1 schema
- **Evidence:** 04 §4.3 and §4.6 specify the complete activity_log schema
- **Consequences:** P0 schema is effectively replaced. No migration needed (dev only).

### D-IMPL-03: Single config.yaml Seed File
- **Date:** 2026-02-11
- **Topic:** How to seed default zones, multipliers, and achievements
- **Decision:** Agreement with D04-01 — use a Python seed function that reads config.yaml for initial values
- **Evidence:** 04 D04-01, config.yaml is already the soft-config mechanism
- **Consequences:** Seed runs on first boot; production config is DB-driven via admin panel

### D-IMPL-04: Streamlit OAuth via streamlit-discord-auth or Manual Implementation
- **Date:** 2026-02-11
- **Topic:** Discord OAuth for Streamlit admin routes
- **Decision:** ~~Implement a lightweight Discord OAuth flow using requests + session state~~
- **Status:** Superseded by D-IMPL-05
- **Evidence:** 07 §7.8 required Discord OAuth session gate + role check
- **Consequences:** Replaced by FastAPI JWT auth in Milestone 2.

---

## Milestone 1 Completion — Full Implementation (2026-02-11)

### What Was Built

| Component | Files | Status |
|-----------|-------|--------|
| Database Models | `models.py` (12 tables, all indexes) | ✅ Complete |
| Reward Engine | `events.py`, `reward.py`, `achievements.py`, `cache.py` | ✅ Complete |
| Service Layer | `reward_service.py`, `admin_service.py`, `seed.py` | ✅ Complete |
| Bot Cogs | `social.py`, `reactions.py`, `voice.py`, `meta.py`, `admin.py` | ✅ Complete |
| Dashboard | `app.py` (Club Pulse + Admin) | ✅ Complete → Superseded by Milestone 2 |
| Tests | `test_reward_engine.py`, `test_achievements.py`, `test_anti_gaming.py`, `test_cache.py` | ✅ Complete |
| Config | `config.yaml`, `config.py`, `pyproject.toml` | ✅ Updated |
| Documentation | `README.md`, `IMPLEMENTATION_DECISIONS.md`, `REQUIREMENTS_TRACE.md` | ✅ Complete |

### All Initial Gaps — Resolved

Every gap from the initial analysis has been addressed:
- 12 database tables with all specified indexes and constraints
- Full SynapseEvent pipeline with 7-stage reward calculation
- PG LISTEN/NOTIFY cache invalidation (no Redis)
- Idempotent persistence with ON CONFLICT DO NOTHING
- Anti-gaming suite (self-reaction filter, unique-reactor weighting, diminishing returns)
- Discord OAuth admin auth with role check and 30/min rate limit
- Audit-logged admin mutations with before/after JSONB snapshots
- 11 seed achievements per §6.8
- Voice tracking with anti-idle
- Thread creation tracking

### Deferred Items (By Design)

| Item | Reason | Status |
|------|--------|--------|
| GitHub Neural Bridge | Requires webhook infrastructure (P2) | Stub column exists |
| LLM Quality Modifier | Deferred per D05-02 | Stub function in reward.py |
| Quests UI | Table exists, P2 feature | DB schema ready |
| Alembic Migrations | Dev uses create_all per D04-03 | Add before production |
| Custom Badge Images | Column exists, rendering deferred | badge_image_url in achievement_templates |
| DM Notifications | Preference column exists | Delivery mechanism deferred |

### Threat Scan

No blocking issues identified. Key risks:
1. **PG LISTEN/NOTIFY reliability** — The listener thread reconnects on failure but has no exponential backoff. Monitor in production.
2. **Voice tick accuracy** — 10-minute loop may drift slightly. Acceptable for engagement tracking (not billing).
3. **OAuth token expiry** — Session state doesn't refresh tokens. Users must re-authenticate after token expires (~7 days).

---

## Milestone 2 — SvelteKit + FastAPI Migration (2026-02-12)

### What Changed

The Streamlit dashboard was replaced entirely with a SvelteKit frontend and
FastAPI backend after a systematic evaluation identified Streamlit's production
limitations as blockers:

- No file-based routing (ghost navigation items, dead-end login page)
- No proper auth primitives (session state lost on refresh)
- No avatar/image support in sidebar
- Persistent Deploy button visible to all users
- Widget styling fights (CSS injection required)
- No JWT support (session-only auth)

### Decisions

### D-IMPL-05: FastAPI JWT Auth Replaces Streamlit OAuth
- **Date:** 2026-02-12
- **Topic:** Admin authentication architecture
- **Decision:** Discord OAuth2 code flow handled by FastAPI. JWT (HS256 via
  python-jose) issued on successful auth. SvelteKit stores in localStorage.
- **Evidence:** Supersedes D-IMPL-04. Required by SvelteKit frontend which
  cannot share Python session state.
- **Consequences:** Stateless auth. No server-side session store. Token
  refresh handled by re-login. JWT_SECRET env var required.

### D-IMPL-06: SvelteKit Replaces Streamlit
- **Date:** 2026-02-12
- **Topic:** Frontend framework choice
- **Decision:** SvelteKit 2 + Svelte 5 + Tailwind CSS 3.4 + Chart.js 4
- **Evidence:** Addresses all Streamlit limitations. File-based routing,
  full CSS control, avatar support, proper SPA behavior.
- **Consequences:** Separate Node.js build pipeline. `dashboard/` directory
  with its own package.json and Dockerfile. Requires Node.js 22.

### D-IMPL-07: Four-Service Docker Topology
- **Date:** 2026-02-12
- **Topic:** Runtime architecture
- **Decision:** `db`, `bot`, `api` (FastAPI :8000), `dashboard` (SvelteKit :3000)
- **Evidence:** SvelteKit cannot access PostgreSQL directly. API layer required.
- **Consequences:** Two Docker images (Python for bot+api, Node for dashboard).
  Dashboard depends on API service. Vite dev proxy handles /api during development.

### What Was Built

| Component | Files | Status |
|-----------|-------|--------|
| FastAPI Backend | `synapse/api/` (main, deps, auth, routes/public, routes/admin) | ✅ Complete |
| SvelteKit Frontend | `dashboard/` (~30 files: config, lib, components, pages) | ✅ Complete |
| Public Pages | Overview, Leaderboard, Activity (Chart.js), Achievements | ✅ Complete |
| Admin Pages | Zones, Achievements, Awards, Settings, Audit Log | ✅ Complete |
| Auth Flow | Discord OAuth → JWT → localStorage → Bearer header | ✅ Complete |
| Dashboard Dockerfile | Multi-stage Node.js 22 build | ✅ Complete |
| Docker Compose | Updated to 4 services | ✅ Complete |

### What Was Removed

| Component | Reason |
|-----------|--------|
| `synapse/dashboard/` | Entire Streamlit dashboard deleted |
| `.streamlit/` | Streamlit config directory deleted |
| `streamlit` dependency | Removed from pyproject.toml |
| `pandas` dependency | Removed (was only used by Streamlit) |
| `pandas-stubs` dev dependency | Removed |

### Threat Scan

1. **JWT secret rotation** — No built-in key rotation. Changing `JWT_SECRET` invalidates all active sessions. Acceptable for current scale.
2. **localStorage XSS risk** — JWT in localStorage is vulnerable to XSS. Mitigated by Content-Security-Policy headers (future) and no user-generated HTML rendering.
3. **Vite proxy in dev only** — The `/api` proxy only works in Vite dev mode. Production uses Docker networking (dashboard → api on shared bridge).

