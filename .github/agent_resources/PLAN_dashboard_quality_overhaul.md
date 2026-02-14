# Planning: Dashboard Quality Overhaul

> **Created:** 2026-02-14
> **Status:** Approved
> **Scope:** Systematic remediation of architectural flaws, security holes, performance bottlenecks, framework misuse, and accessibility gaps across the entire Synapse Dashboard (SvelteKit/Svelte 5 frontend).

---

## 1. Problem Statement

A senior code review identified **12 major issues** across the Synapse Dashboard ranging from P0 (broken viewports, memory leaks) to P3 (accessibility gaps, naming confusion). The issues fall into five categories:

1. **State Management Conflicts** — Svelte 4/5 hybrid with unnecessary bridge pattern
2. **Security Holes** — Client-side privilege escalation, no token expiry handling
3. **Performance Bottlenecks** — Chart.js full-bundle import, effect cleanup failures
4. **Framework Misuse** — SSR disabled with Node adapter, 500-line copy-pasted pages
5. **UX/Accessibility** — No mobile responsive sidebar, missing ARIA, no keyboard DnD

These aren't speculative — they're verified against the running codebase.

---

## 2. Context & Discovery

### Files Inventoried

| Area | Key Files | Lines | Notes |
|------|-----------|-------|-------|
| Root Layout | `routes/+layout.svelte` | 69 | Sidebar + FlashMessage shell |
| Layout Config | `routes/+layout.ts` | 3 | `ssr=false, prerender=false` |
| Sidebar | `lib/components/Sidebar.svelte` | 148 | Fixed `w-72`, no responsive |
| API Client | `lib/api.ts` | 774 | 3 duplicate upload fns, no encoding |
| Auth Store | `lib/stores/auth.ts` | 64 | `is_admin: true` hardcode on login |
| Auth Callback | `routes/auth/callback/+page.svelte` | 43 | JWT decode, no validation |
| Rune Bridge | `lib/stores/rune.svelte.ts` | 27 | `fromStore()` adapter |
| Edit Mode | `lib/stores/editMode.ts` | 50 | `canEdit = derived(isAdmin, x=>x)` |
| Flash Store | `lib/stores/flash.ts` | 41 | OK, no issues |
| Currency Store | `lib/stores/currency.ts` | 62 | OK pattern |
| Site Settings | `lib/stores/siteSettings.ts` | 42 | `pageTitle()` creates uncached derived |
| Names Store | `lib/stores/names.ts` | 78 | Unbounded batch, otherwise solid |
| Dashboard | `routes/+page.svelte` | 505 | Full duplicate fallback (~165 lines) |
| Leaderboard | `routes/leaderboard/+page.svelte` | 245 | Uses fromStore bridge |
| Activity | `routes/activity/+page.svelte` | 230 | Chart.js leak, full import |
| Achievements | `routes/achievements/+page.svelte` | 216 | Uses fromStore bridge |
| Admin Layout | `routes/admin/+layout.svelte` | 66 | Auth guard, setup check |
| Reward Rules | `routes/admin/reward-rules/+page.svelte` | 482 | Large but well-structured |
| Admin Achievements | `routes/admin/achievements/+page.svelte` | 653 | Largest admin page |
| Awards | `routes/admin/awards/+page.svelte` | 184 | OK structure |
| Media | `routes/admin/media/+page.svelte` | 142 | Clean |
| Settings | `routes/admin/settings/+page.svelte` | 362 | Solid implementation |
| Data Sources | `routes/admin/data-sources/+page.svelte` | 341 | OK |
| Logs | `routes/admin/logs/+page.svelte` | 344 | OK |
| EditableCard | `lib/components/EditableCard.svelte` | 334 | No error rollback |
| CardPropertyPanel | `lib/components/CardPropertyPanel.svelte` | 380 | Unchecked fetch on mount |
| MetricCard | `lib/components/MetricCard.svelte` | 55 | Clean |
| HeroHeader | `lib/components/HeroHeader.svelte` | 50 | Clean |
| Avatar | `lib/components/Avatar.svelte` | 30 | Clean |
| ProgressBar | `lib/components/ProgressBar.svelte` | 50 | Clean |
| ConfirmModal | `lib/components/ConfirmModal.svelte` | 66 | No focus trap |
| FlashMessage | `lib/components/FlashMessage.svelte` | 25 | Clean |
| SynapseLoader | `lib/components/SynapseLoader.svelte` | 36 | No ARIA |
| EmptyState | `lib/components/EmptyState.svelte` | 52 | Clean |
| AuditLogView | `lib/components/AuditLogView.svelte` | 197 | Clean |
| Global CSS | `app.css` | 172 | `--ui-scale: 1.25` concern |
| Tailwind Config | `tailwind.config.js` | 97 | Extensive custom palette |
| Vite Config | `vite.config.ts` | 15 | Dev proxy only |
| Svelte Config | `svelte.config.js` | 31 | Adapter try/catch concern |
| Hooks | `hooks.client.js` | 32 | Chunk reload handler — good |
| Error Page | `routes/+error.svelte` | 19 | Clean |

