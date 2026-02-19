# Planning: Pruning for Capture-First Architecture

> **Created:** 2026-02-18
> **Status:** Complete — all phases verified in TRACKER_pruning_for_capture_firewall.md
> **Scope:** Remove or isolate narrow/legacy code paths that block migration to immutable telemetry + composable reward firewall.

---

## 1. Problem Statement

The codebase currently mixes:
- selective event/reward assumptions,
- partially wired legacy abstractions,
- and feature stubs that increase cognitive load.

Before major architecture shifts, we need a controlled pruning pass so migration work lands on a cleaner base.

Pruning goal:
- remove dead/duplicated/narrow logic,
- preserve current production behavior,
- and reduce rewrite churn for phases in PLAN_event_capture_firewall.md.

Scope boundary (hard constraint):
- Pruning is performed for a single-guild operating model only.
- Any multi-guild or tenant-isolation prep that does not benefit single-guild operation is out of scope.

---

## 2. Pruning Principles

1. **No behavior drift unless explicitly approved.**
2. **Delete dead code first, then refactor duplication.**
3. **One canonical source per concern (no parallel docs/paths).**
4. **Every removal has a verification checkpoint.**
5. **If uncertain, quarantine/deprecate before deleting.**
6. **Reasonable propagation over instant propagation.** Prioritize deterministic, bounded-latency behavior instead of forcing instantaneous cross-service consistency.

### Latency Mantra (Operational)

Quick is preferable. Quick does not mean instantaneous.

Implications for architecture prep:
- Keep eventual consistency paths when they are bounded, observable, and reliable.
- Remove assumptions that all config/rule changes must materialize immediately everywhere.
- Optimize for predictable convergence windows and safe retries, not zero-latency illusions.

---

## 3. Target Removal Categories

### A. Dead or Non-functional Paths

Candidates:
- Trigger handlers that intentionally always return false unless infra exists.
- Unused helper wrappers and cache accessors with no callers.
- Half-wired event dispatch plumbing that gives false confidence.

Success outcome:
- No dead symbols in hot paths.
- Clear TODO/deferred map for intentionally postponed capabilities.

### B. Duplicate Logic / Boilerplate

Candidates:
- Repetitive admin CRUD patterns (audit trail wrappers).
- Repeated per-cog adapter methods that can be centralized.
- Redundant utility helpers whose body is a one-line passthrough.

Success outcome:
- Fewer edit surfaces per change.
- Lower risk when evolving schema/rules.

### C. Stale Contracts / Misleading Config

Candidates:
- Stale constants and autocomplete values out of sync with model enums.
- Settings keys and UI labels that imply unsupported runtime behavior.
- Legacy route/docs references no longer used.
- Tenant-oriented wording that suggests multi-guild management in current-phase surfaces.

Success outcome:
- Developer and admin surfaces describe real runtime behavior.

### D. Guardrail Violations (Must Fix Before Expansion)

Candidates:
- check-then-act patterns on mutable state where atomic update is required.
- async functions doing blocking operations.
- retry loops without hard bounds in critical components.

Success outcome:
- Architecture shift does not inherit reliability debt.

---

## 4. Design Options

### Option A — Big-Bang Prune

Pros:
- Fast cleanup in one pass.

Cons:
- High regression risk.
- Hard to isolate failures.

### Option B — Phased Prune (Chosen)

Pros:
- Safer verification and rollback.
- Aligns with existing planning/tracker workflow.

Cons:
- Slower calendar time.

### Chosen Approach

> **Decision:** Option B — phased pruning with verification gates per phase.

---

## 5. Rollout Phases

### Phase 1 — Inventory + Confidence Labels

**Goal:** Produce a concrete removal list with confidence levels.

**Deliverables:**
- Candidate matrix: symbol/file, category, confidence (high/medium/low), replacement plan.
- Mark each candidate as delete/refactor/quarantine.

**Verification:**
- No candidate lacks ownership or decision status.

### Phase 2 — Dead Code Deletion (High Confidence)

**Goal:** Remove obviously unused or non-functional code with minimal blast radius.

**Deliverables:**
- Delete confirmed dead symbols and references.
- Keep deferral notes for postponed capabilities.

**Verification:**
- Tests/lint/type checks pass.
- No missing imports or broken API signatures.

### Phase 3 — Duplication Collapse

**Goal:** Replace repeated patterns with minimal shared abstractions.

**Deliverables:**
- Consolidate repetitive service/cog patterns.
- Preserve existing behavior and output contracts.

**Verification:**
- Functional parity checks for affected endpoints/commands.

### Phase 4 — Contract/Config Alignment

**Goal:** Remove stale or misleading config/metadata paths.

**Deliverables:**
- Align constants/settings/routes/docs to actual runtime capabilities.
- Remove deprecated references.

**Verification:**
- UI/API contract smoke checks pass.

### Phase 5 — Guardrail Hardening

**Goal:** Resolve key reliability violations before major architecture migration.

**Deliverables:**
- Atomic mutation fixes where needed.
- Async blocking I/O fixes.
- Retry bounds and timeout enforcement where missing.

**Verification:**
- Reliability-focused tests and targeted runtime checks pass.

---

## 6. Risks & Mitigations

| # | Risk | Mitigation |
|---|------|------------|
| 1 | Accidental behavior drift | Baseline snapshots + targeted parity checks per phase |
| 2 | Deleting code with hidden consumers | reference search + staged deletion + quick rollback path |
| 3 | Over-abstracting during dedup | enforce minimal abstraction rule |
| 4 | Scope creep into rewrite | pruning-only scope gate; defer feature work |

---

## 7. Success Criteria

- Redundant/dead paths removed or explicitly quarantined.
- Guardrail violations in critical paths addressed.
- Reduced complexity and lower edit surface for upcoming architecture changes.
- PLAN_event_capture_firewall phases can proceed without legacy drag.
