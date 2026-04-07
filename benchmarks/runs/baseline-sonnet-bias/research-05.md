## Good news: PostgreSQL 11+ already solves the hard part

The specific migration you're doing — adding a column with a **constant string default** — is actually safe on PostgreSQL 15. Since PG 11, adding a column with a non-volatile default no longer rewrites the table. PG stores the default in the catalog (`pg_attribute`) and serves it lazily for old rows. The DDL completes in **milliseconds**, not minutes.

Your previous index migration was painful because `CREATE INDEX` holds `SHARE` lock for its entire duration. `ADD COLUMN ... DEFAULT 'free'` is a metadata-only operation.

---

## The real danger: lock contention, not lock duration

Even though the lock is held briefly, `ALTER TABLE` requires `ACCESS EXCLUSIVE` — the most restrictive lock. If a long-running transaction is active when you run the migration, your migration queues behind it. While it queues, **all new queries on that table also queue behind it**. This is what causes the connection pile-up, not the migration itself.

---

## Safe migration procedure

```sql
-- Step 1: Kill the migration fast if it can't get a lock quickly
-- (prevents connection pile-up during high traffic)
SET lock_timeout = '2s';
SET statement_timeout = '5s';

-- Step 2: The actual migration — safe on PG 11+ with constant default
ALTER TABLE users ADD COLUMN subscription_tier VARCHAR(20) DEFAULT 'free';
```

In Rails 7, wrap it in a migration like this:

```ruby
class AddSubscriptionTierToUsers < ActiveRecord::Migration[7.0]
  def up
    execute "SET lock_timeout = '2s'"
    execute "SET statement_timeout = '5s'"
    add_column :users, :subscription_tier, :string, limit: 20, default: 'free'
  end

  def down
    remove_column :users, :subscription_tier
  end
end
```

If `lock_timeout` fires, the migration raises an error and exits cleanly — no lingering lock, no connection pile-up. Just retry during a quieter moment or wait for long transactions to clear.

---

## What if you also want NOT NULL?

If you want `NOT NULL` eventually (which you likely should), **don't do it in one step** — that would require a full table scan to verify. The safe sequence on PG 15:

```sql
-- 1. Add nullable column (instant on PG 11+)
ALTER TABLE users ADD COLUMN subscription_tier VARCHAR(20) DEFAULT 'free';

-- 2. Backfill existing NULLs in batches from your app/script
--    (do this over hours/days, no locking)
UPDATE users SET subscription_tier = 'free'
WHERE subscription_tier IS NULL AND id BETWEEN ? AND ?;

-- 3. Add a NOT VALID check constraint (validates only new rows, no table scan)
ALTER TABLE users ADD CONSTRAINT subscription_tier_not_null
  CHECK (subscription_tier IS NOT NULL) NOT VALID;

-- 4. VALIDATE the constraint (uses ShareUpdateExclusiveLock — doesn't block reads/writes)
ALTER TABLE users VALIDATE CONSTRAINT subscription_tier_not_null;

-- 5. Add the actual NOT NULL constraint (now instant — PG trusts the validated check)
ALTER TABLE users ALTER COLUMN subscription_tier SET NOT NULL;

-- 6. Drop the check constraint
ALTER TABLE users DROP CONSTRAINT subscription_tier_not_null;
```

Steps 3-6 are only needed if you need `NOT NULL`. For your immediate goal of just adding the column with a default, steps 1-2 are sufficient.

---

## On pgroll / pg_repack

- **pg_repack**: Rewrites the table online. Useful for bloat reclamation or changing column types — overkill here, and not available on RDS without the extension being installed.
- **pgroll**: A newer tool for multi-version schema migrations (good for the expand-contract pattern across deploys). Worth evaluating long-term, but adds operational complexity. Not necessary for this specific change.

---

## Strong recommendation: add `strong_migrations` gem

```ruby
# Gemfile
gem 'strong_migrations'
```

It catches dangerous migration patterns at runtime (including the exact lock-timeout issue you hit before) and guides you toward safe alternatives. It would have flagged your previous index migration and suggested `CREATE INDEX CONCURRENTLY`.

---

## Summary

| Your concern | Reality |
|---|---|
| "ADD COLUMN with DEFAULT takes minutes" | False on PG 11+, it's instant |
| "Will lock the table for 50M row rewrite" | No rewrite happens for constant defaults |
| "Need expand-contract pattern" | Only needed if adding NOT NULL in same step |
| Risk that remains | Lock queue pile-up if long-running txns exist |
| Mitigation | `SET lock_timeout = '2s'` before the ALTER |

Your migration as written is safe to run — just prefix it with the lock timeout.