### Dependency Summary

| Package | Version | Notes |
|---------|---------|-------|
| svelte | ^5.28.0 | Runes API |
| @sveltejs/kit | ^2.20.0 | SvelteKit 2 |
| @sveltejs/adapter-node | ^5.2.0 | Node adapter (misuse concern) |
| chart.js | ^4.4.9 | Full bundle imported |
| tailwindcss | ^3.4.17 | Dark theme custom palette |
| typescript | ^5.7.0 | Strict-ish |
| vite | ^6.3.0 | Dev server |

### Pattern Map: `fromStore()` Usage

Every public page and several components use the bridge:

```
routes/+page.svelte          → fromStore(canEdit), fromStore(pageTitle)
routes/leaderboard/+page.svelte → fromStore(canEdit), fromStore(pageTitle)
routes/activity/+page.svelte    → fromStore(canEdit), fromStore(pageTitle)
routes/achievements/+page.svelte → fromStore(canEdit), fromStore(pageTitle)
lib/components/EditableCard.svelte → fromStore(canEdit), fromStore(activeCardId)
lib/components/CardPropertyPanel.svelte → fromStore(activeCardId), fromStore(canEdit)
```

6 stores × 2-3 bridge calls each = **~15 unnecessary subscriptions** on initial load.

---

## 3. Constraints & Guardrails

- [x] **No feature regressions** — every change must be verified against existing behavior
- [x] **Build must pass** after every phase (`npm run check`, `npm run build`)
- [x] **Backend tests unaffected** — dashboard changes don't touch Python code
- [x] **Preserve admin audit trail** — API calls and auth flow must remain intact
- [x] **Dark theme contract** — visual changes must maintain the existing dark palette
- [x] **Support existing Docker deployment** — the Dockerfile and docker-compose.yml patterns remain valid
- [x] **No new dependencies** unless strictly necessary (and verified to exist)
- [x] **Mobile-first responsive** — sidebar fix must work from 320px viewport up
- [x] **Backward-compatible URLs** — no route path changes that break bookmarks

---

## 4. Design Options

### Option A — Incremental Fix-by-Fix

**Summary:** Address each issue from the review individually in priority order. Minimal planning, maximum velocity.

**Pros:**
- Fast start, immediate value
- Each fix is small and reviewable

**Cons:**
- State management refactor (Phase 4) invalidates work done in Phase 1 if we edit the same files
- No holistic view — risk of churn
- Duplicate edit passes over the same files

### Option B — Phase-Grouped by System Boundary

**Summary:** Group fixes by the subsystem they touch (state, auth, rendering, layout, a11y). Each phase is a coherent slice that doesn't overlap with others. Files are edited once per phase.

**Pros:**
- Minimal churn — each file touched at most once per phase
- Phases are independently verifiable
- Natural priority ordering (P0 first, P3 last)

**Cons:**
- Larger individual phases
- Requires more upfront planning (this document)

### Option C — Complete Rewrite of Dashboard

