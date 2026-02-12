# 03 — Dual Economy Model

> *Two currencies, two purposes.  Neither dilutes the other.*

---

## 3.1 The Problem

A single XP currency creates a fundamental tension:

- **Alice** writes a 600-character Docker tutorial in `#programming`.  She
  gets 5 thoughtful reactions.
- **Bob** posts a meme in `#memes`.  He gets 40 laughing-face reactions.

If reactions grant XP equally, Bob out-earns Alice 8:1 for objectively less
educational value.  Alice feels devalued.  The system incentivizes memes
over mentorship.

But we **don't want to punish Bob** either.  Memes build community.

---

## 3.2 The Solution: Two Economies

Synapse separates rewards into two independent tracks:

### Economy 1: XP → Levels (The Climb)

| Attribute | Detail |
|-----------|--------|
| **Currency** | XP (Experience Points) |
| **Earned By** | Messages, thread contributions, code blocks, quality content |
| **Controlled By** | Zone multipliers × Quality modifiers |
| **Visible As** | Level number, progress bar, rank on leaderboard |
| **Purpose** | Long-term progression.  "I am growing." |
| **Tangible Value** | Unlocks roles, shop items, mentor status (future) |

XP is **weighted** — a post in `#programming` with a code block earns
substantially more than a one-liner in `#memes`.  This is the "serious"
currency that reflects effort and contribution.

### Economy 2: Stars → Achievements (The Collection)

| Attribute | Detail |
|-----------|--------|
| **Currency** | Stars (Engagement Points) |
| **Earned By** | All interactions equally — messages, reactions given/received, voice time |
| **Controlled By** | Flat rate (1 star per qualifying event) with light zone multipliers |
| **Visible As** | Achievement badges, progress toward next achievement |
| **Purpose** | Short-term collection.  "I did a thing." |
| **Tangible Value** | Cosmetic prestige only.  Star stickers on your profile. |

Stars reward **participation** regardless of quality.  Posting memes, reacting
to announcements, hanging out in voice — it all counts.  But Stars don't
affect your Level or your position on the XP leaderboard.

---

## 3.3 How It Plays Out

### Scenario: Alice (Technical Contributor)

```
Alice posts a 600-char Docker tutorial in #programming (with code block):
  ├── XP: base(15) × zone(1.5) × quality(1.2 length + 1.4 code) = ~53 XP
  ├── Stars: +1 (message sent)
  └── Gets 5 reactions:
      ├── XP: +0 (reaction_received in programming zone = 0.5 × 5 = 2.5 ≈ 3)
      └── Stars: +5 (one per reaction received)

Total: ~56 XP, 6 Stars
Progress: Steady climb toward Level 5
Achievement progress: "Educator" (10 high-quality posts) → 7/10
```

### Scenario: Bob (Social Butterfly)

```
Bob posts "lol check this out" in #memes (with an image):
  ├── XP: base(15) × zone(0.5) × quality(1.0) = ~8 XP
  ├── Stars: +1 (message sent)
  └── Gets 40 reactions (25 unique reactors):
      ├── XP: capped at +5 (velocity cap: >10 reactions in <5 min)
      └── Stars: +25 (unique-reactor weighting; duplicates ignored)

Total: ~13 XP, 26 Stars
Progress: Slow XP climb, but Star counter flies
Achievement progress: "Comedian" (100 meme stars) → 78/100 ← close!
```

### Scenario: Carol (Community Participant)

```
Carol joins the #study-hall voice channel for 45 minutes:
  ├── XP: +0 (voice presence doesn't grant XP by default)
  ├── Stars: +4 (1 star per 10 minutes, capped at 6/hour)
  └── Achievement progress: "Night Owl" (60 voice minutes) → 45/60

Carol also reacts to 12 messages across various channels:
  ├── XP: 12 × base(2) × zone(varies) ≈ ~18 XP
  ├── Stars: +12
  └── Achievement progress: "Cheerleader" (200 reactions given) → 156/200
```

---

## 3.4 The XP → Level Formula

Leveling uses an exponential curve so early levels feel fast and later
levels require sustained effort:

```
required_xp(level) = level_base × level_factor ^ level
```

With defaults `level_base = 100` and `level_factor = 1.25`:

| Level | XP Required | Cumulative XP | ~Messages at 15 XP/ea |
|-------|------------|---------------|------------------------|
| 2 | 125 | 125 | ~9 |
| 5 | 305 | 1,025 | ~68 |
| 10 | 931 | 5,765 | ~384 |
| 15 | 2,842 | 19,475 | ~1,298 |
| 20 | 8,674 | 58,048 | ~3,870 |

These values are configurable per deployment.

---

## 3.5 Seasonal Stars + Lifetime History

To prevent Star inflation and keep competition fair for new members, Synapse
tracks Stars in two ways:

- **Season Stars (visible on leaderboard):** Reset every semester.
- **Lifetime Stars (profile/history):** Never reset, never deplete.

Achievements can be configured against either season counters (competitive)
or lifetime counters (legacy/prestige).  Counter resolution is explicit in the
template definition.

When a counter crosses an achievement threshold, the system auto-triggers
the award:

