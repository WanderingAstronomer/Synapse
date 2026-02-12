# 03 — Configurable Economy

> *Define your own currencies.  The platform doesn't care what you call them.*

---

## 3.1 The Problem (Why Hardcoded Currencies Fail)

Synapse v1.0–v3.0 had three hardcoded currencies: **XP** (progression),
**Stars** (participation), and **Gold** (spendable).  This worked for a
student club gamification use case, but it fails the moment the platform
is deployed by:

- A **nonprofit** that wants "Impact Points" instead of "XP" and has no
  concept of "Gold."
- A **study group** that only wants to track "Focus Hours" — a single
  counter, not a dual economy.
- A **gaming guild** that wants "Honor," "Loot," and "Reputation" — three
  currencies, not two.
- A **corporate team** that wants analytics without any economy at all.

The solution: **stop hardcoding currencies entirely**.

---

## 3.2 The Ledger Abstraction

Instead of columns on the `users` table (`xp`, `gold`), Synapse v4.0
introduces a **Ledger System** composed of three tables:

### 3.2.1 Currencies (Definition)

A **Currency** is a named, configurable asset.  Admins define as many (or as
few) as they need.

| Property | Description | Example |
|----------|-------------|---------|
| `id` | Machine-readable slug | `"xp"`, `"gold"`, `"karma"` |
| `display_name` | Human-readable label (from Taxonomy) | "Experience Points" |
| `symbol` | Emoji or short string for compact display | "✨", "🪙", "☯" |
| `is_spendable` | Can this currency be deducted (shop, trades)? | `true` for Gold, `false` for XP |
| `is_seasonal` | Does this currency reset with seasons? | `true` for seasonal stars |
| `allow_negative` | Can balance go below zero? | Usually `false` |
| `level_curve` | If non-null, this currency drives leveling | `{"base": 100, "factor": 1.25}` |
| `display_order` | Sort position in UI | `1` (primary), `2` (secondary) |

### 3.2.2 Wallets (Balances)

A **Wallet** holds a user's balance in a specific currency.  One row per
`(user_id, currency_id)`.

| Property | Description |
|----------|-------------|
| `user_id` | The member |
| `currency_id` | Which currency |
| `balance` | Current amount |
| `lifetime_earned` | Total ever earned (never decremented) |

### 3.2.3 Transactions (Append-Only Ledger)

Every change to a wallet is recorded as a **Transaction**.  The transaction
log is append-only and provides a complete audit trail.

| Property | Description |
|----------|-------------|
| `id` | Sequential transaction ID |
| `user_id` | Who received/spent |
| `currency_id` | Which currency |
| `delta` | Amount changed (+/-) |
| `balance_after` | Wallet balance after this transaction |
| `source_type` | What triggered this: `rule`, `manual_award`, `shop_purchase`, `season_roll`, `milestone_reward` |
| `source_id` | Reference to the trigger (rule ID, event lake ID, etc.) |
| `reason` | Optional human-readable note |
| `timestamp` | When it happened |

---

## 3.3 How It Plays Out

### Scenario: Student Club (Classic Gamification)

```
Currencies defined:
  - xp       (✨) — not spendable, drives leveling (base=100, factor=1.25)
  - gold     (🪙) — spendable, not seasonal
  - stars    (⭐) — not spendable, seasonal

Alice posts a Docker tutorial in #programming:
  Rule triggers:
    → Transaction: xp +53 (quality-weighted message)
    → Transaction: stars +1 (any qualifying message)

Bob posts a meme in #memes:
  Rule triggers:
    → Transaction: xp +8 (low zone multiplier)
    → Transaction: stars +1

Alice levels up (xp crosses threshold):
  → Transaction: gold +50 (level-up bonus rule)
  → Announcement embed posted
```

### Scenario: Nonprofit (Single Currency, No Levels)

```
Currencies defined:
  - karma    (☯) — not spendable, no level curve

Volunteer posts a report in #field-updates:
  Rule triggers:
    → Transaction: karma +10

That's it.  No levels.  No gold.  No seasonal resets.
The leaderboard shows Karma rankings.
```

### Scenario: Study Group (No Economy)

```
Currencies defined: (none)
Economy module: OFF

Voice tracking: ON (Event Lake records voice sessions)
Milestones: ON
  - "10-Hour Scholar" — voice_minutes >= 600
  - "Streak Master" — 7 consecutive days with activity

No currencies, no transactions, no leaderboard.
Dashboard shows activity heatmaps and milestone gallery only.
```

---

## 3.4 Leveling

Leveling is **currency-driven, not hardcoded**.  Any currency can optionally
drive a level curve by setting its `level_curve` property.

```
required_for_next_level(current_level) = base × factor ^ current_level
```

