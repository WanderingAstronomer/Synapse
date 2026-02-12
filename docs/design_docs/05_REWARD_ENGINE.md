# 05 — Reward Engine

> *The brain of Synapse.  Events go in; XP, Stars, and Achievements come out.*

---

## 5.1 Overview

The Reward Engine is a **pure calculation pipeline**.  It receives a
`SynapseEvent`, runs it through a series of deterministic stages, and
returns a `RewardResult` describing exactly what XP, Stars, and achievements
to grant.  It does not touch Discord or the database directly — the caller
(the bot or API) handles persistence and announcements.

```
SynapseEvent → [Zone Classify] → [Multiply] → [Quality] → [Anti-Gaming] → [Cap] → RewardResult
```

---

## 5.2 The SynapseEvent (Input)

Every Discord interaction is normalized into this structure before the engine
sees it:

```python
@dataclass(frozen=True, slots=True)
class SynapseEvent:
    user_id: int
    event_type: InteractionType      # MESSAGE, REACTION_GIVEN, REACTION_RECEIVED,
                                     # THREAD_CREATE, VOICE_TICK, etc.
    channel_id: int
    guild_id: int
    source_event_id: str | None      # Discord snowflake, GitHub delivery ID, etc.
                                     # Used for idempotent insert (D04-07).
    metadata: dict                   # Varies by event type (see §5.3)
    timestamp: datetime
```

### InteractionType Enum

| Value | Discord Trigger | Base XP | Base Stars |
|-------|----------------|---------|------------|
| `MESSAGE` | `on_message` | 15 | 1 |
| `REACTION_GIVEN` | `on_reaction_add` (actor) | 2 | 1 |
| `REACTION_RECEIVED` | `on_reaction_add` (target) | 3 | 1 |
| `THREAD_CREATE` | `on_thread_create` | 20 | 2 |
| `VOICE_TICK` | Voice state polling (every 10 min) | 0 | 1 |
| `QUEST_COMPLETE` | Manual or webhook | varies | 5 |
| `MANUAL_AWARD` | `/award` command | varies | 0 |

Base XP and Base Stars are **defaults** that can be overridden in the
`config.yaml` seed file.

---

## 5.3 Metadata by Event Type

| Event Type | Metadata Keys | Purpose |
|------------|--------------|---------|
| `MESSAGE` | `length`, `has_code_block`, `has_link`, `has_attachment`, `emoji_count`, `is_reply`, `reply_to_user_id`, `channel_id` | Quality scoring + reply tracking |
| `REACTION_GIVEN` | `emoji_name`, `target_message_id`, `target_user_id`, `channel_id` | Tracking + per-user per-target cap |
| `REACTION_RECEIVED` | `emoji_name`, `reactor_id`, `unique_reactor_count`, `message_age_seconds`, `channel_id` | Velocity cap + unique-reactor weighting |
| `THREAD_CREATE` | `parent_channel_id` | Zone resolution |
| `VOICE_TICK` | `minutes_in_session`, `is_muted`, `is_deafened` | Anti-idle |

---

## 5.4 Stage 1: Zone Classification

The engine looks up which **Zone** the event's `channel_id` belongs to by
querying the `zone_channels` table (cached in memory, invalidated via PG NOTIFY).

```python
def classify_zone(channel_id: int) -> Zone | None:
    """Returns the Zone for this channel, or None for 'default'."""
    return channel_zone_cache.get(channel_id)
```

If a channel is not mapped to any zone, the **default zone** applies
(multipliers = 1.0 across the board).

---

## 5.5 Stage 2: Multiplier Lookup

Each zone has per-event-type multipliers stored in `zone_multipliers`.

```python
def get_multipliers(zone_id: int, event_type: str) -> tuple[float, float]:
    """Returns (xp_multiplier, star_multiplier) for this zone+event."""
    key = (zone_id, event_type)
    row = multiplier_cache.get(key)
    if row:
        return (row.xp_multiplier, row.star_multiplier)
    return (1.0, 1.0)  # default
```

**Example multiplier table for "programming" zone:**

