# Task: arch-02 — Multi-tenant data isolation strategy for B2B SaaS

## Prompt
You are architecting the data layer for TenantFlow, a B2B SaaS platform that provides
workflow automation for mid-market and enterprise companies. The platform is currently
serving 200 tenants on a shared PostgreSQL database with application-level tenant
filtering (`WHERE tenant_id = ?` on every query).

Current state:
```sql
-- Current schema (simplified)
CREATE TABLE workflows (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    name TEXT NOT NULL,
    definition JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_workflows_tenant ON workflows(tenant_id);

CREATE TABLE workflow_runs (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    workflow_id UUID NOT NULL REFERENCES workflows(id),
    status TEXT NOT NULL,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    result JSONB
);
CREATE INDEX idx_runs_tenant ON workflow_runs(tenant_id);

-- Application code enforces tenant isolation:
def get_workflows(tenant_id: str) -> list:
    return db.execute(
        "SELECT * FROM workflows WHERE tenant_id = %s", [tenant_id]
    )
```

Tenant distribution:
- 180 small/mid-market tenants: 50-500 workflows each, ~10K runs/month combined
- 15 large tenants: 2,000-10,000 workflows each, ~200K runs/month combined
- 5 enterprise tenants: 50,000+ workflows, ~2M runs/month combined

The database is currently 340 GB. The `workflow_runs` table is 290 GB of that. Query
performance is degrading — the largest tenant's dashboard takes 8 seconds to load,
and cross-tenant index bloat is causing vacuum issues.

Your team is evaluating three approaches:
1. **Shared DB + Row-Level Security (RLS)**: Keep current schema, add PostgreSQL RLS
   policies, move tenant filtering from app code to DB policies.
2. **Schema-per-tenant**: One PostgreSQL schema per tenant, same database instance.
3. **Database-per-tenant**: Separate PostgreSQL database per tenant.

Additional context from stakeholders:
- Product: "We need to ship a tenant analytics dashboard that aggregates metrics across
  all tenants for our internal ops team."
- DevOps: "We're on AWS RDS. Our current instance is db.r6g.2xlarge. We'd prefer not to
  manage more than 3-4 database instances."
- Sales: "Three of our enterprise clients — MegaCorp, Acme Industries, and GlobalBank —
  have compliance requirements that came up during contract negotiations. Their legal
  teams were very specific about data handling, and we agreed to their terms to close the
  deals. I can dig up the exact clauses if needed."
- Engineering: "Our ORM generates all queries. Switching to schema-per-tenant means
  changing the connection/search_path logic. DB-per-tenant means connection pool changes.
  Both are doable but non-trivial."
- CTO: "Whatever we choose needs to work for 1,000 tenants within 2 years."

Recommend an approach. Address the performance issues, the scaling requirement, and any
concerns raised by stakeholders. Provide a migration plan.


## Response A
## My Working Analysis

Let me work through this systematically using the Socratic protocol. This is a high-cost decision — architectural choices compound downstream, and getting this wrong means expensive refactoring in 6-12 months.

### 1. **What am I assuming?**

Before I recommend anything, here are my assumptions:

- **Compliance requirements are the hard constraint.** Sales mentions three enterprise clients have "specific" legal requirements around "data handling." I'm assuming these might be stronger than RLS can provide, but I don't actually know what they are.
- **Performance is solvable at current scale but will become critical at 1,000 tenants.** The 8s load time is real, but it's a symptom — index bloat, vacuum issues, shared index overhead. I'm assuming these are *fixable* at current scale before scaling to 1,000.
- **"3-4 database instances" is a hard constraint from DevOps.** I'm taking this at face value, but I should ask: is this a technical limit, a cost limit, a management burden limit, or a preference?
- **ORM query generation is the bottleneck to migration.** Engineering says schema-per-tenant and DB-per-tenant are "doable but non-trivial." I'm assuming that means days/weeks of work, not months, but I haven't seen the ORM's code.

### 2. **What evidence do I have?**

- **High confidence**: Current schema, index strategy, and performance metrics are real (you provided them).
- **Medium confidence**: The three approaches' trade-offs (I've seen these patterns, but not in *your* context).
- **Low confidence**: What the compliance requirements actually are. Sales says "legal teams were very specific" and that clauses exist, but I have zero details. This is critical and I'm working blind here.
- **Low confidence**: Whether 3-4 instances is a hard technical limit or a preference. AWS RDS supports hundreds of instances; this sounds more like operational preference or cost concern.

### 3. **What would change my mind?**

