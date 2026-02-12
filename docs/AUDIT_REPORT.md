# Synapse Repository Audit Report

**Auditor:** GitHub Copilot (Claude Opus 4.6)  
**Date:** 2026-02-12  
**Repository:** WanderingAstronomer/Synapse  
**Branch:** main  

---

## Table of Contents

1. [Audit Methodology](#audit-methodology)
2. [Phase 1: High-Level Orientation](#phase-1-high-level-orientation)
3. [Phase 2: Architecture & Design Docs](#phase-2-architecture--design-documentation)
4. [Phase 3: Database & Data Layer](#phase-3-database--data-layer)
5. [Phase 4: Core Engine](#phase-4-core-engine)
6. [Phase 5: Services Layer](#phase-5-services-layer)
7. [Phase 6: Bot Layer](#phase-6-bot-layer)
8. [Phase 7: API Layer & Auth](#phase-7-api-layer--authentication)
9. [Phase 8: Security Audit](#phase-8-security-audit)
10. [Phase 9: Testing Audit](#phase-9-testing-audit)
11. [Phase 10: Infrastructure & Deployment](#phase-10-infrastructure--deployment)
12. [Phase 11: Dependencies & Supply Chain](#phase-11-dependencies--supply-chain)
13. [Phase 12: Code Quality & Linting](#phase-12-code-quality--linting)
14. [Consolidated Findings Table](#consolidated-findings-table)
15. [Final Synthesis & Recommendations](#final-synthesis--recommendations)

---

## Audit Methodology

This audit proceeded layer-by-layer through the codebase, from outer metadata inward to core logic. Each section was written as findings emerged — not retroactively — to provide an honest trace of the discovery process.

**Approach:**
1. Read project metadata (pyproject.toml, README, config.yaml, CHANGELOG) to understand purpose, stack, and maturity.
2. Review design documentation to understand intended architecture and identify spec-vs-code drift.
3. Read all database models, engine, and migration code.
4. Read all core engine modules (events, reward pipeline, anti-gaming, quality, cache).
5. Read all service-layer modules (reward_service, admin_service, setup_service, announcement_service, event_lake_writer).
6. Read bot core, entrypoint, and sample cogs (social, reactions).
7. Read API layer (FastAPI app, auth, routes, dependency injection).
8. Perform targeted security analysis (secrets, SQL injection, auth flows, CORS, rate limiting).
9. Run full test suite, analyze coverage scope and quality.
10. Review Docker infrastructure, deployment configuration.
11. Audit dependencies for known issues and supply chain concerns.
12. Run ruff linter to assess code quality.

**Tools used:** File reading, grep search, terminal commands (pytest, ruff, wc), file listing.

**Codebase size:**
- Python source: ~5,200 lines across 30+ modules
- Test code: ~2,444 lines across 8 test files
- Test-to-source ratio: ~47% (very good)

---

## Phase 1: High-Level Orientation

### What Is This Project?

**Synapse** is a modular community engagement platform for Discord. It captures Discord events (messages, reactions, voice activity), applies a gamification economy (XP, Stars, Gold), tracks achievements, and surfaces analytics through a SvelteKit dashboard.

### Stack Summary

| Layer | Technology |
|-------|-----------|
| Bot | discord.py 2.6+, Python 3.12+ |
| Database | PostgreSQL 16 (JSONB, LISTEN/NOTIFY, partial indexes) |
| ORM | SQLAlchemy 2.0 (Mapped[] annotations) |
| API | FastAPI + uvicorn |
| Frontend | SvelteKit 2, Svelte 5, Tailwind CSS 3.4, Chart.js 4 |
| Auth | Discord OAuth2 → JWT (HS256, python-jose) |
| Package Mgmt | uv (Python), npm (Node) |
| Deployment | Docker Compose (4 services) |

### Architecture

Four Docker Compose services: `db` (PostgreSQL), `bot` (discord.py), `api` (FastAPI), `dashboard` (SvelteKit).

### Maturity Assessment

- **Version:** 0.1.0 (pyproject.toml), but CHANGELOG declares 1.0.0
- **Development stage:** Active — has an [Unreleased] section describing a "Seedless Bootstrap" migration (Milestone 4.1)
- **Documentation quality:** Excellent — comprehensive README with architecture diagrams, 9 design docs, implementation decisions log, requirements trace, detailed changelog

### Configuration Philosophy

Infrastructure config in `config.yaml` (community name, guild ID, admin role). All gameplay tuning (XP curves, multipliers, anti-gaming thresholds) stored in the database `settings` table, editable from the admin dashboard. This is a **good separation of concerns**.

---

## Phase 2: Architecture & Design Documentation

### Assessment

The project has an **unusually thorough** design documentation suite for a solo-developer project:

- **00_INDEX.md** — Document map with audience guidance
- **01_VISION.md** — Strategic vision and philosophy
- **02_ARCHITECTURE.md** — Four-service topology, three-pillar data architecture
- **03_CONFIGURABLE_ECONOMY.md** — Currency system design
- **03B_DATA_LAKE.md** — Event Lake capture strategy
- **04_DATABASE_SCHEMA.md** — Complete ERD with design principles
- **05_RULES_ENGINE.md** — Configurable trigger/condition/effect rules
- **06_MILESTONES.md** — Achievement system
- **07_ADMIN_PANEL.md** — Dashboard design
- **08_DEPLOYMENT.md** — Infrastructure plan
- **09_ROADMAP.md** — Phased delivery plan (P0–P10)

Additionally: `IMPLEMENTATION_DECISIONS.md` (381 lines, 11+ decisions with rationale) and `REQUIREMENTS_TRACE.md`.

### Spec-vs-Code Alignment

The IMPLEMENTATION_DECISIONS.md shows a disciplined approach to tracking design drift:
- Decisions are dated, referenced to specific design doc sections
- Superseded decisions are marked (e.g., D-IMPL-03 superseded by D-IMPL-08)
- Gap analysis was performed systematically and all gaps resolved

**v4.0 architecture** (Event Lake, Ledger, Rules Engine) is thoroughly documented in design docs but only partially implemented — the Event Lake (P4) is built; Ledger (P5) and Rules Engine (P6) are planned. This is clearly communicated in both docs and README.

---

## Phase 3: Database & Data Layer

### Models (`synapse/database/models.py` — 534 lines)

**14 tables total** (docs say 12, but EventLake + EventCounter were added in P4):
1. `users` — Discord snowflake PK (good: no surrogate key overhead)
2. `user_stats` — Per-season counters (composite PK: user_id + season_id)
3. `seasons` — Competitive windows with unique constraint on (guild_id, name)
4. `activity_log` — Append-only event journal with partial unique index for idempotency
5. `zones` — Channel groupings with soft-delete (`active` flag)
6. `zone_channels` — Zone ↔ channel mapping
7. `zone_multipliers` — Per-zone, per-event-type XP/Star weights
8. `achievement_templates` — Admin-defined recognition with rarity system
9. `user_achievements` — Earned badges
10. `quests` — Gamified tasks (table exists, UI deferred)
11. `admin_log` — Append-only audit trail with JSONB snapshots
12. `user_preferences` — Notification opt-outs
13. `settings` — Key-value config store (all gameplay tuning)
14. `event_lake` — Append-only gateway event capture (P4)
15. `event_counters` — Pre-computed aggregation cache (P4)

### Strengths
- **Idempotent insert pattern**: Partial unique index on `(source_system, source_event_id) WHERE source_event_id IS NOT NULL` — elegant.
- **Comprehensive indexing**: Timestamp-ordered indexes for time-series queries, composite indexes for leaderboards.
- **JSONB usage**: Appropriate for flexible `metadata` and audit `before_snapshot`/`after_snapshot` fields.
- **SQLAlchemy 2.0 style**: Modern `Mapped[]` annotations throughout.

### Engine (`synapse/database/engine.py` — 162 lines)

The "Synapse Bridge Pattern" (`run_db` → `asyncio.to_thread`) is a pragmatic solution for using synchronous psycopg2 from async discord.py contexts. The docstring explains this trade-off clearly.

- `pool_size=5, max_overflow=10, pool_pre_ping=True` — reasonable for a community bot.
- Context manager `get_session()` with auto-commit/rollback — clean pattern.

### Migration Strategy

- Primary approach: `Base.metadata.create_all()` on every startup (dev-friendly but risky for production schema changes).
- Alembic is set up with one migration (`99b1d42a3d9c`) for the Event Lake tables, confirming it's available when needed.
- **Risk**: Running `create_all()` in production could silently miss column additions/renames. The project acknowledges this and defers Alembic-first strategy.

---

## Phase 4: Core Engine

### Events (`synapse/engine/events.py`)
Clean `SynapseEvent` frozen dataclass as the universal event envelope. Base XP/Stars defined per interaction type — straightforward and maintainable.

### Reward Pipeline (`synapse/engine/reward.py` — 162 lines)
The pipeline is **pure** (no DB/Discord I/O) — a significant architectural win for testability:

```
SynapseEvent → Zone Classify → Multiplier Lookup → Quality Modifier → Anti-Gaming → XP Caps → Level-Up Check → RewardResult
```

All tuning parameters read from `ConfigCache` (database-backed). The pipeline is well-documented with design doc section references.

### Quality Modifiers (`synapse/engine/quality.py`)
Multiplicative quality modifier for messages based on:
- Message length (tiered: medium/long bonuses)
- Code blocks, links, attachments (individual multipliers)
- Emoji spam penalty
- Floor at 0.1 to prevent zero-XP

All thresholds configurable via `ConfigCache` with sensible defaults. **LLM quality modifier** is a placeholder stub returning 1.0 — honestly documented as deferred.

### Anti-Gaming (`synapse/engine/anti_gaming.py` — 159 lines)
Solid suite of anti-farming measures:
- Self-reaction filter (zero stars)
- Per-user per-target reaction cap (3/day default, sliding 24h window)
- Diminishing returns formula: `1 / (1 + count)`
- Reaction velocity cap (>10 unique reactors on <5min message → max 5 XP)
- Thread-safe `AntiGamingTracker` with periodic cleanup

### Cache (`synapse/engine/cache.py` — 287 lines)
In-memory config cache with PG LISTEN/NOTIFY invalidation:
- Thread-safe reads (locks on all `get_*` methods)
- Typed setting accessors (`get_int`, `get_float`, `get_bool`, `get_str`)
- Background listener thread with raw psycopg2 connection

**Concern**: The LISTEN thread has no reconnection logic or exponential backoff — if the connection drops, the thread dies silently and the cache becomes stale. This is acknowledged in the Threat Scan section of IMPLEMENTATION_DECISIONS.md.

---

## Phase 5: Services Layer

### reward_service.py (346 lines)
Handles the full event→persist→reward→achievement flow:
- `process_event()` — orchestrates calculation, idempotent insert (SAVEPOINT + IntegrityError), user/stat updates, achievement checks.
- `award_manual()` — admin awards with activity log.
- `grant_achievement()` — manual achievement granting with duplicate check.

Uses nested transactions (SAVEPOINT) for idempotent inserts — correct approach for partial unique indexes.

### admin_service.py (393 lines)
Follows a consistent audit pattern: before-snapshot → mutation → after-snapshot → NOTIFY. Every admin write is logged to `admin_log`.

### setup_service.py (425 lines)
First-run bootstrap that reads live guild snapshot (written by bot) and auto-creates zones, channels, season, and settings. Idempotent re-runs documented and tested.

### announcement_service.py + throttle.py
Unified announcement routing with:
- Per-user preference gating
- Multi-fallback channel resolution (per-template → synapse-achievements → global config → event channel)
- Sliding-window throttle (3 embeds/channel/minute) with async overflow queue

### event_lake_writer.py (527 lines)
Largest service module. Handles:
- Event Lake writes with idempotency (source_id unique index)
- Counter updates (transactional with inserts)
- Voice session tracking (in-memory state machine for join/leave/move derivation)
- Privacy-safe message metadata extraction (content never persisted)
- Per-event-type enable/disable from settings

---

## Phase 6: Bot Layer

### Core (`synapse/bot/core.py` — 327 lines)
`SynapseBot` subclass of `commands.Bot`:
- 8 cog modules loaded in `setup_hook()`
- `on_ready`: slash command sync, achievements channel auto-creation, guild channel discovery, AFK channel detection, announcement throttle startup
- Intent configuration is explicit and documented (MESSAGE_CONTENT + MEMBERS privileged; PRESENCES disabled)

### Cogs
- **social.py** (175 lines) — Message XP/Star pipeline with per-user-per-channel cooldown
- **reactions.py** (200 lines) — Reaction processing for both GIVEN and RECEIVED events
- **voice.py** — Voice channel tracking
- **threads.py** — Thread creation tracking
- **membership.py** — Join/leave event capture
- **meta.py** — User-facing commands (/profile, /leaderboard, /preferences)
- **admin.py** — Admin commands (/award, /create-achievement, /grant-achievement, /season)
- **tasks.py** — Periodic tasks (retention, reconciliation)

All cogs properly wrap handler logic in try/except to prevent one event failure from crashing the bot.

---

## Phase 7: API Layer & Authentication

### FastAPI App (`synapse/api/main.py`)
- CORS configured for localhost:5173 (Vite dev) + localhost:3000 (production) + dashboard:3000 (Docker)
- 4 routers mounted: auth, public, admin, event_lake
- Health endpoint at `/api/health`

### Auth (`synapse/api/auth.py` — 139 lines)
Discord OAuth2 → JWT flow:
1. `/auth/login` → Discord consent screen (with CSRF state parameter)
2. `/auth/callback` → code exchange → user/member lookup → admin role check → JWT issuance
3. JWT contains: sub (user ID), username, avatar, is_admin, exp (12h)

**State store**: In-memory dict with 10-min cleanup — acceptable for single instance but won't work with multiple API replicas.

### Dependency Injection (`synapse/api/deps.py`)
- `get_engine()` and `get_config()` use `@lru_cache(maxsize=1)` — singletons
- `get_current_admin()` validates JWT, checks `is_admin` claim

### Admin Routes (`synapse/api/routes/admin.py` — 484 lines)
Full CRUD for zones, achievements, settings, awards, with Pydantic request validation.

### Public Routes (`synapse/api/routes/public.py` — 308 lines)
Read-only endpoints: metrics, leaderboard (paginated, multi-currency), daily activity, achievements, user profile, settings.

---

## Phase 8: Security Audit

### Secrets Management ✅
- `.env` is gitignored — confirmed
- `.env.example` provides template with placeholder values
- `DISCORD_TOKEN` check at startup with clear error message
- `DATABASE_URL` check with RuntimeError on missing

### JWT Security ⚠️
- **Default secret in code**: `JWT_SECRET = os.getenv("JWT_SECRET", "synapse-dev-secret-change-me")` — the fallback is a weak default. In production, if the env var is unset, JWTs are signed with a known secret.
- **Algorithm**: HS256 — adequate for single-issuer scenarios.
- **Expiry**: 12 hours — reasonable.
- **No refresh token mechanism** — users must re-authenticate after token expires.

### SQL Injection ✅ (mostly)
- All queries use SQLAlchemy ORM or parameterized `select()` statements.
- **One concern**: `send_notify()` in `cache.py` uses `text(f"NOTIFY {NOTIFY_CHANNEL}, '{table_name}'")`. The `NOTIFY_CHANNEL` is a module constant, but `table_name` comes from the service layer (`admin_service.py`). Since `table_name` is always a hardcoded string literal at every call site (e.g., `"zones"`, `"settings"`), this is **safe in practice** but **vulnerable by design** — if a future developer passes user input to `send_notify()`, it would be injectable. Recommendation: validate `table_name` against an allowlist.

### CORS ✅
- Restricted to known origins (localhost:5173, localhost:3000, dashboard:3000).
- For production, these should be replaced with actual domain names.

### Rate Limiting ❌
- **README claims** "Rate limited: 30 mutations/minute per admin session."
- **No such rate limiting exists in the API code.** There is no rate-limiting middleware on admin endpoints. The only throttling in the entire codebase is the announcement throttle (3 embeds/channel/minute) which is a Discord message rate, not an API rate limit.
- The announcement throttle is well-implemented (sliding window + async overflow queue).

### OAuth State Management ✅
- CSRF state parameter generated with `secrets.token_urlsafe(32)` and verified on callback.
- Stale states cleaned up after 10 minutes.
- Single-instance limitation documented.

### Input Validation ✅
- Pydantic models for all admin request bodies.
- Query parameter validation with `ge`/`le` bounds.
- Discord snowflakes used as primary keys (no user-controlled string PKs).

---

## Phase 9: Testing Audit

### Test Suite Results
```
144 tests passed in 2.87s (0 failures)
```

### Coverage by Module

| Test File | Lines | What It Tests |
|-----------|-------|--------------|
| test_reward_engine.py | 264 | Base values, quality modifiers, anti-gaming, full pipeline |
| test_achievements.py | 160 | Achievement check logic (all 4 trigger types) |
| test_anti_gaming.py | 131 | Self-reaction, pair caps, diminishing returns, velocity |
| test_cache.py | 86 | NOTIFY-handler routing |
| test_announcements.py | 447 | Throttle, channel resolution, embeds, preference gating |
| test_bootstrap.py | 410 | Guild snapshot, bootstrap wizard, idempotency, edge cases |
| test_event_lake.py | 489 | Event Lake writer, voice sessions, counter updates |
| test_event_lake_services.py | 451 | Retention, reconciliation, backfill, API auth guards |

### Strengths
- Tests are **unit-focused** — the engine and service layers are tested without a running database (mocks used appropriately).
- Bootstrap tests use an in-memory SQLite database for integration testing.
- Event Lake API tests verify all admin endpoints require authentication.
- Good edge-case coverage (corrupt JSON, duplicate events, empty guilds).

### Gaps
- **No API integration tests** — the FastAPI routes are not tested end-to-end (no `TestClient` usage for public/admin routes).
- **No bot cog tests** — the Discord bot layer has zero test coverage.
- **No reward_service tests** — the critical `process_event()` flow is untested.
- **No admin_service tests** — audit-logged mutations are untested.
- **No config.py tests** — YAML loading/error handling untested.
- **conftest.py is nearly empty** (6 lines) — no shared fixtures for DB-backed tests.

---

## Phase 10: Infrastructure & Deployment

### Docker Compose (4-service mode)
- PostgreSQL 16-alpine with health checks — good.
- Bot, API, and Dashboard are separate containers with proper `depends_on`.
- `develop.watch` configured for hot-reload during development.
- DB credentials hardcoded as `synapse:synapse` in compose file — acceptable for local dev; production should use secrets.

### Docker Compose (single-container mode)
- All-in-one container with `dumb-init` — good practice for signal handling.
- Dashboard built inside container (`npm ci && npm run build`).
- Uses `docker/start-all.sh` as entrypoint.

### Dockerfile (multi-stage)
- Builder stage with uv + cache mounts for fast rebuilds.
- Runtime stage copies only `.venv` — minimal attack surface.
- UV Python interpreter symlink correctly preserved.

### Missing
- **No CI/CD pipeline** — no GitHub Actions, no automated testing on push.
- **No production deployment docs** beyond Docker Compose — no Kubernetes, no cloud deploy scripts.
- **No health checks** for bot, api, or dashboard services (only DB has a healthcheck).

---

## Phase 11: Dependencies & Supply Chain

### Python Dependencies (production)
| Package | Version | Purpose | Notes |
|---------|---------|---------|-------|
| discord-py | >=2.6.4 | Discord bot framework | Active, well-maintained |
| psycopg2-binary | >=2.9.11 | PostgreSQL adapter | Binary wheel — fine for Docker |
| python-dotenv | >=1.2.1 | .env file loading | Standard |
| pyyaml | >=6.0.3 | YAML config parsing | Standard |
| requests | >=2.32.0 | HTTP client | Potentially unused (httpx used for async) |
| sqlalchemy | >=2.0.46 | ORM | Modern version |
| fastapi | >=0.115.0 | REST framework | Standard |
| uvicorn[standard] | >=0.34.0 | ASGI server | Standard |
| python-jose[cryptography] | >=3.3.0 | JWT handling | ⚠️ python-jose is **unmaintained** |
| httpx | >=0.28.0 | Async HTTP client | Used for Discord OAuth |
| alembic | >=1.18.4 | Database migrations | Standard |

### Concerns
- **python-jose**: This package has been effectively abandoned. The recommended replacement is [PyJWT](https://pyjwt.readthedocs.io/) or [joserfc](https://github.com/authlib/joserfc). There have been known security advisories.
- **requests**: Appears to be unused — httpx is used for all async HTTP. May be a leftover dependency.
- **Lock file**: `uv.lock` exists — good for reproducible builds.

### Dev Dependencies
pytest, ruff, mypy, type stubs — all appropriate. No unnecessary packages.

---

## Phase 12: Code Quality & Linting

### Ruff Results
```
21 errors total:
- 16x E501 (line too long) — all in event_lake.py and setup_service.py
-  4x F401 (unused imports) — auto-fixable
-  1x N806 (uppercase variable in function)
```

### Assessment
- **Very clean overall** — 21 lint issues in 5,200 lines is excellent.
- All E501 violations are in data structure literals (table definitions) — cosmetic.
- The 4 unused imports are leftover from refactoring — trivially fixable.
- No complexity warnings, no security-flagged patterns.

### Documentation Quality
- Every module has a docstring explaining purpose and design rationale.
- Functions have docstrings with parameter descriptions.
- Design doc references (e.g., "§5.7.2") are sprinkled throughout — excellent traceability.
- Only 1 TODO in the entire codebase.

---

## Consolidated Findings Table

| ID | Severity | Category | Finding |
|----|----------|----------|---------|
| F-001 | Low | Versioning | pyproject.toml and `__init__.py` say `0.1.0`, CHANGELOG says `1.0.0` — reconcile |
| F-002 | Info | Docs | `__init__.py` docstring references deleted `seed.py` |
| F-003 | **Medium** | Security | `JWT_SECRET` has a hardcoded fallback default (`synapse-dev-secret-change-me`) — if env var is unset in production, JWTs are signed with a known secret |
| F-004 | **High** | Security | API rate limiting is **not implemented** despite being claimed in README ("30 mutations/minute per admin session"). Admin endpoints are completely unthrottled. |
| F-005 | Medium | Security | `send_notify(table_name)` uses f-string interpolation into SQL. Currently safe (all call sites use string literals) but is injection-vulnerable by design. Add allowlist validation. |
| F-006 | Medium | Reliability | PG LISTEN/NOTIFY thread has no reconnection logic. If the DB connection drops, the cache becomes permanently stale until bot restart. |
| F-007 | Low | Dependency | `python-jose` is unmaintained. Replace with `PyJWT` or `joserfc`. |
| F-008 | Low | Dependency | `requests` appears unused (httpx used for async HTTP). Consider removing. |
| F-009 | Medium | Testing | No integration tests for FastAPI routes, no bot cog tests, no reward_service tests. Critical flow paths are untested at the integration level. |
| F-010 | Medium | Testing | conftest.py is nearly empty — no shared DB fixtures for service-level testing. |
| F-011 | Low | Infrastructure | No CI/CD pipeline (no GitHub Actions, no automated testing on push). |
| F-012 | Low | Infrastructure | No health checks for bot, API, or dashboard Docker services. |
| F-013 | Info | Code Quality | 4 unused imports and 16 line-length violations (ruff). Trivially fixable. |
| F-014 | Low | Deployment | CORS origins hardcoded to localhost — must be updated for production. |
| F-015 | Info | Architecture | OAuth state stored in-memory — won't work with multiple API replicas. Documented but worth noting. |
| F-016 | Low | Docs | Design docs reference 12 tables, code has 15 (EventLake, EventCounter, Setting added later). Update docs. |
| F-017 | Info | Migration | Reliance on `create_all()` for schema management. Alembic is set up but not used as default strategy. |

---

## Final Synthesis & Recommendations

### Overall Assessment: **Strong project with good fundamentals**

This is a well-architected Discord community platform with an impressive documentation culture. The codebase demonstrates clear separation of concerns, modern Python patterns (dataclasses, type hints, SQLAlchemy 2.0), and thoughtful design decisions backed by written rationale.

### What's Done Well
1. **Documentation** — Among the best-documented solo projects I've encountered. Design docs, implementation decisions, requirements tracing, and a detailed changelog provide excellent context.
2. **Architecture** — Clean four-service topology, pure reward engine (no I/O in calculation), PG LISTEN/NOTIFY for cache invalidation (avoiding Redis dependency).
3. **Idempotency** — Event deduplication via partial unique indexes and SAVEPOINT handling is correctly implemented.
4. **Anti-gaming** — Thoughtful suite of measures against XP/Star farming with configurable thresholds.
5. **Audit trail** — Every admin mutation is logged with before/after JSONB snapshots.
6. **Privacy** — Message content is explicitly never persisted; only numerical metadata is stored.
7. **Type safety** — Frozen dataclasses, Mapped[] annotations, Pydantic request models.

### Priority Recommendations

**Must Fix (before any production deployment):**
1. **F-003**: Remove the hardcoded JWT_SECRET fallback or add a startup check that refuses to start with the default value.
2. **F-004**: Implement the claimed rate limiting on admin API endpoints, or remove the claim from the README.

**Should Fix (high impact, moderate effort):**
3. **F-006**: Add reconnection logic with exponential backoff to the PG LISTEN thread.
4. **F-007**: Replace `python-jose` with `PyJWT` (minimal API change, maintained package).
5. **F-009**: Add FastAPI `TestClient` integration tests for critical admin and public endpoints.
6. **F-005**: Add an allowlist check in `send_notify()` to prevent future injection risk.

**Nice to Have:**
7. **F-011**: Set up GitHub Actions for CI (pytest + ruff on push/PR).
8. **F-012**: Add health checks to bot/api/dashboard Docker services.
9. **F-001**: Reconcile version numbers across pyproject.toml, `__init__.py`, and CHANGELOG.
10. **F-013**: Run `ruff check --fix` to auto-clean unused imports.

### Risk Summary

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|-----------|
| JWT signed with default secret in prod | Medium | Critical | Startup validation |
| Admin API abuse (no rate limit) | Low | High | Middleware implementation |
| Cache goes stale (LISTEN thread dies) | Low | Medium | Reconnection logic |
| python-jose vulnerability | Low | Medium | Package replacement |

### Final Verdict

The project is **well-designed and well-implemented** for its current stage (v1.0/Milestone 4.1). The primary risks are in the security and operational reliability categories, not in architectural or code quality. The v4.0 vision (Event Lake → Ledger → Rules Engine) is clearly articulated and the first pillar (Event Lake) is already built. With the security fixes above addressed, this would be a solid production-grade deployment for a small-to-medium Discord community.
