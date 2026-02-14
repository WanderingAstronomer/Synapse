# Planning: [Feature / Change Title]

> **Created:** YYYY-MM-DD
> **Status:** Draft | In Review | Approved | Superseded
> **Scope:** Brief one-liner describing what this plan covers.

---

## 1. Problem Statement

_What problem are we solving? Why now? Link to any issue or discussion._

## 2. Context & Discovery

_Summarize what you learned from reading code, docs, and tracing data flow.
Cite specific files/symbols so this section doubles as a reference cache._

| Area | Key Files | Notes |
|------|-----------|-------|
| | | |

## 3. Constraints & Guardrails

_Which project invariants apply? (e.g. pure engine, audit trail, idempotency).
List anything that limits the solution space._

- [ ] …

## 4. Design Options

_Present 2–3 approaches with tradeoffs. Mark the chosen one._

### Option A — …

**Summary:**
**Pros:**
**Cons:**

### Option B — …

**Summary:**
**Pros:**
**Cons:**

### Chosen Approach

> **Decision:** Option _X_ because …

## 5. Rollout Phases

_Break the work into ordered phases. Each phase should be independently
shippable and verifiable. Tests pass at the end of every phase._

### Phase 1 — …

**Goal:**
**Deliverables:**
- [ ] …
**Verification:** How do you know this phase is done?

### Phase 2 — …

**Goal:**
**Deliverables:**
- [ ] …
**Verification:**

### Phase 3 — …

_(Add or remove phases as needed.)_

## 6. Risks & Open Questions

| # | Risk / Question | Mitigation / Answer |
|---|----------------|---------------------|
| 1 | | |

## 7. Success Criteria

_How do we know the whole change is complete and correct?_

- [ ] All tests pass (`uv run pytest tests/ -v`)
- [ ] Lint clean (`uv run ruff check .`)
- [ ] No regressions in existing functionality
- [ ] …
