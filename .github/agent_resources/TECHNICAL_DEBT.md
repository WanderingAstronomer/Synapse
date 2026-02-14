# Technical Debt & Architectural Issues

**Last Updated:** 2026-02-14  
**Status:** All items resolved

---

## 🔴 Critical — Fix Before Production

### 1. `send_notify()` Transaction Race Condition

**Files:** `synapse/services/admin_service.py`, `synapse/services/settings_service.py`  
**Severity:** Medium (low impact at current scale, architecturally wrong)

**Issue:**  
NOTIFY is sent **after** transaction commit using a separate connection:

```python
session.commit()  # Transaction boundary closed
send_notify(engine, "channel_type_defaults")  # NEW connection → NOTIFY
```

**Race condition:**  
If the bot's PG LISTEN thread polls between commit and NOTIFY, it may reload stale data from the cache. The window is <1ms but exists.

**Fix:**  
Execute NOTIFY **within** the transaction before commit:

```python
# Before commit:
session.connection().execute(text(f"NOTIFY {NOTIFY_CHANNEL}, '{table_name}'"))
session.commit()  # NOTIFY fires atomically with commit
```

Or use SQLAlchemy event listeners:

```python
@event.listens_for(Session, "before_commit")
def send_pending_notifies(session):
    for table in session.info.get("pending_notifies", []):
        session.connection().execute(text(f"NOTIFY config_changed, '{table}'"))
```

**Impact if unfixed:**  
Cache invalidation lag of <1ms. At current scale, negligible. At 1000+ req/sec, visible staleness.

---

### 2. Missing Circuit Breaker on PG LISTEN Reconnection

**File:** `synapse/engine/cache.py:380-430` (`start_listener()`)  
**Severity:** High (runaway resource consumption if Postgres is down)

**Issue:**  
Listener thread retries forever with exponential backoff (max 60s). No max retry limit. If Postgres is down for hours, the thread burns CPU indefinitely.

**Fix:**  
Add max retry count with graceful degradation:

```python
MAX_RECONNECT_ATTEMPTS = 10

# In _listen_thread():
if attempt >= MAX_RECONNECT_ATTEMPTS:
    logger.critical("PG LISTEN exhausted retries. Cache invalidation disabled.")
    self._listener_failed = True
    break
```

Expose `_listener_failed` flag in `/health` endpoint.

**Impact if unfixed:**  
Infinite retry loop during prolonged DB outage. Wastes resources, obscures real failure.

---

### 3. No Pool Timeout — Indefinite Blocking on Exhaustion

**File:** `synapse/database/engine.py:50-75`  
**Severity:** Medium (unlikely at current scale, but a hang risk)

**Issue:**  
Connection pool has no timeout:

```python
pool_size=5, max_overflow=10  # 15 max connections
# Missing: pool_timeout
```

If all 15 connections are in use, the next request **blocks forever** waiting for a free connection.

**Fix:**  
Add explicit timeout:

```python
engine = create_engine(
    url,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
    pool_timeout=10,       # Fail after 10s instead of hanging
    pool_recycle=3600,
)
```

**Impact if unfixed:**  
Hung requests during connection storms. At <1 req/sec, impossible to hit. But it's a timebomb.

---

## 🟡 Medium — Pay Before Scaling

### 4. Detached Instance Access Risk After `session.expunge()`

**Files:** `synapse/services/admin_service.py`, `synapse/services/reward_service.py`  
**Severity:** Low (dormant footgun)

**Pattern:**  
Admin service functions expunge objects before returning:

```python
session.commit()
session.refresh(row)
session.expunge(row)  # Detach from session
return row            # Caller may access lazy-loaded attrs → DetachedInstanceError
```

**Issue:**  
If the caller tries to access a lazy-loaded relationship (e.g., `achievement.category`), SQLAlchemy raises `DetachedInstanceError`.

**Current status:**  
Not triggered — return values are mostly scalars, no lazy relationship access in current code.

**Fix options:**  
1. Eager load relationships before expunge: `session.refresh(row, ["category", "rarity"])`
2. Don't expunge — let caller manage lifecycle
3. Return Pydantic models instead of ORM objects

**Impact if unfixed:**  
Future feature that accesses relationships will crash. Add this to code review checklist.

---

### 5. No Graceful Shutdown Hook

**File:** `synapse/bot/core.py`, PG LISTEN thread  
**Severity:** Low (leaves orphaned connections)

**Issue:**  
PG LISTEN thread is `daemon=True`, killed on bot shutdown. May leave Postgres connection in `IDLE in transaction` state, holding locks.

**Fix:**  
Add shutdown hook in `SynapseBot.close()`:

```python
async def close(self):
    logger.info("Bot shutting down...")
    self.cache.stop_listener()  # Graceful thread exit
    await super().close()
```

In `ConfigCache`:

