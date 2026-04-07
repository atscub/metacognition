Let me decompose this problem from first principles:

## **Step 1: Core Problem (No Jargon)**

We have 200 customers sharing one database. Some customers are big (lots of data), some are small. Queries for big customers are slow because they're scanning huge tables. We need it to be fast. We also need to make sure customer data stays private. And in 2 years we'll have 1,000 customers.

## **Step 2: Atomic Components**

**Inputs:**
- A query arrives with a customer ID
- Customer data stored in database tables

**Outputs:**
- Fast query results (sub-second for dashboard)
- Absolute certainty customer A can't see customer B's data
- Ability to report metrics across all customers

**Constraints:**
- Max 3-4 database instances (DevOps hard constraint)
- Three enterprise customers have compliance contracts (specific requirements unknown)
- Must scale to 1,000 customers
- Database is 340 GB today; growing

**Dependencies:**
- ORM must know how to find the right data
- Query results must be correct
- Backups/recovery must work
- Monitoring must work

**Core transformation:**
```
Customer ID + SQL Query → (find right data) → results
```

## **Step 3: Question Each Component**

| Component | Question | Answer |
|-----------|----------|--------|
| Shared database | Do all 200 customers *need* to be in one DB? | No. It's an operational choice, not a functional requirement. |
| App-level filtering | Is `WHERE tenant_id = ?` actually protective? | No. It's a filter, not a wall. A single bug bypasses it. |
| RLS policies | Does adding policy rules to the DB actually solve performance? | No. A slow query with a WHERE clause is still slow. |
| Single index per table | Must all customers share `idx_workflows_tenant`? | Only if they're in one table. If separated, each customer gets its own index. |
| One schema | Do 200+ customers *need* one schema? | No, that's just how it was built. |
| One instance | Do all 200 customers fit in one RDS instance? | Yes, at db.r6g.2xlarge (340GB data). But the largest 5 take 60+ GB. |

**Critical insight:** The performance problem isn't isolation—it's *scale within a shared index*. The enterprise tenant's 50K workflows in a shared `workflow_runs` table means the index has to be enormous and covers workflows from all 200 customers mixed together.

## **Step 4: Rebuild from Fundamentals**

**Core requirement:** Fast queries for each customer, given their ID + SQL.

**Simplest version that works:**
```
Query arrives with customer_id
├─ Find which database/schema has that customer
├─ Connect to it
├─ Run the query
└─ Return results
```

This is just a routing layer + topology. No RLS, no magic.

**Add constraints back, one at a time:**

1. *"Must be fast"* → Smaller datasets per query. Option: don't mix customers in same table.
   - If customer gets own schema/DB, indexes are smaller.
   - If customer stays in shared table, indexes are large. **This trades off speed vs. simplicity.**

2. *"Data must be private"* → Need a guarantee customer A can't see B's data.
   - App-level filtering: not a guarantee (code bugs exist)
   - DB-level enforcement: RLS or physical separation
   - **Simplest guarantee: physical separation** (different schema or different DB). Can't query across boundaries.

3. *"Need cross-customer analytics"* → Aggregate metrics across all customers.
   - Can't do this with physical separation (by design).
   - Solution: separate system for this. ETL or replicated/summarized data.
   - **This is a separate concern from operational queries.**

4. *"Compliance contracts"* → Unknown specifics, but Sales noted "data handling."
   - Could mean: data residency, physical isolation, audit trail, encryption, regulatory certification
   - Without knowing, assume worst case: **physical isolation needed**
   - Solution: **separate database instances for enterprise tier**

5. *"Max 3-4 instances"* → Can't do pure db-per-tenant for all 200.
   - Solution: **tiered approach**. Some customers in shared DB, others in dedicated instances.
   - How to split? By risk/value. Enterprise = dedicated. Everyone else = shared.

**Rebuilt architecture:**

```
Tier 1 (5 enterprise): Dedicated DB per customer (each needs own instance for compliance)
Tier 2 (195 others): Shared DB, schema-per-tenant (fast, no compliance issue)

Shared DB sits on 1 instance (main) → stores 195 schemas
Enterprise tier uses 3-4 additional instances (1 or more customer per instance)

Analytics layer (separate): ETL/replication from operational DBs
```

---

## **Step 5: Compare with Proposed Options**

