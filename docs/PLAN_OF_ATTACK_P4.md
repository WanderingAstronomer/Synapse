# Plan of Attack: Event Lake Implementation (P4)

> Based on the Discord Gateway Events & API Capabilities Audit (Feb 2026)
> and three strategic design conversations.

---

## 1. Audit Key Takeaways

### What We Learned

The audit confirms the dual-layer architecture we designed for:

- **Gateway** = ephemeral real-time stream (capture or lose it)
- **REST API** = historical/static data (fetch on demand, rate-limited)

The Vacuum Principle holds.  The audit also provides concrete numbers
we were missing: payload sizes, volume estimates, rate limit budgets,
and the exact intent requirements for every event we care about.

### The Three Privileged Intents

| Intent | What It Unlocks | Do We Need It? | Verdict |
|--------|----------------|----------------|---------|
| **MESSAGE_CONTENT** | Message text, embeds, attachments in MESSAGE_CREATE | **Yes** — Quality modifiers need message length, code blocks, links | **Required.  Must justify at verification.** |
| **GUILD_MEMBERS** | Member join/leave/update events, full member list cache | **Yes** — Membership tracking, member count metrics, milestone evaluation | **Required.  Standard justification.** |
| **GUILD_PRESENCES** | Online/offline/idle/DND status, activity (game, Spotify) | **No** — Highest bandwidth intent, floods WebSocket, no engagement value | **Skip.  Not worth the cost.** |

This means Synapse needs **2 of 3 privileged intents**.  The
MESSAGE_CONTENT justification is the harder sell — Discord frequently
denies "generic logging."  Our case: **quality-weighted engagement
scoring** (code block detection, link enrichment, length analysis for
educational content).  This is a specific, compelling use case, not
generic logging.

### The 75/100 Server Thresholds

- **75 servers:** Verification unlocks.  Apply immediately.
- **100 servers:** Hard cap.  No new invites, privileged intents revoked
  if unverified.

**Action item:** Document the verification justification in advance so
it's ready when we hit 75 servers.

---

## 2. Intent Configuration (Definitive)

```python
intents = discord.Intents.default()

# Standard (no approval needed)
# GUILDS              — channel/thread/role lifecycle (included in default)
# GUILD_MESSAGES      — message create/update/delete (included in default)
# GUILD_MESSAGE_REACTIONS — reaction add/remove (included in default)
# GUILD_VOICE_STATES  — voice join/leave/move (included in default)

# Privileged (must enable in Developer Portal + justify at verification)
intents.message_content = True   # Quality analysis: length, code, links
intents.members = True           # Join/leave tracking, member cache

# Explicitly disabled
intents.presences = False        # Too expensive, no engagement value
```

---

## 3. Events We Capture (Final List)

### Tier 1: Core Engagement (Always Captured)

| Our Event Type | Gateway Event | Intent | Payload We Store |
|---------------|---------------|--------|-----------------|
| `message_create` | MESSAGE_CREATE | GUILD_MESSAGES + MESSAGE_CONTENT | `{length, has_code_block, has_link, has_attachment, emoji_count, is_reply, reply_to_user_id}` |
| `reaction_add` | MESSAGE_REACTION_ADD | GUILD_MESSAGE_REACTIONS | `{emoji_name, message_id, message_author_id}` |
| `reaction_remove` | MESSAGE_REACTION_REMOVE | GUILD_MESSAGE_REACTIONS | `{emoji_name, message_id}` |
| `thread_create` | THREAD_CREATE | GUILDS | `{parent_channel_id, name}` |

### Tier 2: Presence & Voice (Toggleable)

| Our Event Type | Gateway Event | Intent | Payload We Store |
|---------------|---------------|--------|-----------------|
| `voice_join` | VOICE_STATE_UPDATE | GUILD_VOICE_STATES | `{channel_id, self_mute, self_deaf}` |
| `voice_leave` | VOICE_STATE_UPDATE | GUILD_VOICE_STATES | `{channel_id, duration_seconds}` |
| `voice_move` | VOICE_STATE_UPDATE | GUILD_VOICE_STATES | `{from_channel_id, to_channel_id}` |

