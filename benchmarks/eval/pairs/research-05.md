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
## Premortem Analysis

**Plan being evaluated:** Recommend a migration strategy for `ALTER TABLE users ADD COLUMN subscription_tier VARCHAR(20) DEFAULT 'free'` on PG15, 50M rows, zero downtime.

---

### Step 1: What Could Go Wrong With My Advice?

The highest-risk failure mode here is **giving advice based on pre-PG11 behavior**. This is a knowledge-staleness trap that would send you down unnecessary complexity.

| Risk | Likelihood | Impact | Reversibility |
|------|-----------|--------|---------------|
| Recommending expand-contract for a problem PG15 already solved | High | High — weeks of unnecessary work | Easy (just don't do it) |
| Understating the lock storm risk even for "instant" DDL | Medium | High — the exact failure mode they had before | Hard |
| Conflating pg_repack's purpose with the actual problem | Medium | Medium — wasted implementation effort | Easy |
| Being wrong about PG15 catalog-default behavior | Low | High — entire recommendation changes | N/A |

The most likely way I fail: I treat this like a PG9 migration problem and recommend a complex workaround for a table rewrite that PG15 doesn't actually do.

---

### Step 2: Verify the Critical Assumption

**Is this a table rewrite in PG15?**

PostgreSQL 11 introduced a fundamental optimization: adding a column with a **constant (non-volatile) default** no longer rewrites the table. The default value is stored in `pg_attribute.attmissingval`. Existing rows appear to have the value without it being physically written until the row is next updated. This is confirmed behavior in PG15.

`DEFAULT 'free'` is a constant string literal — this optimization applies.

`DEFAULT NOW()` or `DEFAULT uuid_generate_v4()` are volatile — they would NOT get this optimization.

**Verdict:** In PG15, your specific ALTER does not rewrite the table. It runs in milliseconds of actual work.

---

### Step 3: The Real Problem

The actual risk is **lock acquisition**, not table rewriting. Here's the failure chain your team already experienced:

1. A long-running query (report, analytics, slow API call) holds a weak lock on `users`
2. `ALTER TABLE` queues, waiting for `ACCESS EXCLUSIVE`
3. Every subsequent query on `users` queues *behind the ALTER*
4. After a few seconds, you have hundreds of queued connections
5. RDS connection limit hit → new queries fail immediately
6. The ALTER eventually gets its lock, runs in milliseconds — but damage is done

This is why that index creation took 45 minutes: `CREATE INDEX` (without `CONCURRENTLY`) holds `ACCESS EXCLUSIVE` for the entire duration. That was the wrong tool. Your new ALTER is different — but the lock queue problem is still real.

---

## The Actual Recommendation

**Your specific migration is much simpler than you think.**

### Safe approach for this exact ALTER

```ruby
# Rails migration
class AddSubscriptionTierToUsers < ActiveRecord::Migration[7.0]
  def up
    # Fail fast if we can't get a lock within 2 seconds
    execute "SET lock_timeout = '2s'"
    
    # In PG15: no table rewrite, just catalog update
    # Runs in milliseconds once lock is acquired
    add_column :users, :subscription_tier, :string, limit: 20, default: 'free'
  end
  
  def down
    execute "SET lock_timeout = '2s'"
    remove_column :users, :subscription_tier
  end
end
```

Run this during a low-traffic window (not peak 200 req/s). If it fails due to lock timeout, retry — it will succeed once there's a 2-second gap with no long-running transactions. Most production systems have these gaps naturally.

**Why `lock_timeout` matters:** Without it, the ALTER waits indefinitely, causing the connection storm. With it, it fails fast, nothing queues, you retry. This is the single most important guard.

---

### Clarifying the tools your tech lead mentioned

**pg_repack** — Wrong tool for this problem. pg_repack rebuilds tables to reclaim bloat (dead tuples). It's valuable for table bloat after heavy deletes/updates, not for adding columns. Ignore it here.

**pgroll** — A legitimate zero-downtime migration tool using the expand-contract pattern with dual-write and view-based abstraction. It's powerful but adds operational complexity: you need a running pgroll instance, it requires a migration state table, and rollback involves schema swaps. For your specific ALTER (which PG15 handles natively in milliseconds), pgroll is overkill. Where pgroll shines: renaming columns, changing types, or other operations that genuinely need the dual-write pattern.

**Expand-contract pattern** — You're right that it's complex. You'd need it if you were:
- Renaming a column
- Changing a column type (e.g., `VARCHAR` → `TEXT` in ways that need validation)
- Adding `NOT NULL` to a column that might have existing NULLs

For adding a new column with a constant default, you don't need it. If you later want `NOT NULL`, that's also safe in PG15 with a constant default — same optimization applies.

---

### If you want belt-and-suspenders safety

**Step 1 — Before the migration, check for long-running queries:**
```sql
SELECT pid, now() - pg_stat_activity.query_start AS duration, query, state
FROM pg_stat_activity
WHERE (now() - pg_stat_activity.query_start) > interval '30 seconds'
  AND state != 'idle';
```

**Step 2 — Set a statement_timeout on the migration connection** in addition to lock_timeout, so if something goes sideways the connection cleans itself up.

**Step 3 — Use a retry wrapper** (most teams script this):
```bash
#!/bin/bash
for i in {1..10}; do
  bundle exec rails db:migrate && break
  echo "Migration failed, retrying in 5s..."
  sleep 5
done
```

---

### Bottom line

| Scenario | Recommendation |
|----------|---------------|
| Your exact ALTER as written | `SET lock_timeout = '2s'` + run during lower traffic. Done. |
| If you later need NOT NULL | Same approach — PG15 handles constant-default NOT NULL without rewrite |
| If you need to rename or retype a column | Then use expand-contract or pgroll |
| Table bloat problems | Then pg_repack |

The complexity you read about is real — but it applies to harder migrations than this one. Your previous 45-minute outage was caused by `CREATE INDEX` without `CONCURRENTLY`, which is a separate mistake. Fix that pattern too: always use `CREATE INDEX CONCURRENTLY` for index additions on live tables.

## Response B
## Good news: PostgreSQL 11+ changes the calculus here

Before diving into expand-contract, you need to know that **your specific migration is essentially free in PostgreSQL 11+**. Since PG 11, adding a column with a constant default value does not rewrite the table. PostgreSQL stores the default in `pg_attribute` and returns it on read. The `ALTER TABLE` only touches the catalog — it completes in milliseconds regardless of row count.

Your 45-minute index migration was painful for a different reason: `CREATE INDEX` without `CONCURRENTLY` holds an `AccessExclusiveLock` for the entire duration. `ADD COLUMN` holds that same lock but drops it almost immediately after the catalog update.

---

## The actual risk to worry about

Even a millisecond-level lock is dangerous in one specific scenario: **lock queuing behind long-running transactions**.

If any transaction is currently touching the `users` table (a SELECT counts), your `ALTER TABLE` must wait for it. While it waits, it holds a queue position that blocks *all subsequent queries* on that table. At 200 req/s, a 30-second background job can cause hundreds of queries to pile up, exhausting your connection pool.

This is almost certainly what happened with your index migration.

---

## The safe migration script

Set `lock_timeout` before running. If the lock isn't available within N seconds, fail fast rather than queuing. Retry during a low-traffic window or when you know no long transactions are running.

```sql
-- In a transaction so timeout resets after
BEGIN;
SET lock_timeout = '3s';   -- fail fast instead of queuing
SET statement_timeout = '10s';

ALTER TABLE users ADD COLUMN subscription_tier VARCHAR(20) DEFAULT 'free';

COMMIT;
```

Add retry logic (pseudocode):

```ruby
# In your Rails migration
def up
  retries = 0
  begin
    safety_assured do
      execute "SET lock_timeout = '3s'"
      add_column :users, :subscription_tier, :string, limit: 20, default: 'free'
    end
  rescue ActiveRecord::LockWaitTimeout
    retries += 1
    raise if retries > 5
    sleep(10 * retries)  # back off
    retry
  end
end
```

---

## Rails-specific: use strong_migrations

If you don't have the `strong_migrations` gem, add it. It prevents exactly the class of mistake that caused your 20-minute outage, and it understands the PG 11+ semantics.

```ruby
# Gemfile
gem 'strong_migrations'
```

It will either approve this migration directly (PG 11+) or guide you through the safe steps if it detects a risk.

---

## If you need NOT NULL (more complex)

Your current statement doesn't include `NOT NULL`, so the above is sufficient. If you later want to add it, **do not** run `ALTER TABLE users ALTER COLUMN subscription_tier SET NOT NULL` — that scans all 50M rows to verify.

Instead, use the check constraint trick (PG 12+):

```sql
-- Step 1: Add constraint without validating (no table scan, brief lock)
ALTER TABLE users
  ADD CONSTRAINT subscription_tier_not_null
  CHECK (subscription_tier IS NOT NULL)
  NOT VALID;

-- Step 2: Validate in background (ShareUpdateExclusiveLock, reads/writes continue)
-- Run during low-traffic or just let it run; it doesn't block queries
ALTER TABLE users VALIDATE CONSTRAINT subscription_tier_not_null;

-- Step 3: Once validated, PostgreSQL knows NOT NULL holds
-- You can optionally convert to a real NOT NULL constraint at this point
```

---

## On pgroll and pg_repack

- **pg_repack**: Rebuilds the entire table in a shadow copy and swaps it. Useful when you need to reclaim bloat or change storage parameters. Overkill here, and on RDS you'd need the extension pre-installed.
- **pgroll**: Handles dual-write patterns for multi-version schema migration. Valuable if you're making breaking schema changes that old app versions can't tolerate. Significant operational overhead for a simple column add.

Neither is warranted for this migration.

---

## Summary

| Approach | Right for this case? |
|---|---|
| Simple `ADD COLUMN` with `lock_timeout` | Yes — use this |
| Expand-contract | Only if adding NOT NULL |
| `CREATE INDEX CONCURRENTLY` pattern | Already how you should add future indexes |
| pgroll / pg_repack | No — operational overhead not justified |

The expand-contract pattern you read about is the right mental model, but PostgreSQL 11+ already handles the "add column with default" step as a catalog-only operation — it effectively does the hard part for you.

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
