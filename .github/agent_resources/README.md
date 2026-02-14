# Agent Resources

This folder is the agent's **working memory and toolkit** for multi-step tasks. Everything here is in `.gitignore`-safe territory — live documents are disposable; templates are version-controlled.

## What Goes Here

| Kind | Naming Convention | Example | Persists? |
|------|-------------------|---------|-----------|
| **Templates** | `*_TEMPLATE.md` | `PLANNING_TEMPLATE.md` | Yes (committed) |
| **Plans** | `PLAN_<feature>.md` | `PLAN_voice_rewards.md` | Until merged |
| **Work Trackers** | `TRACKER_<feature>.md` | `TRACKER_voice_rewards.md` | Until merged |
| **Cached Lookups** | `CACHE_<topic>.md` | `CACHE_model_columns.md` | Disposable |
| **Ad-hoc Scripts** | `script_<purpose>.py` | `script_backfill_stats.py` | Disposable |

## Templates

### `PLANNING_TEMPLATE.md`
Copy this to `PLAN_<feature>.md` to plan a multi-phase change. Covers problem statement, context discovery, design options, phased rollout, and success criteria.

### `WORK_TRACKER_TEMPLATE.md`
Copy this to `TRACKER_<feature>.md` to track execution of a plan. Phase-by-phase task tables with status icons and a timestamped completion log.

## Workflow

```
1. Copy PLANNING_TEMPLATE.md → PLAN_<feature>.md
2. Fill out the plan (context, options, phases)
3. Get approval or self-approve if unambiguous
4. Copy WORK_TRACKER_TEMPLATE.md → TRACKER_<feature>.md
5. Work phase-by-phase, update tracker after each task
6. On completion: archive or delete plan + tracker
```

## Cache Files

When the agent discovers information it may need again (e.g. a map of model columns, a list of all cog event handlers, multiplier resolution paths), it can write a `CACHE_<topic>.md` file here. These are **not committed** — they're scratch space to avoid redundant lookups across conversation turns or sessions.

## Cleanup

Plans and trackers should be removed once the work is merged. Cache files can be deleted at any time. Templates stay.
