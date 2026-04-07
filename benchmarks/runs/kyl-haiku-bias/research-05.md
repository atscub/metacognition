## Premortem: PostgreSQL 50M Row Migration

### Step 1: State the Plan
**What we're considering**: Add a single column with a default to a 50M-row production table without downtime, using either:
- Expand-contract pattern (add nullable → backfill in batches → add default → add NOT NULL)
- pgroll (structured migration tool)
- pg_repack or native PostgreSQL 15 features

**Success means**: Column is added, all rows have the value, zero customer downtime, rollback is safe.

**Key assumptions being made**: That standard PostgreSQL locking is what caused the 45-minute timeout last time, and that the expand-contract pattern avoids it.

---

### Step 2: What Could Fail — Likely Scenarios

| Failure Mode | Why It Happens | Impact |
|---|---|---|
| **Expand-contract backfill hangs/times out** | Backfilling 50M rows, even in batches, is slow. If batch size is wrong or there's lock contention, batches stall indefinitely. Meanwhile, the ALTER TABLE DDL queue is blocked. | 30+ min degradation, possible cascading failures |
| **We don't actually know what caused the 45-min lock** | Previous outage might not have been the DEFAULT constraint. If it was index creation, expand-contract doesn't help. | We waste effort on the wrong solution |
| **Expand-contract is incompatible with Rails migrations** | Rails has assumptions about atomicity. Breaking a migration into 4 steps with application coordination is complex and error-prone. | Deployment fails or requires manual intervention |
| **AWS RDS restrictions** | Some tools (pg_repack, pgroll) may not work on RDS without special config or may be blocked. | Choose a tool that doesn't work in your environment |
| **Application doesn't handle NULL in the column** | Code expects subscription_tier to always have a value. Even during backfill, app might crash or return wrong tier. | Downtime during the backfill phase |
| **Rollback is impossible mid-way** | If the migration fails after 30M rows are backfilled, rolling back is manual and slow. | Stuck in a broken state, extended incident |

---

### Step 3: Critical Unknowns (Verify These NOW)

These determine your best path forward:

1. **What caused the 45-minute lock?**
   - Was it the DEFAULT constraint, or something else in that migration?
   - Do you have the migration code or Rails logs from last time?
   - This is answerable — check git history or ask the team.

2. **PostgreSQL 15 capabilities**
   - PostgreSQL 15+ supports adding columns with defaults much more efficiently than older versions
   - Does your version support deferred constraint checking or other optimizations?

3. **AWS RDS specifics**
   - Does RDS allow pgroll? pg_repack? Parameter Group changes for autovacuum tuning?
   - Are there Enhanced Monitoring details from the last migration showing where the lock occurred?

4. **Rails deployment model**
   - Can you deploy code, then run migration, then verify? Or is it all atomic?
   - Does your app need the column to exist before code is deployed, or after?

---

### Step 4: Risk Assessment

| Risk | Likelihood | Impact | Reversibility | Priority |
|---|---|---|---|---|
| Expand-contract is overly complex for this case | **HIGH** | Medium | Hard | 🔴 **HIGH** |
| We're solving the wrong problem (last lock wasn't the DEFAULT) | **MEDIUM-HIGH** | High | Hard | 🔴 **HIGH** |
| Backfill stalls on contention with 200 req/s app | **MEDIUM** | High | Hard | 🔴 **HIGH** |
| PostgreSQL 15 has a simpler built-in solution we don't know about | **MEDIUM** | High | Easy (if we know) | 🟡 **MEDIUM** |
| Tool choice (pgroll vs native) is sub-optimal | **LOW** | Medium | Easy (redo it) | 🟢 **LOW** |

---

### Step 5: What I'm Missing (Knowledge Gaps)

Before I recommend an approach, I need to be honest:

1. **PostgreSQL 15 specifics**: I know that version 15+ improved column addition, but I haven't verified exactly what's available in a constraint context. This is important and verifiable.

2. **AWS RDS + pgroll/pg_repack compatibility**: I'm not certain which tools work seamlessly on RDS vs. self-hosted Postgres.

3. **What actually broke last time**: This is the *most critical* unknown. If the 45-minute lock wasn't the DEFAULT but something else, you'll waste weeks on the wrong strategy.

---

## My Recommendation

**Before choosing a strategy, do this first** (takes 30 mins):

```sql
-- Check your Postgres version capabilities
SELECT version();

-- Examine the previous migration in git
git log --all --oneline -- db/migrate | grep -i users | head -5
git show <commit>  # Show that migration

-- Check what actually held the lock (if you have logs)
-- Query AWS RDS Enhanced Monitoring from ~45 min ago
-- Look for: exclusive locks, long-running queries, connection counts
```

Once you answer "what locked before?" you'll know whether to:

- **Use native PostgreSQL 15** if it's just a DEFAULT constraint (likely fastest, simplest)
- **Use pgroll** if you need safety guarantees and compatibility with RDS
- **Use pg_repack** if table rewriting is unavoidable and you need to keep it online
- **Use expand-contract** if the above don't work (most complex, most error-prone)

**The real issue**: You're biased toward expand-contract because it *sounds* safer (distributed, reversible), but for a single column with a default, it's likely overkill and introduces more failure points than it eliminates.

---

**Want me to help you investigate what actually caused the 45-minute lock?** That's where I'd start — it's one verified fact that changes everything.