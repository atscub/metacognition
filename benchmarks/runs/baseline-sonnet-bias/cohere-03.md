Here are the discrepancies I found:

## 1. Database password mismatch (critical)

| Artifact | Password |
|---|---|
| docker-compose.yml | `secret` |
| .env.example | `postgres` |
| config/default.json | `postgres` |
| README (credentials + troubleshooting) | `postgres` |

The compose file uses `secret` in both `POSTGRES_PASSWORD` and `DATABASE_URL`, but every other artifact says `postgres`. The README's troubleshooting tip actively misleads: "The default is `postgres`" — which is wrong for Docker deployments.

## 2. App port: README says 3000, compose exposes 8080

docker-compose.yml maps `8080:3000` (host:container), so the app is reachable at `http://localhost:8080`. The README says to visit `http://localhost:3000`, which won't work.

## 3. Redis hostname in config/default.json is wrong

`config/default.json` has:
```json
"url": "redis://cache:6379"
```
The docker-compose service is named `redis`, not `cache`. This URL would fail DNS resolution inside Docker. It should be `redis://redis:6379` (or omit the URL and use host/port fields).

## 4. Connection string vs. individual vars (structural inconsistency)

docker-compose passes a single `DATABASE_URL` env var. .env.example (used for local dev) provides individual `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` vars. If the app only reads one format, one of the two environments will be misconfigured. The config file also uses individual fields, suggesting `DATABASE_URL` may not actually be consumed.

## 5. Minor: LOG_LEVEL default inconsistency

| Artifact | Log level |
|---|---|
| .env.example | `debug` |
| config/default.json | `info` |

Lower priority since these may intentionally differ (dev vs. baseline default), but worth making explicit.

---

**Summary of highest-risk issues:** #1 and #2 would cause an immediate failure for anyone following the README quickstart against Docker.