## Premortem: Advice on Zero-Downtime Column Addition

### Step 1: The Claim I'm About to Make
That PostgreSQL 15 handles this migration safely via a metadata-only change, making expand-contract unnecessary for this specific case.

### Step 2–3: Risk Assessment

| Risk | L | I | Rev |
|---|---|---|---|
| Confusing "no table rewrite" with "no lock needed" — ACCESS EXCLUSIVE lock is still required | High | High | Hard |
| Lock queue cascade: ALTER waits for long txn → new queries pile up → connection pool exhaustion | High | High | Hard |
| Stale knowledge on pgroll (relatively new tool, 2023+) | Med | Med | Easy |
| User applies PG 11+ guidance to a PG < 11 system | Low | High | Hard |
| Forgetting RDS session-parameter nuances | Low | Med | Easy |

**Critical insight from the premortem**: The previous 45-minute lock was almost certainly `CREATE INDEX` *without* `CONCURRENTLY` — a completely different beast. That experience is not predictive of this migration's risk profile.

**Verified claim**: PG 11+ `ADD COLUMN` with a *constant* default (`'free'` qualifies) stores the default in the system catalog, not in every row. No table rewrite. The lock is held for milliseconds, not minutes. PostgreSQL 15 inherits this.

**The real threat**: Even a millisecond-held ACCESS EXCLUSIVE lock can cascade catastrophically if a long-running transaction is already open. PostgreSQL's lock queue means every new query blocks *while the ALTER waits*, not just while it holds. At 200 req/s, connection pool exhaustion can happen in seconds.

**Mitigation**: `lock_timeout` — abort the ALTER if it can't get the lock quickly, retry rather than queue-block.

---

## The Actual Answer

**Good news: you don't need expand-contract for this.** PG 15 makes your specific migration (constant default, nullable column) a catalog-only change. The table has 50M rows and it doesn't matter.

**The previous incident was unrelated** — adding an index without `CONCURRENTLY` holds a lock for the full index build. That's a different operation entirely.

### The Safe Strategy

The one real risk is lock queue cascade. Mitigate it with `lock_timeout`:

```sql
-- Run this in a transaction or as two statements
SET lock_timeout = '2s';
ALTER TABLE users ADD COLUMN subscription_tier VARCHAR(20) DEFAULT 'free';
```

If there's a long-running query or transaction when you run this, `lock_timeout` causes the ALTER to *fail fast* with an error instead of queuing. You retry. Far better than holding the queue.

### In Rails

Option A — minimal, explicit:

```ruby
class AddSubscriptionTierToUsers < ActiveRecord::Migration[7.0]
  def up
    execute "SET lock_timeout = '2s'"
    add_column :users, :subscription_tier, :string, limit: 20, default: 'free'
  end

  def down
    remove_column :users, :subscription_tier
  end
end
```

Option B — use the `strong_migrations` gem (recommended for your team):

```ruby
# Gemfile
gem 'strong_migrations'

# Migration
class AddSubscriptionTierToUsers < ActiveRecord::Migration[7.0]
  def change
    # strong_migrations will warn if this isn't safe; on PG 11+ it knows this is fine
    safety_assured { add_column :users, :subscription_tier, :string, limit: 20, default: 'free' }
  end
end
```

`strong_migrations` actively checks your PG version and migration pattern, and will block you from running unsafe patterns — useful given your team's history.

### About the Tools Your Tech Lead Mentioned

**pg_repack**: Rebuilds bloated tables and indexes without long locks. **Not relevant here** — this is for fixing bloat, not adding columns.

**pgroll**: Multi-version schema migration tool. Uses an expand-contract approach automatically. Legitimate tool, but **overkill for this case** and adds operational complexity. Worth evaluating if you have frequent complex migrations (multi-column changes, type changes, renames). For today's problem, it's unnecessary.

### When You Actually Need Expand-Contract

The pattern your tech lead described is correct but applies to different scenarios:

| Scenario | Approach |
|---|---|
| `ADD COLUMN` with constant default, nullable (PG 11+) | Direct ALTER + `lock_timeout` ✅ |
| `ADD COLUMN NOT NULL` with no default | Expand-contract required |
| `ADD COLUMN NOT NULL` with volatile default (e.g., `NOW()`) | Expand-contract required |
| Column type change | Expand-contract required |
| `ADD COLUMN` on PG < 11 with any default | Expand-contract required |

### Checklist Before Running

1. Verify PG version: `SELECT version();` — confirm you're on 11+
2. Check for long-running transactions: `SELECT pid, now() - pg_stat_activity.query_start AS duration, query FROM pg_stat_activity WHERE state != 'idle' ORDER BY duration DESC;`
3. Set a retry loop in your deploy script — `lock_timeout` means you may need 2–3 attempts
4. Run during lowest-traffic window (not because of lock duration, but to minimize retry probability)
5. Have a rollback ready: `ALTER TABLE users DROP COLUMN subscription_tier;` — also fast on PG 15

### What to Fix for Future Index Migrations

Your 45-minute incident: next time use `CREATE INDEX CONCURRENTLY`. It never holds an exclusive lock — it does multiple passes and yields to queries. Takes longer wall-clock but zero blocking.

```sql
CREATE INDEX CONCURRENTLY idx_users_subscription_tier ON users(subscription_tier);
```

In Rails: `algorithm: :concurrently` on `add_index`.