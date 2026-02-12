# 07 — Admin Panel & Web UI

> *Community operators range from students to professionals.  If it isn't point-and-click, it won't get used.*

---

## 7.1 Design Philosophy

The Admin Panel serves two audiences with two access levels:

| Audience | Access | What They See |
|----------|--------|---------------|
| **Any member** | Public (no login) | Community Dashboard: leaderboard, activity charts, quest board, achievement gallery |
| **Server administrators** | Authenticated (Discord OAuth or role-based) | Everything above PLUS zone management, achievement builder, manual awards, settings |

**Key constraint:** Community operators have varying technical skill.
The UI must be **no harder than using a Google Form**.  No terminal, no YAML,
no SQL.

---

## 7.2 Technology Approach

### Current: SvelteKit + FastAPI (v3.0)

The web UI is a SvelteKit 2 application (Svelte 5, Tailwind CSS 3.4, Chart.js 4)
that communicates with a FastAPI backend via REST endpoints.

- **Frontend (`dashboard/`):** SvelteKit with adapter-node, served on port 3000
  (production) or port 5173 (Vite dev server).
- **Backend (`synapse/api/`):** FastAPI + uvicorn on port 8000, providing typed
  REST endpoints under `/api/*`.
- **Auth:** Discord OAuth2 → FastAPI issues JWT (HS256 via python-jose) →
  SvelteKit stores token in localStorage → sends via `Authorization: Bearer` header.
- **Admin guard:** SvelteKit admin layout checks JWT validity client-side;
  FastAPI verifies JWT and Discord admin role on every protected endpoint.

This replaces the original Streamlit-based approach (see superseded decisions
D07-02, D07-04 below).

---

## 7.3 Route Map

```
/                              → Overview (public hero, metrics, charts)
/leaderboard                   → Leaderboard (XP and Stars tabs)
/activity                      → Activity charts (Chart.js, last 30 days)
/achievements                  → Achievement gallery with rarity badges

/auth/callback                 → Discord OAuth callback (exchanges code → JWT)

/admin                         → Admin layout (JWT guard)
/admin/zones                   → Zone CRUD (name, channels, multipliers)
/admin/achievements            → Achievement template CRUD
/admin/awards                  → Manual XP / Gold / Achievement grants
/admin/settings                → Global config editor (key-value)
/admin/audit                   → Audit log viewer (before/after JSON diffs)
```

All `/admin/*` routes are protected by:
1. Client-side auth guard in `admin/+layout.svelte` (redirects to login).
2. Server-side JWT verification on every FastAPI admin endpoint.

---

## 7.4 Admin: Zone Management

### List View (`/admin/zones`)

```
┌──────────────────────────────────────────────────────────────┐
│  Zone Management                                  [+ New Zone]│
├──────────────────────────────────────────────────────────────┤
│  Name          │ Channels │ Active │ Actions                  │
│────────────────┼──────────┼────────┼──────────────────────────│
│  programming   │ 4        │ ✅     │ [Edit] [Deactivate]      │
│  cybersecurity │ 3        │ ✅     │ [Edit] [Deactivate]      │
│  memes         │ 1        │ ✅     │ [Edit] [Deactivate]      │
│  announcements │ 2        │ ✅     │ [Edit] [Deactivate]      │
│  general       │ 1        │ ✅     │ [Edit] [Deactivate]      │
└──────────────────────────────────────────────────────────────┘
```

### Create/Edit Form (`/admin/zones/new`)

```
┌──────────────────────────────────────────────────────────┐
│  Create Zone                                              │
│                                                           │
│  Name:        [________________________]                  │
│  Description: [________________________]                  │
│                                                           │
│  Channels:    [Multi-select dropdown of Discord channels] │
│               ☑ #python-help                              │
│               ☑ #code-review                              │
│               ☐ #off-topic                                │
│                                                           │
│  ── XP Multipliers ──                                     │
│  MESSAGE:            [1.5 ]                               │
│  THREAD_CREATE:      [2.0 ]                               │
│  REACTION_RECEIVED:  [0.5 ]                               │
│  REACTION_GIVEN:     [0.3 ]                               │
│  VOICE_TICK:         [0.0 ]                               │
│                                                           │
│  ── Star Multipliers ──                                   │
│  MESSAGE:            [1.0 ]                               │
│  THREAD_CREATE:      [1.5 ]                               │
│  REACTION_RECEIVED:  [1.0 ]                               │
│  REACTION_GIVEN:     [1.0 ]                               │
│  VOICE_TICK:         [1.0 ]                               │
│                                                           │
│  [Save Zone]  [Cancel]                                    │
└──────────────────────────────────────────────────────────┘
```