| Interaction Type | XP Multiplier | Star Multiplier |
|-----------------|---------------|-----------------|
| MESSAGE | 1.5 | 1.0 |
| THREAD_CREATE | 2.0 | 1.5 |
| REACTION_RECEIVED | 0.5 | 1.0 |
| REACTION_GIVEN | 0.3 | 1.0 |

**Example multiplier table for "memes" zone:**

| Interaction Type | XP Multiplier | Star Multiplier |
|-----------------|---------------|-----------------|
| MESSAGE | 0.5 | 1.0 |
| REACTION_RECEIVED | 0.2 | 1.5 |
| REACTION_GIVEN | 0.2 | 1.0 |

---

## 5.6 Stage 3: Quality Modifiers (Messages Only)

For `MESSAGE` events, the engine applies heuristic bonuses based on content
metadata.  These are **multiplicative** — they stack.

| Modifier | Condition | Effect | Rationale |
|----------|-----------|--------|-----------|
| **Length Bonus** | `length > 200` | ×1.2 | Longer = more effort |
| **Long-Form Bonus** | `length > 500` | ×1.5 | Replaces length bonus |
| **Code Block** | `has_code_block = True` | ×1.4 | Technical contribution |
| **Link Enrichment** | `has_link = True` | ×1.25 | Sharing resources |
| **Attachment** | `has_attachment = True` | ×1.1 | Screenshots, files |
| **Emoji Spam** | `emoji_count > 5` | ×0.5 | Discourage spam |

```python
def calculate_quality_modifier(event: SynapseEvent) -> float:
    """Returns a multiplicative quality modifier (>= 0.1)."""
    if event.event_type != InteractionType.MESSAGE:
        return 1.0

    m = event.metadata
    modifier = 1.0
    length = m.get("length", 0)

    if length > 500:
        modifier *= 1.5
    elif length > 200:
        modifier *= 1.2

    if m.get("has_code_block"):
        modifier *= 1.4
    if m.get("has_link"):
        modifier *= 1.25
    if m.get("has_attachment"):
        modifier *= 1.1
    if m.get("emoji_count", 0) > 5:
        modifier *= 0.5

    return max(modifier, 0.1)  # floor to prevent zero-XP
```

Quality modifiers apply **only to XP**, not to Stars.

---

## 5.7 Stage 4: Anti-Gaming Checks

Between quality scoring and cap enforcement, the engine runs anti-gaming
rules that can **zero-out** partial rewards.  These checks apply to both XP
and Stars unless stated otherwise.

### 5.7.1 Unique-Reactor Weighting (Stars)

For `REACTION_RECEIVED`, the Star award uses `unique_reactor_count` from
metadata instead of raw reaction count.  If a user reacts with multiple emoji
on one message, only 1 Star is credited.

### 5.7.2 Per-User Per-Target Cap (Stars)

A single `reactor_id` can generate at most **3 Stars per target user per
rolling 24-hour window**.  Checked via a fast in-memory sliding window
(`user_pair_cache`).

### 5.7.3 Diminishing Returns (Stars)

Beyond 10 unique reactors on one message, additional `REACTION_RECEIVED`
Stars are applied at **0.5× rate** (rounded down, minimum 0).  Prevents
viral-meme Star explosions.

### 5.7.4 Self-Reaction Filter

If `reactor_id == user_id`, the event is silently dropped (0 XP, 0 Stars).

```python
def apply_anti_gaming(event: SynapseEvent, base_stars: int) -> int:
    """Adjust star award after anti-gaming checks.  Returns adjusted stars."""
    if event.event_type != InteractionType.REACTION_RECEIVED:
        return base_stars

    m = event.metadata
    # Self-reaction
    if m.get("reactor_id") == event.user_id:
        return 0

    # Unique-reactor weighting
    unique = m.get("unique_reactor_count", 1)
    stars = min(base_stars, unique)

    # Per-user per-target cap (checked externally via sliding window)
    if is_pair_capped(m["reactor_id"], event.user_id):
        return 0

    # Diminishing returns above threshold
    if unique > 10:
        excess = unique - 10
        stars = 10 + (excess // 2)

    return stars
```

