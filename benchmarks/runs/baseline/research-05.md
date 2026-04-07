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