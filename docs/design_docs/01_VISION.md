# 01 — Vision & Philosophy

> *"The backbone of an engaged society."*

---

## 1.1 What Is Synapse?

**Synapse** is a **modular community operating system** for Discord.  It is
not a leveling bot.  It is not a gamification engine.  It is a **configurable
platform** that ingests community behavior, stores it as structured data, and
reacts to it according to rules defined by the people who run the server.

At its core, Synapse does three things:

1. **Observes** — captures every meaningful interaction that Discord exposes
   to a bot (messages, reactions, voice presence, member events, thread
   activity, and more), storing raw event data in an **Event Lake**.
2. **Interprets** — runs captured events through a configurable **Rules
   Engine** that determines what, if anything, should happen in response.
3. **Acts** — executes effects defined by those rules: awarding currencies,
   granting milestones, posting announcements, updating rankings.

The critical distinction: Synapse **separates data collection from
interpretation**.  The Event Lake always collects.  What the community *does*
with that data — whether they gamify it, analyze it, or simply archive it —
is entirely up to the administrators.

A student club might configure Synapse to award "XP" for posting in
technical channels and "Gold" for attending events.  A nonprofit might
configure "Karma" for volunteering and disable the economy entirely.  A
gaming community might track voice hours and call them "Party Time."

The platform doesn't care.  It provides the primitives; the community
defines the experience.

---

## 1.2 Who Does Synapse Serve?

### Primary Users

| Persona | Role | What They Care About |
|---------|------|----------------------|
| **Community Member** | Participates in the server | Seeing their contributions recognized, tracking progress, earning milestones |
| **Community Leader** | Manages a sub-community or channel group | Customizing how engagement is tracked and rewarded for their area |
| **Server Administrator** | Oversees the entire Discord server | Platform configuration, analytics, data governance, module management |

### Secondary Users

| Persona | Role | What They Care About |
|---------|------|----------------------|
| **Organization Stakeholder** | Faculty advisor, nonprofit board, team lead | Evidence of engagement for reports, funding, or evaluation |
| **Deployers / Forks** | Other communities who self-host | Forking the repo and spinning up their own instance with custom presets |

### Deployment Archetypes

| Archetype | Example | Likely Configuration |
|-----------|---------|----------------------|
| **University Student Org** | Franklin University CS clubs | Multi-zone gamification: XP + Gold + Achievements, seasonal leaderboards |
| **Nonprofit / Volunteer Group** | Community garden collective | Single "Karma" currency, milestone tracking, no leaderboard |
| **Study / Accountability Group** | Online study circle | Voice-hour tracking, streak milestones, no economy |
| **Gaming Community** | MMO guild | Party-time tracking, raid attendance, custom titles |
| **Open Source Project** | Public Discord for a library | Contribution recognition, helper badges, no currency |
| **Corporate Team** | Internal team Discord | Activity analytics only, all gamification modules off |

---

## 1.3 Core Principles

These principles guide every design and implementation decision in Synapse.

### Principle 1: Data First, Opinions Later

> Capture everything.  Interpret selectively.

The Event Lake collects behavioral data regardless of whether any rule is
configured to act on it.  This means administrators can retroactively
create rules, change reward structures, and re-analyze history without
losing fidelity.

The system never discards raw data to save space at the cost of future
flexibility.  Aggregation and summarization are derived views built on top
of the Lake — never replacements for it.

### Principle 2: Everything Is Configurable

> If a community can imagine it, the platform should support it.

Currencies are not hardcoded.  Event types are not hardcoded.  The names
displayed in the UI are not hardcoded.  Administrators define:

- **What to track** (which Discord event categories to ingest)
- **What to call things** (taxonomy: "XP" or "Karma" or "Points")
- **What the rules are** (trigger → effect logic)
- **What modules are active** (economy, milestones, seasons, analytics)

The codebase uses **neutral internal terminology** (currencies, milestones,
regions, rankings) and maps to user-facing labels through a Taxonomy system.

