# 04 — Database Schema

> *The database is the source of truth.  If it's not in a table, it doesn't exist.*

---

## 4.1 Design Principles

1. **Config lives in the database, not in YAML.**  YAML is used only for
   initial seeding and local development.  In production, all zone definitions,
   multipliers, and achievement templates are rows in PostgreSQL, editable
   through the Admin Panel.

2. **Discord snowflakes are the primary key** for users.  Discord IDs are
   globally unique 64-bit integers.  Using them directly avoids a separate
   surrogate key and makes lookups from bot events O(1).

3. **Append-only where possible.**  The `activity_log` table is insert-only.
   We never update or delete log rows.  This gives us a perfect audit trail
   and makes the dashboard's time-series queries simple.  Admin config
   mutations get their own append-only `admin_log` with before/after snapshots.

4. **Soft deletes over hard deletes.**  Zones and achievements have an
   `active` flag.  Deactivating is preferred over deleting to preserve
   referential integrity in historical data.

5. **Guild-scoped by default.**  Config tables (`zones`, `seasons`,
   `achievement_templates`, `quests`) carry `guild_id` so a single database
   can serve multiple Discord servers without collision.

---

## 4.2 Entity Relationship Diagram

```
┌─────────────┐       ┌──────────────────┐       ┌──────────────────────┐
│   users     │       │   user_stats     │       │  user_achievements   │
│─────────────│       │──────────────────│       │──────────────────────│
│ id (PK)     │──1:N──│ user_id (PK,FK)  │       │ user_id (PK,FK)      │
│ discord_name│       │ season_id (PK,FK)│       │ achievement_id(PK,FK)│
│ avatar_hash │       │ messages_sent    │       │ earned_at            │
│ github_user │       │ reactions_given  │       │ granted_by           │
│ level       │       │ reactions_recv   │       └──────────┬───────────┘
│ gold        │       │ threads_created  │                  │
│ created_at  │       │ season_stars     │                  │
│ updated_at  │       └──────────────────┘                  │
└──────┬──────┘                                             │
       │                                                    │
       │ 1:N                                                │
       ▼                                                    │
┌──────────────────┐                          ┌─────────────┴──────────┐
│  activity_log    │                          │ achievement_templates  │
│──────────────────│                          │────────────────────────│
│ id (PK)          │                          │ id (PK)                │
│ user_id (FK)     │                          │ guild_id (FK)          │
│ event_type       │                          │ name                   │
│ season_id (FK)   │                          │ description            │
│ zone_id (FK)     │                          │ category               │
│ source_system    │                          │ requirement_type       │
│ source_event_id  │                          │ requirement_scope      │
│ metadata (JSONB) │                          │ requirement_field      │
│ xp_delta         │                          │ requirement_value      │
│ star_delta       │                          │ xp_reward              │
│ timestamp        │                          │ gold_reward            │
└──────────────────┘                          │ badge_image_url        │
                                              │ rarity                 │
┌─────────────┐       ┌──────────────────┐    │ announce_channel_id    │
│   zones     │       │ zone_multipliers │    │ active                 │
│─────────────│       │──────────────────│    └────────────────────────┘
│ id (PK)     │──1:N──│ id (PK)          │
│ guild_id    │       │ zone_id (FK)     │
│ name        │       │ interaction_type │
│ description │       │ xp_multiplier    │
│ created_by  │       │ star_multiplier  │
│ active      │       └──────────────────┘
│ created_at  │
└──────┬──────┘
       │ 1:N
       ▼
┌──────────────────┐
│  zone_channels   │
│──────────────────│
│ zone_id (PK,FK)  │
│ channel_id (PK)  │
└──────────────────┘

┌──────────────────┐
│     quests       │
│──────────────────│
│ id (PK)          │       ┌──────────────────┐
│ guild_id         │       │ user_preferences │
│ title            │       │──────────────────│
│ description      │       │ user_id (PK,FK)  │
│ xp_reward        │       │ announce_levelup │
│ gold_reward      │       │ announce_achieve │
│ status           │       │ announce_awards  │
│ github_issue_url │       └──────────────────┘
│ active           │
│ created_at       │
└──────────────────┘

┌──────────────────┐       ┌──────────────┐
│   admin_log      │       │   seasons    │
│──────────────────│       │──────────────│
│ id (PK)          │       │ id (PK)      │
│ actor_id (FK)    │       │ guild_id     │
│ action_type      │       │ name         │
│ target_table     │       │ starts_at    │
│ target_id        │       │ ends_at      │
│ before_snapshot  │       │ active       │
│ after_snapshot   │       └──────────────┘
│ ip_address       │
│ timestamp        │
└──────────────────┘

┌──────────────────┐
│   settings       │
│──────────────────│
│ key (PK)         │
│ value_json       │
│ category         │
│ description      │
│ updated_at       │
└──────────────────┘
```

