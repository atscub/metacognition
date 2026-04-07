# Task: cohere-03 — Docker Compose vs app config vs README

## Prompt
Review the following four artifacts for consistency. Identify any discrepancies between them.

## Artifact 1: docker-compose.yml

```yaml
version: "3.8"

services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: myapp
      POSTGRES_USER: myapp_user
      POSTGRES_PASSWORD: secret
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U myapp_user"]
      interval: 5s
      timeout: 3s
      retries: 5

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    command: redis-server --requirepass redispass123

  app:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "8080:3000"
    environment:
      NODE_ENV: production
      DATABASE_URL: postgres://myapp_user:secret@postgres:5432/myapp
      REDIS_URL: redis://:redispass123@redis:6379
      PORT: 3000
      SESSION_SECRET: ${SESSION_SECRET}
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_started

volumes:
  pgdata:
```

## Artifact 2: .env.example

```dotenv
# Database
DB_HOST=localhost
DB_PORT=5432
DB_NAME=myapp
DB_USER=myapp_user
DB_PASSWORD=postgres

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=redispass123

# App
PORT=3000
NODE_ENV=development
SESSION_SECRET=change-me-in-production

# Logging
LOG_LEVEL=debug
```

## Artifact 3: Application Config (config/default.json)

```json
{
  "server": {
    "port": 3000,
    "host": "0.0.0.0"
  },
  "database": {
    "host": "localhost",
    "port": 5432,
    "name": "myapp",
    "user": "myapp_user",
    "password": "postgres",
    "pool": {
      "min": 2,
      "max": 10
    }
  },
  "redis": {
    "url": "redis://cache:6379",
    "password": "redispass123",
    "keyPrefix": "myapp:"
  },
  "session": {
    "secret": "default-session-secret",
    "maxAge": 86400000
  },
  "logging": {
    "level": "info"
  }
}
```

## Artifact 4: README.md (Quickstart Section)

```markdown
# MyApp

## Quick Start

### Prerequisites
- Docker & Docker Compose
- Node.js 20+

### Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/example/myapp.git
   cd myapp
   ```

2. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```

3. Start the services:
   ```bash
   docker-compose up -d
   ```

4. Wait for services to be healthy:
   ```bash
   docker-compose ps
   ```

5. Visit the application at **http://localhost:3000**

### Default Credentials

- **Database:** `myapp_user` / `postgres`
- **Redis:** password is `redispass123`

### Useful Commands

```bash
# View logs
docker-compose logs -f app

# Run migrations
docker-compose exec app npm run migrate

# Run tests
docker-compose exec app npm test
```

### Troubleshooting

If the app fails to connect to the database, verify that `.env` has the
correct `DB_PASSWORD`. The default is `postgres`.
```


## Response A
Running the 10-category coherence check across all four artifacts:

---

## Coherence Audit Results

### Discrepancies Found

#### 1. DB Password — 3 artifacts disagree with docker-compose.yml [HIGH]

| Artifact | DB Password |
|---|---|
| `docker-compose.yml` | `secret` (in both `POSTGRES_PASSWORD` and `DATABASE_URL`) |
| `.env.example` | `postgres` |
| `config/default.json` | `postgres` |
| `README.md` | `postgres` ("Default Credentials" and Troubleshooting sections) |

The compose file uses `secret` but the other three use `postgres`. The README troubleshooting even says *"The default is `postgres`"* — which is wrong for a Docker-based run. A developer following the README's credential table will get auth failures.

---

#### 2. App access port — README contradicts docker-compose.yml [HIGH]

| Artifact | Port |
|---|---|
| `docker-compose.yml` | `"8080:3000"` — host port **8080**, container port 3000 |
| `README.md` | "Visit the application at **http://localhost:3000**" |

The app is exposed on the host at `8080`, not `3000`. Following the README leads to a dead URL.

---

#### 3. Redis hostname in config — config/default.json contradicts everything [HIGH]

