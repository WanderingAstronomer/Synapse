# Database Schema

PostgreSQL 16. 15 tables defined in `synapse/database/models.py`.

## Tables

### users

Community member profiles. Discord snowflake as primary key.

| Column | Type | Notes |
|--------|------|-------|
| `id` | BIGINT PK | Discord user snowflake |
| `discord_name` | VARCHAR(100) | Display name |
| `discord_avatar_hash` | VARCHAR(100) | For CDN URL construction |
| `github_username` | VARCHAR(39) | Optional linked GitHub account |
| `xp` | INTEGER | Lifetime XP (default 0) |
| `level` | INTEGER | Current level (default 1) |
| `gold` | INTEGER | Spendable currency (default 0) |
| `created_at` | TIMESTAMPTZ | Auto-set |
| `updated_at` | TIMESTAMPTZ | Auto-updated |

Indexes: `ix_users_xp_desc` on `xp`.

### seasons

Competitive time windows.

| Column | Type | Notes |
|--------|------|-------|
| `id` | SERIAL PK | |
| `guild_id` | BIGINT | Discord guild snowflake |
| `name` | VARCHAR(100) | Season name |
| `starts_at` | TIMESTAMPTZ | Season start |
| `ends_at` | TIMESTAMPTZ | Season end |
| `active` | BOOLEAN | Only one active per guild |

Unique: `(guild_id, name)`.

### user_stats

Per-season engagement counters. Composite PK.

| Column | Type | Notes |
|--------|------|-------|
| `user_id` | BIGINT PK, FK → users | |
| `season_id` | INTEGER PK, FK → seasons | |
| `season_stars` | INTEGER | Stars earned this season |
| `lifetime_stars` | INTEGER | Cumulative stars |
| `messages_sent` | INTEGER | |
| `reactions_given` | INTEGER | |
| `reactions_received` | INTEGER | |
| `threads_created` | INTEGER | |
| `voice_minutes` | INTEGER | |

### activity_log

Append-only event journal. Core of the reward pipeline.

| Column | Type | Notes |
|--------|------|-------|
| `id` | SERIAL PK | |
| `user_id` | BIGINT FK → users | |
| `event_type` | VARCHAR(50) | InteractionType enum value |
| `season_id` | INTEGER FK → seasons | Nullable (SET NULL on delete) |
| `category_id` | INTEGER FK → categories | Nullable (SET NULL on delete) |
| `source_system` | VARCHAR(30) | Default "discord" |
| `source_event_id` | VARCHAR(100) | For idempotent insert |
| `xp_delta` | INTEGER | XP awarded |
| `star_delta` | INTEGER | Stars awarded |
| `metadata` | JSONB | Event-specific data |
| `timestamp` | TIMESTAMPTZ | Auto-set |

Indexes:
- `ix_activity_log_idempotent` — UNIQUE on `(source_system, source_event_id)` WHERE `source_event_id IS NOT NULL`
- `ix_activity_log_user_time` on `(user_id, timestamp)`
- `ix_activity_log_timestamp` on `timestamp`
- `ix_activity_log_event_time` on `(event_type, timestamp)`
- `ix_activity_log_category_time` on `(category_id, timestamp)`

### categories

Channel groupings. Created from Discord categories during bootstrap.

| Column | Type | Notes |
|--------|------|-------|
| `id` | SERIAL PK | |
| `guild_id` | BIGINT | Discord guild snowflake |
| `name` | VARCHAR(100) | |
| `description` | TEXT | Optional |
| `created_by` | BIGINT | Admin who created it |
| `active` | BOOLEAN | Soft-delete flag |
| `created_at` | TIMESTAMPTZ | |

Unique: `(guild_id, name)`.

### category_channels

Category ↔ channel mapping. Composite PK.

| Column | Type | Notes |
|--------|------|-------|
| `category_id` | INTEGER PK, FK → categories | |
| `channel_id` | BIGINT PK | Discord channel snowflake |

Indexes: `ix_category_channels_channel_id` on `channel_id`.

### category_multipliers

Per-category, per-event-type reward weights.

| Column | Type | Notes |
|--------|------|-------|
| `id` | SERIAL PK | |
| `category_id` | INTEGER FK → categories | |
| `interaction_type` | VARCHAR(50) | Event type name |
| `xp_multiplier` | FLOAT | Default 1.0 |
| `star_multiplier` | FLOAT | Default 1.0 |

Unique: `(category_id, interaction_type)`.

### achievement_templates

Admin-defined recognition definitions.

| Column | Type | Notes |
|--------|------|-------|
| `id` | SERIAL PK | |
| `guild_id` | BIGINT | |
| `name` | VARCHAR(200) | |
| `description` | TEXT | |
| `category` | VARCHAR(50) | Default "social" |
| `requirement_type` | VARCHAR(50) | counter_threshold, star_threshold, xp_milestone, custom |
| `requirement_scope` | VARCHAR(20) | "season" or "lifetime" |
| `requirement_field` | VARCHAR(50) | Stat field name (for counter_threshold) |
| `requirement_value` | INTEGER | Threshold value |
| `xp_reward` | INTEGER | XP granted on earn |
| `gold_reward` | INTEGER | Gold granted on earn |
| `badge_image_url` | VARCHAR(500) | Optional badge image |
| `rarity` | VARCHAR(20) | common, uncommon, rare, epic, legendary |
| `announce_channel_id` | BIGINT | Override announcement channel |
| `active` | BOOLEAN | |
| `created_at` | TIMESTAMPTZ | |

