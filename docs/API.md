# REST API Reference

Base URL: `/api`. Served by FastAPI + Uvicorn on port 8000.

## Authentication

Discord OAuth2 → JWT (HS256, 12-hour expiry).

Admin endpoints require a `Bearer` token in the `Authorization` header. The token must contain `is_admin: true`. Admin status is verified during OAuth2 callback by checking if the user has the configured `admin_role_id` in their Discord guild roles.

### JWT Secret

Validated at API startup. The API **will not start** if the secret is:
- Missing or blank
- Shorter than 32 characters
- A known-weak value (`synapse-dev-secret-change-me`, `change-me`, `secret`, `dev`)

## Rate Limiting

Admin mutation endpoints (POST/PUT/PATCH/DELETE under `/api/admin`) are rate-limited per admin:

- **Window:** 60 seconds (sliding)
- **Limit:** 30 mutations per window
- **Scope:** Keyed by JWT `sub` claim (admin Discord ID), backed by durable DB events
- **Counting:** Only successful mutations (status < 400) are counted
- **Response headers:** `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`
- **429 body:** `{"detail": {"error": "rate_limit_exceeded", "message": "...", "retry_after": N}}`

## Health

### GET /health

Liveness probe.

**Response:** `{"status": "ok"}`

### GET /health/bot

Bot heartbeat status.

**Response:** `{"online": true, "last_heartbeat": "...", "seconds_ago": N}` — online if heartbeat < 90 seconds old.

## Auth Endpoints

### GET /auth/login

Redirects to Discord OAuth2 consent screen. Persists a one-time state token (10-minute TTL) for CSRF protection.

### GET /auth/callback

Exchanges authorization code for Discord access token. Fetches user profile and guild member data. Verifies admin role. Issues JWT and redirects to `FRONTEND_URL/auth/callback?token=<jwt>`.

Non-admins are redirected to `FRONTEND_URL?auth_error=not_admin`.

### GET /auth/me

**Auth:** JWT required.

**Response:** `{"id": "...", "username": "...", "avatar": "...", "is_admin": true}`

## Public Endpoints

### GET /metrics

Overview metrics for the community dashboard.

**Response:**
```json
{
  "total_users": 150,
  "total_xp": 45000,
  "active_7d": 42,
  "top_level": 15,
  "total_achievements_earned": 87
}
```

### GET /leaderboard/{currency}

Paginated leaderboard.

**Path:** `currency` — one of `xp`, `gold`, `level`.

**Query:** `page` (default 1), `page_size` (default 25, max 100).

**Response:**
```json
{
  "entries": [
    {
      "id": "123456789",
      "discord_name": "User",
      "discord_avatar_hash": "abc123",
      "avatar_url": "https://cdn.discordapp.com/...",
      "xp": 1500,
      "level": 5,
      "gold": 200,
      "xp_for_next": 305,
      "xp_progress": 0.73
    }
  ],
  "page": 1,
  "page_size": 25,
  "total": 150
}
```

### GET /activity

Recent activity feed with daily aggregation.

**Query:** `days` (default 7, max 365), `limit` (default 100, max 500), `event_type` (optional filter).

**Response:**
```json
{
  "events": [
    {
      "id": 1,
      "user_id": "123",
      "event_type": "MESSAGE",
      "xp_delta": 15,
      "star_delta": 1,
      "timestamp": "2026-02-12T10:00:00Z",
      "metadata": {}
    }
  ],
  "daily": {
    "2026-02-12": {"MESSAGE": 45, "REACTION_GIVEN": 12}
  }
}
```

### GET /achievements

All active achievement templates with earn statistics.

**Response:** Array of templates with `earner_count` and `earn_pct` (percentage of total users who earned it).

### GET /achievements/recent

Recently earned achievements with user info.

**Query:** `limit` (default 10, max 50).

### GET /settings/public

Public-facing dashboard settings with defaults.

**Response:**
```json
{
  "dashboard_title": "Synapse Community Dashboard",
  "dashboard_subtitle": "Track your engagement...",
  "currency_name_primary": "XP",
  "currency_name_secondary": "Gold",
  "hero_emoji": "🧠",
  "leaderboard_cta": "Climb the ranks!",
  "show_gold_on_leaderboard": true,
  "show_achievements_on_profile": true
}
```

## Admin Endpoints

All require JWT with `is_admin: true`.

### GET /admin/categories

List all categories with their channel mappings and multipliers.

### POST /admin/categories

Create a category.

