# Synapse Master Rollout Plan

> **Created:** 2026-02-19
> **Status:** Active — Living Document
> **Authority:** This document governs the sequencing of all major system changes.
> **Principle:** No phase begins until the previous phase's verification gate is met.
> No feature is released live until its feature flag is explicitly enabled after monitoring.

---

## How to Use This Document

This plan is the single source of truth for "what order do we do things in and why."
Each phase is self-contained. An agent or developer should be able to pick up any phase
and know exactly: what it does, what it depends on, how to verify it passed, and
how to roll it back if it didn't.

**Status icons:**
| Icon | Meaning |
|------|---------|
| ⬜ | Not started |
| 🔄 | In progress |
| ✅ | Complete — gate passed |
| ⛔ | Blocked |
| 🔒 | Locked — do not start until dependency complete |

**Rules:**
- Mark a phase 🔄 when you begin it.
- Do not mark ✅ until the Verification Gate passes.
- Do not start a phase marked 🔒.
- If a phase fails its gate, roll back, create a tracker issue, and return to the previous stable state before debugging.

---

## Dependency Map

```
Phase 0 (Foundation)
  └── Phase 1 (Schema)
        ├── Phase 2 (Telemetry)
        │     └── Phase 3 (Rule Firewall)
        │           └── Phase 4 (Projections)
     │                 ├── Phase 12 (Cutover)
   │                 └── Phase 9 (Admin Dashboard)  ← also depends on 3 + 4 + 6 + 7 + 8
     │                       └── Phase 11 (Observability)
        ├── Phase 5 (Auth)
        │     └── Phase 10 (Member Dashboard)
        ├── Phase 6 (Media Library v2)
        │     └── Phase 7 (Achievement System v2)
        │           └── Phase 8 (Marketplace)
        │                 └── Phase 10 (Member Dashboard)
```

---

## Parallel Track — Dashboard Quality Overhaul

`PLAN_dashboard_quality_overhaul.md` is an active, approved plan addressing architectural debt, security vulnerabilities, and UX deficiencies in the existing SvelteKit dashboard. It runs in phased passes **alongside** the main numbered rollout and is **not** embedded in the phases below, with one hard exception.

**Hard prerequisite for Phase 5:** `lib/stores/auth.ts` hardcodes `is_admin: true` on every login — a P0 client-side privilege escalation. Any logged-in user appears as admin on the client regardless of their actual role. This fix **must be applied as part of Phase 0** before the three-tier auth system can safely go live.

All other dashboard overhaul work (responsive layout, memory leak fixes, state management, Svelte 5 idioms, accessibility) can proceed independently of the backend phase sequence. When building new admin screens in Phase 9 and member-facing screens in Phase 10, write new code to the **corrected standards** defined in `PLAN_dashboard_quality_overhaul.md` — do not copy existing patterns that the overhaul is fixing.

Create `TRACKER_dashboard_quality_overhaul.md` before beginning dashboard overhaul work.

---

## Phase 0 — Foundation Hardening
**Status:** ⬜
**Risk:** Low
**Purpose:** Fix known loose ends before building on top of them.

### Scope
- Fix storage leak: `DELETE /media/{id}` currently removes the DB record but does **not** delete the file from disk. Must delete the physical file in `upload_service`.
- Confirm test suite baseline: `uv run pytest tests/ -v` passes clean on the current main branch.
- Confirm feature flag infrastructure: the `settings` table accepts boolean keys. Seed the four new flags (`firewall_enabled`, `marketplace_enabled`, `three_tier_auth_enabled`, `projection_workers_enabled`) as `false`.
- **Dashboard P0 security fix:** Remove `is_admin: true` hardcode in `lib/stores/auth.ts`. Role must be derived from the JWT payload or API response — never assumed. This is a prerequisite for Phase 5.

### Verification Gate
- [ ] `pytest tests/ -v` passes with zero failures.
- [ ] `DELETE /media/{id}` removes both the DB record and the physical file.
- [ ] The four feature flags exist in `settings` seeded to `false`.
- [ ] `lib/stores/auth.ts` does not hardcode `is_admin: true` — role is derived from actual auth state.

### Rollback
Not applicable — all changes are additive or bug fixes.

---

## Phase 1 — Database Schema Evolution
**Status:** ⬜
**Risk:** Medium (schema changes are one-way without explicit down-migrations)
**Depends On:** Phase 0 ✅

