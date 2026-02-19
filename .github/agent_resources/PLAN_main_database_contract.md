# Planning: Main Database Contract (Single-Guild Engagement Loop)

> **Created:** 2026-02-19
> **Status:** Active Reference (Schema decisions committed; sequencing governed by MASTER_ROLLOUT_PLAN.md)
> **Purpose:** Define exactly what data belongs in the main PostgreSQL database for the capture-first gamification feedback loop.
> **Scope Lock:** Single guild only.

---

## 1. Mission Alignment

Main DB exists to power a closed-loop engagement system:

1. Capture member interactions (observed telemetry).
2. Evaluate deterministic reward/anti-gaming rules.
3. Materialize derived projections (xp, gold, levels, achievements, leaderboards).
4. Explain outcomes to admins and members.
5. Repeat with audited, versioned policy updates.

This is not a generic analytics warehouse and not a multi-tenant control plane.

---

## 2. Single-Guild Boundary (Hard Constraint)

- Exactly one guild is managed by a deployment.
- `guild_id` is still stored for integrity and future-proofing, but never used to serve multiple guilds in this cycle.
- No multi-guild dashboards, no cross-guild ranking, no RLS rollout for tenant separation.

---

## 3. Main DB Data Domains (What Goes In)

### A) Observed Telemetry (Immutable Source)

Core tables:
- `event_lake` (existing, to be evolved into canonical envelope contract)
- `event_counters` (existing hot-path counter cache)

Required invariants:
- Append-only event writes.
- Idempotent ingest via stable source key + unique partial index.
- Metadata-first payload policy (no raw content persistence by default).

Planned envelope minimum fields:
- Event identity: `id`, stable source id (`source_id` or deterministic equivalent), `event_type`, `timestamp`
- Actor/context: `user_id`, `channel_id`, `target_id`, `guild_id`
- Typed payload: structured JSONB for event-specific metadata and rule predicates
- Provenance: source category (`GATEWAY`/`REST`/`SYNTHETIC`) added as envelope evolution step

### B) Derived Economy Projections (Mutable Read Models)

Core tables:
- `users`
- `user_stats`
- `activity_log`
- `user_achievements`

Expected behavior:
- Recomputable from telemetry + rule snapshots.
- Optimized for leaderboard/profile/UI reads.
- Historical audit retained for reward-affecting deltas.

### C) Rule/Config/Audit Control Plane (The "Firewall")

Core tables:
- `reward_rules` (Predicates + Outcomes with support for non-linear math)
- `settings`
- `channel_type_defaults`
- `channel_overrides`
- `admin_log`
- `admin_rate_limit_events`

Planned additions:
- **Versioned rule snapshots:** for publish/rollback lifecycle.
- **Rule evaluation trace:** linking event -> matched rules -> applied outcomes (for "Why was I rewarded?" explainability).

Expected behavior:
- Rules support atomic predicates (e.g., `payload.length >= 10`) and contextual predicates (e.g., `context.messages_today < 100`).
- Mathematical outcomes support scaling curves (Linear, Logarithmic, Exponential, Step).

### D) Achievement & UX Configuration ("Content Crates")

Core tables:
- `achievements` (Identity: Name, Icon, Description)
- `rarities` (Visuals: Color, Frame, Priority)
- `categories` (Grouping: Social, Voice, etc.)
- `seasons` (Timing: Start/End dates)
- `svg_overlays` (Decorative frames/borders, composited over icons at render time)
- `media_files` (Evolving — add folder support)
- `media_folders` (NEW — organizes media into navigable directories)
- `page_layouts`
- `card_configs`
- `channels`

Role in mission:
- Strictly presentation and identity.
- **Logic Free:** These tables define *what* an achievement is, not *how* to get it.
- **Composable:** Admins mix-and-match Rarity, Season, Category, and SVG Overlay to create content.

### F) Marketplace & User Economy

Core tables:
- `marketplace_items` — Admin-configurable shop items. Pricing is flexible: `cost_xp` and/or `cost_gold`, both nullable; form at item creation defines which currencies apply.
- `user_inventory` — One-way purchase records. Tracks ownership, equipped state, and optional `expires_at` for seasonal items.

Item types supported:
- `COSMETIC_BADGE` — Dashboard-only badge displayed on leaderboards/profiles.
- `CUSTOM_ROLE_COLOR` — References a manually-created Discord role (`discord_role_id`). Bot auto-assigns on purchase.
- `PROFILE_THEME` — Dashboard accent colors/backgrounds.
- `TITLE` — Custom subtitle displayed under username.

