# Synapse Design Documents — Index

> **Last Updated:** 2026-02-12
> **Version:** 4.0 (Modular Community Platform)

This directory contains all architectural decisions, design specifications,
and strategic direction for Project Synapse.  Each document covers a single
domain.  Read them in order for the full picture, or jump to the one you need.

---

## Document Map

| #  | Document | Domain | Summary |
|----|----------|--------|---------|
| 01 | [Vision & Philosophy](01_VISION.md) | Strategy | Synapse as a modular community OS — deployable by any community, configurable for any use case. |
| 02 | [System Architecture](02_ARCHITECTURE.md) | Engineering | Four-service runtime, three-pillar data architecture (Event Lake → Ledger → Rules Engine), module system. |
| 03 | [Configurable Economy](03_CONFIGURABLE_ECONOMY.md) | Economy | Admin-defined currencies, wallets, append-only transaction ledger. Replaces hardcoded XP/Stars/Gold. |
| 03B | [Event Lake & Data Sources](03B_DATA_LAKE.md) | Data | Gateway event capture, retention policies, derived events. **[PENDING RESEARCH]** |
| 04 | [Database Schema](04_DATABASE_SCHEMA.md) | Data | Every table, column, relationship, and the reasoning behind the design. *(v4.0 revision pending)* |
| 05 | [Rules Engine](05_RULES_ENGINE.md) | Core Logic | Configurable trigger/condition/effect rules. Replaces hardcoded Reward Engine pipeline. |
| 06 | [Milestones](06_MILESTONES.md) | Recognition | Requirement expressions against wallets + Event Lake. Replaces hardcoded Achievement system. |
| 07 | [Admin Panel & Web UI](07_ADMIN_PANEL.md) | Frontend | SvelteKit dashboard — rule builder, currency management, module toggles, taxonomy editor. *(v4.0 revision pending)* |
| 08 | [Deployment & Infrastructure](08_DEPLOYMENT.md) | DevOps | Docker, Docker Compose, Azure resource plan, and CI/CD pipeline. |
| 09 | [Roadmap](09_ROADMAP.md) | Planning | P0–P3.5 complete. P4 (Event Lake) → P5 (Ledger) → P6 (Rules Engine) → P7–P10. |

---

## How to Read These Documents

- **Community Operators** should read **01 (Vision)**, **03 (Economy)**, and **06 (Milestones)**.
- **Developers** should read **02 (Architecture)**, **04 (Schema)**, and **05 (Rules Engine)**.
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

## Version History

### v4.0 — Modular Community Platform

- **Vision pivot:** From "gamified student club framework" to "modular community operating system."
- **Three pillars added:** Event Lake (data capture), Ledger (configurable currencies), Rules Engine (configurable logic).
- **Module system:** Toggleable feature groups (Economy, Milestones, Analytics, Announcements, Seasons).
- **Taxonomy system:** Admin-configurable labels for all internal terms.
- **Preset system:** Bundled rule sets for zero-config start (Classic Gamification, Analytics Only, Minimal Engagement).
- **Documents rewritten:** 01_VISION, 03_CONFIGURABLE_ECONOMY (new), 05_RULES_ENGINE (new), 06_MILESTONES (new), 09_ROADMAP.
- **Documents revised:** 02_ARCHITECTURE.
- **Documents pending revision:** 04_DATABASE_SCHEMA, 07_ADMIN_PANEL, 08_DEPLOYMENT.
- **New document:** 03B_DATA_LAKE (stub, pending research results).

### v3.0 — SvelteKit + FastAPI

- Frontend stack replaced: Streamlit → SvelteKit 2 + Svelte 5 + Tailwind CSS 3.4 + Chart.js 4.
- API layer added: FastAPI + uvicorn serves all REST endpoints.
- Four-service topology: `db`, `bot`, `api` (port 8000), `dashboard` (port 3000).
- Auth model replaced: Streamlit OAuth session → Discord OAuth2 → FastAPI JWT.

### v2.2

- Added admin_log, user_preferences, guild_id scoping, structured metadata JSONB.
- Star anti-gaming measures, PG LISTEN/NOTIFY cache, announcement opt-out.
- 17 new decisions added across 9 documents.

### v2.1

- Removed standalone API container. Standardized on Streamlit. *(Superseded by v3.0.)*