### Scope
Generate and apply Alembic migrations for all new and evolved tables in this order (respecting FK dependencies):

**New tables:**
1. `rarities` — Visual tier system for achievements and items.
2. `categories` — Grouping taxonomy for achievements.
3. `seasons` — Time-bounded event windows.
4. `svg_overlays` — Decorative frame registry (shipped defaults + admin-uploadable).
5. `media_folders` — Folder registry for organizing media assets.
6. `reward_rules` — Firewall rule definitions (JSONB predicates + outcomes).
7. `rule_snapshots` — Immutable versioned snapshots of full ruleset on each publish.
8. `rule_evaluations` — Per-event trace linking event → matched rules → outcomes.
9. `projection_checkpoints` — Resume state for projection workers.
10. `user_profiles` — Discord identity cache (avatar, username, left_at).
11. `user_guild_roles` — Synced role membership for RBAC.
12. `marketplace_items` — Admin-configured shop items.
13. `user_inventory` — One-way purchase records.

**Evolved tables:**
- `achievements`: add `rarity_id` FK, `category_id` FK, `season_id` FK, `overlay_id`. Remove any embedded logic fields.
- `media_files`: add `folder_id` FK.

### Verification Gate
- [ ] `uv run alembic upgrade head` applies cleanly against a fresh DB.
- [ ] `pytest tests/ -v` passes with zero failures after migration.
- [ ] Every new table exists in the DB with the correct columns (spot-check via `\d <table>`).
- [ ] No existing data is deleted or silently modified.

### Rollback
`uv run alembic downgrade -1` for each migration in reverse order.
Review each auto-generated migration carefully before applying — autogenerate is not infallible.

---

## Phase 2 — Telemetry Expansion
**Status:** 🔄
**Risk:** Low (additive; existing capture paths unaffected)
**Depends On:** Phase 1 ✅

### Scope
- Formalize the `InteractionEnvelope` schema: minimum required fields for every event entering the lake.
- Map all existing `event_lake` payload shapes to the envelope contract.
- Expand capture coverage where Discord exposes data we do not currently ingest: Polls, Stickers, Thread activity nuance.
- Tag every captured `event_type` with a `source_category` (`GATEWAY` / `REST` / `SYNTHETIC`).

### Verification Gate
- [ ] `InteractionEnvelope` schema is documented and code-level dataclass/schema exists.
- [ ] All existing event types produce valid envelope payloads.
- [ ] At least 1 new event type (Poll, Sticker, or Thread) is captured successfully.
- [ ] `pytest tests/ -v` passes.

### Rollback
Revert capture additions. Existing events are unaffected (append-only lake).

---

## Phase 3 — Rule Firewall Core
**Status:** 🔄
**Risk:** Medium (touches reward pipeline; gated behind feature flag)
**Depends On:** Phase 2 ✅

### Scope
- Wire `RuleEngine` as the reward evaluation path, controlled by `firewall_enabled = false`.
- Implement Context Injection in the service layer: populate `SynapseEvent.context` from `event_counters` and `user_stats` before engine invocation.
- Build the baseline default rules pack: a set of `RewardRule` records that exactly reproduce current hardcoded reward behavior.
- Enable **Shadow Mode**: when the flag is off, the legacy pipeline runs as production AND the new engine runs in parallel, writing to a shadow log for comparison.
- Verify parity: shadow log output must match legacy output for at least 24 hours of live traffic.

### Verification Gate
- [ ] `pytest tests/ -v` passes with deterministic engine unit tests.
- [ ] Shadow mode shows ≤0.1% divergence vs. legacy pipeline over 24h.
- [ ] No DB calls exist inside any `synapse/engine/` module.
- [ ] Baseline default rules reproduce current reward behavior exactly.
- [ ] `firewall_enabled` remains `false` after this phase.

### Rollback
Set `firewall_enabled = false` (instant, no deploy needed). Legacy pipeline continues uninterrupted.

---

## Phase 4 — Projection Pipeline
**Status:** ⬜
**Risk:** Medium (new workers; gated behind feature flag)
**Depends On:** Phase 3 ✅