**Summary:** Scorched earth. Rebuild the dashboard from scratch with Svelte 5 idioms, proper SSR, modern patterns.

**Pros:**
- Clean architecture from day one
- No legacy compromises

**Cons:**
- Absurd scope for a working product
- Throws away functional code
- Weeks of work for marginal user-visible improvement

### Chosen Approach

> **Decision:** Option B — Phase-Grouped by System Boundary. It minimizes churn, matches the priority ordering from the review, and each phase produces a verifiably better codebase. Files are edited once, coherently.

---

## 5. Rollout Phases

### Phase 1 — Critical P0: Mobile Viewport & Memory Leaks

**Priority:** P0 — Application is broken on mobile, memory leaks active
**Goal:** Fix the two issues that cause immediate user-visible failures.
**Estimated Effort:** Small

**Deliverables:**

#### 1.1 — Responsive Sidebar

**Problem:** Sidebar is `w-72 shrink-0 sticky` with no responsive behavior. On viewports < 768px, it consumes the entire screen.

**Changes to `lib/components/Sidebar.svelte`:**
- [ ] Add `$state` for sidebar open/closed
- [ ] On mobile (< `lg` breakpoint): sidebar starts collapsed, renders as full-screen overlay with backdrop
- [ ] Add hamburger button (visible only on mobile) to toggle sidebar
- [ ] Add close button inside the mobile overlay
- [ ] Close sidebar on navigation (listen to `$page` changes)
- [ ] Animate open/close with `transition:fly`

**Changes to `routes/+layout.svelte`:**
- [ ] Wrap sidebar in responsive container
- [ ] Add mobile hamburger trigger button in main area header
- [ ] Ensure main content uses full width on mobile when sidebar is collapsed

**Changes to `app.css`:**
- [ ] Add mobile overlay styles for sidebar backdrop
- [ ] Add `@media` or Tailwind breakpoint utilities as needed

#### 1.2 — Chart.js Memory Leak Fix

**Problem:** `$effect` in `activity/+page.svelte` destroys chart on *next* execution but not on component unmount.

**Change to `routes/activity/+page.svelte`:**
- [ ] Restructure `$effect` to return a cleanup function:
  ```ts
  $effect(() => {
      // ...create chart...
      return () => { chart?.destroy(); chart = null; };
  });
  ```
- [ ] Verify the chart is properly destroyed when navigating away from the Activity page

**Verification:**
- [ ] Build passes: `npm run build`
- [ ] Manual test: sidebar collapses on mobile viewports (320px, 375px, 768px)
- [ ] Manual test: hamburger opens/closes sidebar
- [ ] Manual test: navigate to/from Activity page, verify no Chart.js warnings in console
- [ ] Manual test: all existing desktop functionality unchanged

---

### Phase 2 — P1 Security & Data Integrity: Auth Hardening + Edit Mode Rollback

**Priority:** P1 — Security vector and silent data loss
**Goal:** Fix client-side privilege escalation and add error feedback to optimistic updates.
**Estimated Effort:** Medium

**Deliverables:**

#### 2.1 — Auth: Remove Client-Side `is_admin` Hardcode

**Problem:** `auth.login()` decodes JWT payload and sets `is_admin: true` without server validation.

**Change to `lib/stores/auth.ts`:**
- [ ] In `login()`, remove eager JWT decode path
- [ ] Instead, call `api.getMe()` immediately and use the server response for user state
- [ ] Keep token storage in localStorage (JWT is still the auth mechanism)
- [ ] Add `is_admin` from server response only
- [ ] Add tiny loading state between login redirect and `getMe()` completion

**Change to `routes/auth/callback/+page.svelte`:**
- [ ] Store token, then `await auth.loginWithVerification(token)` (new method that calls `getMe()`)
- [ ] Show loader during verification
- [ ] Handle 401/403 — clear token, redirect with error flash

#### 2.2 — Auth: Token Expiry Handling

**Problem:** No mechanism to detect or handle expired JWTs during a session.