The channel list is populated from zone configuration data returned by the
FastAPI backend.

---

## 7.5 Admin: Achievement Builder

### Gallery View (`/admin/achievements`)

Achievement templates displayed as cards, filterable by category and rarity:

```
┌──────────────────────────────────────────────────────────────────────┐
│  Achievement Builder                        [+ New Achievement]      │
│                                                                      │
│  Filter: [All Categories ▼]  [All Rarities ▼]  [🔍 Search...]       │
│                                                                      │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐         │
│  │ 🟢 Chatterbox  │  │ 🔵 Popular     │  │ 🟡 CTF Champion│         │
│  │ 100 messages   │  │ 500 reactions  │  │ Custom award   │         │
│  │ +50 XP         │  │ +100 XP        │  │ +1000 XP       │         │
│  │ [Edit] [Deact] │  │ [Edit] [Deact] │  │ [Edit] [Deact] │         │
│  └────────────────┘  └────────────────┘  └────────────────┘         │
└──────────────────────────────────────────────────────────────────────┘
```

### Create Form (`/admin/achievements/new`)

```
┌──────────────────────────────────────────────────────────┐
│  Create Achievement                                       │
│                                                           │
│  Name:         [________________________]                 │
│  Description:  [________________________]                 │
│  Category:     [Social ▼]                                 │
│  Rarity:       [◻ Common  ◻ Uncommon  ● Rare  ◻ Epic]    │
│                                                           │
│  ── Trigger ──                                            │
│  Type:   [Counter Threshold ▼]                            │
│  Field:  [messages_sent ▼]                                │
│  Value:  [1000     ]                                      │
│                                                           │
│  ── Rewards ──                                            │
│  XP:    [200  ]                                           │
│  Gold:  [100  ]                                           │
│                                                           │
│  ── Presentation ──                                       │
│  Badge Image URL:    [________________________]           │
│  Announce Channel:   [#achievements ▼]                    │
│                                                           │
│  [Preview Embed]  [Create]  [Cancel]                      │
└──────────────────────────────────────────────────────────┘
```

---

## 7.6 Admin: Manual Awards

```
┌──────────────────────────────────────────────────────────┐
│  Award XP / Gold / Achievement                            │
│                                                           │
│  Recipient:   [@  Search Discord members...  ]            │
│                                                           │
│  ── Quick Award ──                                        │
│  XP:     [500  ]                                          │
│  Gold:   [200  ]                                          │
│  Reason: [Led the Docker workshop________________]        │
│  [Award & Announce]                                       │
│                                                           │
│  ── OR: Grant Achievement ──                              │
│  Achievement: [CTF Champion ▼]                            │
│  [Grant Achievement]                                      │
└──────────────────────────────────────────────────────────┘
```

---

## 7.7 Public: Community Dashboard

The public-facing pages form the "health monitor" for the community.  Any member
can visit the URL (no login required).

### Leaderboard (`/pulse/leaderboard`)

- Sortable table: Rank, Name, Level, XP, Stars, Achievement Count.
- Search by name.
- Click a row to expand and see the member's achievement badges.

### Activity (`/pulse/activity`)

- **Messages per day** (bar chart, last 30 days).
- **XP awarded per day** (line chart, last 30 days).
- **Top channels by volume** (horizontal bar).
- **Active hours heatmap** (hour × day-of-week).

### Achievement Gallery (`/pulse/achievements`)

- Grid of all available achievement templates with rarity colors.
- Shows how many members have earned each one.
- "Micro leaderboard" — who earned it first.

---

## 7.8 Authentication & Authorization Strategy

### Discord OAuth2 → JWT Flow

1. **Login redirect:** SvelteKit sends user to Discord OAuth2 authorize URL
   (via FastAPI `/api/auth/login`).
2. **Callback:** Discord redirects to `/auth/callback` on the SvelteKit app.
   SvelteKit forwards the authorization code to FastAPI `/api/auth/callback`.
3. **Token exchange:** FastAPI exchanges the code with Discord for an access
   token, fetches the user's profile and guild roles.
4. **Role check:** FastAPI verifies the user holds the configured
   `ADMIN_ROLE_ID` in the target guild.  Unauthorized users are rejected.