### Tier 3: Membership (Toggleable, Privileged)

| Our Event Type | Gateway Event | Intent | Payload We Store |
|---------------|---------------|--------|-----------------|
| `member_join` | GUILD_MEMBER_ADD | GUILD_MEMBERS | `{joined_at}` |
| `member_leave` | GUILD_MEMBER_REMOVE | GUILD_MEMBERS | `{}` |

### Derived Events (Computed, Not Captured)

| Derived Event | Source | Logic |
|---------------|--------|-------|
| `voice_session` | `voice_join` + `voice_leave` | Session with duration, channel, idle detection |
| `active_day` | Any user event | One per user per UTC day (streak tracking) |

### Explicitly NOT Captured

| Event | Why |
|-------|-----|
| PRESENCE_UPDATE | Bandwidth bomb.  No engagement signal.  Skip. |
| MESSAGE_UPDATE | Edits have low engagement signal.  Fetchable via REST if needed. |
| MESSAGE_DELETE | No content in payload.  Useful for moderation, not engagement. |
| TYPING_START | Noise.  No engagement signal. |
| GUILD_AUDIT_LOG_ENTRY_CREATE | Discord retains 45 days.  Fetch via REST if needed. |

---

## 4. Voice Tracking Design

This is where the audit really pays off.  The VOICE_STATE_UPDATE event
gives us exactly what we need:

```
Fields: guild_id, channel_id, user_id, session_id,
        deaf, mute, self_deaf, self_mute, self_stream, self_video
```

### What We Track (Connection + Duration Only)

- **Who** connected to **which** voice channel
- **How long** they stayed (derived from join→leave timestamps)
- **Were they idle?** (`self_mute AND self_deaf` = likely AFK)

### What We Do NOT Track

- Audio content (recording/transcription)
- What they said
- Screen share content
- Who they talked to (no way to know without audio processing)

### The AFK Channel Solution

**Problem:** Members park in voice channels while AFK (muted + deafened),
inflating voice engagement metrics.

**Solution:** AFK Channel Exclusion — a configurable list of voice
channel IDs that are excluded from engagement tracking.

Implementation approach:
1. Admin designates an "AFK voice channel" in Discord server settings
   (Discord already has this built-in — `guild.afk_channel`).
2. Synapse reads `guild.afk_channel_id` from the Guild object (available
   via REST or GUILD_CREATE).
3. `voice_join` events where `channel_id == afk_channel_id` are stored
   in the Event Lake (for data completeness) but **tagged as
   `is_afk: true`** in the payload.
4. Rules Engine conditions can filter on `is_afk`:
   - Default rules: `voice.is_afk == false` (skip AFK sessions)
   - Analytics still show AFK time separately (not hidden, just segmented)

**Bonus design:** An admin can also **manually designate additional
"non-tracked" voice channels** beyond Discord's built-in AFK channel
(e.g., a "Music Bot" lounge where people park to listen).  This is a
simple array in the Region/Zone configuration.

### DAVE Protocol Implications (2026)

The audit flags Discord's upcoming DAVE (Discord Audio/Video End-to-End
Encryption) protocol.  This makes audio recording/transcription
significantly harder for bots.  Our decision to focus on connection
metadata rather than audio content is **future-proof** — DAVE doesn't
affect VOICE_STATE_UPDATE events at all.

---

## 5. Storage Budget

The audit provides concrete numbers (§7.2, calibrated for 500 members):

### Per-Event Sizes