```python
def __init__(self, engine: Engine):
    self._shutdown_event = threading.Event()
    ...

def stop_listener(self):
    self._shutdown_event.set()
    self._listener_thread.join(timeout=5)

def start_listener(self):
    def _listen_thread():
        while not self._shutdown_event.is_set():
            # ... existing logic
            if self._shutdown_event.wait(timeout=5.0):
                break
```

**Impact if unfixed:**  
Orphaned Postgres connections on bot restart. No functional impact, but pollutes `pg_stat_activity`.

---

### 6. Unbounded Cooldown Dictionary Growth

**File:** `synapse/bot/cogs/social.py:34`  
**Severity:** Low (slow memory leak)

**Issue:**  
```python
self._cooldowns: dict[tuple[int, int], float] = {}
```

Never pruned. With 500 users × 50 channels = 25K max keys, it's 200KB → not critical. But it grows forever.

**Fix:**  
Add periodic cleanup task:

```python
@tasks.loop(minutes=5)
async def cleanup_cooldowns(self):
    now = time.time()
    cutoff = now - (2 * self.bot.cache.get_int("cooldown_seconds", 30))
    self._cooldowns = {k: v for k, v in self._cooldowns.items() if v > cutoff}
```

Or use `cachetools.TTLCache` instead of dict.

**Impact if unfixed:**  
~1MB memory growth over months. Negligible at current scale.

---

## 🟢 Nice-to-Have — Future-Proofing

### 7. No Health Check Endpoint

**Missing:** `/health` or `/readiness` in API  
**Why it matters:** Monitoring, Azure App Service health probes, uptime checks

**Should expose:**
- DB pool stats: `engine.pool.checkedout()`, `engine.pool.overflow()`
- PG LISTEN thread health: `cache._listener_healthy`
- Discord websocket status (if accessible)

**Example:**
```python
@router.get("/health")
def health(engine: Engine = Depends(get_engine), bot: SynapseBot = Depends(get_bot)):
    return {
        "status": "healthy",
        "db_pool_active": engine.pool.checkedout(),
        "db_pool_overflow": engine.pool.overflow(),
        "cache_listener_healthy": bot.cache._listener_healthy,
        "discord_ws_latency_ms": bot.latency * 1000 if bot.is_ready() else None,
    }
```

---

### 8. Inconsistent Structured Logging

**Files:** All cogs (`synapse/bot/cogs/*.py`)  
**Issue:** Exception logging varies:

```python
logger.exception("Error processing message %s from user %s", msg.id, user.id)
```

**Better:** Structured context for log aggregation (Sentry, Azure App Insights):

```python
logger.exception("Event processing failed", extra={
    "event_type": "message",
    "user_id": user.id,
    "message_id": msg.id,
})
```

**Impact:** Harder to query logs in production monitoring tools.

---

### 9. Unicode Handling in Logging

**Issue:** User-generated content (display names, message content) may contain Unicode that breaks log encoding.

**Fix:** Sanitize or configure logging with explicit UTF-8:

```python
logging.basicConfig(encoding='utf-8', ...)
```

Or sanitize before logging:
```python
safe_name = display_name.encode('ascii', 'replace').decode('ascii')
```

---

## What We DON'T Need (Given Current Scale)

At **1 server, <500 users, <1000 msg/day**:

❌ **Message queues** (Redis Streams, RabbitMQ) — synchronous processing is fine at 0.01 msg/sec  
❌ **Horizontal scaling** (multi-instance bot, Redis cache) — will never hit 2000+ servers  
❌ **Kubernetes** — Docker Compose is perfect for Azure Container Instances or single-VM deployment  
❌ **Distributed tracing** (OpenTelemetry) — entire stack fits on one node  
❌ **Prometheus metrics** — stdlib logging + Azure App Insights is sufficient  

---

## Prioritized Action Plan

### Do Now (1-2 hours)
1. ✅ Add `pool_timeout=10` to engine config
2. ✅ Add PG LISTEN circuit breaker (max 10 retries)
3. ✅ Add graceful shutdown hook in `bot.close()`

### Do Soon (half day)
4. ✅ Fix `send_notify()` race condition — execute NOTIFY before commit
5. ✅ Add `/health` endpoint for Azure health probes

### Do Later (when bored)
6. ✅ Add cooldown cleanup task
7. ✅ `expire_on_commit=False` for detached instance safety
8. ✅ Standardize structured logging
9. ✅ UTF-8 logging encoding

---

## Azure Deployment Notes

**Target:** Azure App Service / Azure Container Instances / Azure VM  
**Implications:**
- Azure App Insights → structured logging becomes more valuable
- Managed Database for PostgreSQL → connection pooling tuning matters
- Health probe endpoint → required for auto-restart on failure
- Secrets → use Azure Key Vault for JWT_SECRET, DATABASE_URL

**Recommended:**
- Enable Application Insights SDK for automatic telemetry
- Configure health check endpoint at `/health`
- Use Azure managed identity for DB auth (no passwords in env vars)
- Set up budget alerts (Postgres + App Service costs)