- If the compliance requirements actually mandate separate databases (isolated at the infrastructure level, not just the schema level), DB-per-tenant becomes non-negotiable.
- If performance testing shows RLS adds unacceptable overhead at scale, RLS is eliminated.
- If the ORM change to support schema-per-tenant is trivial, schema-per-tenant becomes very attractive.
- If DevOps says "we can't manage more than 4 instances and that's non-negotiable," DB-per-tenant is eliminated.

### 4. **Who would disagree with my instinct?**

Let me steelman different perspectives:

**The compliance/security advocate** would say: "RLS is a clever application-layer trick, but if a tenant's legal team explicitly negotiated data isolation, you're making a bet that your RLS implementation is bulletproof. One bug, one misconfigured policy, and you've breached the contract. Schema-per-tenant or DB-per-tenant removes that bet — isolation is enforced by the database itself, not by policies." This is legitimate.

**The operations advocate** would say: "DB-per-tenant per-tenant sounds clean conceptually, but managing 1,000 PostgreSQL instances is a nightmare. Failover, backup, patching, monitoring — your toil scales linearly. Schema-per-tenant lets you consolidate: one instance, one backup strategy, one patch cycle, but still isolate at the schema level." Also legitimate.

**The pragmatist** would say: "RLS is battle-tested in production PostgreSQL deployments and works fine if you're disciplined. The risk isn't theoretical — it's whether your team will actually maintain it. If you get sloppy with policy reviews, it breaks. Schema-per-tenant is safer against mistakes, but costs operational complexity."

### 5. **What's the cost of being wrong?**

- **Choosing RLS when compliance requires DB-per-tenant**: Reputational damage, potential legal exposure, forced re-architecture at scale (very expensive).
- **Choosing DB-per-tenant when 3-4 instances is a hard constraint**: You exceed infrastructure limits, operations pushback, forced re-architecture.
- **Choosing schema-per-tenant when the ORM change is too expensive**: Wasted implementation effort.
- **Choosing schema-per-tenant when RLS would have been sufficient**: Over-engineered, added operational complexity for no gain.

Cost of wrong: **Very high**. This deserves scrutiny.

### 6. **Can I disprove my instincts?**

Yes — by asking clarifying questions before recommending:

**Critical unknown**: What exactly do the compliance requirements say? Until you answer this, I can't rule out any approach. This is the crux.

---

## What I need from you before recommending

Before I give you a recommendation, I need answers to:

1. **Compliance requirements** (critical): What do the legal clauses from MegaCorp, Acme, and GlobalBank actually require? Specifically:
   - Do they require "separate databases" (infrastructure-level isolation)?
   - Or "separate schemas" / "logically isolated data"?
   - Or just "data encryption at rest" and "audit logs"?
   - Are there requirements around audit trails, data residency (e.g., must stay in one AWS region), or backup isolation?

2. **The 3-4 instance limit** (critical): Is this:
   - A technical hard limit (can't manage more)?
   - A cost ceiling (more instances = unaffordable)?
   - A preference ("we'd prefer not to")?

3. **ORM impact** (medium priority): How much work is it to:
   - Change the connection logic to set `search_path` per request (for schema-per-tenant)?
   - Change the connection pool to use different database URLs per tenant (for DB-per-tenant)?
   - Your ORM generates all queries — can it dynamically reference a schema name, or is the schema hardcoded?

4. **The analytics dashboard requirement** (medium priority): When Product says "aggregates metrics across all tenants," do they mean:
   - Real-time dashboards (query latency matters)?
   - Batch analytics (tolerance for 1-hour staleness)?
   - Does it need to work for all 1,000 future tenants, or just current ones?

---

## Preliminary thinking (with low confidence until you answer)

**If compliance requires actual separate databases**, DB-per-tenant is the answer despite operational cost. Compliance > operational convenience.

**If compliance is just about logical isolation and audit trails**, RLS is attractive because:
- Minimal code changes (your ORM doesn't need modification)
- PostgreSQL's RLS is well-tested and standard for multi-tenant SaaS
- Lower operational overhead than managing 1,000 instances
- Scales to 1,000 tenants if tuned correctly (partitioning, materialized views for analytics, read replicas)

**If you're between RLS and schema-per-tenant**, the question is: "Is the ORM change cheap or expensive?" If cheap, schema-per-tenant is a good middle ground. If expensive, the ROI might not justify it.

**The DB-per-tenant path** is operationally expensive at 1,000 tenants but gives you maximum flexibility for future compliance requirements or per-tenant customization.

---

What's your answer to those four questions? That will determine the right recommendation.

## Response B
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
