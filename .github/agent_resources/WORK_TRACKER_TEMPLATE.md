# Work Tracker: [Feature / Change Title]

> **Plan:** Link to the planning doc (e.g. `PLAN_feature_name.md`)
> **Started:** YYYY-MM-DD
> **Last Updated:** YYYY-MM-DD
> **Overall Status:** Not Started | In Progress | Blocked | Complete

---

## Phase 1 — [Phase Title]

**Status:** Not Started | In Progress | Complete
**Branch/Commit:** _(fill in when work begins)_

| # | Task | Status | Notes |
|---|------|--------|-------|
| 1.1 | | ⬜ | |
| 1.2 | | ⬜ | |
| 1.3 | | ⬜ | |

**Verification:**
- [ ] Tests pass
- [ ] Lint clean
- [ ] Manual check: …

**Phase Notes:**
_Decisions made, surprises encountered, deviations from the plan._

---

## Phase 2 — [Phase Title]

**Status:** Not Started | In Progress | Complete
**Branch/Commit:**

| # | Task | Status | Notes |
|---|------|--------|-------|
| 2.1 | | ⬜ | |
| 2.2 | | ⬜ | |

**Verification:**
- [ ] Tests pass
- [ ] Lint clean
- [ ] Manual check: …

**Phase Notes:**

---

## Phase 3 — [Phase Title]

_(Add or remove phases to match the plan.)_

**Status:** Not Started | In Progress | Complete
**Branch/Commit:**

| # | Task | Status | Notes |
|---|------|--------|-------|
| 3.1 | | ⬜ | |
| 3.2 | | ⬜ | |

**Verification:**
- [ ] Tests pass
- [ ] Lint clean
- [ ] Manual check: …

**Phase Notes:**

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

_Append a timestamped line each time a phase completes or a significant decision is made._

```
YYYY-MM-DD  Phase 1 complete. All tests pass. Notes: …
YYYY-MM-DD  Phase 2 complete. …
```

---

## Final Checklist

- [ ] All phases complete
- [ ] Full test suite passes (`uv run pytest tests/ -v`)
- [ ] Lint clean (`uv run ruff check .`)
- [ ] Alembic migration generated (if schema changed)
- [ ] Tracker archived or removed from `agent_resources/`