---

## 4.3 Table Definitions

### `users` — Club Member Profiles

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `BigInteger` | PK | Discord snowflake ID.  Not auto-generated. |
| `discord_name` | `String(100)` | NOT NULL | Cached display name (updated on interaction). |
| `discord_avatar_hash` | `String(100)` | NULLABLE | Discord CDN avatar hash for UI avatar display. |
| `github_username` | `String(39)` | NULLABLE | GitHub handle (set via `/link-github`). |
| `xp` | `Integer` | DEFAULT 0 | Cumulative experience points. |
| `level` | `Integer` | DEFAULT 1 | Current level (derived from XP). |
| `gold` | `Integer` | DEFAULT 0 | Spendable currency. |
| `created_at` | `DateTime(tz)` | DEFAULT now() | First interaction timestamp. |
| `updated_at` | `DateTime(tz)` | DEFAULT now() | Last modification timestamp. |

### `user_stats` — Season-Scoped Engagement Counters

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `user_id` | `BigInteger` | PK, FK→users | User ID. |
| `season_id` | `Integer` | PK, FK→seasons | Competitive season ID. |
| `season_stars` | `Integer` | DEFAULT 0 | Stars earned in this season. |
| `lifetime_stars` | `Integer` | DEFAULT 0 | Lifetime stars for profile history. |
| `messages_sent` | `Integer` | DEFAULT 0 | Qualifying messages in this season. |
| `reactions_given` | `Integer` | DEFAULT 0 | Reactions placed in this season. |
| `reactions_received` | `Integer` | DEFAULT 0 | Reactions received in this season. |
| `threads_created` | `Integer` | DEFAULT 0 | Threads started in this season. |
| `voice_minutes` | `Integer` | DEFAULT 0 | Voice minutes in this season. |

`user_stats` now stores one row per `(user_id, season_id)` to support resets
without deleting historical data.

### `seasons` — Competitive Windows

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `Integer` | PK, AUTO | Season ID. |
| `guild_id` | `BigInteger` | NOT NULL | Discord server this season belongs to. |
| `name` | `String(100)` | NOT NULL | Human-friendly label (e.g., "Spring 2026"). |
| `starts_at` | `DateTime(tz)` | NOT NULL | Inclusive season start. |
| `ends_at` | `DateTime(tz)` | NOT NULL | Exclusive season end. |
| `active` | `Boolean` | DEFAULT FALSE | Exactly one active season per guild at a time. |

**Unique constraint:** `(guild_id, name)`.

### `activity_log` — Append-Only Event Journal

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `Integer` | PK, AUTO | Sequential log ID. |
| `user_id` | `BigInteger` | FK→users | Who performed the action. |
| `event_type` | `Enum(InteractionType)` | NOT NULL | MESSAGE, REACTION_GIVEN, REACTION_RECEIVED, THREAD_CREATE, VOICE_JOIN, VOICE_LEAVE, QUEST_COMPLETE, MANUAL_AWARD, LEVEL_UP, ACHIEVEMENT_EARNED. |
| `season_id` | `Integer` | FK→seasons, NOT NULL | Season in effect when event was recorded. |
| `zone_id` | `Integer` | FK→zones, NULLABLE | Which zone the event occurred in (NULL for non-channel events). |
| `source_system` | `String(30)` | NOT NULL, DEFAULT 'discord' | Origin: `discord`, `github`, `tryhackme`, `admin`. |
| `source_event_id` | `String(100)` | NULLABLE | Natural ID for dedup (Discord snowflake, GitHub delivery ID, etc.). |
| `xp_delta` | `Integer` | DEFAULT 0 | XP change (positive = earned). |
| `star_delta` | `Integer` | DEFAULT 0 | Stars change (positive = earned). |
| `metadata` | `JSONB` | NULLABLE | Structured event context (replaces free-text `detail`). See §4.6. |
| `timestamp` | `DateTime(tz)` | DEFAULT now() | When the event occurred. |

**Partial unique index:** `UNIQUE(source_system, source_event_id) WHERE source_event_id IS NOT NULL`.
This prevents double-award from retried or duplicated events.

