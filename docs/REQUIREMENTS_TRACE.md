# Requirements Traceability Matrix

> Maps every major design requirement to implementation files and tests.
> Status: ✅ Implemented | 🔧 In Progress | ⏳ Deferred | ❌ Not Started

---

## Database Schema (04_DATABASE_SCHEMA.md)

| Req ID | Requirement | Source | Implementation | Tests | Status |
|--------|-------------|--------|---------------|-------|--------|
| DB-01 | `users` table with Discord snowflake PK | §4.3 | `synapse/database/models.py` | — | ✅ |
| DB-02 | `user_stats` table (per-season counters) | §4.3 | `synapse/database/models.py` | — | ✅ |
| DB-03 | `seasons` table with guild-scoped active flag | §4.3 | `synapse/database/models.py` | — | ✅ |
| DB-04 | `activity_log` with idempotent insert | §4.3, D04-07 | `synapse/database/models.py` | — | ✅ |
| DB-05 | `zones` table with guild_id | §4.3 | `synapse/database/models.py` | — | ✅ |
| DB-06 | `zone_channels` mapping table | §4.3 | `synapse/database/models.py` | — | ✅ |
| DB-07 | `zone_multipliers` per-zone per-event-type | §4.3 | `synapse/database/models.py` | — | ✅ |
| DB-08 | `achievement_templates` with requirement types | §4.3 | `synapse/database/models.py` | — | ✅ |
| DB-09 | `user_achievements` earned badges | §4.3 | `synapse/database/models.py` | — | ✅ |
| DB-10 | `quests` with guild_id and gold_reward | §4.3 | `synapse/database/models.py` | — | ✅ |
| DB-11 | `admin_log` append-only audit trail | §4.3, D04-06 | `synapse/database/models.py` | — | ✅ |
| DB-12 | `user_preferences` opt-out table | §4.3 | `synapse/database/models.py` | — | ✅ |
| DB-13 | Partial unique index on (source_system, source_event_id) | §4.4 | `synapse/database/models.py` | — | ✅ |
| DB-14 | All performance indexes per §4.4 | §4.4 | `synapse/database/models.py` | — | ✅ |
| DB-15 | metadata JSONB column on activity_log | §4.6 | `synapse/database/models.py` | — | ✅ |

## Reward Engine (05_REWARD_ENGINE.md)

| Req ID | Requirement | Source | Implementation | Tests | Status |
|--------|-------------|--------|---------------|-------|--------|
| RE-01 | `SynapseEvent` dataclass | §5.2 | `synapse/engine/events.py` | — | ✅ |
| RE-02 | `InteractionType` enum with base XP/Stars | §5.2 | `synapse/engine/events.py` | — | ✅ |
| RE-03 | Zone classification stage | §5.4 | `synapse/engine/reward.py` | `tests/test_reward_engine.py` | ✅ |
| RE-04 | Multiplier lookup stage | §5.5 | `synapse/engine/reward.py` | `tests/test_reward_engine.py` | ✅ |
| RE-05 | Quality modifier stage (messages only) | §5.6 | `synapse/engine/reward.py` | `tests/test_reward_engine.py` | ✅ |
| RE-06 | Anti-gaming checks (unique-reactor, per-user caps, diminishing returns) | §5.7 | `synapse/engine/reward.py` | `tests/test_anti_gaming.py` | ✅ |
| RE-07 | Reaction velocity cap (XP) | §5.8 | `synapse/engine/reward.py` | `tests/test_reward_engine.py` | ✅ |
| RE-08 | `RewardResult` output structure | §5.10 | `synapse/engine/reward.py` | — | ✅ |
| RE-09 | Achievement check pipeline | §6.5 | `synapse/engine/achievements.py` | `tests/test_achievements.py` | ✅ |
| RE-10 | LLM quality assessment slot (disabled) | §5.9, D05-02 | `synapse/engine/reward.py` | — | ✅ |
| RE-11 | PG LISTEN/NOTIFY cache invalidation | §5.12, D05-08 | `synapse/engine/cache.py` | `tests/test_cache.py` | ✅ |

## Dual Economy (03_DUAL_ECONOMY.md)

| Req ID | Requirement | Source | Implementation | Tests | Status |
|--------|-------------|--------|---------------|-------|--------|
| EC-01 | XP → Levels (quality-weighted) | §3.2, §3.4 | `synapse/engine/reward.py` | `tests/test_reward_engine.py` | ✅ |
| EC-02 | Stars → Achievements (participation) | §3.2 | `synapse/engine/reward.py` | `tests/test_reward_engine.py` | ✅ |
| EC-03 | Season stars + lifetime stars | §3.5 | `synapse/services/reward_service.py` | `tests/test_reward_engine.py` | ✅ |
| EC-04 | Gold with minimal sink | §3.6, D03-06 | `synapse/bot/cogs/meta.py` | — | ✅ |
| EC-05 | Star anti-gaming (unique-reactor, caps, diminishing) | §3.7, D03-07 | `synapse/engine/reward.py` | `tests/test_anti_gaming.py` | ✅ |
| EC-06 | Voice earns Stars only | §3.4, D03-04 | `synapse/engine/reward.py` | `tests/test_reward_engine.py` | ✅ |

## Achievements (06_ACHIEVEMENTS.md)