**Change to `lib/api.ts`:**
- [ ] In `request()`, check for 401 response status
- [ ] On 401: clear localStorage token, reset auth store, redirect to `/` with flash message "Session expired"
- [ ] Ensure this only fires once (not a cascade of flash messages from parallel requests)

**Change to `lib/stores/auth.ts`:**
- [ ] Add `expiredLogout()` method that clears state + shows flash
- [ ] Add a flag to prevent multiple concurrent expired-session redirects

#### 2.3 — Edit Mode: Error Rollback & User Feedback

**Problem:** `saveCard()` in `editMode.ts` silently `console.error`s on failure. `saveLayout()` does the same. User sees optimistic state that the backend rejected.

**Change to `lib/stores/editMode.ts`:**
- [ ] `saveCard()`: on error, fire `flash.error('Failed to save card changes')` 
- [ ] `saveLayout()`: on error, fire `flash.error('Failed to save layout order')`
- [ ] Both: trigger a layout reload on failure to restore server state

**Change to `lib/components/EditableCard.svelte`:**
- [ ] Replace `confirm()` with `ConfirmModal` for card deletion
- [ ] On delete failure: show flash error, re-add card to local state
- [ ] On visibility/grid-span toggle failure: revert local state

**Change to `lib/components/CardPropertyPanel.svelte`:**
- [ ] On delete failure: show flash error
- [ ] Add error state for image upload failure (already partially there)

**Verification:**
- [ ] Build passes
- [ ] Manual test: fabricate a 401 API response, verify session expired handling
- [ ] Manual test: disconnect backend, attempt card edit, verify flash error appears
- [ ] Manual test: disconnect backend, attempt drag reorder, verify flash error
- [ ] Manual test: card delete uses ConfirmModal not `confirm()`
- [ ] Verify `getMe()` is called on login, not JWT decode

---

### Phase 3 — P1 Code Quality: Dashboard Page Deduplication

**Priority:** P1 — 165 lines of duplicated template, maintenance trap
**Goal:** Remove the copy-pasted fallback template from the dashboard page.
**Estimated Effort:** Small

**Deliverables:**

#### 3.1 — Remove Duplicate Dashboard Fallback

**Problem:** `routes/+page.svelte` lines ~340-505 are a verbatim copy of the layout-driven rendering path, under an `{:else}` for "no layout loaded."

**Change to `routes/+page.svelte`:**
- [ ] Remove the entire `{:else}` fallback block (~165 lines)
- [ ] When `layout` is null or has no cards, show the existing `EmptyState` component with instructions to run Setup
- [ ] This aligns with the actual user flow: a fresh install runs setup first, which creates the default layout
- [ ] Reduce file from ~505 lines to ~340 lines

**Verification:**
- [ ] Build passes
- [ ] Manual test: dashboard renders normally with layout present
- [ ] Manual test: with no layout, EmptyState message appears (this is already handled above the fallback block)
- [ ] Verify no visual regression on the layout-driven path

---

### Phase 4 — P2 State Management: Svelte 5 Rune Migration

**Priority:** P2 — Architectural inconsistency, unnecessary overhead
**Goal:** Eliminate the Svelte 4/5 hybrid pattern. Migrate all stores to rune-based singletons. Remove `fromStore()` bridge.
**Estimated Effort:** Large (touches every public page and several components)

**Deliverables:**

#### 4.1 — Convert Auth Store to Rune-Based Singleton

**Change to `lib/stores/auth.svelte.ts` (rename from .ts):**
- [ ] Rewrite using `$state` in module-level context
- [ ] Export reactive getters: `auth.user`, `auth.isAdmin`, `auth.loading`
- [ ] Maintain same public API: `auth.init()`, `auth.login()`, `auth.logout()`
- [ ] Export `isAdmin` as a simple getter, not a derived store

**Impact:** Remove `$auth` / `$isAdmin` store subscriptions from:
- `routes/+layout.svelte`
- `routes/admin/+layout.svelte`
- `lib/components/Sidebar.svelte`

#### 4.2 — Convert Edit Mode Store to Rune-Based