Behavior contract:
- Purchases are **one-way** (no refunds, no trading, no gifting).
- Role assignment is **automatic** on purchase via bot (`manage_roles` permission confirmed).
- If role assignment fails, the inventory record is preserved; failure is logged for admin resolution.
- **Seasonal items**: Optional `expires_at` or `season_id` causes an item to expire automatically.
- SVG overlays can be attached to any item for decorative borders/frames.
- Currency rules: `cost_xp` and `cost_gold` are each optional. If both are set, user chooses at purchase time. At least one must be non-null.
- Currency naming: DB/API fields remain canonical (`xp`, `gold`); admin-configurable labels are presentation-only.
- Marketplace scope is cosmetic-only: no channel access locks, no permission grants, no moderation capability is purchasable.

### E) User Identity & Auth State

Core tables:
- `user_profiles` — Display data: `discord_id`, `username`, `avatar_url`, `left_at`, `last_seen`.
- `user_guild_roles` — Synced role membership: `user_id`, `role_id`, `synced_at`.
- `oauth_states` — CSRF-safe OAuth state tokens.
- `user_preferences` — Per-user notification and display preferences.

Role in mission:
- Decouples the dashboard from real-time Discord API calls.
- Powers three-tier access control (Guest / Member / Admin).
- Retains anonymized profiles for members who have left the guild.

Behavior contract:
- Bot syncs `user_profiles` on `on_message`, `on_member_join`, `on_member_remove`.
- On `on_member_remove`: set `avatar_url = NULL`, `username = "Former Member"`, record `left_at`.
- JWT payload is populated from `user_profiles` + `user_guild_roles` at session creation time.

---

## 4. Explicitly Out of Main DB Scope (This Cycle)

- Multi-guild tenancy mapping tables.
- Cross-guild aggregation/materialization tables.
- Global organization/tenant ACL layers.
- Cloud-scale queue/event-bus metadata stores.

---

## 5. Keep / Evolve / Add Matrix (Current -> Target)

### Keep as Core (with minor evolution)
- `users`, `user_stats`, `activity_log`, `admin_log`, `settings`, `channels`, `media_files`, `page_layouts`, `card_configs`, `event_lake`, `event_counters`

### Evolve in-place
- `achievements`: migration to composable "Crate" schema (Identity only).
- `event_lake`: evolve into canonical taxonomy envelope with stricter predicate-ready payload contract.
- `event_counters`: keep as derived cache; verify period semantics and alignment with anti-gaming windows.
- `activity_log`: keep as reward delta audit trail; align field naming with rule-evaluation trace linkage.
- `media_files`: add `folder_id` FK column to support organized folder navigation.

### Add (new contracts required)
- `rarities`, `categories`, `seasons` (Composition tables for Achievement Crates).
- `svg_overlays` (shipped defaults + admin-uploadable; composited client-side over icons).
- `media_folders` (NEW — folder registry for organizing uploaded media assets).
- `reward_rules`: (The Brain). JSONB predicates + outcomes.
- `rule_evaluations`: (The Trace). Per-event explainability logs.
- `projection_checkpoints`: replay/backfill position and idempotent resume state.
- `user_profiles`: Discord identity cache + leaving-member state.
- `user_guild_roles`: Role membership sync for RBAC.
- `marketplace_items`: Admin-configured shop with flexible XP/Gold pricing.
- `user_inventory`: One-way purchase records with equipped state and optional expiry.

---

## 6. Data Classification Rules

- Store IDs and structural metadata required for engagement logic.
- Do not store raw message body by default.
- Treat user IDs as sensitive identifiers.
- Redaction must be compatible with immutable telemetry (compensating events/tombstones, not destructive edits).

---

## 7. Consistency & Latency Targets

- Rule/config propagation target: ~60 seconds.
- User-visible projection freshness: up to 5 minutes.
- At-least-once ingest + idempotent writes is required.
- Deterministic replay from telemetry + rule snapshots is required.

---

## 8. Schema Decision Gates (Status: 🟢 ALL COMMITTED)