### Principle 3: Composable Modules

> Turn things on.  Turn things off.  No dead weight.

Synapse ships with a set of **modules** that can be independently enabled or
disabled:

| Module | What It Does | Default |
|--------|-------------|---------|
| **Event Lake** | Ingests and stores raw Discord events | Always On |
| **Economy** | Currencies, wallets, transactions, level-up logic | On |
| **Milestones** | Achievement-style unlockables with auto-triggers | On |
| **Seasons** | Time-bounded competitive windows with stat resets | On |
| **Rankings** | Leaderboards and player standings | On |
| **Announcements** | Public embeds for milestones, level-ups, awards | On |
| **Analytics** | Dashboard charts, heatmaps, trend analysis | On |
| **Rules Engine** | Configurable trigger → effect logic | On |

Disabling a module cleanly removes its features from the bot, the API,
and the dashboard.  Data already collected is never deleted — only the
active processing and UI surface change.

### Principle 4: Transparency Over Surveillance

> Track with permission.  Display what's active.  Never hide the mechanism.

Synapse must clearly communicate to administrators (and, where relevant, to
members) exactly what data is being collected and why.  The admin dashboard
includes a **Data Sources** panel that shows:

- Which event categories are currently enabled
- Which are available but disabled
- How much data has been collected (volume, date range)
- Retention policy settings

This is not more invasive than existing popular bots (MEE6, Arcane, etc.)
— but it is more honest about what it does.

### Principle 5: Sensible Defaults, Zero-Config Start

> If you just want "a leveling bot," you should be up in 5 minutes.

The platform ships with **presets** — complete configurations that replicate
common use cases:

- **"Classic Gamification"** — XP + Gold, zone multipliers, achievements,
  seasonal leaderboards.  (The current Synapse behavior.)
- **"Analytics Only"** — Data collection and dashboard, no economy or
  milestones.
- **"Minimal Engagement"** — Single currency, simple milestones, no seasons.

When the bot first joins a server, the admin selects a preset (or starts
from scratch).  Presets are stored as exportable/importable YAML, enabling
a future **Recipe Marketplace** where communities share configurations.

### Principle 6: Quality Over Volume

> A 500-character technical write-up is worth more than 50 one-word messages.

When the economy module is active, the Rules Engine supports **quality
modifiers** — configurable bonuses based on event metadata (message length,
code blocks, attachments, reply chains).  Administrators choose which quality
signals matter for their community and how much weight they carry.

### Principle 7: Cloud-Ready From Day One

> If it can't run on a VPS with `docker compose up`, it isn't done.

Local development uses Docker Compose to simulate the full production
topology.  There is never a "works on my machine" gap.  The platform is
designed for self-hosting with minimal operational burden.

---

## 1.4 What Synapse Is NOT

- **Not a moderation bot.**  Synapse does not auto-ban, auto-mute, or enforce
  server rules.  It is purely additive — it recognizes, it never punishes.
- **Not a surveillance tool.**  We track engagement to recognize and reward
  it, not to monitor individuals.  No message content is stored in the
  Event Lake; only metadata (author, channel, timestamp, type, length).
- **Not a single-purpose bot.**  Synapse is a platform.  A leveling bot is
  one configuration of it.  An analytics dashboard is another.  A
  contribution-tracking system is a third.
- **Not opinionated about your community.**  Whether you run a student club,
  a nonprofit, a gaming guild, or a corporate team — the platform adapts
  to your structure, not the other way around.

---

## 1.5 The Name

**Synapse** — a junction between nerve cells where signals are transmitted.
In our context, the "nerve cells" are the community (Discord), external
services (GitHub, APIs), and the data layer (Event Lake).  The "signal" is
any meaningful interaction that flows between them.  The bot is the synapse
itself: the bridge that fires when activity happens.

---

## 1.6 Taxonomy: The Language Layer

A key innovation of Synapse is the **Taxonomy** system — a mapping from
neutral internal names to user-facing labels configured per deployment.

