I've identified **5 significant discrepancies** across these artifacts:

## 1. **Postgres Password Mismatch** ⚠️ CRITICAL
| Artifact | Password |
|----------|----------|
| docker-compose.yml | `secret` |
| .env.example | `postgres` |
| config/default.json | `postgres` |
| README.md | `postgres` |

**Impact**: Docker Compose sets password to `secret`, but all other artifacts expect `postgres`. The app won't connect to the database.

---

## 2. **Redis Hostname Mismatch** ⚠️ CRITICAL
| Artifact | Hostname |
|----------|----------|
| docker-compose.yml | `redis` (service name) |
| config/default.json | `cache` |

**Impact**: config/default.json points to host `cache`, but the Docker service is named `redis`. Redis connections will fail.

---

## 3. **Log Level Inconsistency**
| Artifact | Level |
|----------|-------|
| .env.example | `debug` |
| config/default.json | `info` |

**Impact**: Different verbosity. Unclear which is intended for development/production.

---

## 4. **Session Secret Pattern**
| Artifact | Pattern |
|----------|---------|
| docker-compose.yml | Requires `SESSION_SECRET` env var (no default) |
| .env.example | `change-me-in-production` |
| config/default.json | `default-session-secret` (hardcoded) |

**Impact**: docker-compose will fail if `SESSION_SECRET` isn't set; inconsistent fallback behavior.

---

## 5. **Missing Redis Config in .env.example**
The `.env.example` doesn't show how the app consumes Redis (URL format), only individual host/port/password. This may not match how the app actually connects.

---

### Recommendation
Fix the **critical issues** first (postgres password and redis hostname), then align log levels and session secret patterns.