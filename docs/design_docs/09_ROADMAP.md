# 09 — Roadmap

> *Ship the loop first.  Then make the loop configurable.*

---

## 9.1 Phase Overview

| Phase | Name | Focus | Status |
|-------|------|-------|--------|
| **P0** | Foundation | Scaffold, DB, Bot online, basic XP | ✅ Done |
| **P1** | Reward Engine | Zone system, quality modifiers, economy + seasons | ✅ Done |
| **P2** | Achievements | Templates, auto-award pipeline, Star economy | ✅ Done |
| **P3** | Admin Panel | SvelteKit + FastAPI dashboard | ✅ Done |
| **P3.5** | Dashboard Polish | Cyber-industrial aesthetic, UX improvements | ✅ Done |
| **P4** | Event Lake | Data vacuum, gateway capture, REST backfill | 🔜 Next |
| **P5** | Ledger Abstraction | Configurable currencies, wallets, transactions | 📋 Planned |
| **P6** | Rules Engine | IFTTT trigger/condition/effect system | 📋 Planned |
| **P7** | Milestones v2 | Requirements against ledger + lake | 📋 Planned |
| **P8** | Admin UX Overhaul | Modules, presets, taxonomy, rule builder | 📋 Planned |
| **P9** | Recipes & Sharing | Community-contributed presets and templates | 💭 Backlog |
| **P10** | Intelligence | AI quality assessment, smart suggestions | 💭 Backlog |

---

## 9.2 The v4.0 Pivot

Phases P0–P3.5 built a **working gamification bot** for student clubs.
Starting with P4, Synapse pivots to a **modular community operating
system** — the same bot and dashboard, but rebuilt for configurability.

### Why Now?

- The current system works, but it's hardcoded for one use case.
- Every new community type (nonprofit, guild, study group) would require
  code changes.
- The Event Lake and Ledger Abstraction are foundational infrastructure
  that must be built before the Rules Engine can exist.

### The Three Pillars

These three pillars must be designed simultaneously but built sequentially:

```
P4: Event Lake    →  P5: Ledger    →  P6: Rules Engine
    (data in)         (currency)       (decisions)
```

Each pillar depends on the one before it.  Rules can't trigger ledger
transactions if the ledger doesn't exist.  The ledger can't track
event-driven rewards if the event lake doesn't capture events.

---

## 9.3 Phase Details

### Phase 0 — Foundation ✅

- [x] Project scaffolding with `uv`
- [x] SQLAlchemy 2.0 models
- [x] discord.py bot with hybrid commands
- [x] PostgreSQL in Docker
- [x] Dockerfile + docker-compose.yml
- [x] Bot online, slash commands synced

### Phase 1 — Reward Engine ✅

- [x] Zone system (zones, channels, multipliers)
- [x] Seasons table and active-season management
- [x] `SynapseEvent` dataclass and `InteractionType` enum
- [x] Quality modifier pipeline (length, code blocks, links, emoji)
- [x] Reaction velocity cap + anti-gaming checks
- [x] `reward_service.py` 5-stage pipeline
- [x] `user_stats` table for per-zone accumulation
- [x] Seed script for default zones + multipliers
- [x] Minimal Gold sink (`/buy-coffee`)
- [x] `admin_log` table + audit logging
- [x] Idempotent event insert (source_event_id + UPSERT)
- [x] PG LISTEN/NOTIFY cache invalidation
- [x] Unit tests for reward pipeline

### Phase 2 — Achievements ✅

- [x] `achievement_templates` + `user_achievements` tables
- [x] `AchievementChecker` service with 4 requirement types
- [x] Auto-check pipeline on XP/Star award
- [x] Achievement announcement embeds
- [x] `/achievements` command + `/grant-achievement`
- [x] 11 seed achievements
- [x] Rarity tiers (Common → Legendary)
- [x] User preferences + announcement opt-out
- [x] Announcement channel throttle

### Phase 3 — Admin Panel ✅

- [x] FastAPI REST API with typed endpoints
- [x] SvelteKit dashboard with Tailwind + Chart.js
- [x] Discord OAuth → JWT authentication
- [x] Zone management (CRUD)
- [x] Achievement builder
- [x] Manual award page
- [x] Overview, leaderboard, activity, achievement gallery
- [x] Settings editor
- [x] Audit log viewer

### Phase 3.5 — Dashboard Polish ✅

