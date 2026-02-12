# Audit Remediation Tracker

**Source:** [AUDIT_REPORT.md](AUDIT_REPORT.md)  
**Started:** 2026-02-12  
**Last Updated:** 2026-02-12  

---

## Summary

| Status | Count |
|--------|-------|
| ✅ Done | 13 |
| ⏳ Deferred | 3 |
| ❌ Open | 0 |
| **Total** | **17** (1 not applicable) |

---

## Findings

| ID | Severity | Category | Finding | Status | Notes |
|----|----------|----------|---------|--------|-------|
| F-001 | Low | Versioning | Version mismatch (0.1.0 vs 1.0.0) | ✅ Done | Reconciled to `1.0.0` across pyproject.toml, `__init__.py`, CHANGELOG |
| F-002 | Info | Docs | `__init__.py` docstring references deleted `seed.py` | ✅ Done | Removed stale reference from package docstring |
| F-003 | **Medium** | Security | JWT_SECRET hardcoded fallback | ✅ Done | Removed fallback; added `_load_jwt_secret()` startup validator with min-length (32) and weak-secret blocklist. 6 new tests. |
| F-004 | **High** | Security | No admin rate limiting | ✅ Done | Added `AdminRateLimiter` (sliding window, 30 req/min) + `AdminRateLimitMiddleware`. 13 new tests. |
| F-005 | Medium | Security | `send_notify()` f-string SQL interpolation | ✅ Done | Added `ALLOWED_NOTIFY_TABLES` frozenset allowlist with `ValueError` on unknown tables. 6 new tests. |
| F-006 | Medium | Reliability | LISTEN/NOTIFY no reconnect | ✅ Done | Rewrote `start_listener()` with infinite reconnect loop, exponential backoff (1–60s) + jitter, `_listener_healthy` property. 2 new tests. |
| F-007 | Low | Dependency | `python-jose` unmaintained | ✅ Done | Replaced with `PyJWT[crypto]>=2.10.0`. Removed 9 transitive deps. |
| F-008 | Low | Dependency | `requests` unused | ✅ Done | Removed from dependencies. Confirmed no usage in source. |
| F-009 | Medium | Testing | No integration tests for API/services | ✅ Done | Added 25 API route tests + 10 reward service tests. |
| F-010 | Medium | Testing | Empty conftest.py | ✅ Done | Added shared fixtures: `db_engine`, `db_session`, `admin_token`, `auth_headers`. JSONB→TEXT SQLite compat. |
| F-011 | Low | Infrastructure | No CI/CD pipeline | ✅ Done | Created `.github/workflows/ci.yml` — `ruff check`, `ruff format --check`, `pytest` on push/PR. |
| F-012 | Low | Infrastructure | No Docker healthchecks | ✅ Done | Added healthchecks for bot, api, dashboard, and single-container services. Dashboard `depends_on` upgraded to `condition: service_healthy`. |
| F-013 | Info | Code Quality | Unused imports + line-length | ✅ Done | `ruff check --fix` resolved 31 issues. Manually fixed N806/E741/E501 in remediated files. |
| F-014 | Low | Deployment | CORS origins hardcoded to localhost | ⏳ Deferred | Intentional for local dev. Production deployment should override via env var — documented in deployment guide. |
| F-015 | Info | Architecture | OAuth state in-memory | ⏳ Deferred | Known single-replica limitation. Move to Redis/DB when scaling to multiple API replicas. |
| F-016 | Low | Docs | Table count 12 → 15 | ✅ Done | Updated docs, README, `__init__.py`, CHANGELOG, IMPLEMENTATION_DECISIONS.md. |
| F-017 | Info | Migration | `create_all()` vs Alembic | ⏳ Deferred | Alembic is configured. `create_all()` used for dev convenience. Production should use `alembic upgrade head`. |

---

## Test Coverage

| Metric | Before | After |
|--------|--------|-------|
| Total tests | 146 | 206 |
| API route tests | 0 | 25 |
| Reward service tests | 0 | 10 |
| Rate limit tests | 0 | 13 |
| JWT startup tests | 0 | 6 |
| Cache/NOTIFY tests | 4 | 12 |

---

## Dependency Changes

| Action | Package | Reason |
|--------|---------|--------|
| Removed | `python-jose[cryptography]` | Unmaintained (F-007) |
| Removed | `requests` | Unused (F-008) |
| Added | `PyJWT[crypto]>=2.10.0` | Active replacement for python-jose |

**Transitive deps removed:** charset-normalizer, ecdsa, pyasn1, rsa, six, types-requests, urllib3

---

## Files Created

| File | Purpose |
|------|---------|
| `.github/workflows/ci.yml` | GitHub Actions CI (lint + test) |
| `synapse/api/rate_limit.py` | Admin mutation rate limiter |
| `tests/test_jwt_startup.py` | JWT secret validation tests |
| `tests/test_rate_limit.py` | Rate limiting unit + integration tests |
| `tests/test_api_routes.py` | API route auth/integration tests |
| `tests/test_reward_service.py` | Reward service pipeline tests |
| `docs/AUDIT_REMEDIATION.md` | This tracker |

## Files Modified

| File | Changes |
|------|---------|
| `synapse/api/deps.py` | JWT secret validation, PyJWT migration |
| `synapse/api/auth.py` | PyJWT import |
| `synapse/api/main.py` | Rate limit middleware registration |
| `synapse/engine/cache.py` | NOTIFY allowlist, listener reconnect |
| `synapse/database/models.py` | (no changes — reference only) |
| `synapse/services/event_lake_writer.py` | Unused import removed by ruff |
| `pyproject.toml` | Version bump, dep changes |
| `synapse/__init__.py` | Version bump, docstring fix |
| `tests/conftest.py` | Shared fixtures, JSONB compat |
| `tests/test_cache.py` | NOTIFY + listener health tests |
| `tests/test_event_lake_services.py` | PyJWT migration |
| `docker-compose.yml` | Healthchecks for bot/api/dashboard |
| `CHANGELOG.md` | Audit remediation section, table count fix |
| `README.md` | Table count fix |
| `docs/IMPLEMENTATION_DECISIONS.md` | Table count fix |
| `.env.example` | JWT_SECRET guidance |