### `zones` — Channel Groupings

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `Integer` | PK, AUTO | Zone ID. |
| `guild_id` | `BigInteger` | NOT NULL | Discord server this zone belongs to. |
| `name` | `String(100)` | NOT NULL | Human-readable name ("programming", "memes"). |
| `description` | `Text` | NULLABLE | What this zone represents. |
| `created_by` | `BigInteger` | NULLABLE | Discord ID of the admin who created it. |
| `active` | `Boolean` | DEFAULT TRUE | Soft-delete flag. |
| `created_at` | `DateTime(tz)` | DEFAULT now() | Creation timestamp. |

**Unique constraint:** `(guild_id, name)`.

### `zone_channels` — Zone ↔ Channel Mapping

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `zone_id` | `Integer` | PK, FK→zones | Parent zone. |
| `channel_id` | `BigInteger` | PK | Discord channel snowflake ID. |

A channel belongs to **at most one zone**.  Unmapped channels use a built-in
"default" zone with baseline multipliers.

### `zone_multipliers` — Per-Zone, Per-Event-Type Weights

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `Integer` | PK, AUTO | Row ID. |
| `zone_id` | `Integer` | FK→zones | Which zone. |
| `interaction_type` | `String(50)` | NOT NULL | "MESSAGE", "REACTION_RECEIVED", etc. |
| `xp_multiplier` | `Float` | DEFAULT 1.0 | Multiplier applied to base XP. |
| `star_multiplier` | `Float` | DEFAULT 1.0 | Multiplier applied to base stars. |

**Unique constraint:** `(zone_id, interaction_type)`.

### `achievement_templates` — Admin-Defined Recognition

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `Integer` | PK, AUTO | Template ID. |
| `guild_id` | `BigInteger` | NOT NULL | Discord server this achievement belongs to. |
| `name` | `String(200)` | NOT NULL | "Meme Lord", "First Blood", "CTF Champion". |
| `description` | `Text` | NULLABLE | Flavor text shown in the embed. |
| `category` | `String(50)` | NOT NULL | "social", "technical", "participation", "custom". |
| `requirement_type` | `String(50)` | NOT NULL | "star_threshold", "counter_threshold", "xp_milestone", "custom". |
| `requirement_scope` | `String(20)` | DEFAULT "season" | Which counters to evaluate: "season" or "lifetime". |
| `requirement_field` | `String(50)` | NULLABLE | Which `user_stats` column to check (e.g., "messages_sent"). |
| `requirement_value` | `Integer` | NULLABLE | Threshold value (NULL for "custom" type). |
| `xp_reward` | `Integer` | DEFAULT 0 | Bonus XP on earn. |
| `gold_reward` | `Integer` | DEFAULT 0 | Bonus Gold on earn. |
| `badge_image_url` | `String(500)` | NULLABLE | URL to badge graphic. |
| `rarity` | `String(20)` | DEFAULT "common" | "common", "uncommon", "rare", "epic", "legendary". |
| `announce_channel_id` | `BigInteger` | NULLABLE | Where to post the announcement (NULL = no announcement). |
| `active` | `Boolean` | DEFAULT TRUE | Soft-delete flag. |
| `created_at` | `DateTime(tz)` | DEFAULT now() | Creation timestamp. |

### `user_achievements` — Earned Badges

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `user_id` | `BigInteger` | PK, FK→users | Who earned it. |
| `achievement_id` | `Integer` | PK, FK→achievement_templates | Which achievement. |
| `earned_at` | `DateTime(tz)` | DEFAULT now() | When it was earned. |
| `granted_by` | `BigInteger` | NULLABLE | Discord ID of admin (NULL if auto-triggered). |

### `quests` — Gamified Tasks

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `Integer` | PK, AUTO | Quest ID. |
| `guild_id` | `BigInteger` | NOT NULL | Discord server this quest belongs to. |
| `title` | `String(200)` | NOT NULL | Quest name. |
| `description` | `Text` | NULLABLE | What needs to be done. |
| `xp_reward` | `Integer` | DEFAULT 50 | XP on completion. |
| `gold_reward` | `Integer` | DEFAULT 0 | Gold on completion. |
| `status` | `Enum(QuestStatus)` | DEFAULT OPEN | OPEN, CLAIMED, COMPLETE. |
| `github_issue_url` | `String(500)` | NULLABLE | Backing GitHub issue URL. |
| `active` | `Boolean` | DEFAULT TRUE | Soft-delete flag. |
| `created_at` | `DateTime(tz)` | DEFAULT now() | Creation timestamp. |

