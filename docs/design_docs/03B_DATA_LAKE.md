# 03B — Event Lake & Data Sources

> *Capture what disappears.  Fetch what persists.  Store nothing twice.*

**Status:** COMPLETE — Informed by Discord Gateway Events & API
Capabilities Audit (Feb 2026).

---

## 3B.1 Overview

The Event Lake is an append-only table that captures **ephemeral Discord
gateway events** — data that exists only in the real-time WebSocket stream
and cannot be retrieved later from Discord's REST API.

### The Vacuum Principle

Discord's API v10 bifurcates into two layers:

| Layer | Nature | Example Data | Our Strategy |
|-------|--------|-------------|--------------|
| **Gateway** (WebSocket) | Ephemeral real-time stream | Message sent, reaction added, voice state change, member join | **Capture in Event Lake** — disappears if not captured |
| **REST API** (HTTP) | Historical/static resources | Member list, channel metadata, role list, guild info | **Fetch on demand** — Discord stores it, rate-limited but available |

The Event Lake only captures the ephemeral stream.  Static data is
queried via the Discord REST API when needed, with local caching for
performance.  We never duplicate REST-fetchable data into the Lake.

---

## 3B.2 Intent Configuration

Discord v10 enforces a **Principle of Least Privilege** through Gateway
Intents — a bitfield sent during the WebSocket handshake that controls
which event categories the bot receives.

### Required Intents

| Intent | Type | Bit | Events Enabled | Why We Need It |
|--------|------|-----|---------------|----------------|
| GUILDS | Standard | 1 << 0 | GUILD_CREATE, CHANNEL_CREATE, THREAD_CREATE, GUILD_ROLE_* | Channel/thread/zone structure |
| GUILD_MESSAGES | Standard | 1 << 9 | MESSAGE_CREATE, MESSAGE_UPDATE, MESSAGE_DELETE | Core engagement tracking |
| GUILD_MESSAGE_REACTIONS | Standard | 1 << 10 | MESSAGE_REACTION_ADD, MESSAGE_REACTION_REMOVE | Reaction tracking |
| GUILD_VOICE_STATES | Standard | 1 << 7 | VOICE_STATE_UPDATE | Voice session tracking |
| **MESSAGE_CONTENT** | **Privileged** | 1 << 15 | Unlocks `content`, `embeds`, `attachments` fields in MESSAGE_CREATE | Quality analysis (length, code blocks, links, emoji count) |
| **GUILD_MEMBERS** | **Privileged** | 1 << 1 | GUILD_MEMBER_ADD, GUILD_MEMBER_REMOVE, GUILD_MEMBER_UPDATE | Membership tracking, member cache, leaderboard population |

### Explicitly Disabled

| Intent | Type | Why We Skip It |
|--------|------|---------------|
| GUILD_PRESENCES | Privileged | Highest bandwidth intent — floods WebSocket with thousands of events/sec in large servers. Tracks online/offline/idle/DND status and game activity. Zero engagement signal for our use case. |
| GUILD_MESSAGE_TYPING | Standard | TYPING_START events are noise — no engagement value. |
| DIRECT_MESSAGES | Standard | We don't track DMs. Privacy boundary. |

### discord.py Configuration

```python
intents = discord.Intents.default()
intents.message_content = True   # Privileged: quality analysis
intents.members = True           # Privileged: join/leave tracking
intents.presences = False        # Explicitly disabled: too expensive
```

### Verification Requirements

Discord gates privileged intents behind a verification process:

| Threshold | What Happens |
|-----------|-------------|
| **75 servers** | Verification tab unlocks in Developer Portal. Apply immediately. |
| **100 servers** | **Hard cap.** Bot cannot join new servers. Privileged intents revoked if unverified. |

**MESSAGE_CONTENT justification** (the harder approval): Synapse
performs quality-weighted engagement scoring — analyzing message
properties (length, code blocks, links, attachments) to reward
high-quality contributions.  We do NOT store, log, or persist message
content.  Quality metrics are extracted in-memory and only numerical
scores are saved.

