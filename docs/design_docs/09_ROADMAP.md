# 09 — Roadmap & Future Work

> *Ship the loop first, decorate later.*

---

## 9.1 Phase Overview

| Phase | Name | Focus | Est. Duration |
|-------|------|-------|---------------|
| **P0** | Foundation ✅ | Scaffold, DB, Bot online, basic XP | Done |
| **P1** | Reward Engine ✅ | Zone system, quality modifiers, dual economy + seasons | Done |
| **P2** | Achievements ✅ | Templates, auto-award pipeline, Star economy | Done |
| **P3** | Admin Panel ✅ | SvelteKit + FastAPI dashboard for club leaders | Done |
| **P4** | Webhooks & Integrations | GitHub events, TryHackMe (opt-in) | 2 weeks |
| **P5** | Intelligence | AI quest generation, LLM quality assessment (gated) | Backlog |

---

## 9.2 Phase Details

### Phase 0 — Foundation ✅ (Complete)

- [x] Project scaffolding with `uv`
- [x] SQLAlchemy 2.0 models (User, Quest, ActivityLog)
- [x] discord.py bot with hybrid commands
- [x] PostgreSQL in Docker
- [x] Dockerfile (multi-stage) + docker-compose.yml
- [x] Bot online, slash commands synced

### Phase 1 — Reward Engine ✅ (Complete)

Priority: **Highest.** This is the core differentiator.

- [x] New database tables: `zones`, `zone_channels`, `zone_multipliers`
- [x] Add `seasons` table and active-season management
- [x] Add `season_id` to `activity_log` and `user_stats`
- [x] Add index `activity_log(zone_id, timestamp)`
- [x] Expand `users` table: keep XP/level/gold, move seasonal counters to `user_stats`
- [x] Create `SynapseEvent` dataclass as the universal event envelope
- [x] Implement `InteractionType` enum (message, reply, thread_create,
      reaction_add, voice_join, voice_leave, file_share, command_use)
- [x] Implement Zone lookup service (channel → zone → multipliers)
- [x] Implement Quality Modifier pipeline (length, code blocks, links,
      emoji spam penalty)
- [x] Reaction velocity cap (max 3-5 XP-bearing reactions per message)
- [x] Refactor `social.py` cog to emit `SynapseEvent` objects
- [x] Create `reward_service.py` with the 5-stage pipeline
- [x] Add `user_stats` table for per-zone accumulation
- [x] Create seed script for default zones + multipliers
- [x] Add minimal Gold sink (e.g., `/buy-coffee`) so spendable currency has immediate utility
- [x] Add `admin_log` table and shared service-layer audit logging (D04-06)
- [x] Add `source_system` + `source_event_id` to `activity_log` with partial unique index (D04-07)
- [x] Idempotent event insert: `ON CONFLICT DO NOTHING` in persistence layer (D02-06)
- [x] Implement Star anti-gaming checks: unique-reactor weighting, per-user per-target caps, diminishing returns (D03-07)
- [x] PG LISTEN/NOTIFY cache invalidation for config caches (D05-08)
- [x] Write unit tests for the reward pipeline

**Deliverable:** Any message, reaction, or thread in Discord flows through the
full reward engine.  Leaders can reconfigure zones without code changes.

### Phase 2 — Achievements ✅ (Complete)

Priority: **High.** The "collection" half of the dual economy.

- [x] `achievement_templates` table + `user_achievements` table
- [x] Create `AchievementChecker` service
- [x] Implement 4 requirement types: threshold, count, streak, manual
- [x] Auto-check pipeline: on every XP/Star award, check eligible
      achievements
- [x] Achievement announcement embeds in configured channels
- [x] `/achievements` command (gallery view)
- [x] `/grant-achievement` admin command (manual awards)
- [x] Seed 11 starter achievements (see doc 06)
- [x] Rarity tiers with visual distinction (Common → Legendary)
- [x] Add `user_preferences` table and `/preferences` slash command (D01-04)
- [x] Implement announcement opt-out checks in achievement pipeline (D06-04)
- [x] Implement announcement channel throttle (D06-05)

**Deliverable:** Achievements trigger automatically and are visible in profiles.

### Phase 3 — Admin Panel ✅ (Complete)

Priority: **Medium.** Club leaders need self-service configuration.

- [x] FastAPI REST API with typed endpoints (`synapse/api/`)
- [x] SvelteKit dashboard with Tailwind CSS + Chart.js (`dashboard/`)
- [x] Discord OAuth → JWT admin authentication
- [x] Zone Management page (CRUD zones, channels, multipliers)
- [x] Achievement Builder page (create/edit templates)
- [x] Manual Award page (XP/Gold/achievements to members)
- [x] Overview page (hero banner, metrics cards, Chart.js activity charts)
- [x] Leaderboard page (XP and Stars tabs)
- [x] Activity page (daily message/XP charts, last 30 days)
- [x] Achievement gallery (rarity badges, member counts)
- [x] Settings editor (key-value config management)
- [x] Audit log viewer (before/after JSON diffs)
- [x] Discord avatar integration (CDN URL construction)