### `admin_log` — Append-Only Audit Trail

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `Integer` | PK, AUTO | Sequential log ID. |
| `actor_id` | `BigInteger` | FK→users, NOT NULL | Discord ID of the admin who performed the action. |
| `action_type` | `Enum(AdminActionType)` | NOT NULL | CREATE, UPDATE, DELETE, SEASON_ROLL, MANUAL_AWARD, MANUAL_REVOKE, IMPORT. |
| `target_table` | `String(50)` | NOT NULL | Table that was modified (e.g., "zones", "achievement_templates"). |
| `target_id` | `String(100)` | NULLABLE | Primary key of the affected row (stringified). |
| `before_snapshot` | `JSONB` | NULLABLE | Row state before the mutation (NULL for creates). |
| `after_snapshot` | `JSONB` | NULLABLE | Row state after the mutation (NULL for deletes). |
| `ip_address` | `String(45)` | NULLABLE | Client IP when available (FastAPI request). |
| `reason` | `Text` | NULLABLE | Optional admin-provided justification. |
| `timestamp` | `DateTime(tz)` | DEFAULT now() | When the action occurred. |

This table is **insert-only**.  No UPDATE or DELETE is ever performed on it.

### `user_preferences` — Per-User Notification Opt-Outs

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `user_id` | `BigInteger` | PK, FK→users | Discord ID. |
| `announce_level_up` | `Boolean` | DEFAULT TRUE | Post public embed on level-up. |
| `announce_achievements` | `Boolean` | DEFAULT TRUE | Post public embed on achievement earn. |
| `announce_awards` | `Boolean` | DEFAULT TRUE | Post public embed on manual award. |
| `updated_at` | `DateTime(tz)` | DEFAULT now() | Last preference change. |