```
ActivityLog entry written
    │
    ▼
Reward Engine increments user_stats counters
    │
    ▼
Achievement Checker scans active AchievementTemplates
    │
    ├── requirement_type = "star_threshold"
    │   └── chosen_counter >= requirement_value?  → GRANT
    │
    ├── requirement_type = "counter_threshold"
    │   └── user_stats.messages_sent >= requirement_value?  → GRANT
    │
    └── requirement_type = "custom"
        └── Reserved for admin-granted achievements.  No auto-trigger.
```

---

## 3.7 Star Anti-Gaming Measures

Stars reward participation, not collusion.  The following safeguards prevent
Star farming without undermining the fun of casual interaction.

### 3.7.1 Unique-Reactor Weighting

When a message receives multiple reactions, Stars from `REACTION_RECEIVED`
count **unique reactors only**.  If the same user reacts with 3 different
emoji, the message author receives 1 Star, not 3.

### 3.7.2 Per-User Per-Target Caps

A single user can generate at most **3 Stars per target user per rolling
24-hour window** via `REACTION_GIVEN`.  After that limit, reactions still
appear in Discord but produce 0 Stars.

This prevents two users from endlessly reacting to each other's messages.

### 3.7.3 Diminishing Returns

Beyond 10 unique reactors on a single message, additional Stars from
`REACTION_RECEIVED` are applied at **0.5× rate** (rounded down, minimum 0).
This limits viral-meme Star explosions while still rewarding genuinely
popular content.

### 3.7.4 Admin Override

All thresholds above are stored as admin-configurable values in the
`zone_multipliers` or a future `anti_gaming_config` table so club leads can
tune them per deployment.

---

## 3.6 Gold (Spendable, With Immediate Sink)

Gold sits between XP and Stars as a **spendable** currency:

| Attribute | Detail |
|-----------|--------|
| **Earned By** | Level-ups (bonus), quest completion, manual admin awards |
| **Spent On** | Immediate minimal sink + future shop items |
| **Purpose** | Economic sink that gives the progression system "stakes" |

Gold is awarded now, so it must be spendable now.  Phase 1 includes a minimal
sink (example: `/buy-coffee`) that grants a lightweight cosmetic profile marker
or feed callout.  This teaches users that Gold has utility and prevents trash
currency behavior.

---

## Decisions

> **Decision D03-01:** Dual Economy (XP + Stars)
> - **Status:** Accepted
> - **Context:** A single currency forces a choice between rewarding quality
>   and rewarding participation.
> - **Choice:** Split into XP (weighted, progression) and Stars (flat,
>   collection).  Stars feed achievements; XP feeds levels.
> - **Consequences:** Requires separate multiplier columns in zone config,
>   separate counters in user_stats, and a clear UI distinction.

> **Decision D03-02:** Stars Are Non-Depletable
> - **Status:** Accepted
> - **Context:** If stars could be "spent," achievement progress would feel
>   punitive.
> - **Choice:** Lifetime stars are non-depletable.  Seasonal stars reset per semester.
> - **Consequences:** Permanent history is preserved while competitive boards stay fair.

> **Decision D03-03:** Reaction Velocity Cap (Amended v2.2)
> - **Status:** Accepted
> - **Context:** A viral meme can earn hundreds of reactions in minutes.
> - **Choice:** Cap XP from `REACTION_RECEIVED` events to a maximum per
>   message per time window (e.g., max 5 XP per message in a 5-minute window).
>   Stars are subject to anti-collusion caps (see §3.7) but remain the more
>   permissive currency.
> - **Consequences:** Prevents XP farming via viral content.  Star anti-gaming
>   measures prevent intentional collusion without punishing organic engagement.

> **Decision D03-04:** Voice Presence Earns Stars Only
> - **Status:** Accepted
> - **Context:** Voice channel time is easy to game (idle overnight).
> - **Choice:** Voice minutes earn Stars (capped at 6/hour) but not XP.
>   Anti-idle detection (mute + deafen = no credit) is a future enhancement.
> - **Consequences:** Encourages study-hall participation without inflating the
>   XP leaderboard.

> **Decision D03-05:** Seasons for Competitive Counters
> - **Status:** Accepted
> - **Context:** Lifetime-only Star leaderboards create long-term newcomer disadvantage.
> - **Choice:** Make seasonal counters the default for ranking surfaces.
> - **Consequences:** Leaderboards remain resettable without deleting historical activity.

> **Decision D03-06:** Gold Requires Live Sink
> - **Status:** Accepted
> - **Context:** Awarding non-spendable currency erodes trust in the economy.
> - **Choice:** Keep Gold awards, but ship at least one sink in Phase 1.
> - **Consequences:** Preserves economic credibility before full shop rollout.

> **Decision D03-07:** Star Anti-Gaming Safeguards
> - **Status:** Accepted
> - **Context:** Earlier versions described Stars as fully uncapped.  This
>   invites coordinated reaction farming between accomplices.
> - **Choice:** Apply unique-reactor weighting, per-user per-target caps,
>   and diminishing returns above a threshold (see §3.7).  Thresholds are
>   admin-configurable.
> - **Consequences:** Organic participation is unaffected; only deliberate
>   collusion is bounded.  Achieves credibility without heavy-handed rules.