---

## 3B.3 Event Lake Schema

### Table: `event_lake`

```sql
CREATE TABLE event_lake (
    id              BIGSERIAL PRIMARY KEY,
    guild_id        BIGINT NOT NULL,
    user_id         BIGINT NOT NULL,
    event_type      VARCHAR(64) NOT NULL,
    channel_id      BIGINT,
    target_id       BIGINT,
    payload         JSONB NOT NULL DEFAULT '{}',
    source_id       VARCHAR(128),
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Primary query patterns
CREATE INDEX idx_event_lake_user_ts ON event_lake (user_id, timestamp DESC);
CREATE INDEX idx_event_lake_type_ts ON event_lake (event_type, timestamp DESC);
CREATE INDEX idx_event_lake_guild_ts ON event_lake (guild_id, timestamp DESC);
CREATE INDEX idx_event_lake_channel_ts ON event_lake (channel_id, timestamp DESC)
    WHERE channel_id IS NOT NULL;

-- Idempotency: prevent duplicate events from bot restarts / replays
CREATE UNIQUE INDEX idx_event_lake_source ON event_lake (source_id)
    WHERE source_id IS NOT NULL;
```

### Column Semantics

| Column | Purpose | Notes |
|--------|---------|-------|
| `user_id` | The actor (who did this) | Always the person who sent/reacted/joined |
| `channel_id` | Where it happened | NULL for non-channel events (member_join) |
| `target_id` | Context-dependent target | Message author for reactions, parent channel for threads |
| `payload` | Event-specific metadata (JSONB) | Schema varies by event_type — see §3B.4 |
| `source_id` | Discord snowflake or derived ID | Used for idempotent insert via UNIQUE index |

---

## 3B.4 Event Types & Payload Schemas

### Tier 1: Core Engagement (Always Captured)

#### `message_create`

- **Gateway event:** MESSAGE_CREATE
- **Intent:** GUILD_MESSAGES + MESSAGE_CONTENT
- **source_id:** Message snowflake (`message.id`)
- **target_id:** NULL (or `reply_to_user_id` if reply)

```json
{
  "length": 312,
  "has_code_block": true,
  "has_link": false,
  "has_attachment": true,
  "emoji_count": 0,
  "is_reply": false,
  "reply_to_user_id": null
}
```

> **Privacy note:** We extract metadata in-memory from the `content`
> field and discard the raw text.  Message content is never written to
> the database.

#### `reaction_add`

- **Gateway event:** MESSAGE_REACTION_ADD
- **Intent:** GUILD_MESSAGE_REACTIONS
- **source_id:** `"{user_id}-{message_id}-{emoji_name}"`
- **target_id:** Message author's user ID

```json
{
  "emoji_name": "👍",
  "message_id": "1234567890"
}
```

> **Implementation note:** Use `on_raw_reaction_add` (not `on_reaction_add`)
> to avoid cache dependency.  The raw event always fires regardless of
> whether the message is in discord.py's internal cache.

#### `reaction_remove`