**Change to `lib/stores/editMode.svelte.ts` (rename from .ts):**
- [ ] `canEdit` becomes a simple reactive getter based on `auth.isAdmin` (remove the identity `derived()`)
- [ ] `activeCardId` becomes a `$state` singleton
- [ ] `saveCard()` and `saveLayout()` remain as module-level functions
- [ ] Export reactive getters directly

**Impact:** Remove `fromStore(canEdit)` from:
- `routes/+page.svelte`
- `routes/leaderboard/+page.svelte`
- `routes/activity/+page.svelte`
- `routes/achievements/+page.svelte`
- `lib/components/EditableCard.svelte`
- `lib/components/CardPropertyPanel.svelte`

#### 4.3 — Convert Flash Store to Rune-Based

**Change to `lib/stores/flash.svelte.ts` (rename from .ts):**
- [ ] `flash.messages` becomes `$state<FlashMessage[]>([])`
- [ ] Methods remain the same: `success()`, `error()`, `info()`, `warning()`, `dismiss()`
- [ ] Export reactive array directly

**Impact:** Remove `$flash` subscription from `lib/components/FlashMessage.svelte`

#### 4.4 — Convert Currency Store to Rune-Based

**Change to `lib/stores/currency.svelte.ts` (rename from .ts):**
- [ ] Labels become `$state` values
- [ ] `primaryCurrency` and `secondaryCurrency` become reactive getters, not derived stores

**Impact:** Remove `$primaryCurrency` / `$secondaryCurrency` subscriptions from all pages that use them.

#### 4.5 — Convert Site Settings Store to Rune-Based

**Change to `lib/stores/siteSettings.svelte.ts` (rename from .ts):**
- [ ] Settings map becomes `$state<Record<string, unknown>>({})`
- [ ] `pageTitle()` returns a reactive getter (cached per slug), not a new derived store each call
- [ ] Implement memoization: maintain a `Map<string, string>` of computed titles, invalidated on settings change

**Impact:** Remove `fromStore(pageTitle(...))` calls from all public pages. Eliminates the uncached-derived-store problem.

#### 4.6 — Remove `fromStore()` Bridge

**Delete `lib/stores/rune.svelte.ts`**
- [ ] Once all stores are migrated, this file has zero consumers
- [ ] Remove all `fromStore()` imports from every file that used it
- [ ] Delete the file

#### 4.7 — Clean Up Remaining Store Subscriptions