- [x] Cyber-industrial aesthetic (dark theme, glow effects)
- [x] Human-friendly settings labels + grouped categories
- [x] Zone UI improvements (icons, channel formatting)
- [x] Achievement rarity badges with glow
- [x] Leaderboard XP progress bars + champion spotlight
- [x] Hero header with animated gradients
- [x] Improved empty states with CTAs
- [x] Audit log visual diffs (key-by-key green/red)
- [x] SynapseLoader component
- [x] Sidebar polish + hover effects

---

### Phase 4 — Event Lake 🔜

Priority: **Critical.**  This is the foundation for everything after P3.

The Event Lake captures the ephemeral gateway events that Discord does not
persist.  Design informed by the Discord Gateway Events & API Capabilities
Audit (Feb 2026).  See [03B_DATA_LAKE.md](03B_DATA_LAKE.md) for the full
design and [PLAN_OF_ATTACK_P4.md](../PLAN_OF_ATTACK_P4.md) for the
implementation plan.

#### Week 1: Schema & Core Capture

- [ ] Alembic migration: create `event_lake` table (JSONB payload,
      partial indexes on user_id, event_type, channel_id, timestamp;
      unique partial index on source_id for idempotency)
- [ ] Alembic migration: create `event_counters` table (composite PK)
- [ ] Configure gateway intents: 4 standard (GUILDS, GUILD_MESSAGES,
      GUILD_MESSAGE_REACTIONS, GUILD_VOICE_STATES) + 2 privileged
      (MESSAGE_CONTENT, GUILD_MEMBERS); explicitly disable PRESENCES
- [ ] `EventLakeWriter` service: normalize gateway events → lake rows,
      update counters transactionally, idempotent via source_id
- [ ] `social.py` cog: capture `message_create` events (extract quality
      metadata in-memory, discard raw text)
- [ ] `reactions.py` cog: capture `reaction_add` / `reaction_remove`
      via `on_raw_reaction_add` / `on_raw_reaction_remove` (cache-safe)
- [ ] `threads.py` cog: capture `thread_create`

#### Week 2: Voice & Membership

- [ ] `voice.py` cog: decompose VOICE_STATE_UPDATE into `voice_join`,
      `voice_leave`, `voice_move` derived events
- [ ] Voice session pairing: match join/leave by session_id, compute
      `duration_seconds` on leave
- [ ] AFK channel exclusion: auto-detect `guild.afk_channel_id`,
      read admin-configured non-tracked channels from zone config,
      detect idle state (`self_mute AND self_deaf` for entire session),
      tag with `is_afk: true`
- [ ] Membership cog (or extend existing): capture `member_join` /
      `member_leave` (GUILD_MEMBERS intent)
- [ ] Bot graceful shutdown: flush in-flight voice sessions as leave
      events on SIGTERM

#### Week 3: Infrastructure & Migration

- [ ] Retention cleanup job: daily CRON deletes events + daily counters
      beyond admin-configured retention window (default 90 days)
- [ ] Counter reconciliation job: weekly CRON validates counter accuracy
      against raw Event Lake aggregates
- [ ] REST API endpoints: event volume, event breakdown by type/zone,
      storage estimate, retention status
- [ ] Migration bridge: back-populate Event Lake from `activity_log`
      (one-time script, idempotent via source_id mapping)
- [ ] Bot reconnect safety: handle Gateway resume/reconnect without
      double-counting (source_id idempotency is backbone)

#### Week 4: Dashboard & Testing

- [ ] Dashboard: Data Sources configuration page (toggle capture per
      event type, configure voice AFK exclusion channels, set retention)
- [ ] Dashboard: storage estimate display (~333 MB for 500 members at
      90 days, computed from actual counters)
- [ ] Dashboard: event volume chart (events/hour, events/day by type)
- [ ] Integration tests: event capture (message, reaction, voice, thread,
      member), idempotency, counter accuracy, retention cleanup
- [ ] Load test: simulate 500-member activity and verify storage budget
      (~3.7 MB/day, ~22K events/day)

**Deliverable:** Every qualifying Discord event lands in the Event Lake
in real-time.  The dashboard shows a data sources panel with storage
estimates.  Voice sessions are tracked with AFK filtering.  The old
`activity_log` table continues to work alongside the Event Lake during
the transition.

**Research:** ✅ Complete.  All gateway event payloads, privileged intent
requirements, discord.py raw event behaviors, rate limits, and storage
estimates are documented in [03B_DATA_LAKE.md](03B_DATA_LAKE.md) and
the [audit report](../Discord%20API%20Audit%20for%20Synapse.md).

---

### Phase 5 — Ledger Abstraction 📋

Priority: **High.**  Replaces hardcoded XP/Gold with configurable
currencies.

