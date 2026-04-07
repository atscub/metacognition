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