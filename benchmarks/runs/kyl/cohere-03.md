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