1. Canonical envelope fields: **APPROVED**.
2. Rule snapshot strategy: **APPROVED** (JSONB within `RewardRule`).
3. Achievement Architecture: **APPROVED** (Composable Crate + Dispatch Pattern).
4. Replay checkpoint schema: **COMMITTED** — `projection_checkpoints` table; columns: `worker_id`, `last_processed_evaluation_id`, `updated_at`. Implementation defined in MASTER_ROLLOUT_PLAN Phase 4.
5. Retention window: **DEFERRED** — not a pre-condition for any implementation phase. Default: retain all telemetry indefinitely. Configurable retention is a post-stabilization operational task.

No phase-2+ implementation starts until these gates are signed off.

---

## 9. Immediate Next Actions

> **Note:** These items are now delegated to `MASTER_ROLLOUT_PLAN.md`. Consult the master plan for current phase status instead of tracking work here.

- ~~Draft Alembic design notes for new rule snapshot/evaluation/checkpoint tables.~~ → MASTER Phase 1
- ~~Produce a column-level contract for `event_lake` evolution (v1 -> v2 envelope).~~ → MASTER Phase 2
- ~~Map each API/dashboard dependency to source table(s) to avoid accidental schema drift.~~ → Ongoing — review against current schema before each migration in MASTER Phase 1.

---

## 10. Operational Observability Requirements

Admins operating the system need visibility beyond content management. These are required instrumentation points, not nice-to-haves.

### 10.1 System Health (Bot + API)

| Signal | Source | Dashboard Location |
|---|---|---|
| Bot WebSocket connected | `bot/core.py` heartbeat | Admin header status bar |
| API response latency (p95) | FastAPI middleware | Admin health panel |
| DB connection pool saturation | SQLAlchemy pool events | Admin health panel |
| Last event captured timestamp | `event_lake` MAX(created_at) | Admin health panel |

**Agent note:** Health signals should be queryable via a `GET /api/admin/health` endpoint that returns a JSON summary. This endpoint is polled by the dashboard every 60 seconds.

### 10.2 Economic Health

| Metric | Query Source | Use |
|---|---|---|
| Total XP issued (last 24h) | `activity_log` aggregate | Detect runaway rules |
| Total Gold issued (last 24h) | `activity_log` aggregate | Detect runaway rules |
| Marketplace spend (last 24h) | `user_inventory` aggregate | Economy velocity |
| Top 10 earners (last 24h) | `user_stats` join | Farmer detection |
| Rule match rate (per rule/hour) | `rule_evaluations` aggregate | Over-broad rule detection |

### 10.3 Anti-Gaming Signals

| Signal | Threshold | Action |
|---|---|---|
| Single user earns >5x guild median in 1h | Log to `admin_log` | Display in anomaly feed |
| Rule matches >1000 events in 10 minutes | Log to `admin_log` | Flag rule for admin review |
| Marketplace: >10 purchases by one user in 1 minute | Hard block + log | Rate-limit enforced at API layer |

### 10.4 Admin Dashboard UX Spec (Wireframe Contract)

This section defines what each admin screen must expose. It is the binding spec for SvelteKit implementation.

**Screen: Rule Manager**
- Table of rules (name, type, active toggle, priority, last modified).
- Click rule → opens Rule Canvas (predicate/outcome editor).
- "Run Simulation" button → opens Laboratory overlay.
- "Publish" button → creates rule_snapshot, fires PG NOTIFY.

**Screen: Achievement Manager**
- Table of achievements (name, rarity badge, category, season, active).
- Click achievement → opens Crate editor (identity fields only, no logic).
- "Dispatch Test" button → manually fires achievement to a test user.

**Screen: Marketplace**
- Table of items (name, cost_xp, cost_gold, item_type, rarity, active, expires_at).
- Click item → opens item editor (pricing, overlay, discord_role_id selector for COLOR type).
- "Preview" button → renders item card as members will see it.

**Screen: Media Library**
- Folder tree (left panel) + file grid (right panel).
- Drag-and-drop upload or file picker.
- Click file → copy URL, set alt text, assign to folder, delete.
- Filter by type: `image/*` vs `image/svg+xml` (overlays).

**Screen: Observability / Health**
- System status row (bot, API, DB).
- Economic health charts (XP/Gold issued per hour, last 24h).
- Anomaly feed (flagged users/rules).
- Rule performance table (match rate per rule).

**Screen: Member Profile (Authenticated Member View)**
- Avatar + username + title.
- XP bar, Gold balance, Level.
- Achievement showcase (equipped badge + inventory grid).
- Activity timeline (last 20 rewarded events with "Why" trace).
- Marketplace inventory with equip/unequip controls.