---

## 5.8 Stage 5: Caps and Anti-Gaming (XP)

### Reaction Velocity Cap (XP Only)

If a single message receives >10 reactions within 5 minutes, XP from
`REACTION_RECEIVED` is capped at 5 XP total for that message.  Star caps
are handled by the Anti-Gaming stage (§5.7).

### Voice Idle Detection (Future)

If `is_muted AND is_deafened` for >5 minutes, voice ticks stop generating
Stars.

### Daily XP Ceiling (Optional, Configurable)

Admins can set a maximum XP earnable per user per 24-hour period.  Default:
no ceiling.

---

## 5.9 Stage 6: LLM Quality Assessment (Optional)

For messages in designated high-value zones that exceed a minimum length, the
engine can optionally route the content to an LLM for scoring:

```yaml
llm_quality_check:
  enabled: false                   # Opt-in per deployment
  provider: "groq"                 # or "openai", "anthropic"
  zones: ["programming", "cybersecurity"]
  min_length: 500
  max_daily_calls: 50              # Budget control
```

**LLM Prompt:**
```
You are a technical mentor evaluating a student's contribution.
Rate this post on three dimensions (1-10 each):
- Clarity: How well-written and understandable is it?
- Depth: How technically substantial is it?
- Usefulness: How helpful is it to other students?

Respond ONLY with JSON: {"clarity": N, "depth": N, "usefulness": N}

Post content:
{message_content}
```

**Scoring:**
```python
llm_modifier = (clarity + depth + usefulness) / 30 * 2.0
# Perfect 10/10/10 = 2.0x multiplier
# Average 5/5/5 = 1.0x (no change)
# Poor 2/2/2 = 0.4x (still gets something)
```

This is **deferred to a future phase** but the pipeline has a slot for it.

---

## 5.10 The RewardResult (Output)

```python
@dataclass
class RewardResult:
    xp: int                            # Final XP to award
    stars: int                         # Final Stars to award
    leveled_up: bool                   # Did this push them to a new level?
    new_level: int | None              # If leveled_up, the new level
    gold_bonus: int                    # Gold from level-up (0 otherwise)
    achievements_earned: list[int]     # IDs of achievement_templates triggered
    zone_name: str | None              # For logging
```

---

## 5.11 Full Calculation

```python
def calculate_reward(event: SynapseEvent, user: User, stats: UserStats) -> RewardResult:
    # 1. Zone
    zone = classify_zone(event.channel_id)
    zone_id = zone.id if zone else DEFAULT_ZONE_ID

    # 2. Multipliers
    xp_mult, star_mult = get_multipliers(zone_id, event.event_type.value)

    # 3. Quality (messages only)
    quality = calculate_quality_modifier(event)

    # 4. Base values
    base_xp = BASE_XP[event.event_type]
    base_stars = BASE_STARS[event.event_type]

    # 5. Calculate
    final_xp = int(base_xp * xp_mult * quality)
    final_stars = int(base_stars * star_mult)

    # 6. Level-up check
    new_xp = user.xp + final_xp
    required = int(cfg.level_base * (cfg.level_factor ** user.level))
    leveled_up = new_xp >= required
    new_level = user.level + 1 if leveled_up else None
    gold_bonus = cfg.gold_per_level_up if leveled_up else 0

    # 7. Achievement check
    new_stats = apply_star_delta(stats, event.event_type, final_stars)
    achievements = check_achievements(new_stats)

    return RewardResult(
        xp=final_xp,
        stars=final_stars,
        leveled_up=leveled_up,
        new_level=new_level,
        gold_bonus=gold_bonus,
        achievements_earned=achievements,
        zone_name=zone.name if zone else "default",
    )
```

---

## 5.12 Caching Strategy

Config data (zones, multipliers, achievement templates) is cached in memory
for performance.  Cache invalidation uses **PostgreSQL LISTEN/NOTIFY** so
admin changes propagate instantly instead of waiting for a TTL window.