### Scope
- Implement projection workers: async tasks that read `rule_evaluations` and apply outcomes to Read Models (`users.xp`, `users.gold`, `user_achievements`, etc.).
- Implement idempotent writes: all projection updates use `ON CONFLICT DO NOTHING` or conditional `WHERE` guards.
- Implement `projection_checkpoints`: workers record their last processed evaluation ID so they can resume after failures.
- Implement dry-run replay: run workers from `checkpoint=0` against a static snapshot, output to temp table, compare against current Read Model state.
- Enable workers behind `projection_workers_enabled = false` flag.
- Test replay produces parity with current `user_stats` values.

### Verification Gate
- [ ] Replay from Event Lake reproduces expected `user_stats` values within acceptable tolerance.
- [ ] Worker resumes correctly after simulated failure (kill and restart).
- [ ] Idempotency confirmed: running the same batch twice produces identical state.
- [ ] `pytest tests/ -v` passes.
- [ ] `projection_workers_enabled` remains `false` after this phase.

### Rollback
Set `projection_workers_enabled = false`. Legacy `reward_service` direct writes continue uninterrupted.

---

## Phase 5 — Three-Tier Authentication
**Status:** ⬜
**Risk:** Medium (new auth paths; existing admin auth unaffected until flag enabled)
**Depends On:** Phase 1 ✅

### Scope
- Bot sync: capture `avatar_url`, `username`, `last_seen` into `user_profiles` on `on_message`, `on_member_join`, `on_member_remove`.
- `on_member_remove`: set `avatar_url = NULL`, `username = "Former Member"`, record `left_at`.
- Extend OAuth flow to issue JWTs for non-admin members (not just admins).
- JWT payload: `(user_id, is_admin, roles[], avatar_url, username, iat, exp)`.
- Implement membership verification middleware (hybrid: cache-first, 5min TTL, Discord API fallback).
- Implement route guards in `deps.py`: `get_guest_context()`, `get_member_context()`, `get_admin_context()`.
- Gate behind `three_tier_auth_enabled = false` flag. Existing admin-only flow is default until flag is set.

### Verification Gate
- [ ] All three user tiers authenticate correctly in isolation.
- [ ] A non-guild member is rejected (401) at member-only endpoints.
- [ ] A former member's profile shows "Former Member" anonymization.
- [ ] Existing admin OAuth flow is unbroken when flag is `false`.
- [ ] `pytest tests/ -v` passes.
- [ ] `three_tier_auth_enabled` remains `false` after this phase.

### Rollback
Set `three_tier_auth_enabled = false`. Existing admin-only auth continues uninterrupted.

---

## Phase 6 — Media Library v2
**Status:** ⬜
**Risk:** Low
**Depends On:** Phase 1 ✅

### Scope
- Implement `media_folders` CRUD endpoints (create, rename, delete-if-empty).
- Add `folder_id` assignment to upload and update endpoints.
- Ship default SVG overlays: seed `svg_overlays` table with at minimum `border_common`, `border_rare`, `border_epic`, `border_legendary` on startup.
- Admin can upload custom SVG files via existing upload endpoint (already supports `image/svg+xml`).
- Dashboard folder tree navigation (left panel) + file grid (right panel).

### Verification Gate
- [ ] Admin can create folders, upload files into them, and navigate the folder tree.
- [ ] Default SVG overlays exist in the database on a fresh deploy.
- [ ] File deletion removes both the DB record and the physical file from disk.
- [ ] `pytest tests/ -v` passes.

### Rollback
Folder columns are additive. Removing them requires a migration. Default seed data can be truncated.

---

## Phase 7 — Achievement System v2 (Composable Crates)
**Status:** ⬜
**Risk:** Medium (migrates existing achievement data)
**Depends On:** Phase 1 ✅, Phase 3 ✅, Phase 6 ✅

### Scope
- Seed default `rarities`, `categories`, and `seasons` records.
- Migrate existing `achievement_templates` data to the new Crate schema (`rarity_id`, `category_id`, `season_id`, `overlay_id`). **Non-destructive migration only.**
- Implement `dispatch_achievement` as a first-class outcome type in `RuleEngine`.
- Wire existing legacy achievement triggers to dispatch via rules (not hardcoded checks).
- Admin "Mad Libs" builder: form-based creation of Crates linked to a Strategy (e.g., `THRESHOLD_COUNTER`).

### Verification Gate
- [ ] All existing achievements preserved and earnable post-migration.
- [ ] A new achievement created via the Crate builder can be earned in live play.
- [ ] The `dispatch_achievement` outcome type is covered by engine unit tests.
- [ ] `pytest tests/ -v` passes.

### Rollback
Revert Crate FK columns via Alembic. Legacy achievement triggers remain functional as fallback.