- [ ] Audit every file for `$` prefix auto-subscriptions (e.g., `$page` from `$app/stores` is still fine — it's a SvelteKit store)
- [ ] Verify no `writable()` / `derived()` imports remain in `lib/stores/` (except names.ts which is a different pattern)
- [ ] Update `names.ts` if beneficial (optional — it's a caching layer, stores are appropriate)

**Verification:**
- [ ] Build passes: `npm run build`
- [ ] `npm run check` passes with no type errors
- [ ] Manual test: all pages render correctly
- [ ] Manual test: auth flow works (login, logout, admin guard)
- [ ] Manual test: edit mode works (card edits, drag-drop, property panel)
- [ ] Manual test: flash messages appear and dismiss
- [ ] Manual test: currency labels display correctly
- [ ] Manual test: page titles update from settings

---

### Phase 5 — P2 Performance: Chart.js Tree-Shaking & Adapter Fix

**Priority:** P2 — ~200KB unnecessary bundle, wrong deployment adapter
**Goal:** Tree-shake Chart.js to only what's needed. Fix adapter choice.
**Estimated Effort:** Small

**Deliverables:**

#### 5.1 — Chart.js Tree-Shaking

**Change to `routes/activity/+page.svelte`:**
- [ ] Replace `import { Chart, registerables } from 'chart.js'` with specific imports:
  ```ts
  import {
      Chart,
      BarController,
      BarElement,
      CategoryScale,
      LinearScale,
      Tooltip,
      Legend,
  } from 'chart.js';
  Chart.register(BarController, BarElement, CategoryScale, LinearScale, Tooltip, Legend);
  ```
- [ ] Verify the chart renders identically

#### 5.2 — API Client Consolidation: Deduplicate Upload Functions

**Change to `lib/api.ts`:**
- [ ] Create a single private `uploadFormData(path: string, file: File)` helper
- [ ] Replace `uploadBadge()`, `uploadMedia()`, and `uploadFile()` to use the shared helper
- [ ] Reduce ~45 lines of duplication to ~15

#### 5.3 — Evaluate Adapter Choice

**Change to `svelte.config.js`:**
- [ ] Document the architecture decision: if SSR is never used, switch to `adapter-static`
- [ ] If keeping `adapter-node` (e.g., for future SSR or server hooks), remove the `try/catch` fallback that silently produces broken builds
- [ ] Add a comment explaining the decision

**Note:** This is a deployment config change. Verify with Docker build.

**Change to `package.json`:**
- [ ] If switching to `adapter-static`: `npm install -D @sveltejs/adapter-static` and remove `@sveltejs/adapter-node`
- [ ] If staying node: no change

**Verification:**
- [ ] Build passes
- [ ] Bundle size check: compare before/after with `npm run build` output
- [ ] Manual test: Activity page chart renders correctly
- [ ] Manual test: all three upload flows still work (badge, media, generic)
- [ ] Docker build succeeds if adapter changed

---

### Phase 6 — P2/P3 API Client Hardening

**Priority:** P2-P3 — URL encoding, error granularity
**Goal:** Harden the API client against edge cases.
**Estimated Effort:** Small

**Deliverables:**

#### 6.1 — URL Parameter Encoding

**Change to `lib/api.ts`:**
- [ ] Audit all URL path interpolations for `encodeURIComponent` usage
- [ ] Add encoding to: `getLeaderboard` (currency), `getActivity` (eventType), any endpoint with user-sourced path segments
- [ ] Prefer `URLSearchParams` for query strings consistently (some endpoints use it, some don't)

#### 6.2 — Centralized 401 Handling (if not done in Phase 2)

- [ ] Ensure the `request()` function handles 401 globally
- [ ] Do not duplicate 401 logic in individual endpoints

#### 6.3 — Content-Type Header Flexibility

**Change to `lib/api.ts`:**
- [ ] Only set `Content-Type: application/json` when `body` is present and not `FormData`
- [ ] This prepares for future non-JSON requests without bypassing the client

**Verification:**
- [ ] Build passes
- [ ] Manual test: leaderboard, activity, and all API calls work
- [ ] Test with special characters in search queries (Awards user search)

---

### Phase 7 — P3 Accessibility: ARIA, Focus Traps, Keyboard Navigation

**Priority:** P3 — Accessibility gaps
**Goal:** Bring the dashboard to baseline WCAG 2.1 AA compliance for interactive elements.
**Estimated Effort:** Medium

**Deliverables:**

#### 7.1 — Focus Trap for ConfirmModal

**Change to `lib/components/ConfirmModal.svelte`:**
- [ ] Implement focus trap: on mount, focus first focusable element
- [ ] Tab cycling within modal boundaries
- [ ] Escape key closes modal
- [ ] Restore focus to trigger element on close

#### 7.2 — ARIA for SynapseLoader

**Change to `lib/components/SynapseLoader.svelte`:**
- [ ] Add `role="status"` and `aria-live="polite"` to the container
- [ ] Add `aria-label="Loading"` or use the `text` prop as `aria-label`

#### 7.3 — ARIA for EditableCard Inline Editing

**Change to `lib/components/EditableCard.svelte`:**
- [ ] Add `aria-label` to contenteditable spans (e.g., "Edit card title")
- [ ] Add `role="textbox"` and `aria-multiline="false"` (already has `role="textbox"`)
- [ ] Announce save status to screen readers via `aria-live` region

#### 7.4 — Health Indicator Accessibility

**Change to `lib/components/Sidebar.svelte`:**
- [ ] Add `role="status"` to health indicator containers
- [ ] Add `aria-label` with full status text (e.g., "API status: online")
- [ ] Ensure color is not the only indicator — text is already present, verify contrast

#### 7.5 — Keyboard Alternative for Drag-and-Drop

**Change to `lib/components/EditableCard.svelte` and `routes/+page.svelte`:**
- [ ] Add "Move Up" / "Move Down" buttons to the edit controls (visible in edit mode)
- [ ] Wire buttons to the same `handleReorder()` logic
- [ ] These provide keyboard-accessible reordering as an alternative to drag-and-drop
- [ ] `aria-label` on buttons: "Move card up", "Move card down"

#### 7.6 — Skip Navigation Link

**Change to `routes/+layout.svelte`:**
- [ ] Add visually hidden "Skip to main content" link as first focusable element
- [ ] Link targets `<main>` element with `id="main-content"`
- [ ] Visible only on focus (standard skip-link pattern)

**Verification:**
- [ ] Build passes
- [ ] Manual test with keyboard-only navigation:
  - Tab through the modal, verify focus doesn't escape
  - Escape closes modal
  - Tab through sidebar, hear health status from screen reader
  - Reorder cards via Move Up/Move Down buttons
- [ ] Screen reader test (optional but ideal): verify loader announcements, card edit labels
- [ ] No visual regressions

---

### Phase 8 — P3 Cosmetic & Configuration Cleanup

**Priority:** P3 — Developer experience, naming clarity
**Goal:** Clean up configuration quirks that cause ongoing confusion.
**Estimated Effort:** Small

**Deliverables:**

#### 8.1 — Document or Remove `--ui-scale`

**Problem:** `--ui-scale: 1.25` in `app.css` makes all `rem`-based Tailwind utilities 25% larger than their documented values.

**Options:**
  - **A) Document:** Add a clearly visible comment explaining the scaling and its impact on Tailwind values
  - **B) Remove:** Set `--ui-scale: 1` and adjust any elements that truly need to be larger with explicit Tailwind utilities
  - **C) Font-size only:** Apply the scale to `font-size` only, not the root `rem`, so spacing utilities remain standard