| Data | Cache Location | Invalidation |
|------|---------------|-------------|
| Zone → Channel mapping | In-memory dict | PG NOTIFY `config_changed` on zone/channel write |
| Zone multipliers | In-memory dict | PG NOTIFY `config_changed` on multiplier write |
| Achievement templates | In-memory list | PG NOTIFY `config_changed` on template write |
| User cooldowns | In-memory dict | Bot restart |
| Anti-gaming sliding windows | In-memory dict | Rolling expiry (24h) |

### How It Works

1. On startup, the bot loads all config into memory.
2. An `asyncio.Task` listens on a PG channel (`config_changed`).
3. When the admin panel (via FastAPI) writes a config change, the shared service
   layer issues `NOTIFY config_changed, '<table_name>'` after the commit.
4. The bot's listener receives the notification and reloads the affected
   cache partition.

This gives near-instant propagation (typically <100ms) without polling or
external dependencies (no Redis).  See D05-08 and D08-03.

---

## Decisions

> **Decision D05-01:** Quality Modifiers Apply to XP Only
> - **Status:** Accepted
> - **Context:** Stars are meant to be "fair" counters of participation.
> - **Choice:** Quality multipliers affect XP but not Stars.
> - **Consequences:** A short meme message earns the same 1 Star as a long
>   tutorial.  The differentiation happens in the XP column.

> **Decision D05-02:** LLM Valuation Is Deferred
> - **Status:** Deferred (Phase 3+)
> - **Context:** LLM calls cost money and add latency.
> - **Choice:** The pipeline has a slot for LLM scoring, but it is disabled
>   by default and not yet implemented.
> - **Consequences:** We rely on heuristics (length, code blocks) for now.

> **Decision D05-03:** In-Memory Cache with PG LISTEN/NOTIFY (Amended v2.2)
> - **Status:** Accepted
> - **Context:** Original 5-min TTL cache meant admin changes could be stale
>   for up to 5 minutes.  This is dangerous for multiplier changes applied
>   during live events.
> - **Choice:** Replace TTL polling with PG LISTEN/NOTIFY.  Cache is loaded
>   on startup and refreshed on notification.  No external cache (Redis).
> - **Consequences:** Near-instant invalidation.  Requires an asyncio listener
>   task in the bot.  Shared service layer must issue NOTIFY after commits.

> **Decision D05-04:** Quality Modifiers Are XP-Only
> - **Status:** Accepted (Clarified v2.2)
> - **Context:** Stars are participation counters, not quality rewards.
> - **Choice:** Quality modifiers (§5.6) never affect Star calculations.
> - **Consequences:** Consistent with the dual-economy split (D03-01).

> **Decision D05-05:** Anti-Gaming Is a Separate Pipeline Stage
> - **Status:** Accepted
> - **Context:** Anti-gaming checks (unique-reactor weighting, per-user caps,
>   diminishing returns) were originally lumped into the Cap stage.
> - **Choice:** Extract into a dedicated stage (§5.7) between Quality and Cap.
> - **Consequences:** Cleaner code organization; easier to audit and tune.

> **Decision D05-06:** Self-Reactions Produce Zero Reward
> - **Status:** Accepted
> - **Context:** A user can react to their own message in Discord.
> - **Choice:** The anti-gaming stage silently drops self-reaction events.
> - **Consequences:** No XP or Stars from self-reactions.  No error shown.

> **Decision D05-07:** Idempotent Event Insert
> - **Status:** Accepted
> - **Context:** Discord events can be delivered more than once (retries,
>   reconnects).
> - **Choice:** The persistence layer uses `ON CONFLICT DO NOTHING` on
>   `(source_system, source_event_id)` partial unique index.  Duplicate
>   events are silently skipped.
> - **Consequences:** At-least-once delivery becomes exactly-once crediting.

> **Decision D05-08:** PG LISTEN/NOTIFY for Config Cache
> - **Status:** Accepted
> - **Context:** 5-min TTL cache invalidation was identified as a credibility
>   threat for admin-changed multipliers during live events.
> - **Choice:** PostgreSQL LISTEN/NOTIFY replaces TTL polling.
> - **Consequences:** Near-instant cache refresh.  No Redis dependency.
>   Requires shared NOTIFY call in the service layer write path.
