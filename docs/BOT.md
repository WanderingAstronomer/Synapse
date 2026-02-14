# Discord Bot Reference

Entry point: `python -m synapse.bot` → `synapse/bot/__main__.py`.

## Cogs

8 cog modules loaded on startup (defined in `synapse/bot/core.py`):

| Cog | File | Purpose |
|-----|------|---------|
| Social | `cogs/social.py` | Message tracking → rewards |
| Reactions | `cogs/reactions.py` | Reaction tracking → rewards + lake |
| Voice | `cogs/voice.py` | Voice state tracking + tick rewards |
| Threads | `cogs/threads.py` | Thread creation → rewards |
| Membership | `cogs/membership.py` | Join/leave → lake capture only |
| Meta | `cogs/meta.py` | User slash commands |
| Admin | `cogs/admin.py` | Admin slash commands |
| PeriodicTasks | `cogs/tasks.py` | Background maintenance tasks |

## Slash Commands

### User Commands (Meta cog)

All implemented as hybrid commands (work as both slash and prefix).

#### /profile

View your (or another member's) profile.

**Parameters:** `member` (optional, defaults to caller).

**Shows:** Level, XP (with progress bar to next), gold, rank, season/lifetime stars, messages/reactions/voice stats, up to 5 achievements, GitHub link, season name.

#### /leaderboard

Top members leaderboard.

**Parameters:** `sort_by` (choice: "XP" or "Stars", default "XP").

Size controlled by `leaderboard_size` setting (default 25). Stars leaderboard uses the active season.

#### /link-github

Associate your GitHub account with your Synapse profile.

**Parameters:** `username` (string).

Validates format against `^[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,37}[a-zA-Z0-9])?$`. Ephemeral response.

#### /preferences

Toggle personal announcement visibility.

**Parameters:** `setting` (choice: "Announce Level-Ups", "Announce Achievements", "Announce Awards"), `enabled` (boolean).

Ephemeral response.

#### /buy-coffee

Spend gold to buy a virtual coffee (minimal gold sink).

Cost from `coffee_gold_cost` setting (default 50). Ephemeral response.

### Admin Commands (Admin cog)

All slash-only (not hybrid). Gated by `admin_role_id` check — user must have the configured admin role.

#### /award

Manually award XP and/or Gold to a member.

**Parameters:** `member`, `xp` (default 0), `gold` (default 0), `reason` (default "Manual admin award").

At least one of xp/gold must be > 0. Ephemeral confirmation to admin, then public announcement (preference-gated).

#### /create-achievement

Create a new achievement template.

**Parameters:** `name`, `description`, `requirement_type` (choice: counter_threshold / star_threshold / xp_milestone / custom, default "custom"), `requirement_field` (optional), `requirement_value` (optional), `xp_reward` (default 0), `gold_reward` (default 0), `rarity` (choice: common / uncommon / rare / epic / legendary, default "common").

Public embed response showing created achievement.

#### /grant-achievement

Grant an achievement to a member by template ID.

**Parameters:** `member`, `achievement_id` (integer).

Ephemeral confirmation, then public announcement.

#### /season

Create a new season (deactivates the current one).

**Parameters:** `name`, `duration_days` (default 120).

Public embed response.

### Error Handling

All admin commands catch `CheckFailure` and send an ephemeral "🔒 You need the Admin role" message.

## Event Listeners

### Social: on_message

Fires on every guild message. Gates:
1. Ignore bots
2. Ignore DMs
3. Per-user per-channel cooldown (`cooldown_seconds` setting, default 30s)

On pass: writes to Event Lake (metadata only — content never stored), builds `SynapseEvent`, runs through `reward_service.process_event()`, announces results.

Metadata extracted: content length, has_code_block, has_link, has_attachment, attachment_count, emoji_count, channel_name.

### Reactions: on_raw_reaction_add

Uses raw events to avoid cache misses on old messages. Gates: ignore bots, ignore DMs.

Writes `reaction_add` to Event Lake. Processes **two** reward events:
1. `REACTION_GIVEN` for the reactor
2. `REACTION_RECEIVED` for the message author (skipped for self-reactions and bot messages)

Counts unique reactors on the message for anti-gaming metadata.

Source event IDs: `rxn_given_{msg}_{user}_{emoji}`, `rxn_recv_{msg}_{user}_{emoji}`.

### Reactions: on_raw_reaction_remove

Event Lake capture only (`reaction_remove`). No reward processing. No idempotency key.

### Voice: on_voice_state_update

Tracks join, leave, move, and mute/deaf state changes. Ignores bots. Writes Event Lake events for each state change. Maintains in-memory `_voice_sessions` dict for tracking active sessions.

### Threads: on_thread_create

Awards XP/Stars for creating new threads. Ignores bot-owned threads. Writes `thread_create` to Event Lake. Announces via parent channel or thread.

### Membership: on_member_join / on_member_remove

Data capture only — writes `member_join` / `member_leave` to Event Lake. No reward processing. Requires `GUILD_MEMBERS` privileged intent.

## Background Tasks

### voice_tick_loop (Voice cog)

**Interval:** 10 minutes.

Iterates all guild voice channels. For each non-bot member:
- **Idle detection:** Skips users who are both self-muted AND self-deafened
- **Hourly cap:** Max 6 ticks per user per hour (pruned sliding window)
- Creates `VOICE_TICK` event and processes rewards

Metadata: voice channel name, tick minutes, member count in channel.

### heartbeat_loop (PeriodicTasks cog)

**Interval:** 30 seconds.

Writes a timestamp to the `settings` table. The dashboard reads this to show bot online/offline status (online if < 90s old).

### retention_loop (PeriodicTasks cog)

**Interval:** 24 hours.

Calls `run_retention_cleanup()` to delete Event Lake rows older than `event_lake_retention_days` (default 90 days). Batch size: 5,000 rows. Also prunes stale `day:*` counters.

### reconciliation_loop (PeriodicTasks cog)

**Interval:** 7 days.

Calls `reconcile_counters()` to validate lifetime event counters against raw Event Lake data. Corrects any drift and zeros orphan counters.

## Startup Sequence

1. Load `.env`
2. Validate `DISCORD_TOKEN` (exits if missing or placeholder)
3. Load `config.yaml` → `SynapseConfig`
4. Create SQLAlchemy engine + `init_db()` (CREATE TABLE IF NOT EXISTS)
5. Build `ConfigCache` and warm from DB
6. Start PG LISTEN/NOTIFY listener thread
7. Install ring buffer log handler
8. Create `SynapseBot(cfg, engine, cache)` → `bot.run(token)`

### on_ready

1. Sync slash commands (guild-scoped if `DEV_GUILD_ID` set, global otherwise)
2. Auto-create `#synapse-achievements` channel in the primary guild
3. Auto-discover guild channels and map to categories by Discord category name
4. Audit text channel access for permission issues
5. Detect AFK voice channels for Event Lake tagging
6. Start announcement throttle drain task

## Intents

| Intent | Type | Purpose |
|--------|------|---------|
| Default set | Standard | Guilds, messages, reactions, voice states |
| Message Content | Privileged | Quality analysis (length, code, links) |
| Server Members | Privileged | Join/leave tracking, member cache |
| Presences | Disabled | Explicitly off — too expensive, no engagement value |

## Shared State

All cogs access shared state via `self.bot`:

| Attribute | Type | Description |
|-----------|------|-------------|
| `bot.cfg` | `SynapseConfig` | Parsed config.yaml |
| `bot.engine` | `Engine` | SQLAlchemy database engine |
| `bot.cache` | `ConfigCache` | In-memory config with LISTEN/NOTIFY |
| `bot.lake_writer` | `EventLakeWriter` | Event Lake write service |
| `bot.synapse_announce_channel_id` | `int \| None` | Auto-created achievements channel ID |