- **Gateway event:** MESSAGE_REACTION_REMOVE
- **Intent:** GUILD_MESSAGE_REACTIONS
- **source_id:** NULL (removal events don't have unique IDs)
- **target_id:** Message author's user ID (if known)

```json
{
  "emoji_name": "👍",
  "message_id": "1234567890"
}
```

#### `thread_create`

- **Gateway event:** THREAD_CREATE
- **Intent:** GUILDS
- **source_id:** Thread channel snowflake
- **target_id:** Parent channel ID

```json
{
  "name": "help-with-docker",
  "parent_channel_id": "9876543210"
}
```

### Tier 2: Voice (Toggleable)

Voice tracking is built on VOICE_STATE_UPDATE, which fires whenever a
user joins, leaves, moves between, or changes state in a voice channel.

**Gateway payload fields:** `guild_id`, `channel_id`, `user_id`,
`session_id`, `deaf`, `mute`, `self_deaf`, `self_mute`, `self_stream`,
`self_video`

We decompose this into three derived event types:

#### `voice_join`

- **source_id:** `"{user_id}-{session_id}-join"`

```json
{
  "channel_id": "1111111111",
  "self_mute": false,
  "self_deaf": false,
  "is_afk": false
}
```

#### `voice_leave`

- **source_id:** `"{user_id}-{session_id}-leave"`
- **Derived field:** `duration_seconds` computed from join timestamp

```json
{
  "channel_id": "1111111111",
  "duration_seconds": 3420,
  "self_mute": true,
  "self_deaf": true,
  "is_afk": false
}
```

#### `voice_move`

- **source_id:** `"{user_id}-{session_id}-move-{timestamp}"`

```json
{
  "from_channel_id": "1111111111",
  "to_channel_id": "2222222222",
  "is_afk": false
}
```

#### AFK Channel Exclusion

**Problem:** Members park in voice channels while muted + deafened,
inflating engagement metrics.

**Solution:** Multi-layer AFK detection:

1. **Discord's built-in AFK channel:** Read `guild.afk_channel_id` from
   the Guild object (available in GUILD_CREATE or via REST).  Events in
   this channel are tagged `is_afk: true`.

2. **Admin-designated non-tracked channels:** Admins can mark additional
   voice channels as "non-engagement" (e.g., a Music Bot lounge).
   Stored in Region/Zone configuration.

3. **Idle state detection:** If `self_mute AND self_deaf` for the entire
   session, the `voice_leave` event is tagged `is_afk: true` regardless
   of channel.

AFK events are **still stored** in the Event Lake (for data completeness
and analytics segmentation) but are **tagged** so the Rules Engine can
filter them:

```
Default voice rule condition: voice.is_afk == false
```

The dashboard shows AFK time as a separate segment — visible but not
counted toward engagement.

#### DAVE Protocol (Future-Proofing)

Discord's upcoming DAVE (Audio/Video End-to-End Encryption) protocol
will encrypt voice streams client-side in 2026.  This makes audio
recording/transcription significantly harder for bots.  Our design is
**unaffected** — we only track connection metadata via VOICE_STATE_UPDATE,
which is not encrypted.

### Tier 3: Membership (Toggleable, Privileged)

#### `member_join`

- **Gateway event:** GUILD_MEMBER_ADD
- **Intent:** GUILD_MEMBERS (privileged)
- **source_id:** `"{user_id}-join-{timestamp}"`

```json
{
  "joined_at": "2026-02-12T14:30:00Z"
}
```

#### `member_leave`

- **Gateway event:** GUILD_MEMBER_REMOVE
- **Intent:** GUILD_MEMBERS (privileged)
- **source_id:** `"{user_id}-leave-{timestamp}"`

```json
{}
```

### Derived Events (Computed, Not Directly Captured)

| Derived Event | Source | Logic | Storage |
|---------------|--------|-------|---------|
| `voice_session` | `voice_join` + `voice_leave` | Pair join/leave by session_id, compute duration | Via `voice_leave.duration_seconds` |
| `active_day` | Any user event | Deduplicated: one per user per UTC day | Counter cache only |

### Explicitly NOT Captured

| Gateway Event | Why We Skip It |
|---------------|---------------|
| PRESENCE_UPDATE | Bandwidth bomb.  No engagement signal.  Intent disabled. |
| MESSAGE_UPDATE | Edits have low engagement value.  Content fetchable via REST. |
| MESSAGE_DELETE | No content in payload.  Moderation concern, not engagement. |
| TYPING_START | Pure noise. |
| GUILD_AUDIT_LOG_ENTRY_CREATE | Discord retains audit logs for 45 days.  Fetch via REST if needed. |
| MESSAGE_POLL_VOTE_ADD/REMOVE | Niche.  Could add later if poll engagement matters. |

---

## 3B.5 Storage Estimates

Based on the audit's payload size measurements (§7.2), calibrated for
a moderately active 500-member server generating ~10 messages/minute.

### Per-Event Sizes

| Event Type | Raw Gateway Payload | Our Stored Row |
|------------|--------------------|--------------:|
| `message_create` | ~480 bytes + content | ~200 bytes |
| `reaction_add` | ~180 bytes | ~120 bytes |
| `reaction_remove` | ~180 bytes | ~120 bytes |
| `voice_join/leave/move` | ~250 bytes | ~150 bytes |
| `thread_create` | ~400 bytes | ~150 bytes |
| `member_join/leave` | ~300 bytes | ~100 bytes |

### Volume Projection

| Metric | 500 Members | 2,000 Members | 10,000 Members |
|--------|------------|--------------|---------------|
| Daily events | ~22,000 | ~88,000 | ~440,000 |
| Daily storage | ~3.7 MB | ~15 MB | ~75 MB |
| Monthly storage | ~111 MB | ~450 MB | ~2.25 GB |
| **90-day retention** | **~333 MB** | **~1.35 GB** | **~6.75 GB** |

### Index Overhead

Indexes typically add 30–50% overhead on top of raw data.  At 90-day
retention for 500 members: ~333 MB data + ~150 MB indexes = **~500 MB
total**.

### Counter Cache Overhead

The `event_counters` table is negligible:
500 users × 6 event types × 5 zones × 3 periods = ~45,000 rows × 50 bytes
= **~2.2 MB**.

### Recommendation

| Server Size | PostgreSQL Tier | Storage Allocation |
|-------------|----------------|-------------------|
| < 1,000 members | Basic (1 GB) | Comfortable |
| 1,000–5,000 | General Purpose (4 GB) | Comfortable |
| 5,000–10,000 | General Purpose (16 GB) | Monitor growth |
| > 10,000 | Consider shorter retention or archival | Scale review |

---

## 3B.6 Counter Cache (Aggregation Layer)

To avoid expensive `COUNT(*)` queries on the Event Lake, pre-computed
counters provide O(1) reads for the Rules Engine and Milestone checker.

### Table: `event_counters`

```sql
CREATE TABLE event_counters (
    user_id         BIGINT NOT NULL,
    event_type      VARCHAR(64) NOT NULL,
    zone_id         INT,
    period          VARCHAR(16) NOT NULL,   -- 'lifetime', 'season', 'day:YYYY-MM-DD'
    count           BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, event_type, COALESCE(zone_id, 0), period)
);
```

Counters are updated **transactionally** with each Event Lake insert —
same database transaction, so they never drift from the raw data.

The Rules Engine and Milestone checker read from counters, never from
raw Event Lake rows.  Periodic reconciliation (weekly CRON) validates
counter accuracy against raw counts as a safety net.

---

## 3B.7 Retention Policy

| Tier | Default Retention | Rationale |
|------|------------------|-----------|
| Raw events (`event_lake`) | 90 days | Sufficient for trends, milestones, and rule evaluation |
| Daily counters (`event_counters` with `day:*` period) | 90 days | Matches raw event retention |
| Lifetime/season counters | Forever | Tiny footprint, needed for milestones |
| Season snapshots | Forever | Historical record |

Retention is **admin-configurable** per deployment.  A scheduled cleanup
job (daily CRON) hard-deletes events and daily counters beyond the
retention window.

### Cleanup Query

```sql
DELETE FROM event_lake
WHERE timestamp < NOW() - INTERVAL '90 days';

DELETE FROM event_counters
WHERE period LIKE 'day:%'
  AND period < 'day:' || TO_CHAR(NOW() - INTERVAL '90 days', 'YYYY-MM-DD');
```

---

## 3B.8 Data Sources Panel (Admin UI)

```
┌─────────────────────────────────────────────────────────────┐
│  📡 Data Sources                                             │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  CORE ENGAGEMENT                                             │
│  ✅ Messages     Track message events          [Standard]    │
│  ✅ Reactions     Track reaction add/remove     [Standard]    │
│  ✅ Threads       Track thread creation         [Standard]    │
│                                                              │
│  PRESENCE                                                    │
│  ✅ Voice         Track voice connections       [Standard]    │
│     └─ AFK channel exclusion: ON (auto-detected + manual)    │
│     └─ Non-tracked channels: #music-bot, #afk-lounge         │
│  ☐  Online Status  Track online/offline         [Privileged]  │
│     └─ ⚠️ High bandwidth.  Not recommended.                  │
│                                                              │
│  MEMBERSHIP                                                  │
│  ✅ Joins/Leaves  Track member flow             [Privileged]  │
│                                                              │
│  STORAGE                                                     │
│  Retention: [90] days                                        │
│  Estimated usage: ~333 MB (500 members, 90 days)             │
│  Counter cache: ~2 MB                                        │
│                                                              │
│  🔒 PRIVACY COMMITMENT                                       │
│  Message content is never stored.  Voice audio is never       │
│  recorded.  Online/offline status is not tracked.  See the    │
│  Transparency page for full details.                          │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 3B.9 REST API Backfill

For data that Discord stores (not ephemeral), the API service fetches
on demand:

| Resource | REST Endpoint | Cache TTL | Use Case |
|----------|--------------|-----------|----------|
| Guild info | GET /guilds/{id} | 1 hour | Member count, features, AFK channel ID |
| Channel list | GET /guilds/{id}/channels | 30 min | Zone mapping, channel names for display |
| Member list | Chunked via Gateway OpCode 8 | 5 min | Leaderboard population, profile lookup |
| Role list | Included in GUILD_CREATE | 1 hour | Permission checks, role-gated rules |
| User info | GET /users/{id} | 1 hour | Avatar URL, display name |

### Rate Limit Budget

| Constraint | Limit | Our Approach |
|-----------|-------|-------------|
| Global rate limit | 50 req/sec per bot token | discord.py handles this internally |
| Per-route buckets | Varies (headers: X-RateLimit-*) | discord.py handles this internally |
| Invalid request ban | 10,000 invalid requests in 10 min = Cloudflare IP ban | Never send known-invalid requests; validate IDs before fetching |

Custom REST calls (outside discord.py) must implement exponential backoff
on HTTP 429 responses and respect the `X-RateLimit-Reset-After` header.

---

## 3B.10 discord.py Implementation Notes

### Raw Events vs. Cached Events

| Pattern | Use For | Why |
|---------|---------|-----|
| `on_message(message)` | Reading message content for quality analysis | Content available in the Message object |
| `on_raw_reaction_add(payload)` | Event Lake capture | Cache-independent — fires even if message isn't cached |
| `on_raw_reaction_remove(payload)` | Event Lake capture | Same — never misses events |
| `on_voice_state_update(member, before, after)` | Voice session tracking | Standard event is fine — voice states are always current |
| `on_member_join(member)` | Event Lake capture | Standard event is fine — no cache dependency |
| `on_member_remove(member)` | Event Lake capture | Standard event is fine |

**Rule:** For reactions, always use raw events.  For everything else,
standard events are reliable because they don't depend on message cache.

### Hot Path Safety

All database writes from event handlers must use `asyncio.to_thread()`
to avoid blocking the Gateway heartbeat.  A blocked heartbeat causes
Discord to sever the connection (zombie connection detection).

The `on_socket_raw_receive` listener is the most dangerous hot path
and should **never** be used for Event Lake writes.

---

## Decisions

> **Decision D03B-01:** Append-Only Event Lake
> - **Status:** Accepted
> - **Context:** The bot needs historical event data for trend analysis,
>   milestone evaluation, and rule conditions.
> - **Choice:** Single `event_lake` table with JSONB payload, indexed by
>   user, type, channel, and timestamp.  Idempotent insert via unique
>   `source_id` index.
> - **Consequences:** Simple schema.  Flexible payload.  Retention
>   managed by periodic cleanup.  ~333 MB for 500 members at 90 days.

> **Decision D03B-02:** Counter Cache for Performance
> - **Status:** Accepted
> - **Context:** Counting raw events per-user is O(n) on the Event Lake.
> - **Choice:** Maintain `event_counters` as a transactionally-updated
>   aggregate table.  Weekly reconciliation job validates accuracy.
> - **Consequences:** O(1) reads for milestone checks and rule conditions.
>   ~2 MB overhead.  Slight write amplification per event.

> **Decision D03B-03:** The Vacuum Principle
> - **Status:** Accepted
> - **Context:** Discord's REST API stores persistent data (members,
>   channels, roles).  Duplicating it wastes storage and creates
>   staleness risk.
> - **Choice:** Only capture ephemeral gateway events.  Fetch static
>   data via REST API on demand with local caching.
> - **Consequences:** Smaller Lake.  No data staleness.  Rate-limited
>   REST queries mitigated by caching.

> **Decision D03B-04:** Skip GUILD_PRESENCES Intent
> - **Status:** Accepted
> - **Context:** GUILD_PRESENCES is the most bandwidth-heavy intent,
>   flooding the WebSocket with status changes for every member.
> - **Choice:** Do not enable GUILD_PRESENCES.  Online/offline/idle
>   status is not tracked.
> - **Consequences:** No "who's online" analytics.  Significant bandwidth
>   savings.  One fewer privileged intent to justify at verification.

> **Decision D03B-05:** AFK Channel Exclusion for Voice Tracking
> - **Status:** Accepted
> - **Context:** Members park in voice channels while AFK, inflating
>   engagement metrics.
> - **Choice:** Auto-detect Discord's built-in AFK channel.  Allow
>   admins to designate additional non-tracked channels.  Tag AFK
>   events with `is_afk: true` rather than dropping them.
> - **Consequences:** Clean engagement metrics.  AFK data preserved for
>   analytics segmentation.  Rules Engine can filter on `is_afk`.

> **Decision D03B-06:** Voice = Connection Metadata Only
> - **Status:** Accepted
> - **Context:** Voice tracking could mean audio recording/transcription
>   or connection metadata (who, where, how long).
> - **Choice:** Track connection metadata only.  No audio recording.
>   No transcription.  Discord's DAVE protocol (2026) makes audio
>   access harder anyway.
> - **Consequences:** Simpler implementation.  Future-proof against DAVE.
>   Clear privacy boundary.  Voice engagement = time spent in channel.

> **Decision D03B-07:** Message Content Never Stored
> - **Status:** Accepted
> - **Context:** MESSAGE_CONTENT intent gives access to message text.
>   Storing it would be a surveillance concern and a storage burden.
> - **Choice:** Extract quality metadata (length, has_code_block,
>   has_link, etc.) in-memory.  Write only the metadata to the Event
>   Lake.  Raw text is never persisted.
> - **Consequences:** Clean privacy story.  Simpler verification
>   justification.  Quality analysis works.  Cannot replay message
>   content from the Lake (by design).

> **Decision D03B-08:** Raw discord.py Events for Reactions
> - **Status:** Accepted
> - **Context:** Standard `on_reaction_add` silently drops events when
>   the target message isn't in discord.py's internal cache (LRU, typically
>   1000–5000 messages).
> - **Choice:** Use `on_raw_reaction_add` and `on_raw_reaction_remove`
>   for Event Lake capture.  These fire for every gateway payload
>   regardless of cache state.
> - **Consequences:** 100% reaction capture rate.  Slightly less
>   convenient API (RawReactionActionEvent vs. Reaction object).