**Change to `app.css`:**
- [ ] Choose option A, B, or C (decision deferred to implementation)
- [ ] If keeping: add prominent block comment
- [ ] If removing: audit for visual regressions

#### 8.2 — Svelte Config Adapter Guard

**Change to `svelte.config.js`:**
- [ ] Remove the `try/catch` around adapter import
- [ ] Let the build fail loudly if the adapter is missing
- [ ] This prevents silent broken builds

#### 8.3 — `ManualAwardPayload` Type Consistency

**Change to `lib/api.ts`:**
- [ ] `ManualAwardPayload.user_id` is typed `string` but `awardXpGold()` in Awards page passes `parseInt()`
- [ ] Align: either the type should be `number` or the call site should not `parseInt()`
- [ ] Check backend expectation and match

**Change to `routes/admin/awards/+page.svelte`:**
- [ ] Fix call site to match the corrected type

#### 8.4 — Batch Size Cap for Name Resolution

**Change to `lib/stores/names.ts`:**
- [ ] Add a max batch size (e.g., 50 IDs per request)
- [ ] If pending IDs exceed the cap, flush in chunks
- [ ] Prevents pathologically large POST bodies on audit log pages with many actors

**Verification:**
- [ ] Build passes
- [ ] Visual regression check if `--ui-scale` was modified
- [ ] Docker build succeeds with config changes
- [ ] Awards page still works with corrected types

---

## 6. Risks & Open Questions

