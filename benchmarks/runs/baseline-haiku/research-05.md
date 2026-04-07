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