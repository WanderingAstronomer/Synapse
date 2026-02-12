# 01 — Vision & Philosophy

> *"The system that makes every student club feel alive."*

---

## 1.1 What Is Synapse?

**Synapse** is a **multi-club engagement framework** for student organizations.  It
is not a "coding bot" or a "Discord leveling bot."  It is an **operating system
for student communities** that quantifies, encourages, and publicly celebrates
participation across every type of club — programming, cybersecurity, web
development, databases, analytics, art, and anything else a school runs.

Synapse acts as a **Neural Bridge**: it connects the social layer (Discord) to
external contribution platforms (GitHub, and eventually others) through a
gamified reward system that club leadership can customize without writing code.

---

## 1.2 Who Does Synapse Serve?

### Primary Users

| Persona | Role | What They Care About |
|---------|------|----------------------|
| **Student Member** | Participates in one or more clubs | Earning recognition, seeing progress, collecting achievements |
| **Club Lead / Officer** | Runs a specific club (e.g., Cyber) | Customizing rewards, recognizing standout members, viewing engagement metrics |
| **Organization Admin** | Oversees the entire student org / server | Cross-club analytics, server health, deployment stability |

### Secondary Users

| Persona | Role | What They Care About |
|---------|------|----------------------|
| **Faculty Advisor** | Supervises the org | Evidence of student engagement for funding/reports |
| **Future Forks** | Another school's student org | Forking the repo and spinning up their own instance |

---

## 1.3 Core Principles

These principles guide every design and implementation decision in Synapse.

### Principle 1: Quality Over Volume

> A 500-character technical write-up is worth more than 50 one-word messages.

The system must never reward spam over substance.  High-volume, low-effort
interactions (memes, emoji reactions) are valued — but through a **separate
economy** (Stars → Achievements) that does not dilute the progression ladder
(XP → Levels).

### Principle 2: Club Autonomy

> Every club is different.  The framework must bend to fit, not the other way around.

A cybersecurity club values CTF participation.  A programming club values
pull requests.  An analytics club values data visualizations shared in
Discord.  Synapse achieves this through **Zones** (channel groupings with
custom multipliers) and **Achievement Templates** (admin-defined rewards)
that are configured through a web UI — never by editing source code.

### Principle 3: Public Celebration (with Opt-Out)

> Recognition is the strongest motivator for students.

Every meaningful milestone — level-up, achievement earned, manual award from
a club lead — is announced publicly with a rich embed **by default**.  The
dashboard is not hidden behind an admin login; it is a **Club Pulse** page
that any member can view to see the community's health.

**Opt-out:** Users who prefer privacy can disable specific announcement types
via a `/preferences` slash command (level-ups, achievements, manual awards).
Opt-out suppresses the public embed only; the reward is still earned and
visible on the user's `/profile`.  See D01-04.

### Principle 4: Layers of Abstraction

> Build the octopus's body; leave room for the arms to grow.

The architecture must accommodate new clubs, new channels, new integrations,
and new reward types without requiring restructuring.  We achieve this through:
- **Database-driven configuration** (no hardcoded YAML in production).
- **An event-driven pipeline** (every Discord interaction becomes a typed
  `SynapseEvent` before the Reward Engine touches it).
- **A plugin-ready Cog system** (new integrations = new Cogs, zero changes
  to the core engine).

### Principle 5: Cloud-Ready from Day One

> If it can't run on Azure with a single `docker compose up`, it isn't done.

Local development uses Docker Compose to simulate the full production
topology.  There is never a "works on my machine" gap.

---

## 1.4 What Synapse Is NOT

- **Not a moderation bot.**  Synapse does not auto-ban, auto-mute, or enforce
  server rules.  It is purely additive — it rewards, it never punishes.
- **Not a GitHub-only tool.**  GitHub integration is one arm of the octopus.
  The core is Discord engagement, and external services are opt-in plugins.
- **Not a social media analytics platform.**  We track engagement to reward
  it, not to surveil it.  No message content is stored; only metadata
  (author, channel, timestamp, length, type).

---

## 1.5 The Name

**Synapse** — a junction between two nerve cells where signals are transmitted.
In our context, the "nerve cells" are Discord (social) and GitHub (technical),
and the "signal" is XP flowing between them.  The bot is the synapse itself:
the bridge that fires when activity happens.

---

## Decisions

> **Decision D01-01:** Multi-Club Scope
> - **Status:** Accepted
> - **Context:** The original design (v1.0) was scoped to "incentivize students
>   to learn software development."  This was too narrow for a server hosting
>   5+ clubs across different disciplines.
> - **Choice:** Expand scope to a multi-club engagement framework.  GitHub
>   integration remains a first-class feature for programming clubs but is not
>   the sole focus.
> - **Consequences:** Requires a Zone system, per-club multipliers, and
>   achievement templates that aren't tied to code contributions.

> **Decision D01-02:** No Punishment Mechanics
> - **Status:** Accepted
> - **Context:** Some bots remove XP for rule violations.
> - **Choice:** Synapse is purely additive.  Moderation is a separate concern
>   handled by dedicated moderation bots (e.g., Carl-bot, Dyno).
> - **Consequences:** Simplifies the reward engine.  No negative XP deltas
>   except for future "shop purchases."

> **Decision D01-03:** Public-First Dashboard
> - **Status:** Accepted
> - **Context:** Early design had the dashboard as an admin-only tool.
> - **Choice:** The dashboard is a public Club Pulse page.  A separate
>   authenticated section exists for admin actions (manual awards, zone config).
> - **Consequences:** Requires auth separation in the web layer.  Public pages
>   = read-only.  Admin pages = Discord OAuth or role-based access.

> **Decision D01-04:** Public Celebration Defaults On, Opt-Out Available
> - **Status:** Accepted
> - **Context:** Some students may not want public announcements of their
>   milestones (social anxiety, modesty, or simply preference).
> - **Choice:** Keep public celebration as the default (it drives community
>   energy), but provide `/preferences` to opt out of specific embed types.
>   Opt-out suppresses the public embed only; the reward is still earned.
> - **Consequences:** Respects user agency without degrading the default
>   experience for the majority who enjoy recognition.