| # | Risk / Question | Mitigation / Answer |
|---|----------------|---------------------|
| 1 | Phase 4 (state migration) is the largest and touches every public page — high regression risk | Extract into sub-tasks per store. Test after each store migration. Don't batch. |
| 2 | Adapter switch (Phase 5.3) may break Docker deployment | Test Docker build in Phase 5 verification. Keep adapter-node as fallback. |
| 3 | `fromStore()` removal may break components that depend on the subscription lifecycle (effect cleanup timing) | Verify with manual testing and `svelte-check` after each store migration. |
| 4 | Mobile sidebar overlay may conflict with ConfirmModal z-index stacking | Define z-index layers: sidebar=40, modal=50, flash=60. Document in CSS. |
| 5 | Chart.js tree-shaking may miss a required component (e.g., stacked bar needs specific plugins) | Test the activity chart thoroughly after tree-shaking. Add back any missing components. |
| 6 | `--ui-scale` removal could cause visual regression across entire dashboard | Take before screenshots, compare after. Or keep the scale and just document it. |
| 7 | Some pages use both `$` store syntax and runes — migration must handle the file holistically | Migrate entire file at once, not just the store references. |
| 8 | Focus trap implementation in ConfirmModal may need a utility library | Implement manually first (<20 lines). Consider `svelte-focus-trap` only if complex. |

---

## 7. Success Criteria

### Per-Phase Gates

Each phase must pass ALL of the following before the next phase begins:

- [ ] `npm run build` succeeds (zero errors)
- [ ] `npm run check` succeeds (svelte-check + TypeScript)
- [ ] No visual regressions on affected pages (manual spot check)
- [ ] Phase-specific manual tests pass (documented in each phase's Verification section)

### Overall Completion Criteria

- [ ] All 8 phases complete
- [ ] Build passes: `npm run build`
- [ ] Type check passes: `npm run check`
- [ ] Docker compose build succeeds: `docker compose up -d --build`
- [ ] Mobile viewport works (320px–768px): sidebar collapses, content accessible
- [ ] No memory leaks: navigate to/from Activity page multiple times, no degradation
- [ ] Auth flow hardened: no client-side privilege escalation, expired tokens handled
- [ ] Edit mode resilient: API errors produce user-visible feedback, local state corrected
- [ ] Dashboard page < 350 lines (down from 505)
- [ ] `fromStore()` utility deleted — zero consumers
- [ ] Chart.js bundle impact < 80KB (down from ~200KB)
- [ ] ConfirmModal has focus trap
- [ ] SynapseLoader has ARIA attributes
- [ ] Keyboard-accessible card reordering available
- [ ] No `console.error` as sole error handling for user-affecting operations
- [ ] Backend tests still pass: `uv run pytest tests/ -v`

---

## 8. Phase Dependency Graph

```
Phase 1 (P0: Mobile + Chart Leak)
    │
    ├── Phase 2 (P1: Auth + Edit Rollback)
    │       │
    │       └── Phase 3 (P1: Dashboard Dedup)
    │
    └── Phase 5 (P2: Chart Tree-Shake + Adapter)
            │
            └── Phase 6 (P2: API Client Hardening)

Phase 4 (P2: State Migration) ← independent, can run after Phase 2
    │
    └── Phase 7 (P3: Accessibility) ← depends on Phase 4 for clean component refs
            │
            └── Phase 8 (P3: Cosmetic Cleanup) ← last, lowest risk

```

**Critical Path:** Phase 1 → Phase 2 → Phase 3 (P0→P1→P1 fixes)
**Parallel Track:** Phase 4 can begin independently after Phase 2 completes
**Tail:** Phases 7 and 8 are lowest priority, can be deferred if needed

---

## 9. Estimated Total Effort

| Phase | Effort | Priority | Dependencies |
|-------|--------|----------|-------------|
| Phase 1 — Mobile + Chart Leak | ~1-2 hours | P0 | None |
| Phase 2 — Auth + Edit Rollback | ~2-3 hours | P1 | Phase 1 |
| Phase 3 — Dashboard Dedup | ~30 min | P1 | Phase 2 |
| Phase 4 — State Migration | ~3-5 hours | P2 | Phase 2 |
| Phase 5 — Chart + Adapter | ~1 hour | P2 | Phase 1 |
| Phase 6 — API Hardening | ~1 hour | P2 | Phase 5 |
| Phase 7 — Accessibility | ~2-3 hours | P3 | Phase 4 |
| Phase 8 — Cosmetic Cleanup | ~1 hour | P3 | None |
| **Total** | **~12-16 hours** | | |