See [03_CONFIGURABLE_ECONOMY.md](03_CONFIGURABLE_ECONOMY.md).

- [ ] Create `currencies` table (admin-defined)
- [ ] Create `wallets` table (user_id × currency_id)
- [ ] Create `transactions` table (append-only ledger)
- [ ] Migrate existing `users.xp` and `users.gold` into wallets
  (one-time script — no production data, but for dev parity)
- [ ] Create `season_snapshots` table for seasonal currency resets
- [ ] Implement `LedgerService` (credit, debit, transfer, balance query)
- [ ] Wire dashboard leaderboard to read from wallets instead of
      `users.xp`
- [ ] Wire dashboard overview metrics to wallet aggregates
- [ ] Dashboard: Currency Management page (CRUD currencies)
- [ ] Seed default currencies (XP, Gold, Stars) for Classic Gamification
      preset
- [ ] Update `/profile` command to read from wallets
- [ ] Write unit tests for ledger operations (double-entry integrity)

**Deliverable:** Admins can define currencies.  The leaderboard, profile,
and dashboard all read from wallets.  Transactions provide a full audit
trail.

---

### Phase 6 — Rules Engine 📋

Priority: **High.**  Replaces hardcoded Reward Engine with configurable
rules.

See [05_RULES_ENGINE.md](05_RULES_ENGINE.md).

- [ ] Create `rules` table (JSONB rule documents)
- [ ] Implement `RuleEngine` (trigger matching → condition evaluation →
      effect execution)
- [ ] Implement condition registry (built-in condition types)
- [ ] Implement effect registry (built-in effect types)
- [ ] Implement amount expression evaluator (sandboxed arithmetic)
- [ ] Wire Event Lake events to Rules Engine
- [ ] Implement `milestone_check` effect
- [ ] Implement event chaining (internal events trigger further rules)
- [ ] PG NOTIFY for hot-reload of rules
- [ ] Dashboard: Rule List page (grouped by module, enable/disable)
- [ ] Dashboard: Rule Editor (trigger + conditions + effects builder)
- [ ] Dashboard: Preset Import (one-click rule set import)
- [ ] Dashboard: Dry Run (paste event JSON, see which rules fire)
- [ ] Seed Classic Gamification preset rules
- [ ] Deprecate old `reward_service.py` (keep as fallback behind feature
      flag)
- [ ] Write unit + integration tests for rule evaluation

**Deliverable:** The 5-stage hardcoded pipeline is replaced by
configurable rules.  Admins can create, edit, and disable rules without
code changes.  The Classic Gamification preset reproduces v3.0 behavior
exactly.

---

### Phase 7 — Milestones v2 📋

Priority: **Medium.**  Adapts achievements to work against the new data
model.

See [06_MILESTONES.md](06_MILESTONES.md).

- [ ] Migrate `achievement_templates` to `milestone_templates` (schema
      upgrade: requirement types → requirement expressions)
- [ ] Implement milestone checker that queries wallets + Event Lake
- [ ] Implement compound requirements (AND/OR)
- [ ] Implement streak requirements (consecutive active days)
- [ ] Implement seasonal scope for milestones
- [ ] Wire milestone rewards through Rules Engine
- [ ] Dashboard: Milestone Editor (requirement builder, compound UI)
- [ ] Update `/achievements` command to use milestones
- [ ] Migrate seed achievements to seed milestones
- [ ] Write unit tests for requirement evaluation

**Deliverable:** Milestones work with any configured currencies and event
types.  Compound and streak requirements are supported.

---

### Phase 8 — Admin UX Overhaul 📋

Priority: **Medium.**  Brings the dashboard up to the new platform's
configurability level.

See [07_ADMIN_PANEL.md](07_ADMIN_PANEL.md) (revision pending).

- [ ] Dashboard: Modules page (enable/disable modules with preview)
- [ ] Dashboard: Taxonomy Editor (rename internal terms → community labels)
- [ ] Dashboard: Preset Selector (first-run wizard or settings page)
- [ ] Dashboard: Data Sources panel (toggle event categories + retention)
- [ ] Dashboard: Currency Builder (define currencies with properties)
- [ ] Dashboard: Rule Templates gallery (save/load rule templates)
- [ ] Dashboard: Onboarding wizard (guided setup for new communities)
- [ ] API: Module enable/disable endpoints
- [ ] API: Taxonomy CRUD endpoints
- [ ] API: Preset import endpoints

**Deliverable:** A new community operator can go from "fresh bot install"
to "fully configured for my use case" through the dashboard alone, without
touching config files or code.

