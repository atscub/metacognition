OK, let me apply the checklist here. **Cost of error: VERY HIGH.** A wrong decision means either 3-4 months of migration work, or ongoing reliability issues. This deserves scrutiny.

---

## Explicit Assumptions I'm Making

1. **Sarah's claim**: PostgreSQL fundamentally cannot handle >100 concurrent connections due to its process-per-connection architecture
2. **Implicit assumption**: That architectural limit is immutable and migration is necessary
3. **Evidence interpretation**: Connection errors mean hitting a hard architectural wall, not a configuration problem
4. **Configuration state**: The application is using PostgreSQL as configured

## What Would Actually Falsify Sarah's Claim

- PostgreSQL documentation showing it handles thousands of connections (with pooling)
- Existence of production PostgreSQL clusters running 500+ concurrent connections
- Evidence that their connection pool is misconfigured, not that PostgreSQL itself is broken

**I'm pretty confident** the claim is false. Here's why:

---

## The Critical Configuration Problem I'm Seeing

Your **application is connecting directly to PostgreSQL, bypassing pgbouncer entirely**:

```
# What you configured:
DATABASE_URL=postgresql://app_user@pg-primary.internal:5432/myapp  ← DIRECT
# Not:
DATABASE_URL=postgresql://app_user@pgbouncer-host:6432/myapp      ← POOLED
```

And you have:
- **12 app instances × 10 connections = 120 peak connections**
- **PostgreSQL max_connections = 100** (minus 3 reserved = 97 available)
- **pgbouncer configured but NOT BEING USED**

This isn't PostgreSQL hitting an architectural limit. **This is misconfiguration—you're trying to maintain 120 concurrent connections against a 97-slot pool, and you have pooling infrastructure sitting idle.**

---

## Authority Bias Check: Is Sarah's Technical Claim Correct?

**No.** This claim conflates two different things:

| Aspect | Truth |
|--------|-------|
| **Process-per-connection model** | True — PostgreSQL spawns a backend process per connection |
| **Hard limit at ~100 connections** | FALSE — PostgreSQL scales to thousands of connections |
| **Why pooling exists** | Exactly because of this: to multiplex many application connections over fewer database connections |

PostgreSQL production clusters routinely run 500–5,000+ concurrent connections when properly pooled. This is not exotic. Companies like Heroku, Amazon RDS, and Render run millions of connections across their PostgreSQL infrastructure.

**Where Sarah's experience might mislead:**
- She may have seen badly tuned PostgreSQL clusters that *appeared* to have a 100-connection wall
- But that was misconfiguration, not architecture
- Her mitigation (MySQL migration) would fix the symptom without addressing the actual problem

---

## What They Should Do Instead

### Option 1: Use pgbouncer (Fastest Fix)
1. Change `DATABASE_URL` to point to pgbouncer instead of direct PostgreSQL
2. pgbouncer is already configured—just route traffic through it
3. Increase `max_db_connections` in pgbouncer config if needed
4. **Effort: Hours. Risk: Low. Benefit: Solves immediate problem.**

### Option 2: Increase max_connections + Use pgbouncer
If pgbouncer alone doesn't stabilize:
```ini
# postgresql.conf
max_connections = 200  # Can safely go higher with proper tuning
shared_buffers = 4GB   # May need tuning if you increase connections
```
Plus: Actually use pgbouncer for multiplexing.
**Effort: 1-2 days. Risk: Low. Benefit: More headroom.**

### Option 3: Reduce Application Connection Pool
Lower per-instance connection pool from 10 → 5–7 connections. Use application-level retry logic instead of holding idle connections.
**Effort: Hours. Risk: Low if done carefully.**

---

## The Real Question: What Changed?

- Is this a NEW problem (recent spike in traffic)?
- Or has the misconfiguration existed and traffic just caught up?

If pgbouncer was set up long ago and never connected, someone intended this to be solved—then forgot about it.

---

## What You Should Do Now

1. **Before migration**: Verify the application actually uses pgbouncer
   - Change `DATABASE_URL` in docker-compose to point to pgbouncer host:port
   - Restart one app instance and monitor
   - Check if connection errors disappear
   
2. **Confidence check**: If that works, the problem is solved with **zero migration cost**

3. **If it doesn't work** (and I'd be surprised), *then* investigate:
   - Why pgbouncer isn't helping (config issue? pool size issue?)
   - Whether MySQL would actually fix it (probably not—you'd have the same pool exhaustion)

**Tell the CTO**: "Before committing to 3-4 months of migration, we need 2-3 hours to verify the application is using the connection pooler we already have. If that doesn't work, we'll have much clearer data for the migration decision."

---

## What I'm Uncertain About

- **I haven't verified**: Whether pgbouncer is actually integrated into your deployment (does docker-compose mount the config? Does the service exist?)
- **I haven't confirmed**: Whether there are other reasons the app can't use pgbouncer (protocol incompatibility, prepared statements, etc.)

**This is fixable**, but I'd need you to confirm: *Is pgbouncer actually running in your infrastructure, and is your application configured to use it?*