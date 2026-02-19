# Ground Rules & Scope Contract — Synapse Rework

> **Created:** 2026-02-19  
> **Status:** Active  
> **Applies To:** Capture-first rework, pruning phases, and upcoming implementation tasks.

---

## 1) Scope Lock

- Synapse is a **single-guild platform** for this initiative.
- We are **not** introducing multi-guild management.
- We are **not** introducing tenant isolation architecture (RLS/DB-per-guild/cross-guild analytics) in this cycle.

Implementation interpretation:
- Keep code and UI simple for one guild.
- Preserve clean extension points, but do not implement partial multi-guild logic “just in case.”

---

## 2) Architectural Ground Rules

1.  **Data-Oriented Design (DOD)**: Events are immutable facts (observed telemetry); economy state is a derived projection.
2.  **Reward Firewall**: Logic is a composable set of "ingress rules" (Predicates + Outcomes). It handles both **Reactive Rewards** (single event) and **Proactive Triggers** (state thresholds).
3.  **Projection-Based Triggers**: Achievement and milestone checks are performed against **Materialized Context** (pre-computed counters) provided to the engine. We do not perform expensive "Lake Scans" during the reward loop.
4.  **Capture First**: Every Discord-origin interaction is normalized into the Event Lake before processing.
4.  **Functional Pipeline**: The Reward Engine is a collection of pure functions. `(Event, Ruleset) -> List[Rewards]`.
5.  **Deterministic Evaluator**: Same inputs + same rule snapshot must always produce identical outcomes.
6.  **Auditability**: Every admin mutation and reward-affecting decision must be explainable via the Rule Evaluation Trace.
7.  **Idempotent processing**: Mandatory dedupe keys (`source_id`) and conflict-safe inserts.

---

## 3) Consistency & Latency Policy

- Quick convergence is required.
- Instantaneous convergence is not required.
- Target propagation windows:
  - Rule/config propagation: approximately 60 seconds.
  - User-visible projection freshness: up to 5 minutes acceptable.
- Dashboard surfaces should show data freshness indicators where lag is expected.

---

## 4) Privacy & Data Boundaries

- Default to metadata/features over raw content storage.
- Avoid persisting data not required for telemetry/reward logic.
- Keep redaction/anonymization pathways compatible with immutable event history.
- Treat Discord user IDs as sensitive identifiers and restrict access appropriately.

---

## 5) Reward Firewall Architecture

- **Capture First / Derive Second:** All reward logic must be a pure functional transformation of an event into an outcome. No side effects during rule matching.
- **Context Injection:** The service layer provides stateful context (e.g., current message counts) to the engine so rule evaluation remains O(1) without scanning the database.
- **Explainability:** Every reward projection must be traceable back to the rule snapshot and specific event telemetry that triggered it.

---

## 6) Non-Linear Math Standards (Scaling)

The system supports the following scaling curves for outcomes:
- **Linear:** Rewards scale directly with input intensity.
- **Logarithmic:** $log(n)$ scaling to diminish returns on hyper-frequent activity.
- **Exponential:** $n^x$ scaling to reward high-intensity, rare engagement.
- **Step/Threshold:** Incremental boosts based on hitting specific integer boundaries.

Engineers must choose the least aggressive curve that meets the design goal to prevent economic runaway.

---

## 7) Anti-Gaming Baseline (Non-Optional)

The existing `synapse/engine/anti_gaming.py` (sliding-window tracker) and `event_counters` table are the foundation. These must be preserved and integrated into the Firewall pipeline, not replaced.

**Hard Rules (system-level, not admin-configurable):**
- Per-user per-event-type caps enforced via `event_counters` before rule evaluation.
- Minimum qualifying thresholds (e.g., message length floor) enforced as envelope-level predicates, not rule-level.
- Self-interaction exclusion: reactions/replies to own content yield no reward.
- Bot-authored interaction exclusion: any event with `author.bot == True` is dropped at ingest.

**Context Variables (injected into engine, derived from `event_counters`):**
- `context.msgs_today` — messages sent by this user in the last 24h window.
- `context.msgs_channel_today` — messages in this specific channel in the last 24h.
- `context.reaction_given_today` — reactions given by this user today.
- `context.voice_seconds_today` — cumulative voice time today.

These context variables are **pre-computed by the service layer** before engine invocation. The engine never queries the database.

**Scaling Curves as Anti-Gaming:**
The Log/Exp/Step curves in the Firewall are the primary economic anti-farming tool. Admins reduce reward density for hyper-frequent activity by selecting `LOGARITHMIC` curves on the `msgs_today` context variable. This is preferred over hard caps because it degrades gracefully rather than creating hard cliffs.

**Admin Observability (Required for Operational Use):**
- Dashboard histogram: rewards issued per hour (spike detection).
- Dashboard table: top 10 earners per event type in the last 24h (farmer detection).
- Rule match rate: how many events per rule per hour (identifies over-broad rules).
- Anomaly flag: if a single user earns >5x the guild median in a 1h window, log for admin review.

These controls are system-level guardrails, not optional admin toggles.

---

## 8) The Logic/Identity Split