**Body:**
```json
{
  "name": "Programming",
  "description": "Technical channels",
  "channel_ids": [123, 456],
  "multipliers": {"MESSAGE": [1.5, 1.0], "THREAD_CREATE": [2.0, 1.5]}
}
```

Multiplier format: `{event_type: [xp_multiplier, star_multiplier]}`.

### PATCH /admin/categories/{category_id}

Update a category. Partial updates supported.

### GET /admin/achievements

List all achievement templates.

### POST /admin/achievements

Create an achievement template.

**Body:**
```json
{
  "name": "Chatterbox",
  "description": "Send 100 messages",
  "requirement_type": "counter_threshold",
  "requirement_field": "messages_sent",
  "requirement_value": 100,
  "xp_reward": 50,
  "gold_reward": 25,
  "rarity": "uncommon"
}
```

### PATCH /admin/achievements/{achievement_id}

Update an achievement template. Guards `id`, `guild_id`, `created_at` from modification.

### POST /admin/awards/xp-gold

Manual XP/Gold award.

**Body:** `{"user_id": "123", "xp": 100, "gold": 50, "reason": "Helped with event"}`

### POST /admin/awards/achievement

Grant an achievement to a user.

**Body:** `{"user_id": "123", "achievement_id": 5}`

### GET /admin/users

Search users by name for admin dropdowns.

**Query:** `q` (search string).

### GET /admin/settings

Get all settings.

### PUT /admin/settings

Bulk upsert settings.

**Body:**
```json
[
  {"key": "xp_base_message", "value": 20, "category": "economy", "description": "Base XP for messages"}
]
```

### GET /admin/audit

Paginated admin audit log.

**Query:** `page`, `page_size`.

### GET /admin/setup/status

Returns bootstrap state: whether the guild is initialized, bootstrap version, timestamp.

### POST /admin/setup/bootstrap

Triggers first-run guild bootstrap. Creates categories from Discord categories, maps channels, creates a default season, writes default settings.

**Query:** `allow_guild_mismatch` (default `false`).

When `false`, bootstrap fails closed if the stored guild snapshot's `guild_id` does not match configured `guild_id`. Set `allow_guild_mismatch=true` to explicitly override.

### GET /admin/logs

Recent logs from the in-memory ring buffer.

**Query:** `tail` (max entries), `level` (filter), `logger` (prefix filter).

### PUT /admin/logs/level

Change log capture level at runtime.

**Body:** `{"level": "DEBUG"}` — one of DEBUG, INFO, WARNING, ERROR, CRITICAL.

### POST /admin/resolve-names

Resolve Discord snowflake IDs to display names.

**Body:** `{"user_ids": ["123"], "channel_ids": ["456"]}`

**Response:** `{"users": {"123": "Username"}, "channels": {"456": "#channel-name"}}`

## Event Lake Admin Endpoints

All under `/api/admin/event-lake`, JWT required.

### GET /event-lake/events

Paginated event browser.

**Query:** `page`, `page_size` (max 200), `event_type`, `user_id`, `channel_id`, `since`, `until`.

### GET /event-lake/data-sources

List all 9 data source types with their enabled/disabled state.

Data sources: `message_create`, `reaction_add`, `reaction_remove`, `thread_create`, `voice_join`, `voice_leave`, `voice_move`, `member_join`, `member_leave`.

### PUT /event-lake/data-sources

Toggle data sources.

**Body:** `[{"event_type": "reaction_remove", "enabled": false}]`

### GET /event-lake/health

Health dashboard: total events, total counters, oldest/newest timestamps, table size in bytes, events today, events last 7 days, volume by type, daily volume time series.

### GET /event-lake/storage-estimate

Storage projection based on 340 bytes/row average. Returns current size, daily rate, and 90-day projection.

### POST /event-lake/retention/run

Trigger retention cleanup.

**Query:** `retention_days` (1–730, default 90).

**Response:** `{"events_deleted": N, "counters_deleted": M}`

### POST /event-lake/reconciliation/run

Trigger counter reconciliation against raw Event Lake data.

**Response:** `{"checked": N, "corrected": M, "corrections": [...], "timestamp": "..."}`

### POST /event-lake/backfill/run

Migrate legacy `activity_log` data into `event_counters`.

**Query:** `dry_run` (boolean).

**Response:** `{"rows_read": N, "counters_upserted": M, "skipped_types": [...], "dry_run": false}`

### GET /event-lake/counters

Browse pre-computed event counters.

**Query:** `page`, `page_size`, `user_id`, `event_type`, `period`.