5. **JWT issuance:** FastAPI issues a JWT (HS256, signed with `JWT_SECRET`)
   containing the user's Discord ID, username, avatar hash, and admin status.
6. **Client storage:** SvelteKit stores the JWT in localStorage and attaches
   it as `Authorization: Bearer <token>` on all subsequent API requests.
7. **Per-request verification:** Every admin FastAPI endpoint calls
   `get_current_admin()` which decodes and validates the JWT, checks
   expiry, and confirms admin privileges.

### Rate Limiting

Admin write endpoints are soft-rate-limited (30 mutations/min per actor)
to prevent accidental bulk damage.

### Audit Trail

Every admin config mutation (zone CRUD, multiplier changes, manual awards,
season rolls, settings changes) inserts an `admin_log` row with before/after
JSONB snapshots, actor Discord ID, and request IP.  See D04-06.

---

## 7.9 Service Layer Architecture

Admin operations and reward logic are centralized in shared Python modules.
The FastAPI routes call the same service functions used by bot slash commands:

```
Discord Slash Command → Shared Service Module → Database
FastAPI Admin Route   → Shared Service Module → Database
SvelteKit Dashboard   → FastAPI REST API      → Shared Service Module → Database
```

This keeps business rules consistent while ensuring the dashboard never
touches the database directly.

Every service-layer function that mutates admin-controlled tables:
1. Opens a transaction.
2. Reads the current row state ("before" snapshot).
3. Applies the mutation.
4. Inserts an `admin_log` row with before/after JSONB.
5. Issues `NOTIFY config_changed, '<table_name>'` for cache invalidation.
6. Commits.

---

## Decisions

> **Decision D07-01:** HTMX Over React
> - **Status:** Superseded
> - **Context:** Separate custom web stack was considered too costly.
> - **Choice:** Replaced by D07-04, then D07-06.
> - **Consequences:** See D07-06.

> **Decision D07-02:** Streamlit Retained for Visualization
> - **Status:** Superseded by D07-06
> - **Context:** Streamlit was initially chosen for rapid prototyping.
>   After a comprehensive evaluation, Streamlit's limitations (no proper
>   routing, ghost navigation, widget styling fights, no avatars, no JWT,
>   visible Deploy button) made it unsuitable for a production dashboard.
> - **Choice:** Replaced by SvelteKit + FastAPI (D07-06).
> - **Consequences:** See D07-06.

> **Decision D07-03:** API-First Admin
> - **Status:** Reinstated (v3.0)
> - **Context:** Originally superseded by shared module-first pattern.
>   Reinstated when SvelteKit replaced Streamlit, requiring a proper API.
> - **Choice:** FastAPI serves all admin endpoints.  The shared service
>   module is invoked by FastAPI route handlers.
> - **Consequences:** Clean separation.  API can be versioned and tested.

> **Decision D07-04:** Streamlit-Native Admin Surface
> - **Status:** Superseded by D07-06
> - **Context:** Was the fastest path to shipping admin CRUD.
> - **Choice:** Replaced by SvelteKit + FastAPI when Streamlit's
>   limitations became blockers for a production-quality experience.
> - **Consequences:** See D07-06.

> **Decision D07-05:** Every Admin Write Is Audit-Logged
> - **Status:** Accepted
> - **Context:** Admin mutations need an audit trail regardless of which
>   frontend initiates them.
> - **Choice:** The shared service layer inserts `admin_log` rows with
>   before/after JSONB snapshots, actor Discord ID, and client IP for
>   every config mutation.
> - **Consequences:** Full accountability.  Supports future "undo" or
>   rollback features without additional infrastructure.

> **Decision D07-06:** SvelteKit + FastAPI Dashboard (v3.0)
> - **Status:** Accepted
> - **Context:** After a systematic evaluation of Streamlit's production
>   limitations (no file-based routing, no proper auth primitives, no
>   avatar support, persistent ghost nav items, visible Deploy button,
>   widget styling fights), the decision was made to replace it entirely.
> - **Choice:** SvelteKit 2 + Svelte 5 + Tailwind CSS 3.4 for the frontend,
>   FastAPI + uvicorn for the backend API.  Auth via Discord OAuth → JWT.
> - **Consequences:** Full control over routing, styling, and UX.  Type-safe
>   API layer with auto-generated OpenAPI docs.  Separate Node.js build
>   step and Docker image.  More initial setup but dramatically better
>   long-term maintainability and user experience.