Users opt out via a `/preferences` slash command.  Defaults are all TRUE (public
celebration is the default experience as per D01-04's opt-out model).

### `settings` — Key-Value Configuration Store

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `key` | `String(100)` | PK | Setting identifier (e.g., `xp_base`, `dashboard_hero_emoji`). |
| `value_json` | `JSONB` | NOT NULL | Setting value stored as JSON (supports strings, numbers, booleans). |
| `category` | `String(50)` | NULLABLE | Grouping category for admin UI organization. |
| `description` | `Text` | NULLABLE | Human-readable description shown in admin panel. |
| `updated_at` | `DateTime(tz)` | DEFAULT now() | Last modification timestamp. |

All runtime-configurable settings live in this table.  Initial values are
seeded from `seeds/settings.yaml` on first boot.

---

## 4.4 Indexes (Performance)

| Table | Index | Purpose |
|-------|-------|---------|
| `activity_log` | `(user_id, timestamp)` | Fast per-user history queries |
| `activity_log` | `(timestamp)` | Dashboard time-series aggregation |
| `activity_log` | `(event_type, timestamp)` | Filtered analytics (e.g., messages per day) |
| `activity_log` | `(zone_id, timestamp)` | Fast zone activity charts by time window |
| `zone_channels` | `(channel_id)` | O(1) zone lookup from Discord event |
| `users` | `(xp DESC)` | Leaderboard queries |
| `activity_log` | `UNIQUE(source_system, source_event_id) WHERE source_event_id IS NOT NULL` | Idempotent event insert (partial unique) |
| `admin_log` | `(actor_id, timestamp)` | Who-did-what audit queries |
| `admin_log` | `(target_table, target_id, timestamp)` | Row-level mutation history |

---

## 4.5 Migration Strategy

| Phase | Approach |
|-------|----------|
| **Development** | `Base.metadata.create_all()` — fast iteration, no migration files |
| **Staging** | Alembic auto-generate from model diffs |
| **Production** | Alembic managed migrations, reviewed before apply |

Alembic will be introduced when the schema stabilizes after Phase 1 features
are complete.

---

## 4.6 Metadata Schema (JSONB Conventions)

The `activity_log.metadata` column stores structured context as JSONB.  Each
`event_type` has a documented shape.  Code that writes to `metadata` MUST
conform to these shapes; consumers SHOULD tolerate missing keys gracefully.

| event_type | Expected keys | Example |
|------------|---------------|---------|
| `MESSAGE` | `length`, `has_code_block`, `is_reply`, `reply_to_user_id`, `channel_id` | `{"length": 142, "has_code_block": true, "is_reply": false}` |
| `REACTION_GIVEN` | `emoji_name`, `target_message_id`, `target_user_id`, `channel_id` | `{"emoji_name": "\u2b50", "target_user_id": 123456}` |
| `REACTION_RECEIVED` | `reactor_id`, `unique_reactor_count`, `emoji_name`, `message_age_seconds`, `channel_id` | `{"reactor_id": 789, "unique_reactor_count": 3}` |
| `THREAD_CREATE` | `thread_id`, `parent_channel_id` | `{"thread_id": 456, "parent_channel_id": 123}` |
| `VOICE_JOIN` / `VOICE_LEAVE` | `channel_id`, `session_duration_seconds` (leave only) | `{"channel_id": 789}` |
| `QUEST_COMPLETE` | `quest_id`, `quest_title` | `{"quest_id": 12, "quest_title": "Fix CI"}` |
| `MANUAL_AWARD` | `admin_id`, `reason` | `{"admin_id": 111, "reason": "CTF placement"}` |
| `LEVEL_UP` | `old_level`, `new_level` | `{"old_level": 4, "new_level": 5}` |
| `ACHIEVEMENT_EARNED` | `achievement_id`, `achievement_name` | `{"achievement_id": 7, "achievement_name": "Meme Lord"}` |

Keys not listed here MAY be added as the system evolves.  The JSONB column
has no enforced schema at the DB level; validation is in application code.

---

## Decisions

> **Decision D04-01:** Config in Database, Not YAML
> - **Status:** Accepted
> - **Context:** YAML config requires server restarts and SSH access to modify.
>   Club leads are students who need a web UI.
> - **Choice:** Zones, multipliers, and achievement templates are DB rows.
>   YAML is used only for initial seeding (`seed.py`).
> - **Consequences:** Requires a web admin panel for CRUD operations.

> **Decision D04-02:** Separate `user_stats` Table
> - **Status:** Accepted
> - **Context:** Engagement counters (messages_sent, reactions_given, etc.)
>   could live on the `users` table.
> - **Choice:** Separate table to keep `users` lean and to allow adding new
>   counter columns without touching the core user model.
> - **Consequences:** Requires a JOIN for full profile views.  Acceptable
>   trade-off for schema cleanliness.

> **Decision D04-03:** No Alembic Yet
> - **Status:** Accepted (Temporary)
> - **Context:** The schema is still evolving rapidly.
> - **Choice:** Use `create_all()` during development.  Introduce Alembic
>   once the schema stabilizes.
> - **Consequences:** Dropping and recreating tables is expected during dev.
>   No production data to migrate yet.

> **Decision D04-04:** Season IDs in Core Counters
> - **Status:** Accepted
> - **Context:** Competitive counters must reset without wiping historical records.
> - **Choice:** Add `season_id` to both `activity_log` and `user_stats`.
> - **Consequences:** Seasonal leaderboards become cheap to query and auditable.

> **Decision D04-05:** Zone-Time Composite Index
> - **Status:** Accepted
> - **Context:** Club Pulse will frequently query "activity by zone over time".
> - **Choice:** Add index `activity_log(zone_id, timestamp)`.
> - **Consequences:** Prevents degraded chart performance as logs grow.

> **Decision D04-06:** Append-Only Admin Audit Log
> - **Status:** Accepted
> - **Context:** Admin mutations need a full audit trail regardless of which
>   client initiates them (bot commands, FastAPI endpoints).
> - **Choice:** Introduce `admin_log` table.  Every config mutation (zones,
>   multipliers, achievements, seasons, manual awards) inserts a row with
>   `before_snapshot` / `after_snapshot` JSONB columns.
> - **Consequences:** Full mutation history.  Rollback requires manual SQL
>   for now (automated rollback deferred to Phase 2).

> **Decision D04-07:** Canonical Event Identity
> - **Status:** Accepted
> - **Context:** Bot retries and webhook replays can produce duplicate events.
> - **Choice:** Add `source_system` and `source_event_id` to `activity_log`
>   with a partial unique index.  Inserts use `ON CONFLICT DO NOTHING`.
> - **Consequences:** At-least-once delivery becomes exactly-once crediting.
>   Events without a natural ID (e.g., voice ticks) leave `source_event_id`
>   NULL and bypass the uniqueness check.

> **Decision D04-08:** Guild ID Is a Partition Key
> - **Status:** Accepted
> - **Context:** A single Synapse database may serve multiple Discord servers.
> - **Choice:** Add `guild_id` to `zones`, `seasons`, `achievement_templates`,
>   and `quests`.  Unique constraints are scoped to `(guild_id, name)`.
> - **Consequences:** Multi-server support is baked into the schema from day
>   one.  Single-server deployments simply have one `guild_id` value
>   everywhere.