| Internal Name | Default Label | Could Also Be |
|---------------|---------------|---------------|
| `currency.primary` | "XP" | "Karma", "Impact Points", "Reputation" |
| `currency.secondary` | "Gold" | "Credits", "Tokens", "Coins" |
| `regions` | "Zones" | "Departments", "Realms", "Areas" |
| `milestones` | "Achievements" | "Badges", "Goals", "Awards" |
| `rankings` | "Leaderboard" | "Standings", "Board", "Rankings" |
| `seasons` | "Seasons" | "Cycles", "Semesters", "Sprints" |

The Taxonomy is stored in the database and applied dynamically across:
- Bot embed messages
- Slash command descriptions
- Dashboard UI labels
- API response payloads

Changing the taxonomy is instant and requires no code deployment.

---

## Decisions

> **Decision D01-01:** Platform Scope (Amended v4.0)
> - **Status:** Accepted (Supersedes original "Multi-Club" scope)
> - **Context:** The original design (v1.0–v3.0) was scoped to student club
>   gamification.  This was too narrow for the platform's potential.
> - **Choice:** Expand to a modular community operating system.  Gamification
>   is one configuration; analytics-only, engagement tracking, and
>   contribution recognition are equally valid configurations.
> - **Consequences:** Requires configurable economy, taxonomy system,
>   module toggles, and preset system.  Significantly more complex to build
>   but dramatically wider in applicability.

> **Decision D01-02:** No Punishment Mechanics
> - **Status:** Accepted (Unchanged)
> - **Context:** Some bots remove XP for rule violations.
> - **Choice:** Synapse is purely additive.  Moderation is a separate concern.
> - **Consequences:** No negative currency deltas except for spending.

> **Decision D01-03:** Public-First Dashboard
> - **Status:** Accepted (Unchanged)
> - **Context:** Early design had the dashboard as admin-only.
> - **Choice:** The dashboard has public-facing pages (rankings, activity,
>   milestones) and authenticated admin pages (configuration, data governance).
> - **Consequences:** Requires auth separation in the web layer.

> **Decision D01-04:** Public Celebration Defaults On, Opt-Out Available
> - **Status:** Accepted (Unchanged)
> - **Context:** Public announcements drive community energy.
> - **Choice:** Announcements are on by default.  Members can opt out of
>   specific announcement types.  Opt-out suppresses the public embed only;
>   the reward is still recorded.
> - **Consequences:** Respects user agency without degrading the default
>   experience.

> **Decision D01-05:** Taxonomy System for UI Labels
> - **Status:** Accepted (New in v4.0)
> - **Context:** Hardcoded terms like "XP," "Gold," "Zones," and
>   "Achievements" bake assumptions about the deployment context.
> - **Choice:** All user-facing labels are stored in a `taxonomy` table
>   and applied dynamically.  Internal code uses neutral terms.
> - **Consequences:** Requires a taxonomy editor in the admin panel and
>   dynamic label injection in bot embeds and dashboard UI.

> **Decision D01-06:** Preset System for Zero-Config Start
> - **Status:** Accepted (New in v4.0)
> - **Context:** A fully configurable system risks "configuration hell"
>   for new users who just want basic gamification.
> - **Choice:** Ship with presets (e.g., "Classic Gamification," "Analytics
>   Only") that pre-populate currencies, rules, modules, and taxonomy.
> - **Consequences:** First-run experience is simple.  Advanced users
>   customize from there.  Presets are exportable YAML for sharing.

> **Decision D01-07:** Data Transparency Policy
> - **Status:** Accepted (New in v4.0)
> - **Context:** A bot that tracks "everything" can feel invasive.
> - **Choice:** The admin dashboard includes a Data Sources panel showing
>   exactly which event categories are enabled, what data is collected,
>   and how much has been stored.  No message content is stored.
> - **Consequences:** Builds trust.  Differentiates Synapse from opaque
>   competitors.  Requires a data governance UI surface.