| Artifact | Redis host |
|---|---|
| `docker-compose.yml` | service name `redis` (internal DNS: `redis`) |
| `.env.example` | `localhost` |
| `config/default.json` | `redis://cache:6379` — hostname **`cache`** |

No service named `cache` exists anywhere. `cache` will fail to resolve both inside Docker and locally. This is likely a stale name from an earlier service rename.

---

#### 4. Log level — .env.example contradicts config/default.json [MEDIUM]

| Artifact | Log level |
|---|---|
| `.env.example` | `LOG_LEVEL=debug` |
| `config/default.json` | `"level": "info"` |

If the app reads from the config file as the default and overrides with `LOG_LEVEL` only when present in `.env`, then a developer copying `.env.example` to `.env` gets `debug` logging, while someone running without `.env` gets `info`. Likely intentional for dev vs. default, but the split is undocumented and could be surprising.

---

### Summary Table

| # | Category | Finding | Severity |
|---|---|---|---|
| 1 | Factual Accuracy | DB password is `secret` in compose, `postgres` everywhere else | High |
| 2 | Factual Accuracy | App exposed on host port `8080`, README says `3000` | High |
| 3 | Naming Coherence | Redis hostname `cache` in config doesn't match service name `redis` | High |
| 4 | Factual Accuracy | Log level `debug` in .env.example vs `info` in config default | Medium |

---

### Recommended Fixes

1. **Pick one DB password** — align `docker-compose.yml` (`POSTGRES_PASSWORD` + `DATABASE_URL`), `.env.example` (`DB_PASSWORD`), `config/default.json` (`database.password`), and README's credential table + troubleshooting text.
2. **Fix README port** — change `http://localhost:3000` → `http://localhost:8080`, or change the compose port mapping to `"3000:3000"`.
3. **Fix Redis URL in config** — change `redis://cache:6379` to `redis://redis:6379` (matching the compose service name) or `redis://localhost:6379` (for local dev).
4. **Document the log level split** — either align the values or add a comment in `.env.example` explaining why `debug` overrides the config default.

## Response B
Four discrepancies:

### 1. PostgreSQL password — docker-compose vs everything else
- **docker-compose.yml**: `POSTGRES_PASSWORD: secret` and `DATABASE_URL: postgres://myapp_user:secret@...`
- **.env.example**, **config/default.json**, **README.md**: all use `postgres`

The app container's `DATABASE_URL` uses `secret`, but the other artifacts document and expect `postgres`. These will disagree at runtime depending on which config source wins.

### 2. Redis hostname in config/default.json
- **config/default.json**: `"url": "redis://cache:6379"` — hostname is `cache`
- **docker-compose.yml**: the Redis service is named `redis`, so the internal DNS is `redis:6379`

`cache` won't resolve inside the Docker network. This will cause a connection failure.

### 3. App port in README
- **docker-compose.yml**: maps `"8080:3000"` — the app is reachable at `localhost:8080`
- **README.md**: "Visit the application at **http://localhost:3000**"

The README points to the wrong host port.

### 4. Log level — .env.example vs config/default.json
- **.env.example**: `LOG_LEVEL=debug`
- **config/default.json**: `"level": "info"`

Minor, but the two default configurations disagree on log verbosity. If the app reads `LOG_LEVEL` from env it gets `debug`; if it falls back to the JSON config it gets `info`.

---

**Summary table:**

| Issue | docker-compose.yml | .env.example | config/default.json | README.md |
|---|---|---|---|---|
| DB password | `secret` | `postgres` | `postgres` | `postgres` |
| Redis hostname | `redis` | — | `cache` ❌ | — |
| App host port | `8080` | — | — | `3000` ❌ |
| Log level | — | `debug` | `info` | — |

---
Score each response on the following metrics (0-3):

| Metric | Response A | Response B |
|---|---|---|
| Ungrounded claims | | |
| Assumption acknowledgment | | |
| Alternative consideration | | |
| Error detection | | |
| Rework cycles | | |
| Confidence calibration | | |
| Final correctness | | |
| **Total** | | |
