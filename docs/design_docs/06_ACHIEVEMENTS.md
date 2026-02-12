# 06 — Achievements System

> *Star stickers for your digital binder.  Public trophies that say "I was here."*

---

## 6.1 Purpose

Achievements are the **collection economy** of Synapse.  They reward
participation patterns that don't fit neatly into the XP progression ladder:

- Consistency (logged in 7 days straight).
- Volume (sent 1,000 messages lifetime).
- Community (gave 500 reactions to others).
- Presence (spent 10 hours in voice channels).
- Custom (awarded by a club lead for a specific contribution).

Achievements are **cosmetic trophies**.  They appear on a member's `/profile`
card, on the dashboard, and (optionally) as a public announcement embed.
They have no mechanical effect on XP or Gold (though templates can specify
bonus XP/Gold as a one-time reward on earn).

---

## 6.2 Achievement Anatomy

Every achievement is defined by an **Achievement Template** — a row in the
`achievement_templates` table.  Templates are created and managed by club
leadership through the Admin Panel or slash commands.

### Template Fields

| Field | Example | Purpose |
|-------|---------|---------|
| **Name** | "Meme Lord" | Display name on profile and embeds |
| **Description** | "Earned 100 stars from the memes zone" | Flavor text |
| **Category** | "social" | Grouping for the profile display |
| **Requirement Type** | "counter_threshold" | How the system checks eligibility |
| **Requirement Field** | "messages_sent" | Which `user_stats` column to check |
| **Requirement Value** | 1000 | Threshold to trigger |
| **XP Reward** | 200 | One-time XP bonus on earn |
| **Gold Reward** | 100 | One-time Gold bonus on earn |
| **Badge Image URL** | `https://i.imgur.com/abc.png` | Custom graphic |
| **Rarity** | "rare" | Color-coding and prestige tier |
| **Announce Channel** | `#achievements` channel ID | Where to post the embed |

---

## 6.3 Requirement Types

### `counter_threshold` — Automatic

Triggers when a `user_stats` column crosses the template's
`requirement_value`.  Checked after every Reward Engine calculation.

| Example Name | Field | Value | Description |
|-------------|-------|-------|-------------|
| "Chatterbox" | `messages_sent` | 100 | Send 100 messages |
| "Thousand Words" | `messages_sent` | 1000 | Send 1,000 messages |
| "Cheerleader" | `reactions_given` | 200 | React to 200 messages |
| "Popular" | `reactions_received` | 500 | Receive 500 reactions |
| "Night Owl" | `voice_minutes` | 600 | 10 hours in voice |

### `star_threshold` — Automatic

Triggers when `user_stats.total_stars` crosses the template's
`requirement_value`.

| Example Name | Value | Description |
|-------------|-------|-------------|
| "Rising Star" | 100 | Earn 100 total stars |
| "Constellation" | 1000 | Earn 1,000 total stars |
| "Galaxy" | 10000 | Earn 10,000 total stars |

### `xp_milestone` — Automatic

Triggers when `users.xp` crosses the template's `requirement_value`.

| Example Name | Value | Description |
|-------------|-------|-------------|
| "First Steps" | 100 | Earn 100 XP |
| "Committed" | 5000 | Earn 5,000 XP |
| "Veteran" | 50000 | Earn 50,000 XP |

### `custom` — Manual Only

Does NOT auto-trigger.  Can only be granted by a club lead via the
`/grant-achievement` command or the Admin Panel.

| Example Name | Description |
|-------------|-------------|
| "CTF Champion" | Won the Spring 2026 CTF |
| "Hackathon MVP" | Best project at club hackathon |
| "Founding Member" | Charter member of the organization |
| "Guest Speaker" | Gave a presentation at a club meeting |

---

## 6.4 Rarity Tiers

Rarity is cosmetic — it affects the embed color and the prestige perception.

