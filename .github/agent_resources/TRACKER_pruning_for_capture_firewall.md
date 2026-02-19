# Work Tracker: Pruning for Capture-First Architecture

> **Plan:** PLAN_pruning_for_capture_firewall.md
> **Started:** 2026-02-18
> **Last Updated:** 2026-02-18
> **Overall Status:** Complete

---

## Phase 1 — Inventory + Confidence Labels

**Status:** Complete
**Branch/Commit:** main / working

| # | Task | Status | Notes |
|---|------|--------|-------|
| 1.1 | Build candidate removal matrix from audit + code search | ✅ | Completed in `CACHE_pruning_matrix_phase1.md`. |
| 1.2 | Label each item delete/refactor/quarantine | ✅ | Included in matrix with confidence labels. |
| 1.3 | Map each item to verification method | ✅ | Verification column added for each candidate. |

**Verification:**
- [x] Candidate list reviewed
- [x] Confidence labels assigned
- [x] Verification strategy attached to each item

---

## Phase 2 — Dead Code Deletion (High Confidence)

**Status:** Complete
**Branch/Commit:** main / working

| # | Task | Status | Notes |
|---|------|--------|-------|
| 2.1 | Remove confirmed dead symbols | ✅ | verified: llm_quality_modifier, get_default_tracker, etc gone |
| 2.2 | Remove stale imports/re-exports | ✅ | |
| 2.3 | Keep explicit deferral notes for postponed features | ✅ | |

**Verification:**
- [x] Targeted tests pass
- [x] Lint/type checks pass

---

## Phase 3 — Duplication Collapse

**Status:** Complete
**Branch/Commit:** main / working

| # | Task | Status | Notes |
|---|------|--------|-------|
| 3.1 | Consolidate repetitive service patterns | ✅ | admin_service generic helpers fully implemented |
| 3.2 | Consolidate repetitive cog wrappers/helpers | ✅ | bot/core processor wrappers implemented |
| 3.3 | Validate parity on affected flows | ✅ | |

**Verification:**
- [x] Behavior parity checks complete
- [x] No API/command regressions

---

## Phase 4 — Contract/Config Alignment

**Status:** Complete
**Branch/Commit:** main / working

| # | Task | Status | Notes |
|---|------|--------|-------|
| 4.1 | Align stale constants and enums | ✅ | InteractionType and BASE_XP/STARS aligned. |
| 4.2 | Remove misleading/deprecated references | ✅ | |
| 4.3 | Verify dashboard/admin contract integrity | ✅ | |

**Verification:**
- [x] UI/API smoke checks pass
- [x] No stale docs/metadata in active paths

---

## Phase 5 — Guardrail Hardening

**Status:** Complete
**Branch/Commit:** main / working

| # | Task | Status | Notes |
|---|------|--------|-------|
| 5.1 | Fix atomic mutation weak spots | ✅ | /buy-coffee fixed with atomic atomic SQL |
| 5.2 | Remove blocking I/O from async paths | ✅ | save_upload uses to_thread |
| 5.3 | Add retry bounds/timeouts where missing | ✅ | httpx calls have timeouts |

**Verification:**
- [x] Reliability checks pass
- [x] No regressions introduced by hardening

---

## Status Key

| Icon | Meaning |
|------|---------|
| ⬜ | Not started |
| 🔄 | In progress |
| ✅ | Complete |
| ⛔ | Blocked |
| ⏭️ | Skipped / deferred |

---

## Completion Log

2026-02-18  Pruning plan and tracker initialized after architecture planning consolidation.
2026-02-18  Phase 1 complete. Inventory + confidence + verification matrix created in `CACHE_pruning_matrix_phase1.md`.

---

## Final Checklist

- [x] All phases complete
- [x] Tests/lint/type checks pass
- [x] Ready to begin PLAN_event_capture_firewall implementation phases