- **Smart Rules, Dumb Achievements:** Logic lives exclusively in the `RewardRule`. An achievement is a static data container (Name, Icon, Rarity) that is *dispatched* by a rule.
- **Composable Content:** Content is built by mixing standardized "Crates" (Rarity, Season, Category, SVG Overlay).
- **No Hardcoded Triggers:** Engineers must not write `if event.type == MSG award_achievement()`. They must write `evaluate_rules(event)`.

---

## 9) Three-Tier Authentication (Approved Architecture)

The dashboard serves three distinct audiences with different access levels.

**Tier 1 — Public Guest (No auth)**
- Can see: Server-wide leaderboard (anonymized — rank + XP only, no names or avatars).
- Cannot see: Any individually-identified user data.

**Tier 2 — Authenticated Member (Discord OAuth + guild membership)**
- Can see: Own stats (XP, Gold, Level, Achievements), personal leaderboard rank, activity timeline.
- Cannot see: Other members' private stats, admin panel, rule logic.

**Tier 3 — Administrator (Discord OAuth + admin role in guild)**
- Can see and do: Everything. All user stats, all rules, audit logs, rule builder, simulation lab.

**Membership Verification Strategy:** Hybrid cache-first with API fallback.
- Cache TTL: 5 minutes (staleness is acceptable for this use case).
- On cache miss: Query `GET /users/@me/guilds` (requires `guilds` OAuth scope).
- JWT carries: `(user_id, is_admin, roles[], avatar_url, username)` — no DB query needed per-request.

**User Profile Sync:**
- Bot captures `avatar_url`, `username`, `last_seen` continuously via gateway events.
- `user_profiles` is the dashboard's source of truth for display data (decoupled from Discord API).

**Leaving Member Policy:**
- Retain the `user_profiles` record.
- Set `avatar_url = NULL`, `username = "Former Member"`.
- Add `left_at` timestamp for historical context.
- Retain all stats and leaderboard history (anonymized display).

---

## 10) Dashboard UI/UX Architecture (Approved Design)

The admin dashboard is divided into four functional zones:

**Zone A — The Rule Canvas (Policy Builder)**
- Left Rail: A searchable dictionary of available `Facts` (Predicate fields sourced from the Taxonomy API).
- Right Rail: Outcome blocks (XP, Gold, Achievement dispatch).
- Center: A curvature selector (Linear/Log/Exp/Step) with a live sparkline preview of the scaling shape.

**Zone B — The Laboratory (Simulation & Safety)**
- "Run Simulation" button replays the last N events from the Event Lake against the *draft* rule.
- Side-by-side diff: current rewards vs. proposed rewards.
- "Why" trace: per-event breakdown of which predicates passed and what math was applied.

**Zone C — The Taxonomy Browser (Discovery)**
- Browseable list of every event type the bot has observed.
- New interaction types appear automatically.
- Click-to-create: "Create a Rule for this Event Type."

**Zone D — Projection Dashboard (Operational Feedback)**
- Growth trend histograms, not just totals.
- Admins can validate that scaling curves are working as intended (e.g., "Is my log curve suppressing farmers?").

---

## 11) Marketplace Architecture (Approved Design)

**Philosophy:** Same "Firewall" principle — items are data, not hardcoded logic.

**Pricing:** Each item exposes `cost_xp` (nullable) and `cost_gold` (nullable). The creation form controls which currencies are active. If both are set, user chooses at purchase time.

**Currency Naming:** Internal economic variables remain canonical (`xp`, `gold`) for schema and APIs. Admins may define display labels in UI copy/settings (e.g., rename XP to "Kudos") without changing storage field names.

**Item Types:**
- `COSMETIC_BADGE` — Dashboard-only icon displayed on leaderboards/profiles.
- `CUSTOM_ROLE_COLOR` — References a Discord role created manually in the server. Bot auto-assigns on purchase.
- `PROFILE_THEME` — Dashboard accent colors/backgrounds.
- `TITLE` — Custom subtitle displayed under username.

**Scope Boundary:** Marketplace remains cosmetic-only. No channel access locks, permission grants, or moderation powers are sold through shop items.

**Economy Rules:**
- Purchases are one-way (no refunds, no trading, no gifting).
- Seasonal items expire via `expires_at` or `season_id`.
- Role assignment is automatic on purchase (bot has `manage_roles`).
- If role assignment fails, inventory record is preserved and failure is logged.

**SVG Overlay System:**
- Decorative SVG borders/frames composited client-side over item and achievement icons.
- Synapse ships a set of default overlays.
- Admins can upload custom SVGs via the Media Library.
- Items and achievements reference overlays by `overlay_id`.

**Media Library (Evolving):**
- Existing implementation: flat file storage, SVGs already supported.
- Required addition: `media_folders` table + `folder_id` FK on `media_files` for organized navigation.
- Folders are admin-managed (create, rename, delete-if-empty).
- No role/permission tiering on folders — all admins see all media.

---

## 12) Out of Scope (Current Cycle)

- Multi-guild dashboards/admin controls.
- Cross-guild ranking or pooled economy logic.
- Heavy distributed infrastructure for cloud-scale orchestration.
- Advanced graph-driven abuse detection beyond deterministic baseline heuristics.
- Marketplace item trading, gifting, or refunds.

---

## 13) Change Control

If any task conflicts with this contract:
- pause implementation,
- capture the conflict in the tracker,
- and resolve scope before code changes continue.