---

### Phase 9 — Recipes & Sharing 💭

Priority: **Low.**  Not committed.

- [ ] Export a community's full configuration as a "Recipe" (JSON/YAML)
- [ ] Import recipes (rules + currencies + milestones + taxonomy)
- [ ] Recipe marketplace (community-contributed presets)
- [ ] Recipe diff viewer (compare your config to a recipe before importing)

**Entry Gate:** P6–P8 complete and stable for at least 2 months.

---

### Phase 10 — Intelligence 💭

Priority: **Low.**  Not committed.

- [ ] LLM quality assessment slot in the Rules Engine (optional condition
      type that calls an LLM API for message quality scoring)
- [ ] AI-generated milestone suggestions based on server activity patterns
- [ ] Weekly digest generation (natural language summaries)
- [ ] Smart rule recommendations ("Your server has high voice activity but
      no voice-related rules")

**Entry Gate:** Core loop + admin workflows stable.  Monthly cloud spend
within budget.

---

## 9.4 Migration Strategy

There is no production data to migrate.  The v3.0 → v4.0 transition is a
**clean pivot**, not a migration.

However, the codebase transitions incrementally:

1. **P4:** Event Lake is additive.  The old `activity_log` continues to
   work.  Bot cogs emit to both.
2. **P5:** Ledger tables are new.  A one-time script copies dev `users.xp`
   and `users.gold` into wallets for testing parity.
3. **P6:** Rules Engine runs alongside old `reward_service.py` behind a
   feature flag.  When validated, the old service is deprecated.
4. **P7:** Milestones coexist with old achievements during transition.

At no point does the system become non-functional.  Each phase adds new
capabilities while maintaining backward compatibility.

---

## 9.5 Deferred Decisions

| Decision | Status | Revisit When |
|----------|--------|-------------|
| Alembic migrations | Deferred | P4 start (Event Lake is the first schema-breaking change) |
| LLM provider choice | Deferred | Phase 10 begins |
| Redis cache layer | Deferred | >10k active members or >100 rules |
| Async SQLAlchemy | Rejected | Sync + `asyncio.to_thread()` works |
| GitHub webhook integration | Deferred | After Rules Engine (P6) — becomes a custom event source |
| Mobile companion app | Deferred | Post-v1 if demand exists |
| Recipe marketplace hosting | Deferred | Phase 9 scoping |

---

## 9.6 Success Metrics

| Metric | Target | Measured By |
|--------|--------|-------------|
| Event capture completeness | >99.5% of gateway events ingested | Event Lake count vs. Discord audit |
| Rule evaluation latency | <5ms per event (50 rules) | Instrumented timer in Rules Engine |
| Time to configure new community | <15 minutes | First-run wizard completion time |
| Currency flexibility | ≥1 deployment with non-XP primary currency | User feedback |
| Preset adoption | >80% of new deployments start from a preset | Analytics |
| Dashboard self-service | Zero code changes needed for configuration | Support ticket count = 0 |

---

## Decisions

> **Decision D09-01:** Phase-Gated Delivery (Retained)
> - **Status:** Accepted (Updated for v4.0)
> - **Context:** Trying to build everything at once leads to nothing shipping.
> - **Choice:** Strict phase ordering.  P4 ships before P5 starts.
>   Exception: P4–P6 are *designed* simultaneously but *built*
>   sequentially.
> - **Consequences:** Each phase is a usable product increment.

> **Decision D09-02:** Clean Pivot, Not Migration
> - **Status:** Accepted (New in v4.0)
> - **Context:** There is no production data.  The system is in development.
> - **Choice:** New tables and services are additive.  Old code runs alongside
>   new code behind feature flags until the new path is validated.
> - **Consequences:** No migration scripts needed.  No downtime.  No data
>   loss risk.

> **Decision D09-03:** Design Three Pillars Simultaneously
> - **Status:** Accepted (New in v4.0)
> - **Context:** The Event Lake, Ledger, and Rules Engine are tightly
>   coupled in their interfaces.
> - **Choice:** Design all three in P4 docs/design.  Build them in sequence
>   (P4 → P5 → P6).
> - **Consequences:** Avoids rework.  Each pillar's API contract is known
>   before implementation begins.

> **Decision D09-04:** Intelligence Remains Hard-Gated
> - **Status:** Retained from v3.0
> - **Context:** LLM features are high-risk for cost and scope drift.
> - **Choice:** P10 stays in backlog until P6–P8 are stable.
> - **Consequences:** Focus stays on configurable foundations first.