**Deliverable:** Club leaders can manage ALL configuration without touching
code, YAML, or SQL.

### Phase 4 — Webhooks & Integrations

Priority: **Medium.** Extends XP beyond Discord.

- [ ] GitHub webhook receiver module integrated with bot/deployment boundary
- [ ] GitHub events: push, pull_request, issue_comment, review
- [ ] GitHub → SynapseEvent adapter (reuses the same pipeline)
- [ ] `/link-github` improvements (verify ownership via OAuth)
- [ ] TryHackMe API adapter (opt-in, cybersecurity clubs)
- [ ] Google Calendar adapter (meeting attendance, deferred)

**Deliverable:** Commits and PRs earn XP through the same reward pipeline.

### Phase 5 — Intelligence (Hard-Gated)

Priority: **Low.** Not started until P1-P3 reliability targets are met.

- [ ] LLM quality assessment slot in the reward pipeline
- [ ] AI-generated quests based on user activity patterns
- [ ] Smart achievement suggestions for club leaders
- [ ] Weekly digest generation (natural language summaries)

**Deliverable:** LLM augments (but never gates) the core XP loop.

**Entry gate for P5:**
- Reward pipeline and seasonal leaderboards stable for one full academic cycle.
- Admin workflows used successfully by club leads without developer intervention.
- Monthly cloud spend remains within budget limits.

---

## 9.3 Deferred Decisions

These were discussed but intentionally deferred:

| Decision | Status | Revisit When |
|----------|--------|-------------|
| Alembic migrations | Deferred | Before first schema migration beyond P0 |
| LLM provider choice | Deferred | Phase 5 begins |
| Mobile companion app | Deferred | Post-v1 if demand exists |
| TryHackMe integration | Deferred | Cybersecurity club on-boards |
| Google Calendar sync | Deferred | Meeting tracking requested by club |
| Redis cache layer | Deferred | >10k active members |
| Async SQLAlchemy | Rejected | Sync + `asyncio.to_thread()` works, no revisit planned |
| Full Gold shop economy | Deferred | After validating minimal sink usage in P1 |

---

## 9.4 Stretch Goals (v2+)

These are not committed but represent potential future direction:

- **Shop System:** Spend Gold on cosmetic roles, profile badges, custom
  embed colors.
- **Team Quests:** Multi-user objectives ("Squad ships 3 PRs this week").
- **Cross-Club Leaderboard:** University-wide leaderboard across all clubs.
- **Resume Export:** Generate a PDF/Markdown summary of a student's
  achievements, contributions, and stats for job applications.
- **Club Analytics Dashboard:** Trend analysis, cohort retention curves,
  event ROI metrics for faculty sponsors.
- **Notification Preferences:** Per-user settings for which announcements
  they receive (DM vs. channel vs. off).  *(Core opt-out moved to P2;
  extended DM routing remains stretch.)*

---

## 9.5 Success Metrics

How we know Synapse is working:

| Metric | Target | Measured By |
|--------|--------|-------------|
| Weekly active participants | ≥60% of club members | Discord ID count with ≥1 event/week |
| Messages per zone per week | Increasing trend | `activity_log` aggregation |
| Achievements earned per member | ≥3 within first month | `user_achievements` count |
| Admin panel adoption | All clubs self-managing | Login frequency per club |
| Time from code to XP | <2 seconds | Event timestamp → DB write delta |

---

## Decisions

> **Decision D09-01:** Phase-Gated Delivery
> - **Status:** Accepted
> - **Context:** Trying to build everything at once leads to nothing shipping.
> - **Choice:** Strict phase ordering.  P1 ships before P2 starts.
> - **Consequences:** Each phase is a usable product increment.  Later phases
>   can be re-prioritized based on club feedback.

> **Decision D09-02:** Alembic Deferred Until P1
> - **Status:** Accepted
> - **Context:** Models are still evolving rapidly.  Running migrations during
>   scaffolding burns time.
> - **Choice:** Use `Base.metadata.create_all()` during P0.  Introduce Alembic
>   at the start of P1 when schema changes become incremental.
> - **Consequences:** No rollback capability during P0 (acceptable — dev only).

> **Decision D09-03:** Intelligence Is Reliability-Gated
> - **Status:** Accepted
> - **Context:** LLM features are high-risk for cost and scope drift.
> - **Choice:** Keep P5 in backlog until core loop + admin operations are stable.
> - **Consequences:** Team focus stays on shipping durable foundations first.

> **Decision D09-04:** Credibility Items Promoted to P1/P2
> - **Status:** Accepted
> - **Context:** v2.2 review identified admin audit trail, idempotency,
>   anti-gaming, and announcement opt-out as credibility prerequisites.
> - **Choice:** Promote `admin_log`, idempotent insert, Star anti-gaming,
>   and PG LISTEN/NOTIFY to P1.  Promote `user_preferences` and
>   announcement throttle to P2.
> - **Consequences:** P1 scope grows moderately but ships a trustworthy core.
>   P2 adds user-facing polish.
