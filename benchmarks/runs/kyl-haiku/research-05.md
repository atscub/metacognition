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