Unique: `(guild_id, name)`.

### user_achievements

Earned badges. Composite PK.

| Column | Type | Notes |
|--------|------|-------|
| `user_id` | BIGINT PK, FK → users | |
| `achievement_id` | INTEGER PK, FK → achievement_templates | |
| `earned_at` | TIMESTAMPTZ | |
| `granted_by` | BIGINT | Admin who granted (null = automatic) |

### quests

Gamified tasks. Schema present; dashboard UI deferred.

| Column | Type | Notes |
|--------|------|-------|
| `id` | SERIAL PK | |
| `guild_id` | BIGINT | |
| `title` | VARCHAR(200) | |
| `description` | TEXT | |
| `xp_reward` | INTEGER | Default 50 |
| `gold_reward` | INTEGER | Default 0 |
| `status` | ENUM (open, claimed, complete) | |
| `github_issue_url` | VARCHAR(500) | Optional link |
| `active` | BOOLEAN | |
| `created_at` | TIMESTAMPTZ | |

### admin_log

Append-only audit trail. Every admin mutation is recorded.

| Column | Type | Notes |
|--------|------|-------|
| `id` | SERIAL PK | |
| `actor_id` | BIGINT | Admin's Discord snowflake |
| `action_type` | VARCHAR(50) | CREATE, UPDATE, DELETE, SEASON_ROLL, MANUAL_AWARD, MANUAL_REVOKE, IMPORT |
| `target_table` | VARCHAR(50) | Table that was modified |
| `target_id` | VARCHAR(100) | Row identifier |
| `before_snapshot` | JSONB | State before change |
| `after_snapshot` | JSONB | State after change |
| `ip_address` | VARCHAR(45) | Optional |
| `reason` | TEXT | Optional |
| `timestamp` | TIMESTAMPTZ | |

Indexes:
- `ix_admin_log_actor_time` on `(actor_id, timestamp)`
- `ix_admin_log_target` on `(target_table, target_id, timestamp)`

### user_preferences

Per-user announcement opt-outs.

| Column | Type | Notes |
|--------|------|-------|
| `user_id` | BIGINT PK, FK → users | |
| `announce_level_up` | BOOLEAN | Default true |
| `announce_achievements` | BOOLEAN | Default true |
| `announce_awards` | BOOLEAN | Default true |
| `updated_at` | TIMESTAMPTZ | |

### settings

Key-value configuration store. All gameplay tuning lives here.

| Column | Type | Notes |
|--------|------|-------|
| `key` | VARCHAR(100) PK | Setting identifier |
| `value_json` | TEXT | JSON-serialized value |
| `category` | VARCHAR(50) | Grouping (economy, anti_gaming, quality, display, etc.) |
| `description` | TEXT | Human-readable description |
| `updated_at` | TIMESTAMPTZ | |

Indexes: `ix_settings_category` on `category`.

### event_lake

Append-only ephemeral Discord event capture.

| Column | Type | Notes |
|--------|------|-------|
| `id` | BIGSERIAL PK | |
| `guild_id` | BIGINT | |
| `user_id` | BIGINT | |
| `event_type` | VARCHAR(64) | message_create, reaction_add, etc. |
| `channel_id` | BIGINT | Nullable |
| `target_id` | BIGINT | Nullable (e.g., message author for reactions) |
| `payload` | JSONB | Event metadata (never raw content) |
| `source_id` | VARCHAR(128) | For idempotent insert |
| `timestamp` | TIMESTAMPTZ | |

Indexes:
- `idx_event_lake_user_ts` on `(user_id, timestamp DESC)`
- `idx_event_lake_type_ts` on `(event_type, timestamp DESC)`
- `idx_event_lake_guild_ts` on `(guild_id, timestamp DESC)`
- `idx_event_lake_channel_ts` on `(channel_id, timestamp DESC)` WHERE `channel_id IS NOT NULL`
- `idx_event_lake_source` — UNIQUE on `source_id` WHERE `source_id IS NOT NULL`

### event_counters

Pre-computed aggregation cache. Updated transactionally with each Event Lake insert.

| Column | Type | Notes |
|--------|------|-------|
| `user_id` | BIGINT PK | |
| `event_type` | VARCHAR(64) PK | |
| `category_id` | INTEGER PK | 0 = global |
| `period` | VARCHAR(16) PK | "lifetime", "season", or "day:YYYY-MM-DD" |
| `count` | BIGINT | |

## Enums

### InteractionType

Defined in `synapse/database/models.py`:

`MESSAGE`, `REACTION_GIVEN`, `REACTION_RECEIVED`, `THREAD_CREATE`, `VOICE_TICK`, `QUEST_COMPLETE`, `MANUAL_AWARD`, `LEVEL_UP`, `ACHIEVEMENT_EARNED`, `VOICE_JOIN`, `VOICE_LEAVE`

### QuestStatus

`open`, `claimed`, `complete`

### AdminActionType

`CREATE`, `UPDATE`, `DELETE`, `SEASON_ROLL`, `MANUAL_AWARD`, `MANUAL_REVOKE`, `IMPORT`

## Migrations

Managed by Alembic. Configuration in `alembic/env.py` reads `DATABASE_URL` from the environment and uses `Base.metadata` from `synapse.database.models` for autogeneration.

Current migrations:
- `99b1d42a3d9c` — Add `event_lake` and `event_counters` tables

Schema initialization on bot startup uses `Base.metadata.create_all()` for convenience. Alembic is used for additive migrations in production.
