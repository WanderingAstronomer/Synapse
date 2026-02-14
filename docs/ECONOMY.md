# Economy System

All economy configuration is stored in the `settings` database table and editable from the admin dashboard without redeploying.

## Currencies

Three built-in currencies:

| Currency | Default Name | Purpose | Earning |
|----------|-------------|---------|---------|
| **XP** | XP | Progression — drives leveling | Events (quality-modified) |
| **Stars** | Stars | Seasonal recognition | Events (per-season tracking) |
| **Gold** | Gold | Spendable | Level-up bonus + manual awards |

Currency display names are configurable via `currency_name_primary` and `currency_name_secondary` settings.

## Leveling

Exponential formula:

```
XP required for level N = level_base × (level_factor ^ N)
```

| Setting | Default | Description |
|---------|---------|-------------|
| `level_base` | 100 | Base XP constant |
| `level_factor` | 1.25 | Exponential growth factor |
| `gold_per_level_up` | 50 | Gold bonus on each level-up |

Implementation: `synapse/constants.py` → `xp_for_level(level, cache)`.

## Base Reward Rates

Defined in `synapse/engine/events.py`:

| Event Type | Base XP | Base Stars |
|------------|---------|------------|
| MESSAGE | 15 | 1 |
| REACTION_GIVEN | 5 | 1 |
| REACTION_RECEIVED | 8 | 2 |
| THREAD_CREATE | 20 | 2 |
| VOICE_TICK | 10 | 1 |
| QUEST_COMPLETE | 50 | 5 |
| MANUAL_AWARD | 0 | 0 |
| LEVEL_UP | 0 | 0 |
| ACHIEVEMENT_EARNED | 0 | 0 |
| VOICE_JOIN | 0 | 0 |
| VOICE_LEAVE | 0 | 0 |

## Categories

Channels are grouped into **Categories**. Each category has per-event-type multipliers for XP and Stars.

### Bootstrap

During first-run setup, categories are created from Discord server categories. Channels are mapped to categories by matching Discord category name to category name (case-insensitive substring match). Unmapped channels fall back to a "general" category or the first available category.

### Multipliers

Stored in `category_multipliers` table. Each row maps `(category_id, interaction_type)` → `(xp_multiplier, star_multiplier)`. Defaults to `(1.0, 1.0)` if no entry exists.

### Category Classification

In the reward pipeline, each event's `channel_id` is resolved to a category via `ConfigCache.get_category_for_channel()`. The category's multipliers are then looked up for the event type.

## Reward Pipeline

Implemented in `synapse/engine/reward.py` as a pure calculation function (no I/O):

```
SynapseEvent
  → Category Classification (channel → category lookup)
  → Multiplier Lookup (category × event_type → xp_mult, star_mult)
  → Quality Modifier (MESSAGE only, multiplicative on XP)
  → Anti-Gaming Adjustments
  → XP Cap Application
  → Level-Up Check
  → RewardResult
```

The pipeline returns a `RewardResult` dataclass with: `xp`, `stars`, `leveled_up`, `new_level`, `gold_bonus`, `achievements_earned`, `category_name`.

## Quality Modifiers

Applied only to MESSAGE events, multiplicatively on XP. Implemented in `synapse/engine/quality.py`.

| Condition | Modifier | Setting Key |
|-----------|----------|-------------|
| Content > 500 chars | ×1.5 | `quality_length_long` / `quality_multiplier_long` |
| Content > 200 chars | ×1.2 | `quality_length_medium` / `quality_multiplier_medium` |
| Contains code block | ×1.4 | `quality_multiplier_code` |
| Contains link | ×1.25 | `quality_multiplier_link` |
| Contains attachment | ×1.1 | `quality_multiplier_attachment` |
| Emoji count > 5 | ×0.5 | `quality_emoji_spam_threshold` / `quality_penalty_emoji_spam` |

Length tiers are mutually exclusive (longest match wins). All modifiers stack multiplicatively. Floor: `max(result, 0.1)`.

## Anti-Gaming

Implemented in `synapse/engine/anti_gaming.py`. Thread-safe via `threading.Lock`.

### Self-Reaction Filter

Reacting to your own message: XP and Stars both set to 0.

### Pair Cap

Max reactions rewarded per reactor→author pair per 24-hour sliding window.

| Setting | Default |
|---------|---------|
| `max_reactions_per_pair_per_day` | 3 |

Uses `AntiGamingTracker` — in-memory dict mapping `(reactor_id, target_user_id)` → list of timestamps. Automatic hourly cleanup of expired entries (>24h).

### Diminishing Returns

For REACTION_RECEIVED: returns factor `1/(1+count)` where count is the number of times this reactor→author pair has interacted in the current window.

### Unique-Reactor Weighting

REACTION_RECEIVED stars are scaled based on the number of distinct reactors on the message.

### Velocity Cap

XP capped to 5 for REACTION_RECEIVED events where:
- Message has > 10 unique reactors
- Message age < 5 minutes

| Setting | Default |
|---------|---------|
| `xp_cap_reaction_burst` | 5 |

### Message Cooldown

Per-user per-channel cooldown prevents MESSAGE reward spam.

| Setting | Default |
|---------|---------|
| `cooldown_seconds` | 30 |

Implemented in the Social cog — a dict mapping `(user_id, channel_id)` → last reward timestamp.

## Gold Economy

Gold is earned via:
- Level-up bonus (`gold_per_level_up`, default 50)
- Manual admin awards (`/award`)
- Achievement rewards (template-defined)

Gold is spent via:
- `/buy-coffee` command (`coffee_gold_cost`, default 50)

## Default Settings

Written to the `settings` table during first-run bootstrap:

| Key | Default | Category |
|-----|---------|----------|
| `xp_base_message` | 15 | economy |
| `xp_base_reaction_given` | 5 | economy |
| `xp_base_reaction_received` | 8 | economy |
| `xp_base_thread` | 20 | economy |
| `xp_base_voice_tick` | 10 | economy |
| `gold_per_level_up` | 50 | economy |
| `coffee_gold_cost` | 50 | economy |
| `level_base` | 100 | economy |
| `level_factor` | 1.25 | economy |
| `cooldown_seconds` | 30 | anti_gaming |
| `max_reactions_per_pair_per_day` | 3 | anti_gaming |
| `xp_cap_reaction_burst` | 5 | anti_gaming |
| `quality_length_medium` | 200 | quality |
| `quality_length_long` | 500 | quality |
| `quality_multiplier_long` | 1.5 | quality |
| `quality_multiplier_code` | 1.4 | quality |
| `currency_name_primary` | XP | display |
| `currency_name_secondary` | Gold | display |
| `leaderboard_size` | 25 | display |
| `announce_level_ups` | true | announcements |
| `announce_achievements` | true | announcements |
| `event_lake_retention_days` | 90 | event_lake |
| `voice_tick_minutes` | 10 | event_lake |
