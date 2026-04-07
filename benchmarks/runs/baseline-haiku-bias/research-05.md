I'd recommend the **expand-contract pattern** for your situation. Here's why the alternatives don't fit, and then I'll give you the exact implementation.

## Why the alternatives don't work for you

**Naive `ALTER TABLE ADD COLUMN DEFAULT`** — Rewrites entire table with `ACCESS EXCLUSIVE` lock. At 50M rows on RDS, expect 30-60 minutes of lock hold. During peak 200 req/s, you'll see connection timeouts immediately. (This is what happened last time.)

**pg_repack** — Rebuilds the table without an exclusive lock, but still rewrites all 50M rows. On your instance size, that's still 20-40 minutes of I/O saturation. Better than naive, but risky during peak hours. More overhead than you need.

**pgroll** — Solid tool, but over-engineered for a single nullable column. Adds deployment complexity and one more thing to learn mid-incident.

## The expand-contract pattern for your use case

This is the industry standard for a reason: it's safe, predictable, and you control every step. Here's how to do it:

```ruby
# db/migrate/[timestamp]_add_subscription_tier_to_users.rb

class AddSubscriptionTierToUsers < ActiveRecord::Migration[7.0]
  def up
    # Step 1: Add nullable column (FAST - seconds)
    add_column :users, :subscription_tier, :string, null: true
    
    # Step 2: Backfill in batches (SLOW - do off-peak if possible)
    batch_size = 2_000_000  # 2M rows per batch
    user_count = User.count
    batches = (user_count.to_f / batch_size).ceil
    
    puts "Backfilling #{user_count} rows in #{batches} batches of #{batch_size}..."
    
    batches.times do |i|
      offset = i * batch_size
      User.limit(batch_size).offset(offset).update_all(subscription_tier: 'free')
      
      puts "  Batch #{i + 1}/#{batches} complete"
      sleep(2)  # 2-second pause between batches to let replication catch up
    end
    
    # Step 3: Add default (FAST - seconds)
    change_column_default :users, :subscription_tier, 'free'
    
    # Step 4: Make NOT NULL (FAST on Postgres 11+ - just metadata change)
    change_column_null :users, :subscription_tier, false
  end

  def down
    remove_column :users, :subscription_tier
  end
end
```

## Critical operational steps

**Before you run this:**

1. **Test on staging** — Run the full migration on a staging DB with similar data volume. Time each step. Measure replication lag if you have a standby.

2. **Disable connection pooling limits temporarily** — During the backfill, you'll have slightly higher I/O. Make sure PgBouncer or your connection pool won't evict connections mid-batch.

3. **Monitor these during the migration:**
   ```sql
   -- Check table lock status (run this in a separate connection)
   SELECT 
     pid, 
     usename, 
     query, 
     state 
   FROM pg_stat_activity 
   WHERE query LIKE '%users%' AND state != 'idle';
   
   -- Check replication lag (if you have a standby)
   SELECT EXTRACT(EPOCH FROM (now() - pg_last_xact_replay_timestamp())) as lag_seconds;
   ```

4. **Run during off-peak if possible** — 2-4 AM in your timezone. The backfill steps don't lock the table, but they do consume I/O. During off-peak, you have margin for error.

5. **Have a rollback ready:**
   ```sql
   -- If something goes wrong mid-backfill, this is safe to run:
   ALTER TABLE users DROP COLUMN subscription_tier;
   -- Then re-run the migration after fixing the issue
   ```

## Key safety details

**Why batches?** — 50M rows all at once would generate massive WAL (write-ahead log) pressure and pin your replica behind. 2M-row batches let the replica keep up. Monitor `pg_stat_replication` lag; if it exceeds 10GB, increase the sleep duration.

**Why NOT NULL last?** — On Postgres 11+, adding `NOT NULL` is just a metadata update (no table rewrite). But only if all rows are already filled. If you reverse the order, you lock the table again.

**Application compatibility** — While the backfill is running, `users.subscription_tier` will be `NULL` for new users created before their batch backfills. Your Rails code must handle this:
   ```ruby
   # app/models/user.rb
   def subscription_tier
     self[:subscription_tier] || 'free'
   end
   ```
   Or safer, use `#fetch` in views: `user.subscription_tier || 'free'`

## Why this beats your last migration

Your last one took 45 minutes because the lock was held the entire time. This approach:
- Lock time: ~5 seconds total (Step 1 + 3 + 4 combined)
- Backfill time: ~15-20 minutes, *without any lock*
- Application can serve traffic the entire time

If you want even more safety, you can pause the migration mid-backfill: just stop the rake task, the partial column data is harmless, and re-run the migration later to pick up where it left off.

**One more thing:** Test the exact `change_column_null` behavior on your Postgres 15 version before production. On modern versions it's instant (just a pg_catalog metadata change), but double-check in your staging environment.