---

## Phase 8 — Marketplace
**Status:** ⬜
**Risk:** Medium (currency deduction is financially sensitive)
**Depends On:** Phase 1 ✅, Phase 5 ✅, Phase 6 ✅, Phase 7 ✅

### Scope
- Implement `POST /api/shop/{item_id}/purchase` endpoint:
  - Validate item is active and not expired.
  - Validate user has sufficient XP or Gold (user's choice if both are set).
  - Atomically deduct currency using `UPDATE ... WHERE balance >= cost` (no check-then-act).
  - Insert `user_inventory` record idempotently.
  - If `item_type == CUSTOM_ROLE_COLOR`: dispatch role assignment to bot (async, fire-and-forget with retry, log failures).
- Admin shop builder: create/edit/deactivate items, set prices, set rarity, assign SVG overlays, set `expires_at`.
- Member inventory view: list owned items, equip/unequip cosmetics.
- Gate behind `marketplace_enabled = false` flag.
- Keep marketplace cosmetic-only (no channel access unlocks, no permission/moderation grants).
- Keep canonical storage keys `xp`/`gold`; allow admin-defined display labels at UI level only.

### Verification Gate
- [ ] Purchase deducts currency atomically (race condition test: two simultaneous purchases of the same item at exact balance).
- [ ] Purchasing a role item results in the Discord role being assigned.
- [ ] Role assignment failure is logged but does not fail the purchase.
- [ ] Expired items cannot be purchased.
- [ ] `pytest tests/ -v` passes.
- [ ] `marketplace_enabled` remains `false` after this phase.

### Rollback
Set `marketplace_enabled = false`. Purchased inventory records are preserved (non-destructive).

---

## Phase 9 — Admin Dashboard UX
**Status:** ⬜
**Risk:** Low (frontend-only; backend APIs already exist by this point)
**Depends On:** Phase 3 ✅, Phase 4 ✅, Phase 6 ✅, Phase 7 ✅, Phase 8 ✅

### Scope
Implement six admin screens. The Rule Manager screen contains four functional sub-zones (see `GROUND_RULES_SCOPE_CONTRACT.md § 10` and `PLAN_main_database_contract.md § 10.4` for full wireframe contract):

**Rule Manager** (the most complex screen — four zones within it):
- *Zone A — Rule Canvas:* Searchable predicate field dictionary (left rail), outcome blocks (right rail), curvature selector with live sparkline, structured form only — no raw JSON. "Publish" → creates `rule_snapshot`.
- *Zone B — Laboratory:* "Run Simulation" replays last N events against the draft rule. Side-by-side diff (current vs. proposed rewards). Per-event "Why" trace showing which predicates passed and what math was applied.
- *Zone C — Taxonomy Browser:* Browseable registry of every event type the bot has observed. New types appear automatically. Click-to-create shortcut: "Build a Rule for this Event Type."
- *Zone D — Projection Dashboard:* Histograms of rewards issued over last 24h. Growth trend lines. Validates that scaling curves are producing the intended effect (e.g., "Is my log curve suppressing farmers?").

**Achievement Manager:** Crate table, Crate editor (identity fields only), "Dispatch Test" button.

**Marketplace Screen:** Item table, item editor (pricing, overlay, `discord_role_id` selector), "Preview" card render.

**Media Library Screen:** Folder tree + file grid, drag-and-drop upload, metadata editor.

**Settings Screen:** Existing settings management (no new scope here).

**Observability / Health Screen:** Moved to Phase 11 — do not build here.

### Verification Gate
- [ ] Admin can build a rule, simulate it against historical events, and see the diff before publishing.
- [ ] Taxonomy Browser shows all observed event types from the live Event Lake.
- [ ] Admin can create a new achievement Crate from the UI.
- [ ] Admin can create a marketplace item with XP-only, Gold-only, or dual pricing.
- [ ] Media folder navigation works end-to-end.
- [ ] All screens are accessible only to Tier 3 (admin) users.

### Rollback
Frontend-only. Revert SvelteKit route changes.

---

## Phase 10 — Member Dashboard
**Status:** ⬜
**Risk:** Low (read-only views)
**Depends On:** Phase 4 ✅, Phase 5 ✅, Phase 8 ✅

### Scope
- **Public leaderboard (`/`):** Anonymized top-50 (rank + XP only, no names or avatars). No auth required.
- **Member profile (`/profile`):** Own stats (XP, Gold, Level), achievement showcase, activity timeline with "Why" trace per rewarded event, marketplace inventory with equip/unequip controls.
- **Member leaderboard position:** Show authenticated user's own rank alongside the anonymized public board.
- Avatar displayed on profile using `user_profiles.avatar_url`.

### Verification Gate
- [ ] Public leaderboard shows no usernames or avatars for unauthenticated visitors.
- [ ] Authenticated member can see their own profile, stats, and inventory.
- [ ] "Why" trace shows correct predicate breakdown for a rewarded event.
- [ ] Former members display as "Former Member" everywhere.
- [ ] Tier 2 users cannot access admin routes.

### Rollback
Frontend-only. Revert SvelteKit route changes.

---

## Phase 11 — Operational Observability
**Status:** ⬜
**Risk:** Low (additive)
**Depends On:** Phase 9 ✅

### Scope
- `GET /api/admin/health` endpoint: bot status, API latency, DB pool saturation, last event timestamp.
- Dashboard polls health endpoint every 60 seconds, displays status bar.
- Economic health charts: XP/Gold issued per hour (last 24h histogram).
- Anomaly feed: flags users earning >5x guild median in 1h, rules matching >1000 events in 10min.
- Rule performance table: match rate per rule per hour.
- Anti-gaming signals dashboard: top-10 earners per event type in last 24h.

### Verification Gate
- [ ] Health endpoint returns correct status for bot connected / bot disconnected.
- [ ] Economic chart populates after at least 1 hour of live data.
- [ ] Anomaly feed correctly flags a synthetically injected anomaly in test.

### Rollback
Additive only. Revert new API endpoint and dashboard chart components.

---

## Phase 12 — Feature Flag Cutover (Going Live)
**Status:** ⬜
**Risk:** High (each flag changes production behavior)
**Depends On:** ALL previous phases ✅

### Scope
Enable each feature flag **one at a time** with a 24-hour monitoring window between each.

**Cutover Order:**
1. `projection_workers_enabled = true`
   - Monitor: Read Model values drift vs. direct `activity_log` sum. Acceptable delta < 0.5%.
   - Rollback trigger: Delta > 1% or worker error rate > 0.1%.

2. `firewall_enabled = true`
   - Pre-condition: Shadow mode showed ≤0.1% divergence vs. legacy for ≥24h.
   - Monitor: Anomaly feed, reward rate per rule, total XP issued per hour.
   - Rollback trigger: Anomaly count spikes or total XP/hour doubles vs. baseline.

3. `three_tier_auth_enabled = true`
   - Monitor: Auth error rate, 401 rejections for non-members.
   - Rollback trigger: Auth error rate > 0.5%.

4. `marketplace_enabled = true`
   - Monitor: Purchase success rate, currency deduction correctness, role assignment success rate.
   - Rollback trigger: Any failed atomic purchase, any currency duplication.

### Rollback for Any Flag
Set the flag back to `false` in `settings`. Takes effect within 60 seconds via PG NOTIFY. No deploy required.

### Final Verification Gate
- [ ] All four flags enabled and stable for ≥72 hours.
- [ ] No anomaly flags in the observability feed.
- [ ] `pytest tests/ -v` passes against production schema.
- [ ] Admin confirms: legacy hardcoded reward pipeline can be safely deprecated.

---

## Current Phase Status Summary

| Phase | Name | Status | Gate Passed |
|-------|------|--------|-------------|
| 0 | Foundation Hardening | ⬜ | |
| 1 | Database Schema Evolution | ⬜ | |
| 2 | Telemetry Expansion | 🔄 | |
| 3 | Rule Firewall Core | 🔄 | |
| 4 | Projection Pipeline | ⬜ | |
| 5 | Three-Tier Authentication | ⬜ | |
| 6 | Media Library v2 | ⬜ | |
| 7 | Achievement System v2 | ⬜ | |
| 8 | Marketplace | ⬜ | |
| 9 | Admin Dashboard UX | ⬜ | |
| 10 | Member Dashboard | ⬜ | |
| 11 | Operational Observability | ⬜ | |
| 12 | Feature Flag Cutover | 🔒 | |

---

## Completion Log

| Date | Event |
|------|-------|
| 2026-02-19 | Master Rollout Plan created. Phase 1 (Pruning) confirmed complete. Phases 2 and 3 in progress. |
