## Do not migrate to MySQL. This is a fixable configuration problem.

Sarah's diagnosis has a critical factual error, and there's a smoking gun in your config that explains the outages entirely.

---

### The Root Cause

Your application is **bypassing PgBouncer entirely**.

```yaml
# Application connects directly to PostgreSQL:
DATABASE_URL=postgresql://app_user:...@pg-primary.internal:5432/myapp
#                                       ^^^^^^^^^^^^^^^^^^^^ PostgreSQL host, not PgBouncer
```

You have PgBouncer running and configured, but nothing is using it. Your 12 app servers (×10 connections each) are hammering PostgreSQL directly, attempting 120 connections against a 97-slot limit (100 − 3 reserved). During peak traffic, a brief surge trips the limit and you get the FATALs.

**The fix:** point `DATABASE_URL` at PgBouncer.

```yaml
DATABASE_URL=postgresql://app_user:${DB_PASS}@pgbouncer.internal:6432/myapp
```

That's it. PgBouncer in transaction mode will multiplex your 2,000 potential client connections into ≤100 PostgreSQL server connections. Your outages stop.

---

### Why Sarah's Assessment Is Wrong

Her claim: *"PostgreSQL fundamentally cannot handle more than 100 concurrent connections"*

| Claim | Reality |
|---|---|
| 100 is a hard limit | It's the **default** for `max_connections`. You can set it to 1,000+ |
| Process-per-connection kills you at ~100 | Rough rule of thumb, not a cliff edge. Large Postgres deployments run 500–1,000+ direct connections routinely |
| MySQL thread model solves this | MySQL/Aurora has its own scaling limits; threads aren't magic. Shopify, Instagram, GitHub, and Notion all run PostgreSQL at massive scale |
| You need to migrate databases | You need to **use the connection pooler you already deployed** |

The process-per-connection model is a real architectural difference, and it *is* why connection poolers like PgBouncer exist for PostgreSQL. But you already have one. It's just not wired up.

---

### Secondary Issues to Fix After Routing Through PgBouncer

**1. `work_mem = 64MB` is dangerously high**

With 100 connections and complex queries, PostgreSQL can allocate `work_mem` multiple times per connection (once per sort/hash node in a query plan). Worst case: `64MB × 100 connections × multiple operations` easily exceeds available RAM. Lower this:

```
work_mem = 16MB   # or even 8MB; use SET LOCAL for specific heavy queries
```

**2. PgBouncer `default_pool_size = 500` exceeds `max_db_connections = 100`**

This is contradictory — PgBouncer won't actually open 500 server connections because `max_db_connections` caps it at 100. That's fine for your case, but the misconfiguration suggests the PgBouncer setup was never tested end-to-end. Review it carefully:

```ini
[pgbouncer]
pool_mode = transaction
default_pool_size = 25        # server connections per user/db pair
max_db_connections = 95       # leave headroom below pg max_connections
max_client_conn = 2000        # keep high for your many app clients
```

**3. Optional: raise `max_connections` modestly as a safety buffer**

After routing through PgBouncer, you can bump this for headroom:

```
max_connections = 200   # requires PostgreSQL restart
```

Each connection costs ~5–10MB of shared memory, so this is safe on any reasonably sized DB server.

---

### What to Tell Your CTO

The MySQL migration would cost 3–4 months and solve a problem you don't actually have. The real fix is a one-line change to `DATABASE_URL` plus an afternoon of testing. Sarah's experience at three previous companies was likely the same underlying issue (apps not using poolers correctly) that she attributed to PostgreSQL's architecture.

Ask Sarah to explain why PgBouncer is deployed but not in use — that's the conversation worth having.