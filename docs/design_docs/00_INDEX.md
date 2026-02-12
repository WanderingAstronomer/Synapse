# Synapse Design Documents — Index

> **Last Updated:** 2026-02-12
> **Version:** 3.0 (SvelteKit + FastAPI)

This directory contains all architectural decisions, design specifications,
and strategic direction for Project Synapse.  Each document covers a single
domain.  Read them in order for the full picture, or jump to the one you need.

---

## Document Map

| #  | Document | Domain | Summary |
|----|----------|--------|---------|
| 01 | [Vision & Philosophy](01_VISION.md) | Strategy | What Synapse is, who it serves, and the core principles that guide every decision. |
| 02 | [System Architecture](02_ARCHITECTURE.md) | Engineering | Four-service runtime (db, bot, api, dashboard), data flow, and service boundaries. |
| 03 | [Dual Economy Model](03_DUAL_ECONOMY.md) | Game Design | XP vs. Stars, progression vs. collection, and why we separate them. |
| 04 | [Database Schema](04_DATABASE_SCHEMA.md) | Data | Every table, column, relationship, and the reasoning behind the design. |
| 05 | [Reward Engine](05_REWARD_ENGINE.md) | Core Logic | Zones, multipliers, quality modifiers, LLM valuation, and the full calculation pipeline. |
| 06 | [Achievements System](06_ACHIEVEMENTS.md) | Game Design | Templates, custom awards, rarity tiers, and the admin workflow. |
| 07 | [Admin Panel & Web UI](07_ADMIN_PANEL.md) | Frontend | SvelteKit dashboard + FastAPI backend — zone management, achievement builder, manual awards, public analytics. |
| 08 | [Deployment & Infrastructure](08_DEPLOYMENT.md) | DevOps | Docker, Docker Compose, Azure resource plan, and CI/CD pipeline. |
| 09 | [Roadmap & Future Work](09_ROADMAP.md) | Planning | Phased delivery plan, stretch goals, and deferred decisions. |

---

## Superseded Documents

| Document | Status | Notes |
|----------|--------|-------|
| [SYNAPSE_DESIGN.md](SYNAPSE_DESIGN.md) | **Archived (v1.0)** | Original single-file TDD.  Superseded by this modular document set. |

---

## How to Read These Documents

- **Club Leads** should read **01 (Vision)**, **03 (Economy)**, and **06 (Achievements)**.
- **Developers** should read **02 (Architecture)**, **04 (Schema)**, and **05 (Reward Engine)**.
- **DevOps / Deployers** should read **08 (Deployment)**.
- **Everyone** should read **09 (Roadmap)** to know what's coming.

---

## Decision Log Convention

Each document contains a **Decisions** section at the bottom with entries formatted as:

> **Decision DXX-NN:** [Title]
> - **Status:** Accepted / Proposed / Deferred
> - **Context:** Why this came up.
> - **Choice:** What we decided.
> - **Consequences:** What this enables or constrains.

---

## v3.0 Amendment Notes

- **Frontend stack replaced:** Streamlit removed entirely; replaced by SvelteKit 2 + Svelte 5 + Tailwind CSS 3.4 + Chart.js 4.
- **API layer added:** FastAPI + uvicorn serves all REST endpoints; dashboard no longer accesses the database directly.
- **Four-service topology:** `db`, `bot`, `api` (port 8000), `dashboard` (port 3000). Supersedes D02-04 (three services).
- **Auth model replaced:** Streamlit OAuth session → Discord OAuth2 → FastAPI JWT (HS256 via python-jose). Supersedes D07-02, D07-04.
- **New env vars:** `JWT_SECRET`, `FRONTEND_URL`, updated `DISCORD_REDIRECT_URI`.
- **Dashboard Dockerfile:** Separate multi-stage Node.js 22 build for the SvelteKit frontend (adapter-node).
- **`discord_avatar_hash`** added to users table for CDN avatar URL construction.
- **`settings`** table added (key-value config stored in DB, managed via admin panel).
- `synapse/dashboard/` deleted; replaced by `synapse/api/` (FastAPI) + `dashboard/` (SvelteKit).
- Decisions D02-04, D07-02, D07-04 superseded. New decisions added for the stack migration.

## v2.2 Amendment Notes

- Added `admin_log` table for append-only audit trail on all config mutations.
- Added `user_preferences` table for per-user announcement opt-out.
- Added `guild_id` to `zones`, `seasons`, `achievement_templates`, `quests` and scoped unique constraints.
- Replaced free-text `detail` in `activity_log` with structured `metadata` JSONB column (§4.6).
- Added `source_system` and `source_event_id` to `activity_log` for idempotent insert.
- Introduced Star anti-gaming measures: unique-reactor weighting, per-user per-target caps, diminishing returns.
- Replaced 5-min TTL cache with PG LISTEN/NOTIFY for config cache invalidation.
- Hardened admin authorization model (OAuth session gate, role check, rate limit).
- Added announcement opt-out checks and channel throttle in achievement pipeline.
- Amended Principle 3 (Public Celebration) with opt-out clause.
- Promoted credibility items to P1/P2 roadmap.
- 17 new decisions added across 9 documents.

## v2.1 Amendment Notes

- Removed standalone API container from core runtime.
- Standardized Admin UX on Streamlit (no FastAPI/HTMX admin stack in current scope).
- Added season-aware economy direction for leaderboard fairness.
- *(Superseded by v3.0 — standalone API and SvelteKit frontend now in production.)*
