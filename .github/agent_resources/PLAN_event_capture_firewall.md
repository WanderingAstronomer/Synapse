# Planning: Event Capture First + Reward Firewall Architecture

> **Created:** 2026-02-18
> **Status:** Active Reference (Sequencing governed by MASTER_ROLLOUT_PLAN.md)
> **Scope:** Define the architecture shift from selective reward handling to comprehensive Discord event capture plus composable reward rules.

---

## 1. Problem Statement

The current system is functional for core reward loops, but it is too selective and hard-coded. It lacks the modularity required to support complex community-driven reward policies (e.g., "Reward high-quality programming deep-dives in this specific forum").

**Target direction:**
- **Reward Firewall:** Move from hardcoded branches to a composable, admin-defined rules engine.
- **Paradigm Shift:** Graduate from "Vibe Coding" to **Data-Oriented Design (DOD)**. Interactions are "Facts" (Lake), and Economy is a "Projection" (Rules).
- **Pure Functional Engine:** The engine remains side-effect free, transforming `(Event, Ruleset, Context)` into a deterministic set of `Outcomes`.
- **Capture Completeness:** If Discord results in an interaction, we capture it. Abstraction first.

---

## 2. Context & Discovery

| Area | Key Files | Notes |
|------|-----------|-------|
| Event capture service | synapse/services/event_lake_writer.py | Existing capture path and source toggles are present; taxonomy still partial vs full Discord surface. |
| Event lake API/admin ops | synapse/api/routes/event_lake.py | Supports events, source toggles, retention, reconciliation, backfill, counters. |
| Reward pipeline | synapse/engine/reward.py, synapse/services/reward_service.py | Functional but still shaped around preselected interaction paths. |
| Achievement triggers | synapse/engine/achievements.py | Trigger framework exists; some trigger types intentionally not wired yet. |
| Dashboard admin surfaces | dashboard/src/routes/admin/* | Good CRUD/admin breadth; not yet a full boolean rule-builder UX. |

Primary data contract companion:
- `PLAN_main_database_contract.md` defines exactly what belongs in the main DB for this initiative.

---

## 3. Constraints & Guardrails

- Keep engine modules pure (no DB or Discord I/O in synapse/engine).
- Keep admin mutations audited via service layer.
- Preserve idempotency and source event dedupe patterns.
- Do not make schema dynamic per admin; use stable schema + dynamic config/rules.
- Keep master observed telemetry immutable; projections can be recomputed.
- Enforce single-guild operational model across bot, API, and dashboard contracts.

---

## 4. Design Options

### Option A — Continue Incremental Selective Rewards (Current Trajectory)

**Summary:** Keep adding new event types directly into reward logic and UI forms.

**Pros:**
- Fastest short-term delivery.
- Minimal migration effort.

**Cons:**
- Architecture drift and increasing complexity debt.
- Hard to support broad custom rules and admin freedom.
- Repeated rewrites as new Discord interactions are requested.

### Option B — Capture First + Rule Firewall (Chosen)

**Summary:** Prioritize complete telemetry ingestion and a normalized interaction abstraction. Build a rules compiler/evaluator on top, then produce derived economy projections.

**Pros:**
- Aligns with platform goals (modular, customizable, future-safe).
- Decouples Discord surface growth from economy feature churn.
- Enables advanced per-channel/content/intent rule authoring.

**Cons:**
- Requires phased implementation and migration planning.
- Initial pace slower than tactical feature patching.

### Option C — Hybrid with Limited Capture Expansion

**Summary:** Expand a few high-value capture areas and keep rules mostly static.

**Pros:**
- Medium effort.
- Some near-term flexibility.

**Cons:**
- Risks stopping halfway; still not truly composable.
- Can lock in another transitional architecture.

### Chosen Approach

> **Decision:** Option B. Build around immutable observed telemetry + composable reward firewall.

---

## 5. Domain Model Clarification

### 5.0 The Two Data Classes

1. **Observed Telemetry (Discord-origin):**
   - Objective event stream from Discord interactions.
   - Immutable, append-only, versioned envelope.
   - Source of truth for replay, analytics, and new rule derivation.
   - Terminology: use "event telemetry" or "event lake."

2. **Derived Economy State (Synapse-origin):**
   - XP, gold, levels, achievements, ranks, counters, projections.
   - Recomputable from telemetry + rules + config snapshots.
   - Mutable and operationally optimized for app reads.
   - Terminology: use "projections" or "read models."

**Never mix observed and derived semantics in the same model or table.**

---

## 5.1 The Reward Firewall Lexicon

**The Lexicon:**
- **Atomic Predicate:** A simple, deterministic "Fact Check" (e.g., `content_length >= 500`).
- **Contextual Predicate:** A check against **Accumulated Data** for the user (e.g., `context.lifetime_messages == 100`).
- **Selector:** A collection of predicates that must all evaluate to `True` for a rule to "fire."
- **Outcome:** What the rule produces—can be **Base Rewards** (scalable), **Bonus Rewards** (fixed), or **System Triggers** (Achievements/Awards).
- **Scaling Curve:** Mathematical transformation (Linear, Logarithmic, Exponential) applied to scalable outcomes based on **Contextual Variables** (e.g., `messages_today`).
- **Context:** The "Materialized State" passed into the pure engine (User levels, daily counts, lifetime stats). This is populated by the Service layer (via `event_counters` and `user_stats`) to avoid expensive lake-scans during rule evaluation.

### 5.1 Rule Schema Example (JSONB)
```jsonc
{
  "name": "Technical Deep Dive",
  "priority": 100,
  "predicates": [
    {"field": "channel_id", "op": "==", "value": 112233},
    {"field": "content_length", "op": ">=", "value": 1000},
    {"field": "has_code_block", "op": "==", "value": true}
  ],
  "outcomes": [
    {
      "type": "XP",
      "base_value": 20,
      "is_scalable": true,
      "scaling": { "curve": "LOGARITHMIC", "variable": "daily_count", "factor": 1.1 }
    }
  ]
}
```

---

## 6. Rollout Phases

### Phase 1 — Inventory & Pruning
**Goal:** Align current system with DOD paradigm before expansion. (See PLAN_pruning_for_capture_firewall.md).

### Phase 2 — Telemetry Expansion & Abstraction
**Goal:** Standardize capture abstraction and event vocabulary.
- Define InteractionEnvelope schema.
- Map existing event_lake payloads.
- Ensure "Capture All" coverage for Polls, Stickers, Thread nuance, etc.

### Phase 3 — Rule Firewall Core (Engine)
**Goal:** Build the pure functional engine for rule evaluation.
- Implement `PredicateEvaluator` (Atomic & Contextual Predicates).
- Implement `ScalingResolver` (Non-linear curves: Log/Exp/Step).
- Implement `RuleEngine` to match events to outcomes.

### Phase 4 — Projection Pipeline & Replay
**Goal:** Materialize economy state from rules outcomes.
- Projection workers for XP/Gold/Achievements.
- Recomputable via "Replay" from the Event Lake.
- Idempotent checkpoints for resume safety.

### Phase 5 — Admin Rule Builder & Simulator UX
**Goal:** Deliver full admin control over reward logic with "safety gear."

**Rule Canvas (The Builder)**
- Left Rail: Searchable Taxonomy dictionary of all predicate fields sourced from the engine.
- Right Rail: Outcome blocks — XP, Gold, Achievement Dispatch.
- Curvature selector with live sparkline previewing the scaling shape (Log/Exp/Step/Linear).
- Structured form only — no free-text logic entry, no raw JSON editing by admins.

**The Laboratory (Simulation & Safety)**
- "Run Simulation" button replays the last N events from the Event Lake against the *draft* rule.
- Side-by-side diff view: current rewards vs. proposed rewards.
- Per-event "Why" trace showing which predicates passed and what math determined the outcome.
- Prevents "I accidentally gave everyone infinity XP" failure modes before going live.

**Taxonomy Browser (Discovery)**
- Browseable registry of every event type the bot has observed in the Event Lake.
- New Discord interaction types appear automatically as the bot captures them.
- Click-to-create shortcut: "Build a Rule for this Event Type."

**Projection Dashboard (Operational Feedback)**
- Histogram of rewards issued over the last 24 hours (validate curve is working).
- Growth trend lines, not just totals.

**Member Explainability Panel**
- Authenticated members can see exactly why they earned a reward.
- "You earned +50 XP because: Message Length >= 500 AND Channel: #tech-help."

**Verification:**
- Deterministic outputs for identical inputs.
- Existing baseline behavior reproducible via default rules.
- Simulation output matches engine expectations for historical data.
- Taxonomy API is always in sync with engine field registry.

---

## 7. Risks & Open Questions

| # | Risk / Question | Mitigation / Answer |
|---|----------------|---------------------|
| 1 | Discord API/Library does not expose all interaction details directly | Maintain feature matrix with capture status: native, partial, unavailable. |
| 2 | Rule expressiveness may become unbounded and slow | Start with constrained DSL and explicit precedence; add profiler before broadening. |
| 3 | Telemetry volume growth increases storage costs | Keep retention policy, tiering, and archive strategy from day one. |
| 4 | Legacy reward behavior drift during migration | Build baseline default rules that exactly mirror current behavior first. |
| 5 | PII/privacy boundaries in event payloads | Define field-level retention and redaction policy in envelope spec. |

---

## 7.1 Explicit Non-Goals (This Rework)

- No multi-guild management UX.
- No DB-per-guild tenancy model.
- No row-level security (RLS) rollout for tenant isolation.
- No cross-guild analytics aggregation.

Rationale:
- The operating target is one guild; architecture should stay focused and lean.
- Keep extension seams clean so multi-guild can be a future initiative, not an implicit partial implementation now.

---

## 8. Success Criteria

- A stable observed telemetry model exists, independent of reward logic.
- Admin-defined rules can express scope + boolean predicates + reward actions.
- Derived economy data is projection-based and replayable.
- Existing behavior is preserved under default rules.
- UI supports rule authoring without requiring backend code edits per policy.

---

## 9. Achievement System Appendix (Refactored)

**Architecture:** The "Crate" Concept & Start-Dispatch Pattern.
Achievements are strictly **Identity** (Name, Icon, Description) and **Composition** (Rarity, Season, Category). They contain **NO LOGIC**.

### 9.1 Data Model (The "Crate")

An Achievement is a composed object linking standardized references:
- **Identity:** `id`, `name`, `description`, `icon_url` (The Trophy).
- **Style:** `rarity_id` -> `Rarity` (Color, Frame, Priority).
- **Grouping:** `category_id` -> `Category` (Social, Voice, etc.).
- **Timing:** `season_id` -> `Season` (Start/End dates).

### 9.2 The Dispatch Architecture

Rules (`RewardRule`) are the only source of logic. A rule evaluates predicates and *dispatches* outcomes.
1.  **Event:** User sends 1,000th message.
2.  **Rule:** `IF context.msg_count >= 1000 THEN dispatch(UNLOCK_ACHIEVEMENT, "social_1k")`.
3.  **Outcome:** The system awards the achievement identified by `social_1k`.

This allows multiple rules (e.g., specific channel vs. global count) to unlock the same achievement.

### 9.3 Admin UX: The "Mad Libs" Builder

We avoid a complex visual node editor for simple tasks.
- **Construction:** Admins use a form to fill in the "Crate" (Name, Rarity, Flavor).
- **Logic:** Admins select a "Strategy" (e.g., "Counter Threshold") and fill in the blanks:
    - *"Unlock when [Metric Dropdown] reaches [Number Input]."*
- **Verification:** The "Laboratory" shows a diff of who *would* have earned this achievement based on historical data.

### 9.4 Phase Mapping into Master Plan

> ⚠️ Phase numbers below refer to **MASTER_ROLLOUT_PLAN.md** phase numbers, not to the internal phases of this document.

- **Master Phase 3 (Rule Firewall Core):** Implement `dispatch_achievement` outcome in `RuleEngine`.
- **Master Phase 4 (Projection Pipeline):** Materialize `UserAchievement` state from rule outcomes.
- **Master Phase 7 (Achievement System v2):** "Mad Libs" form for Rarity/Season/Achievement creation and simulation.
- **Master Phase 9 (Admin Dashboard UX):** Achievement Manager screen with Crate editor and Dispatch Test button.

This keeps achievements as a first-class consumer of the new architecture,
instead of a parallel special-case system.
---

## 10. State Projection Architecture (Technical Spec)

### 10.1 The Two-Table Contract

Every piece of data in the system belongs to exactly one of two categories:

| Category | Characteristics | Tables |
|---|---|---|
| **Source of Truth** | Immutable, append-only, never updated | `event_lake`, `reward_rules` (versioned) |
| **Read Models** | Mutable projections, recomputable from source | `users`, `user_stats`, `activity_log`, `user_achievements`, `user_inventory` |

The dashboard **only reads from Read Models**. It never scans the Event Lake directly.

### 10.2 Projection Worker Design

A projection worker is an async background task that:
1. Reads a batch of `rule_evaluations` since the last `projection_checkpoint`.
2. Applies each evaluation outcome to the appropriate Read Model (`users.xp`, `users.gold`, `user_achievements`, etc.).
3. Updates `projection_checkpoints` with the last processed evaluation ID.

```
Event Lake → [RuleEngine] → rule_evaluations → [ProjectionWorker] → Read Models
```

**Key properties:**
- Workers are **idempotent**: processing the same `rule_evaluation` twice must produce the same Read Model state (use `ON CONFLICT DO NOTHING` or conditional updates).
- Workers use `projection_checkpoints` to resume safely after failures.
- Workers never modify `event_lake` or `rule_evaluations` — both are append-only.

### 10.3 Staleness Policy (Per Read Model)

| Read Model | Acceptable Lag | Strategy |
|---|---|---|
| `users.xp`, `users.gold` | ~5 minutes | Batch worker, runs every 60s |
| `user_achievements` | ~5 minutes | Triggered on state-type rule match |
| Leaderboard queries | ~5 minutes | Materialized from `user_stats` |
| Own profile (member view) | ~1 minute | Priority re-projection on profile load |
| Admin audit logs | Real-time | Written synchronously in service layer |

### 10.4 Replay Strategy

Replay = running the projection worker from `checkpoint=0` against a static snapshot of `reward_rules`. Used for:
- Migrating to a new rule schema.
- Verifying a rule change would produce the same historical outcome.
- Recovering from database corruption.

Replay is always a **dry-run** first (output to temp table), then swapped atomically.

### 10.5 Context Population (Service Layer Responsibility)

Before the engine is invoked, the service layer must populate `SynapseEvent.context` with:
```python
context = {
    "msgs_today": event_counters.get(user_id, "message", window="24h"),
    "msgs_channel_today": event_counters.get(user_id, "message", channel_id, window="24h"),
    "lifetime_messages": user_stats.message_count,
    "current_level": users.level,
    "voice_seconds_today": event_counters.get(user_id, "voice", window="24h"),
}
```

This is the **Context Injection** contract. The engine is O(1) per rule evaluation because all state is pre-fetched. **Never call the database from within the engine.**

---

## 11. Rollback, Feature Flags & Migration Strategy

### 11.1 Feature Flags

Feature flags are stored in the existing `settings` table as boolean keys.

| Flag Key | Meaning | Default |
|---|---|---|
| `firewall_enabled` | Route events through RuleEngine instead of legacy pipeline | `false` |
| `marketplace_enabled` | Enable shop endpoints and purchase flow | `false` |
| `three_tier_auth_enabled` | Enable member/guest JWT tiers (vs. admin-only) | `false` |
| `projection_workers_enabled` | Run async projection workers | `false` |

Flags are read from `ConfigCache` (PG LISTEN/NOTIFY on `settings` change). No service restarts needed to toggle a flag.

**Shadow Mode Pattern:**
When `firewall_enabled = false`, the legacy pipeline runs as production. The new RuleEngine runs in parallel but writes outcomes to a shadow log rather than applying them. Admins compare shadow vs. legacy output in the admin dashboard before cutting over.

### 11.2 Cutover Sequence

> ⚠️ **Authoritative sequence is in MASTER_ROLLOUT_PLAN.md Phase 12.** This section describes only the `firewall_enabled` flag logic. Four flags must be cut over in the correct order: projection workers first, then firewall, then auth, then marketplace. Do not treat this section as the complete cutover plan.

For `firewall_enabled` specifically, the safe cutover order is:
1. Deploy code (both pipelines present, flag off).
2. Generate baseline default rules that exactly mirror current hardcoded behavior.
3. Enable shadow mode. Monitor diff dashboard for 24–48h.
4. If diff is clean: set `firewall_enabled = true` in `settings`.
5. Watch `rule_evaluations` for anomalies. If error rate spikes, set flag back to `false` (instant rollback, no deploy needed).

Pre-condition: `projection_workers_enabled` must already be `true` and stable before enabling `firewall_enabled`. Projection workers are what consume the `rule_evaluations` that the firewall produces.

### 11.3 Rule Snapshot Rollback

Every time an admin publishes a rule change, the system creates a `rule_snapshot` record:
```
rule_snapshots: id, created_at, created_by, snapshot_json (full ruleset at that moment)
```

Rollback = select a previous snapshot, set it as the active ruleset, fire PG NOTIFY. Sub-second recovery. No migration needed.

### 11.4 Data Migration (Legacy → Firewall)

The existing `backfill_service.py` is the migration vehicle. Order of operations:
1. Keep `activity_log` intact (it is the audit trail, never drop it).
2. Generate `rule_evaluations` from historical `activity_log` entries (synthetic backfill).
3. Run projection workers against synthetic evaluations to validate Read Model parity.
4. If parity check passes: promote. If not: debug rule definitions.

The migration is **non-destructive**. Legacy tables are preserved until explicitly deprecated by an admin decision, not by code.