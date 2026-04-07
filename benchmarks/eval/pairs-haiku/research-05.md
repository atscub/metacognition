# Task: research-05 — Zero-downtime column addition on large PostgreSQL table

## Prompt
We need to add a new column to our users table in PostgreSQL 15. The table has about
50 million rows. We're running on AWS RDS (db.r6g.xlarge, 4 vCPUs, 32 GB RAM). The
application is a Rails 7 app with ~200 req/s during peak hours.

The column we need to add is:

```sql
ALTER TABLE users ADD COLUMN subscription_tier VARCHAR(20) DEFAULT 'free';
```

We absolutely cannot have any downtime — this is a production system serving paying
customers 24/7. Our last migration on this table (adding an index) took 45 minutes and
caused connection timeouts because it held a lock the entire time.

I've been reading about the expand-contract pattern where you:
1. Add the column as nullable with no default
2. Backfill the data in batches
3. Add the default constraint
4. Make it NOT NULL

But this seems really complex for just adding one column. Our tech lead also mentioned
tools like pgroll or pg_repack.

What's the safest migration strategy for this? We want to get it right because last
time we messed up a migration it caused a 20-minute outage.


## Response A
## Premortem Results

I'm working through the failure scenarios for this migration. Given that you've already experienced a 20-minute outage and a 45-minute lock situation, this is exactly the kind of decision that needs rigorous vetting.

---

### **The Plan Under Review**

- Add `subscription_tier VARCHAR(20) DEFAULT 'free'` to 50M-row users table
- Zero-downtime requirement (non-negotiable)
- Three candidate approaches: expand-contract, pgroll, or pg_repack
- Context: Production Rails 7, 200 req/s peak, previous migration caused timeouts

---

### **Critical Failure Modes**

| Risk | Likelihood | Impact | Reversibility | Priority |
|------|-----------|--------|---------------|----------|
| **Backfill takes 3-4x longer than estimated** | High | High | Hard | 🔴 CRITICAL |
| **Lock contention during backfill starves app** | High | High | Hard | 🔴 CRITICAL |
| **App code deployed before migration completes** | Medium | High | Medium | 🔴 CRITICAL |
| **Expand-contract adds complexity that creates new bugs** | Medium | High | Medium | 🟠 HIGH |
| **pgroll/pg_repack not actually zero-downtime on RDS** | Medium | High | Hard | 🟠 HIGH |
| **Connection pool exhausted by backfill threads** | Medium | High | Hard | 🟠 HIGH |
| **Rollback after 6-hour partial backfill is slow** | Low | High | Impossible | 🟡 MEDIUM |

---

### **What You Need to Verify RIGHT NOW**

Before choosing an approach:

1. **Understand what actually broke last time**
   - Was it the lock itself (45 min of table lock)?
   - Or something else (connection pool, replication lag, queries timing out)?
   - This changes which solution applies.

2. **Test backfill performance on a staging clone**
   - Take a snapshot of production (or use AWS DMS to clone)
   - Run a test backfill on 50M rows with realistic concurrent load
   - Measure: time, lock duration, query impact, connection count
   - You need empirical data, not guesses

3. **Verify pgroll/pg_repack actually work on RDS 15**
   - pgroll is newer and promising, but has it been used at your scale?
   - pg_repack needs superuser or rds_superuser role — does RDS allow this on your instance?
   - Are there version/extension compatibility issues?

---

### **The Real Problem with Each Approach**

**Expand-contract:**
- ✅ Doesn't require special tools
- ✅ Proven pattern
- ❌ **Your last lock issue suggests the problem is long-running operations**, not just adding the column. Expand-contract adds *more* operations (nullable → backfill → default → NOT NULL). More steps = more opportunities for contention.
- ❌ **Assumes backfill batches won't cause lock contention**, but 50M rows with 200 req/s concurrent load is NOT trivial to backfill safely

**pgroll:**
- ✅ Designed specifically for zero-downtime migrations
- ✅ Handles deployment coordination automatically (versioned table approach)
- ❌ **You haven't verified it works on your RDS setup**
- ❌ **Adds operational complexity** (new tool, new failure modes)
- ❌ **If it fails mid-way, you're in uncharted recovery territory**

**pg_repack:**
- ✅ Actually zero-downtime (uses version snapshots)
- ✅ Simpler than expand-contract (one operation instead of many)
- ❌ **Requires superuser/rds_superuser—check if RDS grants this**
- ❌ **Uses temporary disk space** (might be an issue on db.r6g.xlarge with 32GB)
- ✅ For just adding a column, less heavy than full table repack

---

### **My Recommendation**

**Don't choose yet.** Do this first:

1. **Investigate the last migration failure** (45-minute index lock)
   - Get the exact query from CloudWatch logs
   - Was it `CREATE INDEX CONCURRENTLY`? If so, why did it take 45 min?
   - Are there missing indexes on critical query columns?
   - This tells you whether expand-contract will have the same problem

2. **Run a test migration on staging**
   - Restore a production snapshot to a staging RDS instance (same class, same size)
   - Try the expand-contract approach with production-realistic load
   - Measure: backfill time, peak lock duration, connection spike, max query latency
   - If peak lock > 30 seconds, you'll get customer-facing timeouts at 200 req/s

