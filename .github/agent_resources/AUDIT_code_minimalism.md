# Code Minimalism Audit — Synapse

**Date**: 2026-02-14  
**Scope**: Full codebase — engine, services, bot/cogs, API, database/config, tests, infrastructure

---

## Executive Summary

The Synapse codebase is well-structured overall, with a clear separation of concerns between engine (pure calc), services (I/O), and bot/API layers. The main areas of waste fall into five themes:

| Theme | Estimated LOC Savings | Count |
|-------|----------------------|-------|
| **Dead code / YAGNI** (stubs, unused functions, phantom features) | ~200 | 22 |
| **Duplication** (copy-paste across cogs, CRUD boilerplate, test fixtures) | ~500 | 14 |
| **Stale data** (constants out of sync, misleading metrics) | ~30 | 5 |
| **Guardrail violations** (project's own rules not followed) | — | 3 |
| **Minor style / readability** | ~30 | 15 |

**Top 5 highest-impact items:**

1. **`admin_service.py` CRUD dedup** — ~400 lines of identical audit-trail boilerplate across 6+ entity types (Services #5)
2. **Dead event dispatch infrastructure** — `_dispatch_event` in `cache.py` is never called; event notification is half-wired (Engine #12)
3. **Quest system is fully dead** — model, enum, base XP entries, no consumer anywhere (DB #1)  
4. **`/buy-coffee` race condition** — check-then-act pattern violates project's own guardrails (Bot #7)
5. **Stale `ACHIEVEMENT_REQUIREMENT_TYPES`** — autocomplete serves wrong values to admins (DB #5)

---

## Layer 1: Engine (`synapse/engine/`)

### Issue E1 — `llm_quality_modifier()` stub
- **Location**: [quality.py](synapse/engine/quality.py) — `llm_quality_modifier()`
- **Assessment**: YAGNI
- **The "Why"**: Unconditionally returns `1.0`. Called in `calculate_reward()`, where multiplying by 1.0 is a no-op. Docstring says "DEFERRED per D05-02" — speculative infrastructure.
- **Pragmatic Suggestion**: Delete the function. Remove the import and `_llm` variable from `calculate_reward()`. A `# TODO` comment is sufficient as a bookmark.
- **Critical Question**: Is there any roadmap milestone for the LLM quality modifier, or is this aspirational?

### Issue E2 — Always-false achievement handlers
- **Location**: [achievements.py](synapse/engine/achievements.py) — `_check_member_tenure()`, `_check_invite_count()`
- **Assessment**: YAGNI
- **The "Why"**: Both unconditionally `return False` but are registered in `TRIGGER_HANDLERS`. On every achievement check, they're dispatched and return nothing. The backing infrastructure (join date tracking, invite tracking) doesn't exist.
- **Pragmatic Suggestion**: Remove both functions and their `TRIGGER_HANDLERS` entries. The `TriggerType` enum values can stay (schema concern).
- **Critical Question**: Are admins creating `MEMBER_TENURE` or `INVITE_COUNT` templates? If so, behavior is unchanged (still returns False), but removal makes the skip explicit.

### Issue E3 — Trivial `resolve_multipliers()` wrapper
- **Location**: [reward.py](synapse/engine/reward.py) — `resolve_multipliers()`
- **Assessment**: Over-Engineering
- **The "Why"**: Entire body is `return cache.resolve_multipliers(channel_id, event_type.value)`. Only called internally. Adds indirection for a `.value` call.
- **Pragmatic Suggestion**: Inline into `calculate_reward()`. Remove from `__all__`.
- **Critical Question**: Was this intended as a public API? Grep shows no external callers.

### Issue E4 — Bloated `__all__` re-exports in `reward.py`
- **Location**: [reward.py](synapse/engine/reward.py) — `__all__`
- **Assessment**: Bloat
- **The "Why"**: Re-exports `AntiGamingTracker`, `apply_anti_gaming_stars/xp`, `apply_xp_caps`, `calculate_quality_modifier`, `get_default_tracker`. No production code imports these from `reward.py`. Tests do, but only because the re-exports exist.
- **Pragmatic Suggestion**: Remove re-exports. Keep only `RewardResult` and `calculate_reward`. Update test imports.
- **Critical Question**: Any downstream consumers relying on these re-exports?

### Issue E5 — Unused `get_diminishing_factor()`
- **Location**: [anti_gaming.py](synapse/engine/anti_gaming.py) — `get_diminishing_factor()`
- **Assessment**: YAGNI
- **The "Why"**: Tested but never called in production. The actual diminishing logic uses a flat `if unique > 10:` branch. This implements a `1/(1+count)` formula that isn't wired into any pipeline. Also mutates tracker state via side effects.
- **Pragmatic Suggestion**: Delete the function and its tests.
- **Critical Question**: Was this meant to replace the `if unique > 10` branch but never wired in?

### Issue E6 — Unused `get_default_tracker()`
- **Location**: [anti_gaming.py](synapse/engine/anti_gaming.py) — `get_default_tracker()`
- **Assessment**: Over-Engineering
- **The "Why"**: Accessor for module-level singleton. Never called in production — `apply_anti_gaming_stars()` already defaults to the singleton internally.
- **Pragmatic Suggestion**: Delete the function. The module-level instance is fine as-is.
- **Critical Question**: Any planned external consumer?

### Issue E7 — Unused `get_channel_type()` in ConfigCache
- **Location**: [cache.py](synapse/engine/cache.py) — `get_channel_type()`
- **Assessment**: YAGNI
- **The "Why"**: Zero callers in the entire codebase.
- **Pragmatic Suggestion**: Delete it. 3-line method to re-add if needed.
- **Critical Question**: Written for a feature that was implemented differently?

### Issue E8 — Unused `get_str()` in ConfigCache
- **Location**: [cache.py](synapse/engine/cache.py) — `get_str()`
- **Assessment**: YAGNI
- **The "Why"**: Zero callers. Added for symmetry with `get_int/get_float/get_bool` but nobody needs it.
- **Pragmatic Suggestion**: Delete. Re-add when a caller exists.
- **Critical Question**: Any string-typed settings planned?

### Issue E9 — Over-complex `get_bool()` string parsing
- **Location**: [cache.py](synapse/engine/cache.py) — `get_bool()`
- **Assessment**: Over-Engineering
- **The "Why"**: Multi-branch parser for `"true"`, `"1"`, `"yes"`. But settings are parsed via `json.loads()` — JSON booleans are already Python `bool`. The string branches defend against hand-written `"\"true\""` JSON, which is a data entry error.
- **Pragmatic Suggestion**: Simplify to `return bool(self.get_setting(key, default))`.
- **Critical Question**: Are any settings stored as JSON string `"true"` rather than JSON boolean `true`?

### Issue E10 — Duplicated threshold defaults in `quality.py`
- **Location**: [quality.py](synapse/engine/quality.py) — `calculate_quality_modifier()`
- **Assessment**: Bloat
- **The "Why"**: Full `if cache is not None` / `else` fork duplicates every threshold as a variable assignment. If a default changes, update two places.
- **Pragmatic Suggestion**: Eliminate the branch. Define defaults as module-level constants and reference them in both the cache call defaults and the else path. Or always use cache with a mock in tests.
- **Critical Question**: Is there a real use case for calling without a cache in production?

### Issue E11 — Misleading `InteractionType` re-export in `events.py`
- **Location**: [events.py](synapse/engine/events.py) — `__all__`
- **Assessment**: Bloat
- **The "Why"**: `InteractionType` is defined in `models.py`, not here. Re-export creates a second import path. No code imports it from here.
- **Pragmatic Suggestion**: Remove from `__all__`.
- **Critical Question**: Any code importing `InteractionType` from `synapse.engine.events`?

### Issue E12 — Dead event dispatch infrastructure ⚠️ HIGH
- **Location**: [cache.py](synapse/engine/cache.py) — `_dispatch_event()`, `register_event_callback()`, `_event_callbacks`, `_event_loop`
- **Assessment**: YAGNI / Potential Bug
- **The "Why"**: `_dispatch_event()` is defined but never called. The LISTEN thread only handles `NOTIFY_CHANNEL` (config changes), not `EVENT_NOTIFY_CHANNEL`. `send_event_notify()` sends NOTIFYs on `synapse_events`, but nothing LISTENs on that channel. The entire event callback infrastructure is half-wired — gives a **false sense** of working cross-service event dispatch.
- **Pragmatic Suggestion**: Either wire it properly (add `LISTEN synapse_events;` to the listener thread) or remove the dead dispatch infrastructure until it's needed.
- **Critical Question**: Is the event dispatch actually working in production, or is this half-implemented?

### Issue E13 — Deferred `time`/`random` imports
- **Location**: [cache.py](synapse/engine/cache.py) — `start_listener()` / `_listen_thread()`
- **Assessment**: Bloat
- **The "Why"**: `time` and `random` are stdlib modules importing in microseconds. Deferring them provides no measurable benefit and hides imports.
- **Pragmatic Suggestion**: Move to module-level imports.
- **Critical Question**: Any intentional reason for deferring these?

---

## Layer 2: Services (`synapse/services/`)

### Issue S1 — Dead `_setting_exists()` in setup_service
- **Location**: [setup_service.py](synapse/services/setup_service.py) — `_setting_exists()`
- **Assessment**: Bloat
- **The "Why"**: Defined but never called anywhere.
- **Pragmatic Suggestion**: Delete.
- **Critical Question**: Leftover from an earlier bootstrap flow?

### Issue S2 — Dead `get_user_preferences()` in reward_service
- **Location**: [reward_service.py](synapse/services/reward_service.py) — `get_user_preferences()` + unused `UserPreferences` import
- **Assessment**: Bloat
- **The "Why"**: Never called. The `UserPreferences` import exists solely for this dead function.
- **Pragmatic Suggestion**: Delete both.
- **Critical Question**: Was this moved to `announcement_service._load_preferences()` and never cleaned up?

### Issue S3 — Redundant `import discord.abc`
- **Location**: [announcement_service.py](synapse/services/announcement_service.py) — line 18
- **Assessment**: Bloat
- **The "Why"**: `Messageable` is already imported from `discord.abc`. The bare import exists for `discord.abc.Snowflake` in annotations.
- **Pragmatic Suggestion**: Import `Snowflake` directly: `from discord.abc import Messageable, Snowflake`. Drop `import discord.abc`.
- **Critical Question**: Reason `Snowflake` wasn't imported alongside `Messageable`?

### Issue S4 — Dead `get_settings_by_category()`
- **Location**: [settings_service.py](synapse/services/settings_service.py) — `get_settings_by_category()`
- **Assessment**: YAGNI
- **The "Why"**: Never called anywhere — no route, no cog, no test.
- **Pragmatic Suggestion**: Delete. 5-line function to recreate.
- **Critical Question**: Planned dashboard settings panel that would use category filtering?

### Issue S5 — `admin_service.py` CRUD boilerplate ⚠️ HIGH
- **Location**: [admin_service.py](synapse/services/admin_service.py) — ~757 lines
- **Assessment**: Over-Engineering
- **The "Why"**: 6+ nearly identical CRUD groups with the exact same pattern: session open → read before → mutate → flush → dict → log → commit → notify → refresh → expunge → return. ~80-100 lines per entity, only the model class and field list differ. ~450 lines of boilerplate. If the audit pattern ever changes, you must change it in 18+ places.
- **Pragmatic Suggestion**: Extract generic helpers:
  ```python
  def _audited_upsert(engine, model_cls, table_name, lookup, values, actor_id, ip_address=None): ...
  def _audited_delete(engine, model_cls, table_name, pk, actor_id, ip_address=None): ...
  ```
  Each CRUD function becomes a 3–5 line delegate. Estimated reduction: ~400 lines.
- **Critical Question**: Has the audit pattern ever diverged between entities, or has it always been identical?

### Issue S6 — `_make_id()` wrapper in layout_service
- **Location**: [layout_service.py](synapse/services/layout_service.py) — `_make_id()`
- **Assessment**: Over-Engineering
- **The "Why"**: One-line wrapper around `str(uuid.uuid4())`. Called 3 times. The function name doesn't communicate anything the raw call doesn't.
- **Pragmatic Suggestion**: Inline `str(uuid.uuid4())` at call sites.
- **Critical Question**: Plan to switch ID format (ULID, nanoid)?

### Issue S7 — Per-upload `ensure_upload_dir()` call
- **Location**: [upload_service.py](synapse/services/upload_service.py) — `save_upload()`
- **Assessment**: Over-Engineering
- **The "Why"**: Called on every upload but also at API startup. The startup call is sufficient.
- **Pragmatic Suggestion**: Remove from `save_upload()`. Keep the startup call.
- **Critical Question**: Deployment scenario where uploads directory gets deleted at runtime?

### Issue S8 — `EventType` is not a StrEnum
- **Location**: [event_lake_writer.py](synapse/services/event_lake_writer.py) — `EventType`
- **Assessment**: Over-Engineering / Inconsistency
- **The "Why"**: Plain class with string constants, not `StrEnum`. Project convention (per copilot-instructions) is `StrEnum` for serialized values.
- **Pragmatic Suggestion**: Convert to `class EventType(StrEnum)`.
- **Critical Question**: Intentionally kept as plain class for performance, or oversight?

### Issue S9 — Inaccurate `emoji_count` metric
- **Location**: [event_lake_writer.py](synapse/services/event_lake_writer.py) — `extract_message_metadata()`
- **Assessment**: Bloat
- **The "Why"**: `content.count(":") // 2` counts all colons, not emoji. URLs (`https://`), timestamps (`10:30`) produce false positives. This metric feeds into quality scoring downstream.
- **Pragmatic Suggestion**: Use a regex for Discord custom emoji or drop the field if no consumer relies on it.
- **Critical Question**: Is `emoji_count` consumed by any dashboard widget, achievement trigger, or analytics query?

### Issue S10 — Deferred inner imports in announcement_service
- **Location**: [announcement_service.py](synapse/services/announcement_service.py) — `_load_preferences()`, `_load_achievement_template()`
- **Assessment**: Over-Engineering
- **The "Why"**: Inner `from synapse.database.engine import get_session` despite `run_db` already being imported at module level (proving no circular dep).
- **Pragmatic Suggestion**: Move to module-level imports.
- **Critical Question**: Historical circular import, or copy-paste artifact?

### Issue S11 — Dialect-branching upsert in channel_service
- **Location**: [channel_service.py](synapse/services/channel_service.py) — dialect-branching upsert
- **Assessment**: Over-Engineering
- **The "Why"**: Checks `engine.dialect.name` and branches between PostgreSQL and SQLite implementations. Production always runs PostgreSQL. SQLite is only for tests. Dual-dialect logic pollutes production code.
- **Pragmatic Suggestion**: Use only PostgreSQL dialect. Handle SQLite compat in test fixtures (like the existing JSONB hack).
- **Critical Question**: Any other services branching on dialect? If only this one, it's an inconsistency.

### Issue S12 — Stale doc references
- **Location**: [backfill_service.py](synapse/services/backfill_service.py), [reconciliation_service.py](synapse/services/reconciliation_service.py) — module docstrings
- **Assessment**: Bloat
- **The "Why"**: Reference "PLAN_OF_ATTACK_P4.md Task #12/#13" which doesn't exist in the repo.
- **Pragmatic Suggestion**: Update to reference `EVENT_LAKE.md` or remove task references.
- **Critical Question**: Is the plan doc archived somewhere?

### Issue S13 — `save_upload()` is async but does sync I/O ⚠️ GUARDRAIL
- **Location**: [upload_service.py](synapse/services/upload_service.py) — `save_upload()`
- **Assessment**: Guardrail Violation
- **The "Why"**: Declared `async def` but calls `dest.write_bytes(content)` — synchronous file I/O. Per project guardrails: "No blocking I/O in `async def` functions — P0 failure mode."
- **Pragmatic Suggestion**: Either make it a regular `def` and call via `asyncio.to_thread()`, or use `aiofiles`.
- **Critical Question**: Has this caused event loop stalls under load?

### Issue S14 — `get_setting()` in settings_service returns detached ORM object
- **Location**: [settings_service.py](synapse/services/settings_service.py) — `get_setting()`
- **Assessment**: Bloat / Potential Bug
- **The "Why"**: Returns ORM object from closed session without `expunge()`, unlike `get_all_settings()` which does expunge. Inconsistency = latent `DetachedInstanceError`.
- **Pragmatic Suggestion**: Expunge before returning, or return a dict/value.
- **Critical Question**: Is this function ever called where the returned ORM object's attributes are accessed?

---

## Layer 3: Bot / Cogs (`synapse/bot/`)

### Issue B1 — Duplicated `_process()` method across 4 cogs
- **Location**: [social.py](synapse/bot/cogs/social.py), [reactions.py](synapse/bot/cogs/reactions.py), [voice.py](synapse/bot/cogs/voice.py), [threads.py](synapse/bot/cogs/threads.py)
- **Assessment**: Bloat
- **The "Why"**: Four identical 4-line methods passing `self.bot.engine`, `self.bot.cache`, `event`, `display_name` to `process_event`.
- **Pragmatic Suggestion**: Add to `SynapseBot`: `def process_event_sync(self, event, name): return process_event(self.engine, self.cache, event, name)`. Or just inline.
- **Critical Question**: Were per-cog wrappers intended to diverge in the future?

### Issue B2 — Repeated guild-lookup pattern in core.py
- **Location**: [core.py](synapse/bot/core.py) — 4 methods using `for g in self.guilds: if g.id != self.cfg.guild_id: continue`
- **Assessment**: Bloat
- **The "Why"**: `self.get_guild(self.cfg.guild_id)` does the same thing in one call. Repeated loop adds ~12 lines of scaffolding.
- **Pragmatic Suggestion**: Replace with `guild = self.get_guild(self.cfg.guild_id); if guild is None: return`.
- **Critical Question**: Any plan for multi-guild support?

### Issue B3 — Verbose `_audit_text_channel_access()` logging
- **Location**: [core.py](synapse/bot/core.py) — `_audit_text_channel_access()`
- **Assessment**: YAGNI
- **The "Why"**: Logs every readable and blocked channel at INFO on every startup. For 50+ channels, this is log noise. Information is immediately stale.
- **Pragmatic Suggestion**: Downgrade per-channel lists to DEBUG. Keep only summary counts at INFO.
- **Critical Question**: Has this audit ever caught a real permission issue in production?

### Issue B4 — INFO-level gateway event logging
- **Location**: [social.py](synapse/bot/cogs/social.py), [reactions.py](synapse/bot/cogs/reactions.py), [voice.py](synapse/bot/cogs/voice.py), [threads.py](synapse/bot/cogs/threads.py)
- **Assessment**: Bloat
- **The "Why"**: Every gateway message/reaction/voice event is logged at INFO. On an active server → hundreds of lines/minute. These are DEBUG traces.
- **Pragmatic Suggestion**: Downgrade all "Gateway event:" log lines to `logger.debug(...)`.
- **Critical Question**: Are these consumed by monitoring/alerting?

### Issue B5 — Broken log format string in social.py ⚠️ BUG
- **Location**: [social.py](synapse/bot/cogs/social.py) — message result logging
- **Assessment**: Bloat / Bug
- **The "Why"**: `"[Level %d%s]"` uses `result.new_level if result.leveled_up else result.xp` — when `leveled_up` is False and `new_level` is None, it falls through to `result.xp`, producing nonsensical logs like `"[Level 5230]"`.
- **Pragmatic Suggestion**: Fix to conditionally include level-up info.
- **Critical Question**: Has anyone noticed this bad output?

### Issue B6 — Dead `if True else {}` in meta.py
- **Location**: [meta.py](synapse/bot/cogs/meta.py) — `_get_profile()`
- **Assessment**: Bloat
- **The "Why"**: `if True else {}` — the else branch can never execute. Development artifact.
- **Pragmatic Suggestion**: Remove `if True else {}`, keep only the dict literal.
- **Critical Question**: Originally a feature flag? If so, make it a real setting.

### Issue B7 — Check-then-act race in `/buy-coffee` ⚠️ GUARDRAIL
- **Location**: [meta.py](synapse/bot/cogs/meta.py) — `_buy_coffee()`
- **Assessment**: Guardrail Violation
- **The "Why"**: `if user.gold < cost: ... user.gold -= cost` — classic race condition the project's own instructions explicitly prohibit. Two concurrent commands can overdraw.
- **Pragmatic Suggestion**: Replace with atomic SQL: `UPDATE users SET gold = gold - :cost WHERE id = :id AND gold >= :cost`.
- **Critical Question**: Is `/buy-coffee` used in production, or is it a placeholder?

### Issue B8 — Discarded return value from `_write_lake_event`
- **Location**: [social.py](synapse/bot/cogs/social.py) — `_write_lake_event`
- **Assessment**: Bloat
- **The "Why"**: Returns `bool` but caller discards it. Either check/log failures or change return type to `None`.
- **Pragmatic Suggestion**: Change to `-> None` or log failures.
- **Critical Question**: Does `write_message_create` return False on any meaningful failure?

### Issue B9 — Inaccurate `emoji_count` in social.py metadata
- **Location**: [social.py](synapse/bot/cogs/social.py) — message metadata
- **Assessment**: Bloat
- **The "Why"**: `message.content.count(":")` counts all colons, not emoji. Feeds into quality scoring where it penalizes non-emoji colons.
- **Pragmatic Suggestion**: Use a regex for Discord custom emoji or drop the field.
- **Critical Question**: Is the quality engine intended to penalize emoji-heavy messages?

### Issue B10 — Expensive unique reactor counting on every reaction
- **Location**: [reactions.py](synapse/bot/cogs/reactions.py) — unique reactor counting
- **Assessment**: Over-Engineering
- **The "Why"**: For every `REACTION_RECEIVED`, fetches message then iterates **every reaction** and **every user** (via `async for user in reaction.users()`). 50 reactions × 30 users = 50 API calls. This count is only used for anti-gaming metadata.
- **Pragmatic Suggestion**: Use `sum(r.count for r in message.reactions)` as a rough total, or batch the exact count in a periodic task.
- **Critical Question**: Does anti-gaming actually use `unique_reactor_count` to make decisions?

### Issue B11 — Misleading configurable `voice_tick_minutes`
- **Location**: [voice.py](synapse/bot/cogs/voice.py) — `@tasks.loop(minutes=10)` vs `voice_tick_minutes` setting
- **Assessment**: YAGNI
- **The "Why"**: Loop interval is hardcoded at 10 minutes, but reads `voice_tick_minutes` from settings. Changing the setting won't change the loop frequency — creates illusion of configurability.
- **Pragmatic Suggestion**: Either remove the configurable setting or dynamically adjust via `self.voice_tick_loop.change_interval(minutes=minutes)`.
- **Critical Question**: Is configurable voice tick frequency a real requirement?

### Issue B12 — Repetitive channel discovery in core.py
- **Location**: [core.py](synapse/bot/core.py) — `_auto_discover_channels()`
- **Assessment**: Bloat
- **The "Why"**: Five consecutive blocks iterate different channel types with nearly identical `ChannelInfo(...)` construction (~40 lines of structural repetition).
- **Pragmatic Suggestion**: Use a mapping: `channel_sources = [(g.categories, "category"), (g.text_channels, "text"), ...]`. Reduces ~40 lines to ~10.
- **Critical Question**: Do any channel types need special handling beyond the generic pattern?

### Issue B13 — `tasks.py` types `bot` as `commands.Bot` instead of `SynapseBot`
- **Location**: [tasks.py](synapse/bot/cogs/tasks.py)
- **Assessment**: Bloat / Type Safety
- **The "Why"**: Every other cog types `bot` as `SynapseBot`, but this one uses `commands.Bot`. Mypy won't catch invalid attribute accesses.
- **Pragmatic Suggestion**: Change to `SynapseBot`.
- **Critical Question**: N/A — type safety gap.

### Issue B14 — Deferred `announcement_service` imports in core.py
- **Location**: [core.py](synapse/bot/core.py) — `on_ready()`, `close()`
- **Assessment**: Bloat
- **The "Why"**: `start_queue` and `stop_queue` imported inside method bodies, but `announcement_service` is already imported at module level in every cog. No actual circular dependency.
- **Pragmatic Suggestion**: Move to top-level imports.
- **Critical Question**: Is there an actual circular import chain?

---

## Layer 4: API (`synapse/api/`)

### Issue A1 — Unused `engine` parameter in `get_current_admin`
- **Location**: [deps.py](synapse/api/deps.py) — `get_current_admin()`
- **Assessment**: Bloat
- **The "Why"**: `engine: Engine = Depends(get_engine)` declared but never used. Triggers needless DI resolution.
- **Pragmatic Suggestion**: Remove the parameter.
- **Critical Question**: Plan for DB-based token revocation?

### Issue A2 — Duplicate `get_setting` / `_setting_val` logic
- **Location**: [deps.py](synapse/api/deps.py) — `get_setting()`; [public.py](synapse/api/routes/public.py) — `_setting_val()`
- **Assessment**: Bloat / Duplication
- **The "Why"**: Two functions doing the same thing (parse JSON from a Setting row) with different interfaces.
- **Pragmatic Suggestion**: Consolidate into `settings_service`. Remove from deps.py.
- **Critical Question**: Reason `get_setting` lives in DI module instead of the service?

### Issue A3 — Two separate `httpx.AsyncClient` contexts in OAuth callback
- **Location**: [auth.py](synapse/api/auth.py) — `callback()`
- **Assessment**: Bloat
- **The "Why"**: Two context managers for three sequential requests. One would do.
- **Pragmatic Suggestion**: Merge into one `async with httpx.AsyncClient(timeout=10) as client:`.
- **Critical Question**: None — straightforward fix.

### Issue A4 — Missing timeouts on Discord API calls ⚠️ GUARDRAIL
- **Location**: [auth.py](synapse/api/auth.py) — all `httpx` calls
- **Assessment**: Guardrail Violation
- **The "Why"**: Project guardrails mandate "Always set explicit timeouts on HTTP requests." All Discord API calls have no timeout. A Discord outage hangs the callback indefinitely.
- **Pragmatic Suggestion**: Add `timeout=10` to the client constructor.
- **Critical Question**: Desired timeout policy for external Discord API calls?

### Issue A5 — Dual in-memory + DB mode in `AdminRateLimiter`
- **Location**: [rate_limit.py](synapse/api/rate_limit.py) — `AdminRateLimiter`
- **Assessment**: Over-Engineering / YAGNI
- **The "Why"**: Two complete code paths: in-memory (unused in production) and DB-backed. Production always uses DB. In-memory exists only for tests. Doubles the class surface area.
- **Pragmatic Suggestion**: Remove in-memory branch. Tests can use the SQLite-backed engine from conftest. Class shrinks by ~40%.
- **Critical Question**: Is the in-memory fallback used anywhere in production?

### Issue A6 — Double JWT decode (middleware + dependency)
- **Location**: [rate_limit.py](synapse/api/rate_limit.py) — `_extract_admin_id()`
- **Assessment**: Over-Engineering / Duplication
- **The "Why"**: Middleware does its own JWT decode with the same secret/algorithm as `get_current_admin()`. Full second decode of the same token on every admin mutation.
- **Pragmatic Suggestion**: Move rate limiting into a dependency that chains after `get_current_admin`, sharing the decoded payload.
- **Critical Question**: Is middleware the right layer for rate limiting?

### Issue A7 — Triple DB round-trip for rate limiting
- **Location**: [rate_limit.py](synapse/api/rate_limit.py) — middleware
- **Assessment**: Over-Engineering
- **The "Why"**: check → record → check again (for response headers). Three `to_thread` calls per admin mutation.
- **Pragmatic Suggestion**: `record()` could return updated counts. No need for the second `check()`.
- **Critical Question**: Are the `X-RateLimit-Remaining` headers consumed by the dashboard?

### Issue A8 — Dead `warnings` list in `resolve_names()`
- **Location**: [admin.py](synapse/api/routes/admin.py) — `resolve_names()`
- **Assessment**: Bloat
- **The "Why"**: `warnings: list[str] = []` initialized, checked, but never appended to. Dead scaffolding.
- **Pragmatic Suggestion**: Remove the variable and `if warnings:` block.
- **Critical Question**: Was this meant to catch invalid IDs?

### Issue A9 — Local `sqlfunc` import in `get_audit_log()`
- **Location**: [admin.py](synapse/api/routes/admin.py) — `get_audit_log()`
- **Assessment**: Bloat
- **The "Why"**: `from sqlalchemy import func as sqlfunc` inside function body. No conflict with module-level imports.
- **Pragmatic Suggestion**: Move to module-level imports as `func`.
- **Critical Question**: None — trivial cleanup.

### Issue A10 — Triple upload endpoints
- **Location**: [admin.py](synapse/api/routes/admin.py), [layouts.py](synapse/api/routes/layouts.py)
- **Assessment**: Bloat / Duplication
- **The "Why"**: Three file upload endpoints (`/admin/uploads`, `/admin/badges/upload`, `/admin/media`) all doing the same thing.
- **Pragmatic Suggestion**: Consolidate. Badge endpoint can use `/admin/uploads` or `/admin/media`.
- **Critical Question**: Does the dashboard actually call `/admin/badges/upload` separately?

### Issue A11 — Hardcoded trigger metadata endpoint
- **Location**: [admin.py](synapse/api/routes/admin.py) — `list_trigger_types()`
- **Assessment**: Over-Engineering / YAGNI
- **The "Why"**: Large hardcoded dict with config schemas, UI labels. Two entries marked "(Coming soon)". UI metadata baked into the API. Can drift from `TriggerType` enum.
- **Pragmatic Suggestion**: Derive from `TriggerType` enum. Consider moving labels/schemas to the dashboard as static config.
- **Critical Question**: Is this metadata consumed for dynamic form rendering? Could it live in the frontend?

### Issue A12 — `serve_upload()` handler reimplements `StaticFiles`
- **Location**: [main.py](synapse/api/main.py) — `serve_upload()`
- **Assessment**: Over-Engineering
- **The "Why"**: Custom route handler with local imports that reimplements what `StaticFiles` middleware does out of the box.
- **Pragmatic Suggestion**: Replace with `app.mount("/api/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")`.
- **Critical Question**: Are the custom `Cache-Control` headers critical?

### Issue A13 — `admin.py` is 1234 lines
- **Location**: [admin.py](synapse/api/routes/admin.py)
- **Assessment**: Over-Engineering
- **The "Why"**: 10+ domains in one file. Finding anything requires scrolling through ~40 endpoints.
- **Pragmatic Suggestion**: Split into `routes/achievements.py`, `routes/settings.py`, `routes/media.py`, `routes/setup.py`. Each ~150-250 lines.
- **Critical Question**: Deliberate reason for one file, or organic growth?

---

## Layer 5: Database / Config

### Issue D1 — Dead `Quest` system ⚠️ HIGH
- **Location**: [models.py](synapse/database/models.py) — `Quest` model, `QuestStatus` enum; [events.py](synapse/engine/events.py) — `QUEST_COMPLETE` entries
- **Assessment**: YAGNI
- **The "Why"**: `Quest` model is never instantiated, queried, or imported outside models.py. `QuestStatus` has one variant (`OPEN`). No cog creates quests, no service processes them, no API exposes them. Dead table, dead enum, dead XP entries.
- **Pragmatic Suggestion**: Delete `Quest`, `QuestStatus`, `QUEST_COMPLETE`. Generate Alembic migration to drop the table.
- **Critical Question**: Any plan to ship quests in the next 2 releases?

### Issue D2 — Dead `RARITY_COLORS_HEX` constant
- **Location**: [constants.py](synapse/constants.py) — `RARITY_COLORS_HEX`
- **Assessment**: YAGNI
- **The "Why"**: Never imported. V2 achievement system stores colors per-guild in DB.
- **Pragmatic Suggestion**: Delete.
- **Critical Question**: Any planned feature using hardcoded colors?

### Issue D3 — Dead `RARITY_LABELS` constant
- **Location**: [constants.py](synapse/constants.py) — `RARITY_LABELS`
- **Assessment**: YAGNI
- **The "Why"**: Never imported. V2 system uses per-guild names from DB.
- **Pragmatic Suggestion**: Delete.
- **Critical Question**: Same as D2.

### Issue D4 — Dead `ACHIEVEMENT_CATEGORIES` constant
- **Location**: [constants.py](synapse/constants.py) — `ACHIEVEMENT_CATEGORIES`
- **Assessment**: YAGNI
- **The "Why"**: Never imported. `AchievementCategory` DB model replaced it. Actively misleading.
- **Pragmatic Suggestion**: Delete.
- **Critical Question**: Any test relying on this?

### Issue D5 — Stale `ACHIEVEMENT_REQUIREMENT_TYPES` ⚠️ HIGH
- **Location**: [constants.py](synapse/constants.py) — `ACHIEVEMENT_REQUIREMENT_TYPES`
- **Assessment**: Bloat / Stale
- **The "Why"**: Used in admin cog autocomplete but values **don't match** `TriggerType` enum. Offers `counter_threshold` and `custom` which aren't trigger types, omits 6 real types. Admins see wrong/stale autocomplete options.
- **Pragmatic Suggestion**: Delete. Replace admin cog autocomplete with `[t.value for t in TriggerType]`.
- **Critical Question**: Was the drift intentional?

### Issue D6 — Dead `LOG_LEVELS` constant (Python side)
- **Location**: [constants.py](synapse/constants.py) — `LOG_LEVELS`
- **Assessment**: YAGNI
- **The "Why"**: Never imported by Python code. Dashboard has its own TypeScript copy.
- **Pragmatic Suggestion**: Delete from Python.
- **Critical Question**: Plan to use it Python-side?

### Issue D7 — Unused `dashboard_port` config
- **Location**: [config.py](synapse/config.py) — `SynapseConfig.dashboard_port`
- **Assessment**: YAGNI
- **The "Why"**: Loaded from YAML but never read by Python code at runtime. Actual port is Docker Compose + SvelteKit config.
- **Pragmatic Suggestion**: Remove from dataclass or make optional with default.
- **Critical Question**: Plan for Python backend to use this port?

### Issue D8 — `DEFAULT_SETTINGS` / seeding in engine.py (misplaced)
- **Location**: [engine.py](synapse/database/engine.py) — `DEFAULT_SETTINGS`, `_seed_default_settings()`, `init_db()`
- **Assessment**: Over-Engineering / Misplaced
- **The "Why"**: 55% of engine.py (90 lines) is application-layer settings seeding mixed into the DB infrastructure module. `init_db()` also calls `create_all()`, redundant with Alembic.
- **Pragmatic Suggestion**: Extract into `synapse/database/seed.py`. Consider removing `create_all()` or adding a dev-only comment.
- **Critical Question**: In production, do you run `alembic upgrade head` before starting, or does `init_db()` serve as primary schema creator?

### Issue D9 — Triple `load_dotenv()` calls
- **Location**: [engine.py](synapse/database/engine.py) — `create_db_engine()`
- **Assessment**: Bloat
- **The "Why"**: `load_dotenv()` called in bot/__main__.py, api/main.py, AND `create_db_engine()`. Entrypoints already call it first. Having it in the factory is a hidden side effect.
- **Pragmatic Suggestion**: Remove from `create_db_engine()`.
- **Critical Question**: Any standalone script calling `create_db_engine()` without an entrypoint?

### Issue D10 — Dead `ACHIEVEMENT_RARITIES` constant
- **Location**: [constants.py](synapse/constants.py) — `ACHIEVEMENT_RARITIES`
- **Assessment**: Bloat
- **The "Why"**: Hardcoded list used in admin cog autocomplete, but V2 system has per-guild `AchievementRarity` DB rows. Autocomplete diverges from actual guild config.
- **Pragmatic Suggestion**: Replace autocomplete with dynamic query from `ConfigCache`. Delete constant.
- **Critical Question**: Is static autocomplete intentional?

---

## Layer 6: Tests & Infrastructure

### Issue T1 — Dead `auth_headers` fixture in conftest
- **Location**: [conftest.py](tests/conftest.py) — `auth_headers`
- **Assessment**: YAGNI
- **The "Why"**: Defined but never used by any test.
- **Pragmatic Suggestion**: Delete.
- **Critical Question**: Missing test that should use this?

### Issue T2 — `admin_token` fixture defined 4 times
- **Location**: [conftest.py](tests/conftest.py), [test_api_routes.py](tests/test_api_routes.py), [test_event_lake_services.py](tests/test_event_lake_services.py), [test_rate_limit.py](tests/test_rate_limit.py)
- **Assessment**: Bloat
- **The "Why"**: Conftest version is shadowed in all 3 test files. JWT construction logic duplicated 4 times.
- **Pragmatic Suggestion**: Create a `make_admin_token(sub=...)` factory fixture in conftest.
- **Critical Question**: Do tests actually care about the `sub` value?

### Issue T3 — `engine` fixture duplicated
- **Location**: [test_reward_service.py](tests/test_reward_service.py), [test_bootstrap.py](tests/test_bootstrap.py)
- **Assessment**: Bloat
- **The "Why"**: Both define their own `engine` fixture identical to conftest's `db_engine`.
- **Pragmatic Suggestion**: Use `db_engine` from conftest.
- **Critical Question**: Does `test_bootstrap.py` intentionally test with partial schema?

### Issue T4 — `client` fixture triplicated
- **Location**: [test_api_routes.py](tests/test_api_routes.py), [test_event_lake_services.py](tests/test_event_lake_services.py), [test_rate_limit.py](tests/test_rate_limit.py)
- **Assessment**: Bloat
- **The "Why"**: FastAPI `TestClient` fixture defined 3 times. Two are identical.
- **Pragmatic Suggestion**: Move basic `TestClient` to conftest. Keep specialized version in rate_limit tests.
- **Critical Question**: Is `raise_server_exceptions=False` the desired default?

### Issue T5 — Cache test boilerplate (40 duplicate lines)
- **Location**: [test_cache.py](tests/test_cache.py) — `TestNotifyRouting`
- **Assessment**: Bloat
- **The "Why"**: Every test repeats 8 lines of manual `ConfigCache.__new__` construction.
- **Pragmatic Suggestion**: Extract into a fixture. Use `@pytest.mark.parametrize` for the 4 happy-path tests.
- **Critical Question**: Is manual `__new__` actually needed, or can you just use `ConfigCache(MagicMock())`?

### Issue T6 — Anti-gaming tests duplicated across 2 files
- **Location**: [test_anti_gaming.py](tests/test_anti_gaming.py), [test_reward_engine.py](tests/test_reward_engine.py)
- **Assessment**: Bloat
- **The "Why"**: Both test the same functions with overlapping assertions. Two files to update if behavior changes.
- **Pragmatic Suggestion**: Consolidate into one file.
- **Critical Question**: Intentionally testing at different abstraction levels?

### Issue T7 — Custom `run_async()` helper instead of `asyncio.run()`
- **Location**: [test_announcements.py](tests/test_announcements.py) — `run_async()`
- **Assessment**: Over-Engineering
- **The "Why"**: Creates a new event loop per call (deprecated). `asyncio.run()` is simpler and correct.
- **Pragmatic Suggestion**: Replace with `asyncio.run()` or add `pytest-asyncio`.
- **Critical Question**: Is avoiding `pytest-asyncio` intentional?

### Issue T8 — `TestStorageEstimate` tests pure arithmetic
- **Location**: [test_event_lake_services.py](tests/test_event_lake_services.py) — `TestStorageEstimate`
- **Assessment**: YAGNI
- **The "Why"**: Tests `1000 * 90 * 340 == 1000 * 90 * 340`. Does not test application code.
- **Pragmatic Suggestion**: Delete.
- **Critical Question**: Does any app code use a `340` constant?

### Issue T9 — Bot healthcheck is a no-op
- **Location**: [docker-compose.yml](docker-compose.yml) — bot healthcheck
- **Assessment**: Over-Engineering
- **The "Why"**: Tests module import, not that the bot is running. Passes even after a crash.
- **Pragmatic Suggestion**: Remove or implement a real probe (PID file, heartbeat).
- **Critical Question**: Has this ever caught a real outage?

### Issue T10 — Fragile uv Python symlink copy in Dockerfile
- **Location**: [Dockerfile](Dockerfile) — `COPY --from=builder /root/.local/share/uv/python`
- **Assessment**: Over-Engineering
- **The "Why"**: Depends on uv's internal directory structure, which could change between versions.
- **Pragmatic Suggestion**: Use `uv sync --python-preference system` to avoid copying uv's managed Python.
- **Critical Question**: Has this broken during a uv upgrade?

---

## Prioritized Action Plan

### Tier 1 — Fix Now (bugs + guardrail violations)
| Issue | What | Impact |
|-------|------|--------|
| B7 | Fix `/buy-coffee` check-then-act race condition | Data integrity |
| A4 | Add timeouts to Discord OAuth httpx calls | Availability |
| S13 | Fix async-but-blocking `save_upload()` | Event loop safety |
| B5 | Fix broken log format string | Observability |
| E12 | Resolve dead event dispatch infrastructure | Correctness / dead code |

### Tier 2 — High Value (significant LOC reduction)
| Issue | What | Est. LOC Saved |
|-------|------|----------------|
| S5 | Dedup admin_service CRUD boilerplate | ~400 |
| D1 | Remove dead Quest system | ~50 + migration |
| A13 | Split 1234-line admin.py | 0 (restructure) |
| D5 | Fix stale autocomplete values | ~10 |
| A5 | Remove dual-mode rate limiter | ~80 |

### Tier 3 — Cleanup (dead code, unused functions)
| Issues | Count | Est. LOC Saved |
|--------|-------|----------------|
| D2-D4, D6, D10 | 5 dead constants | ~25 |
| E1-E2, E5-E8, S1-S2, S4 | 9 dead functions/stubs | ~60 |
| T1-T6 | 6 test fixture dedup items | ~100 |
| E3-E4, E11, E13, S3, S6, S10, S12 | 9 minor cleanups | ~40 |

### Tier 4 — Consider (architecture discussions)
| Issue | What | Decision Needed |
|-------|------|-----------------|
| B10 | Expensive unique reactor counting | Rate limit budget analysis |
| B11 | Fake configurable voice tick | Remove setting or make it real |
| A6-A7 | Rate limiter middleware vs dependency | Architecture decision |
| A11-A12 | Hardcoded metadata + custom StaticFiles | Frontend ownership discussion |

**Total estimated removable lines: ~750-800**
