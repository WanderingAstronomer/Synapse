# Work Tracker: Event Capture First + Reward Firewall Architecture

> **Plan:** PLAN_event_capture_firewall.md
> **Overall Status:** In Progress
>
> ⚠️ **Sequencing Authority:** `MASTER_ROLLOUT_PLAN.md` governs phase ordering for the full system.
> Phase numbers in this document are internal to the event-capture initiative only and do **not** correspond to master plan phase numbers.
> Consult the master plan before starting any phase here to confirm correct sequencing context.

---

## Phase 1 — Inventory & Pruning (Alignment)

**Status:** Complete
**Task:** Align current system with DOD paradigm and clear technical debt. (Tracked separately in TRACKER_pruning_for_capture_firewall.md).

---

## Phase 2 — Telemetry Expansion & Abstraction

**Status:** In Progress
**Branch/Commit:** main

| # | Task | Status | Notes |
|---|------|--------|-------|
| 2.1 | Define InteractionEnvelope schema | 🔄 | |
| 2.2 | Map existing event_lake payloads | ⬜ | |
| 2.3 | Expand coverage (Polls, Stickers, Threads) | ⬜ | |

---

## Phase 3 — Rule Firewall Core

**Status:** In Progress

| # | Task | Status | Notes |
|---|------|--------|-------|
| 3.1 | Implement `RewardRule` SQL Model | ✅ | Added to `models.py`. |
| 3.2 | Implement `PredicateEvaluator` (Atomic + Contextual) | ✅ | Pure function in `engine/reward.py`. |
| 3.3 | Implement `ScalingResolver` (Log/Exp/Step) | ✅ | `engine/reward.py`. |
| 3.4 | Define `Achievement` / `Rarity` / `Season` / `Category` models | ⬜ | Composable Crate schema. |
| 3.5 | Wire `RuleEngine` to replace hardcoded multipliers | 🔄 | Pending feature flag gating. |
| 3.6 | Build baseline default rules parity pack | ⬜ | Must match current reward behavior before flag flip. |
| 3.7 | Deterministic evaluator test suite | ⬜ | Same inputs → same outputs, always. |
| 3.8 | Baseline parity verification against legacy pipeline | ⬜ | Run side-by-side before cutover. |

**Verification:**
- [ ] `evaluate_predicate` and `resolve_scaling` unit tests pass
- [ ] Baseline default rules reproduce current reward output
- [ ] No DB calls inside `engine/` modules

**Phase Notes:**
- `firewall_enabled` feature flag must remain `false` until 3.6 + 3.8 are verified.
- No UI dependency required to validate evaluator correctness.

---

## Phase 4 — Projection Pipeline

**Status:** Not Started
**Branch/Commit:**

| # | Task | Status | Notes |
|---|------|--------|-------|
| 4.1 | Projection model for XP/gold/stats/achievements | ⬜ | Derived-only contracts. |
| 4.2 | Replay/backfill pipeline from telemetry | ⬜ | Idempotent and resumable. |
| 4.3 | Drift detection and reconciliation hooks | ⬜ | Compare projection vs expected replay outputs. |

**Verification:**
- [ ] Replay produces stable derived outputs
- [ ] Drift checks operational

**Phase Notes:**
- Protect immutable source telemetry.

---

## Phase 5 — Admin Rule Builder UX

**Status:** Not Started
**Branch/Commit:**

| # | Task | Status | Notes |
|---|------|--------|-------|
| 5.1 | Rule authoring UI with AND/OR groups | ⬜ | Channel/category/type/content predicates. |
| 5.2 | Rule simulation and explainability | ⬜ | Show match path and computed reward actions. |
| 5.3 | Safe publish/version rollback UX | ⬜ | Rule set lifecycle controls. |

**Verification:**
- [ ] Admin can author scoped complex rules without code changes
- [ ] Simulation matches evaluator outputs

**Phase Notes:**
- This phase depends on core evaluator and schemas from phases 3-4.

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

2026-02-18  Planning and tracking docs created for architecture pivot toward capture-first + reward firewall.

---

## Final Checklist

- [ ] Plan reviewed and approved
- [ ] All phases complete
- [ ] Implementation validations complete
- [ ] Temporary planning artifacts cleaned up post-merge
