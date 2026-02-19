# Cache: Pruning Matrix — Phase 1 (Inventory + Confidence)

> **Created:** 2026-02-18
> **Source:** AUDIT_code_minimalism.md + current architecture plans
> **Purpose:** Actionable delete/refactor/quarantine list with confidence and verification mapping.

## Decision Legend
- **Delete**: remove now (high-confidence dead/redundant)
- **Refactor**: keep behavior, reduce duplication/complexity
- **Quarantine**: keep temporarily but isolate/flag for later removal

## Priority Principle

Quick is preferable; quick is not instantaneous.

Interpretation for pruning and migration:
- Prefer correctness and deterministic propagation over instant propagation.
- Keep eventual consistency paths when they are bounded and observable.
- Remove code that assumes immediate consistency where system guarantees are eventual.

---

## Phase 2 Candidates — High-Confidence Deletions

| ID | Area | Candidate | Action | Confidence | Why | Verification |
|---|---|---|---|---|---|---|
| E1 | engine/quality | `llm_quality_modifier()` stub | Delete | High | Always returns 1.0, no functional value | reward tests + import checks |
| E6 | engine/anti_gaming | `get_default_tracker()` | Delete | High | No callers; internal singleton already used | anti-gaming tests |
| E7 | engine/cache | `get_channel_type()` | Delete | High | No callers | grep + tests |
| E8 | engine/cache | `get_str()` | Delete | High | No callers | grep + tests |
| E11 | engine/events | `InteractionType` re-export in `__all__` | Delete | High | Misleading alternate import path | lint + import search |
| S1 | services/setup | `_setting_exists()` | Delete | High | No callers | grep + tests |
| S2 | services/reward | dead `get_user_preferences()` helper | Delete | High | Unused; duplicates announcement behavior | grep + tests |
| S4 | services/settings | `get_settings_by_category()` | Delete | High | Unused dead helper | grep + tests |
| S6 | services/layout | `_make_id()` passthrough | Delete (inline) | High | One-line wrapper around uuid | unit/integration tests |
| S10 | services/announcement | deferred local imports | Delete pattern | High | No circular dependency justification | lint + runtime smoke |
| S12 | services/backfill/reconcile | stale task references in docstrings | Delete/update text | High | Dead references, confusion only | lint/docs check |

---

## Phase 3 Candidates — Refactor for Duplication Collapse

| ID | Area | Candidate | Action | Confidence | Why | Verification |
|---|---|---|---|---|---|---|
| S5 | services/admin | repetitive audited CRUD blocks | Refactor | High | ~400 LOC duplicate behavior | endpoint parity tests |
| B1 | bot/cogs | repeated process wrappers | Refactor | High | same adapter logic in multiple cogs | command/event smoke tests |
| A13 | api/routes | oversize admin route file segmentation | Refactor | Medium | lower edit risk, same API | route tests |
| T6 | tests | duplicated anti-gaming assertions | Refactor | Medium | maintenance burden | test suite |

---

## Phase 4 Candidates — Contract/Config Alignment

| ID | Area | Candidate | Action | Confidence | Why | Verification |
|---|---|---|---|---|---|---|
| D5 | db/constants/ui | stale achievement requirement autocomplete constants | Refactor/remove | High | enum/UX mismatch | admin API + UI checks |
| A11 | api/achievements | static trigger metadata location decision | Quarantine -> decide | Medium | risk of frontend/backend drift | contract tests |
| Public settings | api/public vs dashboard settings usage | Refactor | High | key mismatch causes partial UI disconnect | dashboard smoke tests |

---

## Phase 5 Candidates — Guardrail Hardening (Pre-Migration Critical)

| ID | Area | Candidate | Action | Confidence | Why | Verification |
|---|---|---|---|---|---|---|
| B7 | bot/meta | `/buy-coffee` race vulnerability | Refactor/fix | High | check-then-act risk | targeted command tests |
| S13 | services/upload | async function with sync file I/O | Refactor/fix | High | event-loop blocking | upload route test |
| E12 | engine/cache | half-wired event dispatch/listen paths | Quarantine or complete | Medium | false reliability assumptions | integration check |
| retry bounds | cache listener/service retries | Refactor/fix | Medium | bounded failure behavior needed | fault-injection test |

---

## Quarantine List (Do Not Delete Yet)

| Item | Reason for Quarantine | Exit Criterion |
|---|---|---|
| `member_tenure`, `invite_count` trigger placeholders | feature intent exists but infra not ready | telemetry + source-of-truth fields implemented |
| event dispatch callback infrastructure | uncertain near-term need for cross-service event notifications | explicit decision in rule firewall phase |
| dashboard quality overhaul artifacts | may still contain pending actionable UI hardening | mark superseded or active explicitly |

---

## Suggested Execution Order (Minimal Cleanup Debt)

1. Phase 2 high-confidence deletions.
2. Phase 5 guardrail-critical fixes (`/buy-coffee`, blocking async I/O).
3. Phase 3 duplication collapse (`admin_service` first).
4. Phase 4 contract alignment before rule firewall API expansion.

This order minimizes migration rework while keeping system behavior stable and predictable.