| Req ID | Requirement | Source | Implementation | Tests | Status |
|--------|-------------|--------|---------------|-------|--------|
| AC-01 | 4 requirement types (counter, star, xp_milestone, custom) | §6.3 | `synapse/engine/achievements.py` | `tests/test_achievements.py` | ✅ |
| AC-02 | Rarity tiers (common→legendary) | §6.4 | `synapse/database/models.py` | — | ✅ |
| AC-03 | Achievement check pipeline after reward calc | §6.5 | `synapse/engine/achievements.py` | `tests/test_achievements.py` | ✅ |
| AC-04 | Announcement opt-out check | §6.5, D06-04 | `synapse/bot/cogs/social.py` | — | ✅ |
| AC-05 | Channel announcement throttle (3/channel/60s) | §6.5, D06-05 | `synapse/bot/cogs/social.py` | — | ✅ |
| AC-06 | `/award` command | §6.6 | `synapse/bot/cogs/admin.py` | — | ✅ |
| AC-07 | `/grant-achievement` command | §6.6 | `synapse/bot/cogs/admin.py` | — | ✅ |
| AC-08 | Seed 11 default achievements | §6.8 | `synapse/services/seed.py` | — | ✅ |
| AC-09 | `/profile` shows achievements | §6.7 | `synapse/bot/cogs/meta.py` | — | ✅ |

## Admin Panel (07_ADMIN_PANEL.md)

| Req ID | Requirement | Source | Implementation | Tests | Status |
|--------|-------------|--------|---------------|-------|--------|
| AP-01 | Public Club Pulse (leaderboard, activity, achievements) | §7.7 | `dashboard/src/routes/` (overview, leaderboard, activity, achievements) | — | ✅ |
| AP-02 | Admin zone CRUD | §7.4 | `synapse/api/routes/admin.py`, `dashboard/src/routes/admin/zones/` | — | ✅ |
| AP-03 | Admin achievement builder | §7.5 | `synapse/api/routes/admin.py`, `dashboard/src/routes/admin/achievements/` | — | ✅ |
| AP-04 | Admin manual awards | §7.6 | `synapse/api/routes/admin.py`, `dashboard/src/routes/admin/awards/` | — | ✅ |
| AP-05 | Discord OAuth session gate | §7.8 | `synapse/api/auth.py`, `dashboard/src/routes/auth/callback/` | — | ✅ |
| AP-06 | Role check for ADMIN_ROLE_ID | §7.8 | `synapse/api/auth.py`, `synapse/api/deps.py` | — | ✅ |
| AP-07 | Per-action audit logging | §7.9, D07-05 | `synapse/services/admin_service.py` | — | ✅ |
| AP-08 | Soft rate-limiting (30 mutations/min) | §7.8 | `synapse/api/routes/admin.py` | — | ✅ |
| AP-09 | NOTIFY config_changed after commits | §7.9 | `synapse/services/admin_service.py` | `tests/test_cache.py` | ✅ |

## Bot Architecture (02_ARCHITECTURE.md)

| Req ID | Requirement | Source | Implementation | Tests | Status |
|--------|-------------|--------|---------------|-------|--------|
| BOT-01 | Four-service topology (db, bot, api, dashboard) | §2.1 | `docker-compose.yml` | — | ✅ |
| BOT-02 | SynapseEvent normalization layer | §2.2 | `synapse/engine/events.py` | — | ✅ |
| BOT-03 | social.py cog (on_message → SynapseEvent) | §2.4 | `synapse/bot/cogs/social.py` | — | ✅ |
| BOT-04 | reactions.py cog | §2.4 | `synapse/bot/cogs/reactions.py` | — | ✅ |
| BOT-05 | voice.py cog | §2.4 | `synapse/bot/cogs/voice.py` | — | ✅ |
| BOT-06 | admin.py cog (/award, /create-achievement, /grant-achievement) | §2.4 | `synapse/bot/cogs/admin.py` | — | ✅ |
| BOT-07 | meta.py (/profile, /leaderboard, /preferences) | §2.4 | `synapse/bot/cogs/meta.py` | — | ✅ |
| BOT-08 | Idempotent event persistence | §2.2, D02-06 | `synapse/services/reward_service.py` | — | ✅ |

## Deployment (08_DEPLOYMENT.md)

| Req ID | Requirement | Source | Implementation | Tests | Status |
|--------|-------------|--------|---------------|-------|--------|
| DEP-01 | Docker Compose with 4 services | §8.2 | `docker-compose.yml` | — | ✅ |
| DEP-02 | Multi-stage Dockerfile | §8.3 | `Dockerfile` | — | ✅ |
| DEP-03 | Compose Watch for live reload | §8.2 | `docker-compose.yml` | — | ✅ |
| DEP-04 | .env for secrets, config.yaml for soft config | §8.6 | `.env.example`, `config.yaml` | — | ✅ |
| DEP-05 | Required env vars documented | §8.6 | `README.md` | — | ✅ |

## Deferred (per D05-02, D09-03, and Roadmap)

| Req ID | Requirement | Source | Status | Notes |
|--------|-------------|--------|--------|-------|
| DEF-01 | LLM quality assessment | 05 §5.9 | ⏳ Deferred | Pipeline slot present, disabled by default |
| DEF-02 | GitHub webhook integration | 09 P4 | ⏳ Deferred | github.py cog placeholder only |
| DEF-03 | TryHackMe integration | 09 P4 | ⏳ Deferred | — |
| DEF-04 | Full Gold shop | 09 stretch | ⏳ Deferred | Minimal sink (/buy-coffee) implemented |
| DEF-05 | Alembic migrations | D04-03 | ⏳ Deferred | create_all() for now |
| DEF-06 | Redis cache layer | D08-03 | ⏳ Deferred | PG LISTEN/NOTIFY used instead |
| DEF-07 | Voice idle detection (mute+deafen) | 05 §5.8 | ✅ | Anti-idle check + hourly tick cap implemented |
