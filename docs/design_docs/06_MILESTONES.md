# 06 — Milestones

> *Trophies that say "I did this." Configurable, queryable, displayable.*

---

## 6.1 Purpose

Milestones are the **collection layer** of Synapse.  They recognize
participation patterns, accomplishments, and community landmarks that go
beyond simple currency accumulation:

- **Consistency** — "Active 7 days in a row."
- **Volume** — "Sent 1,000 messages lifetime."
- **Community** — "Reacted to 500 other people's messages."
- **Presence** — "Spent 10 hours in voice channels."
- **Custom** — Manually awarded by an admin for a specific contribution.

Milestones are **cosmetic trophies** by default.  They appear on a member's
profile, on the dashboard, and (optionally) as a public announcement embed.
They have no mechanical effect on the economy — however, a milestone_earned
event can trigger Rules Engine effects (e.g., "Award 100 Gold when
'Veteran' milestone is earned").

### What Changed from v3.0

| v3.0 (Achievements) | v4.0 (Milestones) |
|---------------------|-------------------|
| Requirements check `user_stats` columns | Requirements query Wallets + Event Lake |
| Hardcoded counter types | Composable requirement expressions |
| Fixed names (XP, Stars) | Works with any configured currency |
| Checked by the Reward Engine | Checked by the Rules Engine (`milestone_check` effect) |
| "Achievement" everywhere | Admin-configurable label via Taxonomy |

---

## 6.2 Milestone Anatomy

Every milestone is defined by a **Milestone Template** — a row in the
`milestone_templates` table.

### Template Fields

| Field | Type | Example | Purpose |
|-------|------|---------|---------|
| `id` | string | `"chatterbox"` | Machine-readable slug |
| `name` | string | `"Chatterbox"` | Display name |
| `description` | string | `"Send 100 messages"` | Flavor text |
| `category` | string | `"volume"` | Grouping for display |
| `icon` | string | `"💬"` | Emoji or image URL |
| `rarity` | enum | `"rare"` | Visual tier (see §6.4) |
| `requirement` | Requirement | (see §6.3) | When is this earned? |
| `reward_rule_id` | string? | `"chatterbox-reward"` | Optional Rule to fire on earn |
| `announce` | bool | `true` | Post an embed when earned? |
| `scope` | enum | `"lifetime"` or `"season"` | Reset on season roll? |
| `enabled` | bool | `true` | Toggle without deleting |
| `display_order` | int | `10` | Sort position in galleries |

---

## 6.3 Requirement System

### 6.3.1 Requirement Types

Requirements define **when** a milestone is earned.  They query the Ledger
(Wallet balances) and Event Lake (event counts) rather than hardcoded
`user_stats` columns.

| Type | Description | Example |
|------|-------------|---------|
| `wallet_threshold` | A wallet balance crosses a value | `xp >= 5000` |
| `lifetime_threshold` | Lifetime earned in a currency crosses a value | `stars.lifetime >= 1000` |
| `event_count` | Count of events in the Lake crosses a value | `message_create.count >= 100` |
| `streak` | Consecutive days with at least one qualifying event | `active_days.streak >= 7` |
| `compound` | Multiple sub-requirements (AND/OR) | `xp >= 5000 AND active_days >= 30` |
| `custom` | Cannot be auto-earned; manual award only | — |

### 6.3.2 Requirement Expressions

Requirements are stored as JSON and evaluated by the milestone checker:

**Simple wallet threshold:**
```json
{
  "type": "wallet_threshold",
  "currency": "xp",
  "operator": ">=",
  "value": 5000
}
```

**Event count:**
```json
{
  "type": "event_count",
  "event_type": "message_create",
  "operator": ">=",
  "value": 1000
}
```

**Filtered event count (zone-specific):**
```json
{
  "type": "event_count",
  "event_type": "message_create",
  "zone_filter": "programming",
  "operator": ">=",
  "value": 100
}
```

**Streak:**
```json
{
  "type": "streak",
  "event_type": "*",
  "min_consecutive_days": 7
}
```

**Compound (all sub-requirements must be met):**
```json
{
  "type": "compound",
  "operator": "AND",
  "requirements": [
    { "type": "wallet_threshold", "currency": "xp", "operator": ">=", "value": 5000 },
    { "type": "event_count", "event_type": "voice_session_end", "operator": ">=", "value": 50 }
  ]
}
```

### 6.3.3 Scoped Requirements

When `scope = "season"`, the requirement queries are filtered to the
current season's date range.  This allows milestones like "Earn 500 Stars
this season" without lifetime inflation.

When `scope = "lifetime"`, the requirement queries have no time boundary.

---

## 6.4 Rarity Tiers

Rarity is cosmetic — it affects the embed color, badge glow, and prestige
perception.  The tier names and colors are configurable via Taxonomy, but
defaults are provided:

| Tier | Default Color | Default Glow | Typical Use |
|------|--------------|-------------|-------------|
| **Common** | Gray (#95A5A6) | None | Low-threshold auto milestones |
| **Uncommon** | Green (#2ECC71) | Subtle | Medium-threshold counters |
| **Rare** | Blue (#3498DB) | Soft pulse | High-threshold counters |
| **Epic** | Purple (#9B59B6) | Strong pulse | Multi-condition or high-effort |
| **Legendary** | Gold (#F1C40F) | Animated glow | Custom, one-of-a-kind admin awards |

The dashboard already renders these with appropriate glow effects (see
Phase 1 UI work — `RarityBadge.svelte`).

---

## 6.5 Milestone Check Pipeline

Milestone evaluation is triggered by the Rules Engine's `milestone_check`
effect, which fires after events that might advance a user toward a
milestone.

```
1. Rules Engine processes an event
2. A rule's effects include `milestone_check`
3. Load all enabled milestone_templates (cached, PG NOTIFY refresh)
4. Load the user's earned milestones (user_milestones table)
5. For each template NOT already earned by this user:
   a. Evaluate the requirement against the user's wallets + event counts
   b. If requirement is met:
      - INSERT into user_milestones
      - Emit a `milestone_earned` internal event
      - If announce = true: queue announcement embed
      - If reward_rule_id is set: enqueue that rule for evaluation
6. Return list of newly earned milestones
```

### Performance Notes

- Template list is cached and refreshed via PG LISTEN/NOTIFY.
- Wallet lookups are single-row reads (indexed by `user_id + currency_id`).
- Event counts use pre-aggregated counters where possible (the Event Lake
  maintains per-user per-event-type counts as a materialized view or
  counter cache — see 03B_DATA_LAKE for details).
- Streak calculation queries the Event Lake for distinct active days.
- A typical milestone check for 50 templates completes in < 10ms.

---

## 6.6 Milestone Rewards via Rules

In v3.0, achievements had hardcoded `xp_reward` and `gold_reward` fields.
In v4.0, milestone rewards are just rules triggered by the `milestone_earned`
event:

```json
{
  "id": "chatterbox-reward",
  "trigger": { "event_type": "milestone_earned" },
  "conditions": [
    { "type": "expression", "params": { "expr": "event.metadata.milestone_id == 'chatterbox'" } }
  ],
  "effects": [
    { "type": "ledger_credit", "params": { "currency": "gold", "amount_expr": "100", "base": 100 } },
    { "type": "announce", "params": { "template": "🏆 {user} earned **{milestone.name}**! +100 🪙" } }
  ]
}
```

This is more flexible than the v3.0 approach:
- Any number of currencies can be awarded.
- Announcements are customizable per milestone.
- Rewards can be conditional (e.g., only if user is below level 10).
- A milestone can trigger role assignment, not just currency.

---

## 6.7 Seed Milestones

The Classic Gamification preset includes the following seed milestones
(equivalent to v3.0's seed achievements):

### Volume

| Name | Requirement | Rarity |
|------|-------------|--------|
| Chatterbox | 100 messages | Common |
| Thousand Words | 1,000 messages | Uncommon |
| Novelist | 10,000 messages | Rare |

### Community

| Name | Requirement | Rarity |
|------|-------------|--------|
| Cheerleader | 200 reactions given | Common |
| Superfan | 1,000 reactions given | Uncommon |
| Popular | 500 reactions received | Uncommon |
| Celebrity | 5,000 reactions received | Rare |

### Presence

| Name | Requirement | Rarity |
|------|-------------|--------|
| First Steps | xp >= 100 | Common |
| Committed | xp >= 5,000 | Uncommon |
| Veteran | xp >= 50,000 | Rare |
| Night Owl | 600 voice minutes | Uncommon |
| Insomniac | 6,000 voice minutes | Rare |

### Consistency

| Name | Requirement | Rarity |
|------|-------------|--------|
| Streak Starter | 3-day streak | Common |
| Week Warrior | 7-day streak | Uncommon |
| Iron Will | 30-day streak | Rare |
| Unstoppable | 100-day streak | Epic |

### Special

| Name | Requirement | Rarity |
|------|-------------|--------|
| Founding Member | Custom (manual) | Legendary |
| Event Champion | Custom (manual) | Epic |

---

## 6.8 Admin UI

The milestone management interface provides:

1. **Milestone Gallery** — Grid view of all templates with rarity badges,
   icons, and earn rates.
2. **Milestone Editor** — Form-based builder:
   - Name, description, icon, rarity, category
   - Requirement builder (dropdown of types, parameter fields)
   - Compound requirement builder (add sub-requirements, choose AND/OR)
   - Reward rule auto-generator (specify currencies + amounts, generates
     the corresponding rule automatically)
   - Preview: shows how the embed will look
3. **Bulk Actions** — Enable/disable, change rarity, export/import as YAML.
4. **Analytics** — Earn rate per milestone (how many users have earned it
   vs. total), time-to-earn distribution.

---

## Decisions

> **Decision D06-01:** Milestones Query Ledger + Event Lake
> - **Status:** Accepted (Supersedes v3.0 `user_stats` column checks)
> - **Context:** v3.0 checked `user_stats.messages_sent`,
>   `user_stats.total_stars`, etc.  These columns don't exist in v4.0.
> - **Choice:** Requirements query wallet balances and Event Lake
>   aggregates.  The milestone checker has no knowledge of specific
>   currency names — it evaluates expressions against data.
> - **Consequences:** Milestones work with any configured currencies.
>   No schema changes needed when adding new currencies.

> **Decision D06-02:** Milestone Rewards via Rules Engine
> - **Status:** Accepted (New in v4.0)
> - **Context:** v3.0 had `xp_reward` and `gold_reward` on the template.
> - **Choice:** Milestone earn events trigger Rules Engine rules.  A
>   convenience builder in the admin UI auto-generates the reward rule.
> - **Consequences:** Any effect can fire on milestone earn (not just
>   currency).  Role assignments, announcements, etc.

> **Decision D06-03:** Compound Requirements
> - **Status:** Accepted (New in v4.0)
> - **Context:** v3.0 achievements had single-condition requirements.
> - **Choice:** Support AND/OR compound requirements as nested JSON.
> - **Consequences:** Rich milestones like "5,000 XP AND 50 voice
>   sessions AND 7-day streak."  Adds complexity to the evaluator but
>   is bounded (no recursion beyond 2 levels).

> **Decision D06-04:** Seasonal Scope for Milestones
> - **Status:** Accepted (New in v4.0)
> - **Context:** v3.0 achievements were all lifetime.
> - **Choice:** Milestones can be scoped to `"season"`, meaning their
>   requirements are evaluated against current-season data only.
> - **Consequences:** Supports seasonal challenges.  Earned seasonal
>   milestones are preserved in history but requirements reset.
