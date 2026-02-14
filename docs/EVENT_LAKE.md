# Event Lake

Append-only capture of ephemeral Discord gateway events. Implemented in `synapse/services/event_lake_writer.py`.

## Purpose

The Event Lake stores raw event data regardless of whether any reward rule acts on it. This decouples data collection from interpretation — communities can retroactively analyze behavior or build new rules without losing historical events.

Message content is **never** persisted. Only metadata is stored (length, has_code_block, has_link, emoji_count, etc.).

## Event Types

9 captured event types:

| Event Type | Bot Source | Description |
|------------|-----------|-------------|
| `message_create` | `on_message` | Message metadata (no content) |
| `reaction_add` | `on_raw_reaction_add` | Emoji, message ID, reactor |
| `reaction_remove` | `on_raw_reaction_remove` | Emoji, message ID, reactor |
| `thread_create` | `on_thread_create` | Thread name, parent channel |
| `voice_join` | `on_voice_state_update` | Voice channel joined |
| `voice_leave` | `on_voice_state_update` | Duration from in-memory session |
| `voice_move` | `on_voice_state_update` | From/to channels |
| `member_join` | `on_member_join` | Join timestamp |
| `member_leave` | `on_member_remove` | — |

### Data Source Toggles

Each event type can be independently enabled/disabled from the admin dashboard. Stored as settings with key pattern `event_lake.source.<event_type>.enabled`. Default: enabled. Cached for 60 seconds.

## Idempotency

Each event with a natural key gets a `source_id` string (e.g., `msg_{message_id}_{user_id}`, `rxn_add_{message_id}_{user_id}_{emoji}`). The `event_lake` table has a partial unique index on `source_id WHERE source_id IS NOT NULL`.

Duplicate inserts are safely ignored via `ON CONFLICT DO NOTHING`.

`reaction_remove` events have no `source_id` (removal can happen multiple times for the same emoji) and always insert.

## Payload Examples

### message_create

```json
{
  "length": 142,
  "has_code_block": false,
  "has_link": true,
  "has_attachment": false,
  "attachment_count": 0,
  "emoji_count": 2,
  "is_reply": true,
  "reply_to_user_id": 123456789
}
```

### reaction_add

```json
{
  "emoji": "👍",
  "message_id": 987654321
}
```

### voice_leave

```json
{
  "channel_name": "General Voice",
  "duration_seconds": 1847,
  "was_afk": false
}
```

## Pre-Computed Counters

The `event_counters` table maintains pre-aggregated counts for O(1) reads. Updated transactionally with each Event Lake insert via raw SQL UPSERT.

### Composite Key

`(user_id, event_type, category_id, period)`

- `category_id = 0` means global (no category filter)
- `period` values: `lifetime`, `season`, `day:YYYY-MM-DD`

### Update Logic

Each `write_event()` call updates three counter rows:
1. `lifetime` — cumulative all-time
2. `season` — current active season
3. `day:YYYY-MM-DD` — today's date

## Voice Session Tracking

`VoiceSessionTracker` maintains in-memory state for voice joins/leaves/moves:

- `join(user_id, channel_id)` — records join timestamp
- `leave(user_id)` → `(channel_id, duration_seconds)` — computes duration, removes session
- `get(user_id)` → `(channel_id, join_time)` — check active session
- `update_state(user_id, *, muted, deafened)` — track mute/deaf for AFK detection

AFK channels are detected on bot startup and configurable via `set_afk_channels()`.

## Metadata Extraction

`extract_message_metadata(content, attachments, is_reply, reply_to_user_id)` produces a privacy-safe metadata dict:

- `length` — character count
- `word_count` — whitespace-split word count
- `has_code_block` — triple backtick detection
- `has_link` — URL regex match
- `has_attachment` — boolean
- `attachment_count` — integer
- `emoji_count` — Unicode + custom emoji count
- `is_reply` — boolean
- `reply_to_user_id` — integer or null

## Maintenance

### Retention Cleanup

Daily background task (`retention_loop` in `PeriodicTasks` cog). Implemented in `synapse/services/retention_service.py`.

- Deletes `event_lake` rows older than `event_lake_retention_days` (default 90 days)
- Batch size: 5,000 rows per DELETE to avoid long row locks
- Also prunes stale `day:*` counters matching dates before the cutoff
- Triggered manually via `POST /api/admin/event-lake/retention/run`

`get_retention_stats()` returns: total events, total counters, oldest/newest timestamps, PG table size in bytes.

### Counter Reconciliation

Weekly background task (`reconciliation_loop` in `PeriodicTasks` cog). Implemented in `synapse/services/reconciliation_service.py`.

- Ground truth: `COUNT(*)` from `event_lake` grouped by `(user_id, event_type)`
- Compares against `event_counters` where `period='lifetime'` and `category_id=0`
- Corrects mismatches via SQL UPSERT
- Detects orphan counters (no matching events) and zeros them
- Daily counters are **not** reconciled — they share the retention window
- Triggered manually via `POST /api/admin/event-lake/reconciliation/run`

### Backfill

One-shot migration utility. Implemented in `synapse/services/backfill_service.py`.

Reads legacy `activity_log` rows and populates `event_counters` for historical data:

| Legacy Event Type | Event Lake Type |
|-------------------|-----------------|
| MESSAGE | message_create |
| REACTION_GIVEN | reaction_add |
| THREAD_CREATE | thread_create |
| VOICE_TICK | voice_join |

Skipped types: REACTION_RECEIVED, MANUAL_AWARD, ACHIEVEMENT_EARNED, LEVEL_UP.

Only `lifetime` period is backfilled. Uses `GREATEST(existing, new)` to avoid overwriting higher counts. Supports `dry_run=True`.

Triggered via `POST /api/admin/event-lake/backfill/run`.

## Storage

Average row size: ~340 bytes (used for storage projections in the admin dashboard).

The health endpoint provides: events today, events last 7 days, volume by type, daily volume time series, and table size via `pg_total_relation_size('event_lake')`.