3. **Then choose based on results:**
   - If backfill takes 30 min without lock issues → expand-contract is safe
   - If backfill causes lock contention → test pg_repack or pgroll
   - If you can verify pgroll works → use pgroll (least operational risk)
   - If pg_repack works → second choice (simpler than expand-contract, proven zero-downtime)

---

### **The One Thing You Cannot Afford to Skip**

**Do not assume expand-contract is safe because it's a "pattern."** Your last migration suggests lock contention is *your* specific problem. Expand-contract doesn't inherently solve lock contention—it just spreads operations over time. If those operations themselves cause contention, you've added complexity without fixing the root issue.

**Test on staging with real load before any approach hits production.**

## Response B
I'll give you a clear, pragmatic strategy. The good news: PostgreSQL 15 has optimizations that make this much safer than your previous migration, but you need to do it carefully.

## The Core Issue with Your Previous Migration

Your 45-minute lock + timeouts likely came from one of these:
1. **NOT NULL constraint being added immediately** — forces a full table rewrite to fill NULL values
2. **Applying a non-constant DEFAULT** (like a function call) — same rewrite
3. **Acquiring an `ACCESS EXCLUSIVE` lock** for too long

Your simple command (`DEFAULT 'free'`) *should* be fast in PostgreSQL 15 (it's just a metadata change), but clearly something went wrong. Let's avoid repeating that.

## Recommended: Modified Expand-Contract (Safest)

This is simpler than full expand-contract but has the same zero-downtime guarantee:

```sql
-- Step 1: Add nullable column WITHOUT a DEFAULT (immediate, non-blocking)
-- Run during business hours, takes ~100ms for metadata change
ALTER TABLE users ADD COLUMN subscription_tier VARCHAR(20);

-- Step 2: Backfill in batches (do this immediately after, during normal traffic)
-- This backfill is transparent to the app — the column exists but is NULL
UPDATE users SET subscription_tier = 'free' WHERE subscription_tier IS NULL LIMIT 100000;
-- Repeat until no rows updated. Spread these over 5-10 minutes.
-- Do this with your app running normally — no lock contention

-- Step 3: Add the DEFAULT (fast metadata change, ~100ms)
ALTER TABLE users ALTER COLUMN subscription_tier SET DEFAULT 'free';

-- Step 4: Optional NOT NULL (only if you need it, 100ms metadata-only)
-- Skip this if nullable is fine — defaults to 'free' anyway
ALTER TABLE users ALTER COLUMN subscription_tier SET NOT NULL;
```

**Why this works:**
- Step 1 is metadata-only, no rewrite
- Step 2 has no exclusive locks; your app keeps running at 200 req/s
- Steps 3-4 are metadata-only in PostgreSQL 15
- Each step is reversible if something goes wrong

## Timing & Monitoring

```bash
# Before 8am your peak traffic time, run Step 1
# Then immediately start batching Step 2 over 10 minutes
# Monitor: 
#  - SELECT count(*) FROM users WHERE subscription_tier IS NULL;
#  - Watch CloudWatch metrics for connection count, CPU

# Each UPDATE batch should take <100ms and complete during off-peak

# Once backfill is done (0 NULL rows), run Step 3-4
```

## When NOT to Do This

- **Don't run all 4 steps at once** — that defeats the purpose
- **Don't add NOT NULL immediately** unless your app requires it (Step 4 can be skipped)
- **Don't backfill with `UPDATE users SET subscription_tier = 'free'` without LIMIT** — that's a table-wide lock that will cause your 200 req/s to timeout

## Alternative: pgroll (If You Want Automation)

If you want the tool to handle orchestration:

```bash
# Install: https://github.com/xataio/pgroll
pgroll start --postgres-url "$POSTGRES_URL" migration.sql
# pgroll handles batching, backfilling, and rollback automatically
```

**Pros:** Automated, handles rollback, idempotent  
**Cons:** Requires additional tool, learning curve, but increasingly standard for this exact problem

## pg_repack Alternative (If Disk Space Available)

```bash
pg_repack --host prod-rds.amazonaws.com --dbname mydb --table users
```

Good if you want a "rebuild the table fresh" approach, but overkill for just adding one column. Use this if you're doing index maintenance too.

## My Recommendation

**Use the modified expand-contract above.** It's:
- ✅ Zero downtime
- ✅ Reversible at each step (if Step 2 times out, stop and troubleshoot)
- ✅ Native SQL (no new tools to trust)
- ✅ Takes ~15 minutes total spread over low-traffic window
- ✅ Your app continues normally during the entire thing

**Before you run it:**
1. Test in staging with similar data volume (10M+ rows)
2. Have a rollback plan: `ALTER TABLE users DROP COLUMN subscription_tier`
3. Monitor RDS CloudWatch metrics (CPU, connections, read/write latency) during execution
4. Schedule for a quieter traffic window (even 20% reduction helps)
5. Confirm your application handles `NULL` values gracefully until Step 2 completes (it should, since the column won't exist yet during queries)

**If Step 2 backfilling gets slow:** You can pause, wait for traffic to drop, resume. Unlike the old `ALTER TABLE` approach, you're not holding locks.

Want me to create a monitoring dashboard or a script that safely batches Step 2 with metrics? Or test this approach against your table size?

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
