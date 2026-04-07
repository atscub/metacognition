## Socratic Analysis: Working Through the Bias Checklist

Before giving you a recommendation, let me explicitly run the checklist — because this scenario has several landmines.

---

### Step 1: Authority Bias Check

Sarah's claim rests on three pillars: 8 years of experience, observations across three companies, and a causal mechanism. The socratic rule: **experience is evidence, not proof**. Experience can entrench a wrong diagnosis if the pattern-match was consistently applied to the wrong root cause. Her claim is falsifiable — let's check it against the actual evidence provided.

**Sarah's specific technical claim**: "After ~100 connections you hit kernel scheduling overhead that tanks performance."

This claim is:
- **Directionally true**: PostgreSQL's process-per-connection architecture does have scaling overhead compared to thread-per-connection
- **Numerically wrong**: The threshold where this becomes a real problem is not 100. It's in the hundreds to low thousands, depending on workload and hardware. This is well-established in PostgreSQL benchmarking literature (pgBench studies, Citus benchmarks, etc.)
- **Strategically irrelevant**: Because the actual problem in this system is not PostgreSQL's architecture — it's a misconfiguration. See below.

---

### Step 2: What Does the Actual Evidence Show?

I'm going to read the configuration you provided carefully, rather than pattern-match to Sarah's framing.

**The smoking gun:**

```yaml
# pgbouncer.ini
pool_mode = transaction
default_pool_size = 500
max_client_conn = 2000
max_db_connections = 100   # This caps PgBouncer→PG connections
```

```
# Application connection string
DATABASE_URL=postgresql://app_user:...@pg-primary.internal:5432/myapp
#                                        ^^^^^^^^^^^^^^^^^^^^ port 5432
```

**The application is connecting directly to PostgreSQL on port 5432 — bypassing PgBouncer entirely.**

PgBouncer typically listens on port **6432**. Your app is hitting raw PostgreSQL. You have a connection pooler deployed and not used.

Now the error makes complete sense:

```
12 app servers × 10 connections = 120 connections
max_connections = 100
superuser_reserved_connections = 3
Usable connections = 97
```

120 > 97. You exhaust the connection limit 3 times a day at peak. PgBouncer is sitting idle while your app hammers PostgreSQL directly.

---

### Step 3: What Am I Assuming? What Evidence Do I Have?

| Claim | Confidence | Basis |
|---|---|---|
| App bypasses PgBouncer | **High** | DATABASE_URL shows port 5432, PgBouncer uses 6432 by default |
| 120 connections exceeds pg limit of 97 | **High** | Arithmetic from provided config |
| PostgreSQL handles hundreds of connections fine | **High** | General knowledge; PgBouncer exists specifically for this |
| Fixing the DATABASE_URL resolves the issue | **Medium** | High probability, but there may be other config drift to address |
| MySQL migration is unnecessary | **High** | The root cause is not PostgreSQL's architecture |

---

### Step 4: Steelmanning Sarah

The strongest version of Sarah's position:

> "Even if the app pointed at PgBouncer, PostgreSQL's process-per-connection model means you'll hit a ceiling eventually. MySQL's thread model genuinely does scale better under high concurrency. We're growing, and 3-4 months of migration pain now beats hitting this ceiling again in a year."

This is not crazy. The architectural difference is real. MySQL Aurora *can* handle more native connections than PostgreSQL before degrading. But:

- **The ceiling Sarah describes is not 100** — it's typically 300–500+ before you see meaningful scheduler overhead on modern hardware
- **PgBouncer eliminates the problem** at the PostgreSQL level entirely. It multiplexes thousands of client connections into a small, stable pool of PostgreSQL connections. This is the industry-standard solution — used at companies running PostgreSQL at massive scale (Shopify, GitHub, Heroku)
- **MySQL has its own connection overhead**. 5,000 concurrent threads are not free — they consume memory and context-switch cost. MySQL also recommends pooling at scale
- **Aurora MySQL migration carries real risk**: different SQL dialect, different transaction semantics, different indexing behavior, potential application bugs introduced, 3-4 months of roadmap loss

---

### Step 5: What Would Change My Mind?

If PostgreSQL *with PgBouncer properly configured* still produced 503s under your peak load, that would be evidence the architecture is the problem. That experiment costs you a config change and an hour of observation. The migration costs 3-4 months and carries significant risk.

Run the cheap experiment first.

---

## Recommendation

**Do not migrate to MySQL. Fix the configuration.** Here's what to do, in order:

### Immediate fix (hours, not months)

Point your application at PgBouncer, not PostgreSQL directly:

```yaml
# Change this in docker-compose.yml
DATABASE_URL=postgresql://app_user:${DB_PASS}@pg-primary.internal:6432/myapp
#                                              ^^^ PgBouncer port, not 5432
```

Verify PgBouncer is actually running and reachable at that address first.

### Verify PgBouncer pool sizing makes sense

Your current config:

```ini
default_pool_size = 500   # PgBouncer→PG connections per user/db pair
max_db_connections = 100  # Hard cap on connections to PG
```

These conflict. `default_pool_size = 500` is meaningless when `max_db_connections = 100` caps the total. With transaction pooling mode, you likely need far fewer PG connections than you think — 20-50 is often sufficient for hundreds of app clients. But set `max_db_connections` to something sane relative to `max_connections`:

```ini
max_db_connections = 90   # Leave headroom for superuser and monitoring
```

### Consider raising max_connections modestly

```
max_connections = 200
```

With 4GB shared_buffers you have the memory headroom. But with PgBouncer working correctly, this becomes less critical — PgBouncer's pooling means PostgreSQL only sees a small number of actual connections regardless of how many clients connect to PgBouncer.

### One memory caveat to watch

```
work_mem = 64MB × (active connections) = potentially several GB
```

If you raise max_connections, watch for memory pressure. `work_mem` applies per sort/hash operation, not per connection — but under load it adds up. Monitor with `pg_stat_activity` and adjust if you see swap.

---

## The Bottom Line on Sarah's Claim

The claim "PostgreSQL fundamentally cannot handle more than 100 concurrent connections" is **false as stated**. The number 100 comes from your current `max_connections` setting, which is a knob you turn, not a hard limit. The process-per-connection concern is real but the threshold is far higher, and PgBouncer exists specifically to eliminate it.

Sarah may be right that PostgreSQL has architectural limitations compared to MySQL at extreme scale. She's not right that you've hit them, and she's not right that the fix is a 3-4 month migration when you have a pooler deployed but not connected.

The CTO's skepticism is well-founded. Run the config fix first. Observe for a week. If you're still hitting connection exhaustion after that, you have new evidence — and a much more informed decision about whether a migration is warranted.