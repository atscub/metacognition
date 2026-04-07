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