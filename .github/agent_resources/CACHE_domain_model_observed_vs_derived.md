# Cache: Domain Model Split — Observed vs Derived Data

> **Created:** 2026-02-18
> **Purpose:** Lock in terminology and boundaries so architecture and UI stay aligned.

## Core Distinction

### 1) Observed Telemetry (Discord-Origin)

Definition:
- Event data that originates from Discord interactions.
- Captured as close to source as possible.
- Immutable and append-only once written.

Examples:
- Message create/reply metadata
- Reaction add/remove
- Thread/forum create/reply metadata
- Voice join/leave/move state transitions
- Member join/leave
- Poll-related interactions (when exposed)
- Sticker/emoji/gift usage signals (when exposed)

Properties:
- Source-of-truth for historical replay.
- Should include normalization and schema version markers.
- Should avoid irreversible interpretation at write-time.

### 2) Derived Economy Data (Synapse-Origin)

Definition:
- State computed from observed telemetry + rules/config snapshots.
- Mutable and optimized for product features.

Examples:
- XP, gold, level, stars
- Achievements earned
- Leaderboards
- User progression stats
- Admin-facing performance projections

Properties:
- Must be replayable from source telemetry.
- Can be rebuilt when rules change.
- Never considered source-of-truth over telemetry.

## Invariants

- Never mutate observed telemetry to “fix” derived state.
- Always adjust rules/projections and recompute when needed.
- Keep a clear boundary between ingestion contracts and reward contracts.

## Suggested Vocabulary

Use these terms consistently:
- Observed Telemetry
- Interaction Envelope
- Rule Evaluation
- Derived Projection
- Baseline Default Rules
- Rule Snapshot Version

Avoid ambiguous terms:
- “raw rewards data” (mixes observed and derived semantics)
- “master XP log” (XP is derived, not observed)

## Why this matters

This split directly supports the platform goals:
- Maximum capture flexibility
- Strong auditability and replay
- Admin-defined modular reward systems
- Safe iteration without data corruption of source events