| Event | Raw Gateway Payload | Our Stored Row (after extraction) |
|-------|--------------------|---------------------------------|
| MESSAGE_CREATE | ~480 bytes + content length | ~200 bytes (metadata only, no content stored) |
| MESSAGE_REACTION_ADD | ~180 bytes | ~120 bytes |
| VOICE_STATE_UPDATE | ~250 bytes | ~150 bytes |
| THREAD_CREATE | ~400 bytes | ~150 bytes |
| GUILD_MEMBER_ADD | ~300 bytes | ~100 bytes |

### Volume Projection (500-Member Server, Moderately Active)

| Event Type | Est. Daily Volume | Est. Daily Storage |
|------------|------------------|-------------------|
| Messages | 14,400 (10/min) | 2.8 MB |
| Reactions | ~7,200 (0.5× messages) | 0.8 MB |
| Voice state changes | ~500 | 0.07 MB |
| Thread creates | ~50 | 0.007 MB |
| Member joins/leaves | ~10 | 0.001 MB |
| **Daily total** | **~22,160** | **~3.7 MB** |
| **Monthly total** | **~665,000** | **~111 MB** |
| **90-day retention** | **~2M rows** | **~333 MB** |

For a 500-member server, **90-day retention keeps the Event Lake under
350 MB**.  Well within a standard managed PostgreSQL tier.

### Counter Cache Overhead

The `event_counters` table is tiny: one row per (user, event_type, zone,
period).  For 500 members × 5 event types × 3 zones × 3 periods =
~22,500 rows at ~50 bytes each = **~1.1 MB**.  Negligible.

---

## 6. discord.py Implementation Notes

### Use Raw Events for Reliability

The audit's §6.1–6.2 (Cache Dependency Problem) is directly relevant.
Standard discord.py events like `on_message_delete` silently drop events
when the message isn't in cache.

**Rule:** Always use raw event listeners (`on_raw_reaction_add`,
`on_raw_message_delete`) for Event Lake capture.  Standard events
(`on_message`) are fine for cached data enrichment (e.g., reading
message content for quality analysis), but raw events are the
**reliability backbone**.

### Hot Path Warning

`on_socket_raw_receive` sits on the event loop's hot path.  We should
**never** use it for Event Lake writes.  All database writes must use
`asyncio.to_thread()` (our existing pattern) to avoid blocking the
heartbeat.

### Rate Limit Awareness

REST API backfill (member lists, channel metadata) must respect:
- **50 requests/second** global cap
- **Per-route buckets** (X-RateLimit-Bucket header)
- **10,000 invalid requests in 10 min = Cloudflare IP ban** (critical)

discord.py's built-in rate limiter handles most of this, but our custom REST
calls (if any) must implement exponential backoff on 429 responses.

---

## 7. What We DON'T Store (The Anti-Surveillance Commitment)

Critical for the Transparency principle (01_VISION §1.4, Principle 4):

| Data | Why We Don't Store It |
|------|----------------------|
| Message content/text | Quality metrics are extracted in-memory; raw text is discarded |
| Who reacted with what specific emoji | We store emoji_name for analytics, but don't build user↔emoji profiles |
| Online/offline status | GUILD_PRESENCES deliberately disabled |
| What game someone is playing | GUILD_PRESENCES deliberately disabled |
| Voice audio | Only connection metadata; DAVE makes this impossible anyway |
| DM content | DIRECT_MESSAGES intent not enabled |
| Deleted message content | MESSAGE_DELETE payload doesn't contain content; we don't pre-cache it |

The Data Sources panel in the admin dashboard should display this
commitment prominently.

---

## 8. Verification Justification (Draft)

For when we hit 75 servers:

### MESSAGE_CONTENT Justification

> Synapse is a community engagement platform that uses message metadata
> to calculate quality-weighted engagement scores.  We analyze message
> properties (length, presence of code blocks, links, and attachments)
> to reward high-quality contributions more than low-effort messages.
>
> We do NOT store, log, or persist message content.  Quality metrics are
> extracted in-memory and only numerical scores are saved.  This is not
> a logging bot — it is an engagement analytics system.
>
> Specific features requiring MESSAGE_CONTENT:
> - Code block detection (×1.4 quality multiplier for technical content)
> - Link enrichment detection (×1.25 for resource sharing)
> - Length-based quality scoring (longer = more effort)
> - Emoji spam detection (anti-gaming measure)