| Tier | Color | Typical Use |
|------|-------|-------------|
| **Common** | Gray (#95A5A6) | Low-threshold auto achievements |
| **Uncommon** | Green (#2ECC71) | Medium-threshold counters |
| **Rare** | Blue (#3498DB) | High-threshold counters |
| **Epic** | Purple (#9B59B6) | Multi-condition or high-effort |
| **Legendary** | Gold (#F1C40F) | Custom, one-of-a-kind admin awards |

---

## 6.5 Achievement Check Pipeline

After the Reward Engine calculates XP and Stars, it runs this check:

```
1. Load all active achievement_templates (cached, invalidated via PG LISTEN/NOTIFY).
2. Load the user's current user_achievements (what they already have).
3. For each template NOT already earned:
   a. If requirement_type == "counter_threshold":
      - Read user_stats[requirement_field]
      - If value >= requirement_value → EARN
   b. If requirement_type == "star_threshold":
      - Read user_stats.total_stars
      - If value >= requirement_value → EARN
   c. If requirement_type == "xp_milestone":
      - Read users.xp (after this event's delta)
      - If value >= requirement_value → EARN
   d. If requirement_type == "custom":
      - SKIP (manual only)
4. For each newly earned achievement:
   a. INSERT into user_achievements
   b. Apply one-time XP/Gold reward
   c. Log to activity_log
   d. If announce_channel_id is set:
      i.  Check user_preferences for the target user.
          - If announce_achievements = FALSE → skip public embed.
      ii. Check channel throttle: max 3 announcement embeds per channel
          per 60-second window.  If exceeded, queue for next window.
      iii. Post announcement embed.
5. Return list of earned achievement IDs.
```

---

## 6.6 Custom Award Commands

### `/award @user <xp> <gold> [reason]`

**Who can use it:** Club leads (configurable Discord role check).

**What it does:**
1. Adds XP and Gold to the user's profile.
2. Logs a `MANUAL_AWARD` entry in `activity_log` with the reason.
3. Posts a public embed:

```
┌─────────────────────────────────────┐
│  🏆 Manual Award                    │
│                                     │
│  @StudentName earned:               │
│    +500 XP  |  +200 🪙 Gold         │
│                                     │
│  Reason: "Led the Docker workshop"  │
│  Awarded by: @ClubPresident         │
└─────────────────────────────────────┘
```

### `/create-achievement`

**Who can use it:** Club leads.

**What it does:** Opens an interactive form (Discord Modal) to define a new
`AchievementTemplate`.  Fields: name, description, category, requirement
type/field/value, XP reward, Gold reward, image URL, rarity, announce channel.

Alternatively, achievements can be created through the Admin Panel web UI.

### `/grant-achievement @user <achievement_name>`

**Who can use it:** Club leads.

**What it does:**
1. Looks up the achievement template by name.
2. Checks the user hasn't already earned it.
3. Awards XP/Gold, logs to activity_log.
4. Posts the announcement embed with the custom badge image.

---

## 6.7 The `/profile` Achievement Display

When a user runs `/profile`, their earned achievements appear grouped by
rarity:

```
┌─────────────────────────────────────┐
│  🧠 Alice's Synapse Profile         │
│                                     │
│  Level 8  |  XP: 2,450 / 3,052     │
│  Gold: 🪙 350  |  Rank: #3 of 47   │
│  GitHub: alice-dev                   │
│                                     │
│  ── Achievements (7) ──             │
│  🟡 Founding Member                 │
│  🟣 CTF Champion                    │
│  🔵 Chatterbox  |  🔵 Cheerleader   │
│  🟢 Rising Star  |  🟢 First Steps  │
│  ⚪ Night Owl                        │
└─────────────────────────────────────┘
```

---

## 6.8 Seed Achievements (Default Set)

These ship with every Synapse deployment as a starting point.  Club leads
can modify or deactivate them.

| Name | Type | Field | Value | Rarity | XP |
|------|------|-------|-------|--------|-----|
| First Steps | xp_milestone | — | 100 | Common | 0 |
| Rising Star | star_threshold | — | 100 | Common | 25 |
| Chatterbox | counter_threshold | messages_sent | 100 | Uncommon | 50 |
| Thousand Words | counter_threshold | messages_sent | 1000 | Rare | 200 |
| Cheerleader | counter_threshold | reactions_given | 200 | Uncommon | 50 |
| Popular | counter_threshold | reactions_received | 500 | Rare | 100 |
| Night Owl | counter_threshold | voice_minutes | 600 | Uncommon | 75 |
| Committed | xp_milestone | — | 5000 | Rare | 0 |
| Constellation | star_threshold | — | 1000 | Rare | 100 |
| Veteran | xp_milestone | — | 50000 | Epic | 500 |
| Galaxy | star_threshold | — | 10000 | Epic | 250 |

---

## Decisions

> **Decision D06-01:** Achievements Are Permanent
> - **Status:** Accepted
> - **Context:** Some systems allow revoking achievements.
> - **Choice:** Once earned, an achievement cannot be removed (except by direct
>   DB manipulation by a system admin).
> - **Consequences:** Simplifies the system.  No "un-earn" logic.

> **Decision D06-02:** Custom Achievements Are Manual-Only
> - **Status:** Accepted
> - **Context:** Custom achievements represent real-world events (CTFs,
>   hackathons, presentations) that can't be detected programmatically.
> - **Choice:** `requirement_type = "custom"` achievements must be granted
>   via `/grant-achievement` or the Admin Panel.
> - **Consequences:** Club leads must be active participants in the reward
>   system.  This is by design — it keeps the human element.

> **Decision D06-03:** One-Time Bonus, Not Recurring
> - **Status:** Accepted
> - **Context:** Achievement XP/Gold rewards could be recurring (every time
>   you re-trigger the threshold).
> - **Choice:** Rewards fire once, when the achievement is first earned.
> - **Consequences:** Prevents infinite XP farming from counter-based
>   achievements.

> **Decision D06-04:** Announcements Respect User Opt-Out
> - **Status:** Accepted
> - **Context:** Some users prefer not to be publicly called out.
> - **Choice:** Before posting a public achievement embed, check
>   `user_preferences.announce_achievements`.  If FALSE, skip the public
>   announcement (the achievement is still earned and visible on `/profile`).
> - **Consequences:** Respects user agency while keeping public celebration
>   as the default experience.

> **Decision D06-05:** Channel Announcement Throttle
> - **Status:** Accepted
> - **Context:** A batch of users crossing a threshold simultaneously could
>   flood an announcement channel with dozens of embeds.
> - **Choice:** Rate-limit announcement embeds to max 3 per channel per
>   60-second window.  Excess embeds are queued and posted in the next window.
> - **Consequences:** Prevents channel spam during mass events (e.g., season
>   rollover triggering many achievements).  Users still receive their
>   achievement; only the public embed is delayed.
