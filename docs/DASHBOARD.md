# Dashboard

SvelteKit 2 application with Svelte 5, TypeScript, Tailwind CSS, and Chart.js. Runs as a client-side SPA (SSR disabled) on port 3000.

## Routes

### Public Pages

| Route | File | Description |
|-------|------|-------------|
| `/` | `routes/+page.svelte` | Overview — hero metrics, activity ticker, champion spotlight, recent achievements |
| `/leaderboard` | `routes/leaderboard/+page.svelte` | Paginated leaderboard (XP, Gold, or Level) |
| `/activity` | `routes/activity/+page.svelte` | Activity feed with daily Chart.js charts |
| `/achievements` | `routes/achievements/+page.svelte` | Achievement gallery with earn percentages and rarity tiers |

### Auth

| Route | File | Description |
|-------|------|-------------|
| `/auth/callback` | `routes/auth/callback/+page.svelte` | Receives JWT from API redirect, stores in localStorage |

### Admin Pages

All admin pages are nested under `routes/admin/+layout.svelte`, which provides:
- **Auth guard:** Blocks non-admins with a "🔒 Admin Access Required" screen
- **Setup gate:** Auto-redirects to `/admin/setup` if the guild hasn't been bootstrapped

| Route | File | Description |
|-------|------|-------------|
| `/admin/setup` | `routes/admin/setup/+page.svelte` | First-run bootstrap wizard |
| `/admin/zones` | `routes/admin/zones/+page.svelte` | Zone management — channels, multipliers |
| `/admin/achievements` | `routes/admin/achievements/+page.svelte` | Achievement template builder |
| `/admin/awards` | `routes/admin/awards/+page.svelte` | Manual XP/Gold/Achievement awards |
| `/admin/settings` | `routes/admin/settings/+page.svelte` | Dashboard and economy settings editor |
| `/admin/audit` | `routes/admin/audit/+page.svelte` | Admin audit log viewer |
| `/admin/logs` | `routes/admin/logs/+page.svelte` | Live log viewer with level control |
| `/admin/data-sources` | `routes/admin/data-sources/+page.svelte` | Event Lake data source toggles |

### API Proxy

`routes/api/[...path]/+server.ts` — Catch-all reverse proxy. Forwards all `/api/*` requests to the FastAPI backend (`API_BASE_URL` env var, default `http://localhost:8000/api`).

- Strips `host` header
- Preserves auth headers
- Passes query strings
- Handles redirect responses manually
- All HTTP methods (GET/POST/PUT/PATCH/DELETE/OPTIONS)

This avoids CORS issues in production — the frontend only talks to its own origin.

## Layout

Root layout (`routes/+layout.svelte`):
- Imports global CSS
- Initializes `auth` and `currencyLabels` stores on mount
- Version mismatch handling: uses SvelteKit's `$updated` store with `beforeNavigate` — forces full page reload on stale JS chunks
- Fixed sidebar + scrollable main content area

SSR and prerendering are disabled in `routes/+layout.ts`.

## Components

10 reusable components in `lib/components/`:

| Component | Description |
|-----------|-------------|
| `Avatar.svelte` | Lazy-loaded Discord avatar with configurable size, optional brand ring, fallback to default avatar |
| `ConfirmModal.svelte` | Generic confirmation dialog with backdrop blur, danger variant, customizable labels |
| `EmptyState.svelte` | Placeholder for empty data — `default` (centered icon + text) and `hero` (gradient card with blur) variants |
| `FlashMessage.svelte` | Fixed-position toast renderer with fly-in transitions, subscribes to flash store |
| `HeroHeader.svelte` | Full-width gradient hero banner with animated glows, grid overlay, title/subtitle, inline metric cards |
| `MetricCard.svelte` | Single-stat card with large number, optional trend arrow, themed icon ring (brand/gold/green/blue/pink) |
| `ProgressBar.svelte` | Animated progress bar (0–1) with configurable color, optional label/percentage, glow at >50% |
| `RarityBadge.svelte` | Inline pill for achievement rarity (Common → Legendary) with per-tier colors, optional glow pulse on legendary |
| `Sidebar.svelte` | Fixed sidebar (72-wide): brand header, public nav, conditional admin nav (8 pages), API + Bot health indicators (30s poll), auth section |
| `SynapseLoader.svelte` | Loading spinner component |

## Stores

4 stores in `lib/stores/`:

### auth.ts

Writable store for auth state (`AuthUser | null`).

- `init()` — reads JWT from localStorage, decodes payload
- `login(token)` — stores JWT, decodes user
- `logout()` — clears localStorage and store
- Derived `isAdmin` store

### currency.ts

Configurable currency display names.

- `init()` / `refresh()` — pulls labels from `/settings/public`
- Derived `primaryCurrency` and `secondaryCurrency` stores
- Defaults: "XP" and "Gold"

### flash.ts

Toast notification system.

- `success(msg)`, `error(msg)` (6s), `info(msg)`, `warning(msg)` (5s)
- `dismiss(id)`
- Auto-removes messages after timeout

### names.ts

Client-side batching snowflake ID → name resolver.

- `userNames` / `channelNames` writable stores (ID → name maps)
- `requestResolve(userIds, channelIds)` — queues IDs, flushes in 50ms batches via `api.admin.resolveNames`
- `resolveUser(id)` / `resolveChannel(id)` — display helpers

## API Client

`lib/api.ts` — Typed fetch-based client (~530 lines, ~30 endpoints).

Exports an `api` object with namespaced methods:

- `api.getMetrics()`, `api.getLeaderboard()`, `api.getActivity()`, `api.getAchievements()`, `api.getRecentAchievements()`, `api.getPublicSettings()`
- `api.auth.me()`, `api.auth.getLoginUrl()`
- `api.admin.getZones()`, `api.admin.createZone()`, `api.admin.updateZone()`
- `api.admin.getAchievements()`, `api.admin.createAchievement()`, `api.admin.updateAchievement()`
- `api.admin.awardXpGold()`, `api.admin.grantAchievement()`
- `api.admin.searchUsers()`, `api.admin.resolveNames()`
- `api.admin.getSettings()`, `api.admin.updateSettings()`
- `api.admin.getAuditLog()`
- `api.admin.getSetupStatus()`, `api.admin.triggerBootstrap()`
- `api.admin.getLogs()`, `api.admin.setLogLevel()`
- `api.admin.getEventLakeEvents()`, `api.admin.getDataSources()`, `api.admin.toggleDataSources()`
- `api.admin.getEventLakeHealth()`, `api.admin.getStorageEstimate()`
- `api.admin.runRetention()`, `api.admin.runReconciliation()`, `api.admin.runBackfill()`
- `api.admin.getEventCounters()`

Includes `ApiError` class and typed TypeScript interfaces for all request/response shapes.

## Utilities

`lib/utils.ts` — Shared formatting helpers:

- `fmt(n)` — locale number string
- `fmtShort(n)` — compact format (1.2k, 3.4M)
- `timeAgo(date)` — relative time string
- `fmtDate(date)` — locale date
- `fmtDateTime(date)` — locale date+time
- `capitalize(s)` — first letter uppercase
- `eventTypeLabel(type)` — human-readable event type name
- `clamp(n, min, max)` — numeric clamping
- `raritySort(a, b)` — sort by rarity tier
- `EVENT_COLORS` — map of event types → hex colors
- `eventColor(type)` — lookup with fallback

## Build

```bash
cd dashboard
npm install
npm run dev      # Development (port 5173)
npm run build    # Production build
npm run preview  # Preview production build (port 3000)
```

Docker: built from `dashboard/Dockerfile`, served by Node adapter on port 3000.