| Option | Strengths | Weaknesses | Verdict |
|--------|-----------|-----------|---------|
| **Shared DB + RLS** | Simple, unified | Doesn't fix speed; RLS isn't a compliance wall; ignores enterprise needs | ❌ Fails on performance and compliance |
| **Schema-per-tenant (all)** | Fast, scales well, clear isolation | One instance still limits compliance guarantees; doesn't meet DevOps constraint for enterprise | ⚠️ Better, but incomplete |
| **DB-per-tenant (all)** | Best isolation, true scaling | Needs 50+ instances for 200 customers; DevOps says max 4; doesn't fit constraint | ❌ Doesn't fit constraints |
| **Hybrid: Tiered approach** | Fast for all; compliance for enterprise; fits DevOps constraint; scales to 1K | More complex topology; federation needed for analytics | ✅ **Fits all constraints** |

---

## **Recommended Approach: Tiered Multi-Tenancy**

### **Topology**

```
MAIN INSTANCE (db.r6g.2xlarge)
├─ Schema: tenant_001 (small)
├─ Schema: tenant_002 (mid)
├─ ... (195 schemas total)
└─ Schema: tenant_195

ENTERPRISE INSTANCES (3 additional instances)
├─ Instance 1: database for MegaCorp
├─ Instance 2: database for Acme Industries  
├─ Instance 3: database for GlobalBank (or shared with one other enterprise)

ANALYTICS DB
├─ Aggregated metrics/snapshots
├─ Updated hourly via ETL
└─ Powers cross-tenant dashboard
```

### **Why This Works**

✅ **Performance**: 
- Small/mid-market schemas: shared table per schema, small indexes → fast queries
- Enterprise: dedicated DB, no contention → 8-second dashboard becomes <1s

✅ **Compliance**:
- Enterprise tenants get dedicated database instances (can be in different regions/VPCs if needed)
- Contractual guarantee of isolation + technical guarantee (physical separation)
- Small customers don't over-pay for isolation they don't need

✅ **Scaling**:
- Main instance handles 500+ schemas before degradation (PostgreSQL can do 1000+)
- Enterprise tier adds instances only as needed (contract-driven, not scale-driven)
- Scales to 1,000 customers: main + 5-6 enterprise instances (fits constraint)

✅ **DevOps**:
- 3-4 instances (main + 3 enterprise), fits the constraint
- Clear topology (no dynamic instance creation)
- Monitoring/backups are routine (not per-customer)

✅ **Analytics**:
- ETL federation, not real-time queries
- No cross-tenant query performance risk
- Scalable to any number of tenants

---

### **Migration Plan (3 Months)**

**Phase 1: Schema-per-tenant (Week 1-2)** 
- Create 195 schemas in current DB (one per non-enterprise tenant)
- Migrate data from mixed tables to per-schema tables
- Update ORM to use `search_path` for schema switching
- Verify performance: expect 50-70% latency reduction for mid-market tenants

**Phase 2: Enterprise Instance Provisioning (Week 3)** 
- Provision 3 dedicated RDS instances (db.r6g.xlarge or sized per tenant demand)
- Create database schemas/tables in each
- Clarify compliance requirements with Sales (data residency, encryption, audit needs)
- Configure network/VPC isolation as required

**Phase 3: Enterprise Migration (Week 4-6)** 
- Migrate 5 enterprise customers to dedicated instances (one at a time, high-ceremony)
- Test failover/backup/recovery procedures
- Verify compliance checklist with legal/Sales

**Phase 4: Analytics Layer (Week 7-12)** 
- Build ETL pipeline (Fivetran, custom service, etc.) to replicate metrics from all DBs
- Create analytics database (small, separate instance)
- Develop dashboards against analytics DB, not operational DBs
- Test 1000-tenant capacity model

---

### **Immediate Action Items**

1. **Ask Sales for specifics**: Get exact compliance clauses from MegaCorp, Acme, GlobalBank contracts. This drives instance config.

2. **ORM migration scope**: Change search_path logic for schema switching. Should be ~2-3 days of engineering work per the team's estimate.

3. **Instance sizing**: Run query profiling on enterprise tenants. May need bigger instances than main DB to absorb their workload.

4. **Analytics design**: Product should specify which metrics are needed cross-tenant. This informs ETL schema.

---

**This approach delivers performance, compliance, scalability, and respects all stakeholder constraints—while avoiding the operational complexity of true db-per-tenant for all customers.**