Only one currency per deployment should typically drive levels, but the
system does not enforce this.  If multiple currencies have level curves,
each produces an independent level (e.g., "Combat Level" and "Crafting
Level" in a gaming context).

Default (Classic Gamification preset):

| Level | XP Required | Cumulative XP |
|-------|------------|---------------|
| 2 | 125 | 125 |
| 5 | 305 | 1,025 |
| 10 | 931 | 5,765 |
| 15 | 2,842 | 19,475 |
| 20 | 8,674 | 58,048 |

Level-up events can trigger additional rules (e.g., "On level-up: award
50 Gold") through the Rules Engine.  This replaces the hardcoded
`gold_per_level_up` config value.

---

## 3.5 Seasons and the Economy

When Seasons are enabled, currencies marked `is_seasonal = true` have their
wallet balances snapshotted and reset at season boundaries.

The season roll process:
1. Snapshot all seasonal wallet balances to a `season_snapshots` table.
2. Reset seasonal wallet balances to 0.
3. `lifetime_earned` is never affected.
4. Log a `SEASON_ROLL` transaction for each affected wallet.
5. Milestones scoped to `"season"` re-evaluate from zero.
6. Non-seasonal currencies (e.g., XP, Gold) are unaffected.

This replaces the v3.0 `user_stats.season_stars` column with a general
mechanism that works for any number of currencies.

---

## 3.6 Anti-Gaming

Anti-gaming measures remain essential to currency credibility.  However,
they are no longer hardcoded into the Reward Engine — they become
**configurable rule conditions** and **global safety rails**.

### Safety Rails (Always Active)

| Rail | Description |
|------|-------------|
| **Self-Interaction Filter** | Events where actor == target produce zero currency |
| **Transaction Rate Limit** | Max N transactions per user per minute (configurable, default 30) |
| **Balance Overflow Protection** | Reject transactions that would exceed `MAX_INT` |

### Configurable via Rules

| Behavior | How It's Configured |
|----------|---------------------|
| Unique-reactor weighting | Rule condition: `reaction.unique_reactors > 1` |
| Per-user per-target caps | Rule condition with sliding window: `pair_events(24h) < 3` |
| Diminishing returns | Rule effect modifier: `min(count, 10) + max(0, count - 10) * 0.5` |
| Reaction velocity cap | Rule condition: `message.reaction_count(5min) < 10` |
| Daily earning ceiling | Rule condition: `user.daily_earned(currency) < max` |
| Voice idle detection | Rule condition: `voice.is_muted AND voice.is_deafened` → skip |

This moves anti-gaming from "hardcoded Python functions" to
"admin-configurable rule predicates."  The Classic Gamification preset
ships with all of these pre-configured.

---

## 3.7 Gold Sinks and Spending

For currencies marked `is_spendable = true`, the platform supports:

- **Admin-defined shop items** (future: role purchases, cosmetic profile
  markers, custom embed colors).
- **Manual deductions** via admin commands.
- **Rule-triggered spending** (e.g., "Entering the weekly contest costs
  50 Gold").

The minimal sink (`/buy-coffee`) from v3.0 becomes a shop item seeded by
the Classic Gamification preset.

---

## Decisions

> **Decision D03-01:** Ledger System Replaces Hardcoded Columns
> - **Status:** Accepted (Supersedes original Dual Economy in v4.0)
> - **Context:** Hardcoded `xp` and `gold` columns on the `users` table
>   prevent communities from defining their own currencies.
> - **Choice:** Introduce `currencies`, `wallets`, and `transactions`
>   tables.  Remove `xp`, `gold`, and `level` from `users`.  Level is
>   derived from the currency with a `level_curve`.
> - **Consequences:** Any number of currencies with any names.  Complete
>   audit trail via append-only transactions.  Slightly more complex
>   queries for "what is this user's XP?" (wallet JOIN vs. column read).

> **Decision D03-02:** Currencies Drive Levels (Not Hardcoded)
> - **Status:** Accepted (New in v4.0)
> - **Context:** The `level_base` / `level_factor` config was tied to XP.
> - **Choice:** Attach an optional `level_curve` to any currency definition.
> - **Consequences:** Flexible leveling.  Gaming communities could have
>   multiple level tracks.  Most deployments will have one.

> **Decision D03-03:** Anti-Gaming via Rules, Not Hardcode
> - **Status:** Accepted (New in v4.0)
> - **Context:** v3.0 anti-gaming checks (unique-reactor weighting, per-user
>   caps, diminishing returns) were Python functions in `reward.py`.
> - **Choice:** Express anti-gaming as rule conditions with sensible defaults
>   in the Classic Gamification preset.  Safety rails (self-interaction
>   filter, rate limits) remain hardcoded.
> - **Consequences:** Communities can tune their own anti-gaming thresholds.
>   Wilder communities can relax them; strict communities can tighten them.

> **Decision D03-04:** Seasonal Currencies via Wallet Snapshots
> - **Status:** Accepted (Supersedes v3.0 `user_stats.season_stars`)
> - **Context:** v3.0 used a dedicated `season_stars` column.  The new
>   ledger system needs a general approach.
> - **Choice:** Any currency can be marked `is_seasonal`.  Season rolls
>   snapshot and reset seasonal wallet balances.
> - **Consequences:** Works for any number of seasonal currencies.
>   Historical seasonal data preserved in snapshots.

> **Decision D03-05:** Transactions Are Append-Only
> - **Status:** Accepted (New in v4.0)
> - **Context:** Wallet balances could be updated in-place, but that
>   loses the audit trail.
> - **Choice:** Every balance change is a `Transaction` row.  Wallet
>   `balance` is a denormalized cache of `SUM(delta)` for performance.
> - **Consequences:** Full financial audit trail.  Enables "replay" of
>   economy history.  Slightly higher write volume.
