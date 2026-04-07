Running the audit now across all 10 categories.

---

## Coherence Audit: 4-Artifact Infrastructure Review

### Step 1: Parts Inventory

| Artifact | Role |
|---|---|
| `docker-compose.yml` | Runtime environment definition |
| `.env.example` | Developer local config template |
| `config/default.json` | Application config defaults |
| `README.md` | Developer onboarding guide |

---

### Step 2: Checklist Results

---

#### 1. Factual Accuracy — **3 critical failures**

**A. DB password is `secret` in compose, `postgres` everywhere else**

| Artifact | DB Password |
|---|---|
| `docker-compose.yml` | `secret` (in `DATABASE_URL`) |
| `.env.example` | `postgres` |
| `config/default.json` | `postgres` |
| `README.md` | `postgres` (in credentials table and troubleshooting) |

The compose file uses `postgres://myapp_user:secret@postgres:5432/myapp`. All three other artifacts say the default password is `postgres`. The containerized app will fail to connect if it reads from `.env.example` or `config/default.json` instead of the compose-injected `DATABASE_URL`.

**B. Redis hostname is `cache` in config, `redis` in compose**

| Artifact | Redis hostname |
|---|---|
| `docker-compose.yml` | service named `redis` |
| `config/default.json` | `"url": "redis://cache:6379"` |

`cache` is not a defined service in `docker-compose.yml`. Inside the compose network, DNS resolves service names — `cache` will not resolve. This is a runtime connection failure.

**C. App host port is `8080` in compose, `3000` in README**

| Artifact | External port |
|---|---|
| `docker-compose.yml` | `"8080:3000"` — host port is 8080 |
| `README.md` | "Visit the application at **http://localhost:3000**" |

The container's internal port 3000 is mapped to host port 8080. The README sends developers to the wrong URL.

---

#### 2. Representational Completeness — **1 gap**

`LOG_LEVEL` appears in `.env.example` (`debug`) and `config/default.json` (`info`) but is absent from `docker-compose.yml`'s environment block. If the containerized app reads `LOG_LEVEL` from the environment (reasonable), it will silently fall through to the config default (`info`) rather than `debug`, which may confuse developers expecting verbose logs when running via compose.

---

#### 3. Voice Consistency — **clean**

README is consistently addressed to a developer onboarding to local setup. No audience shifts.

---

#### 4. Naming Coherence — **1 failure**

The Redis service is called `redis` in compose but `cache` in `config/default.json`. These names are used in different contexts (service DNS vs. config URL host) but refer to the same thing and must match inside the compose network.

---

#### 5. Framing Precision — **1 mismatch**

README step 2 says "Copy the example environment file" (`cp .env.example .env`) as if that's what configures the app. But `docker-compose.yml` injects its own hardcoded environment variables (`DATABASE_URL`, `REDIS_URL`, `PORT`, `NODE_ENV`) directly into the container — bypassing `.env` entirely for the containerized app. The README implies `.env` is the primary config mechanism; compose overrides it. This framing will mislead developers who edit `.env` expecting it to affect the running container.

---

#### 6. Origin Fidelity — **clean**

No narrative drift detected. The artifacts don't contain "why this exists" claims.

---

#### 7. Tone Calibration — **minor**

README troubleshooting says: *"verify that `.env` has the correct `DB_PASSWORD`"* — but per the framing issue above, the compose app doesn't read `DB_PASSWORD` from `.env`; it uses the hardcoded `DATABASE_URL`. This advice will send developers on a fruitless chase.

---

#### 8. Category Accuracy — **1 structural inconsistency**

The DB connection is modeled differently across artifacts:

| Artifact | Approach |
|---|---|
| `docker-compose.yml` | Single `DATABASE_URL` DSN |
| `.env.example` | Individual `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` |
| `config/default.json` | Individual `host`, `port`, `name`, `user`, `password` fields |

The application reads one of these at runtime — not all three. There's no indication which pattern is authoritative. If the app uses `DATABASE_URL`, then the individual fields in `.env.example` and `config/default.json` are either unused or duplicated by a separate parsing step. If the app uses individual fields, `DATABASE_URL` in compose is irrelevant. Either way, one side is wrong.

---

#### 9. Cross-Reference Redundancy — **clean**

No pure copy-paste redundancy. Each artifact serves a distinct role and adds value the others don't.

---

#### 10. Scope Discipline — **clean**

All content is about this project. No ecosystem evangelism or platform explanation.

---

### Step 3: Findings Summary

| # | Finding | Severity | Location |
|---|---|---|---|
| 1 | DB password: `secret` (compose) vs `postgres` (everywhere else) | **Critical** | `docker-compose.yml` ↔ `.env.example`, `config/default.json`, `README.md` |
| 2 | Redis hostname: `cache` (config) vs `redis` (compose service name) | **Critical** | `config/default.json` ↔ `docker-compose.yml` |
| 3 | App URL: `localhost:3000` (README) vs host port `8080` (compose) | **Critical** | `README.md` ↔ `docker-compose.yml` |
| 4 | DB connection model: DSN vs individual fields — one set is unused | **High** | `docker-compose.yml` ↔ `.env.example` + `config/default.json` |
| 5 | `.env` framing: README implies it configures the container; compose bypasses it | **High** | `README.md` ↔ `docker-compose.yml` |
| 6 | Troubleshooting advice points to `DB_PASSWORD` in `.env`, which compose ignores | **Medium** | `README.md` ↔ `docker-compose.yml` |
| 7 | `LOG_LEVEL` missing from compose environment block | **Low** | `docker-compose.yml` ↔ `.env.example` |
| 8 | Session secret defaults differ: `default-session-secret` vs `change-me-in-production` | **Low** | `config/default.json` ↔ `.env.example` |

---

### Recommended Fixes (in priority order)

1. **Unify the DB password**: pick `secret` or `postgres` and apply it to all four artifacts.
2. **Fix Redis hostname in `config/default.json`**: change `cache` → `redis` to match the compose service name.
3. **Fix README URL**: change `localhost:3000` → `localhost:8080` to match the compose port mapping.
4. **Resolve connection model**: decide whether the app uses `DATABASE_URL` or individual fields; remove or comment out the unused pattern.
5. **Clarify `.env` scope in README**: note that `.env.example` is for local (non-Docker) development; compose supplies its own environment for containerized runs.
6. **Fix troubleshooting tip**: remove the advice to check `DB_PASSWORD` in `.env` for the Docker case.