### GUILD_MEMBERS Justification

> Synapse tracks community growth by recording member join/leave events
> to calculate retention metrics, display activity trends, and trigger
> welcome-related engagement rules.  The member list is used to populate
> leaderboards and profile displays with current member information.

---

## 9. Implementation Sequence (P4 Breakdown)

### P4.1: Schema + Bot Capture (Week 1–2)

1. Create `event_lake` table with indexes
2. Create `event_counters` table
3. Add `voice_sessions` in-memory tracker (join timestamp cache)
4. Wire `on_message` → Event Lake (message metadata extraction)
5. Wire `on_raw_reaction_add` / `on_raw_reaction_remove` → Event Lake
6. Wire `on_thread_create` → Event Lake
7. Wire `on_voice_state_update` → Event Lake (join/leave/move derivation)
8. Wire `on_member_join` / `on_member_remove` → Event Lake
9. AFK channel detection (`guild.afk_channel_id` + manual exclusion list)
10. Update intent configuration in bot startup

### P4.2: Counter Cache + Retention (Week 2–3)

11. Transactional counter updates on Event Lake insert
12. Retention cleanup job (scheduled, configurable TTL)
13. Back-populate counters from existing `activity_log` (bridge)

### P4.3: API + Dashboard (Week 3–4)

14. Event Lake read endpoints (paginated, filtered by type/user/date)
15. Data Sources toggle endpoints (CRUD)
16. Event volume health metrics endpoint
17. Dashboard: Data Sources configuration page
18. Dashboard: Event Lake health widget (volume, lag, storage estimate)
19. Storage estimate calculator (based on audit numbers)

### P4.4: Testing + Validation (Week 4)

20. Integration tests: each event type captured correctly
21. Test AFK channel exclusion
22. Test retention cleanup
23. Test counter accuracy vs. raw event count
24. Parallel run: old `activity_log` + new Event Lake side by side
25. Performance benchmark: event capture latency < 50ms p99

---

## 10. Open Questions (For Us to Decide)

1. **Do we store message content for moderation log replay?**
   Current answer: No.  We extract metadata in-memory and discard text.
   If a community wants moderation logging, that's a different bot.

2. **Do we capture MESSAGE_UPDATE (edits)?**
   Current answer: No.  Low engagement signal.  Could revisit if
   communities want "edit tracking" as a feature.

3. **Do we capture INTERACTION_CREATE (slash commands)?**
   Interesting: no intent needed.  We could track bot command usage
   for analytics ("which commands are popular?").  Low priority but
   free — no intent cost, no verification burden.

4. **Should the counter cache be a materialized view or a maintained
   table?**
   Current answer: Maintained table (transactional updates).
   Materialized views have refresh lag.  But if counter drift becomes
   a problem, we could add periodic reconciliation.

5. **Do we keep the old `activity_log` table permanently or deprecate
   it?**
   Proposed: Keep it running in P4 (parallel write).  Deprecate in P6
   when the Rules Engine fully replaces the Reward Engine.  Drop in P7.

---

## 11. Doc Updates Needed

| Document | Update | Scope |
|----------|--------|-------|
| **03B_DATA_LAKE.md** | Complete rewrite — remove all [PENDING RESEARCH], fill with audit data | Major |
| **02_ARCHITECTURE.md** | Add intent configuration section, update data flow for raw events | Minor |
| **09_ROADMAP.md** | Expand P4 checklist with audit-informed tasks | Minor |
| **08_DEPLOYMENT.md** | Add storage estimates, intent configuration for Developer Portal | Minor (deferred) |
