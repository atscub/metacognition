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
## Recommendation: Tiered Hybrid Architecture

None of the three options alone is correct. The right answer is a tiered model that matches isolation level to tenant requirements.

---

## The Core Diagnosis First

Before choosing an isolation model, name the actual problems:

1. **The `workflow_runs` table is unpartitioned at 290 GB.** This is the root cause of the 8-second dashboard and vacuum failures — not the isolation model. Any approach you pick will degrade the same way without fixing this.
2. **Application-level tenant filtering is a security liability.** One missing `WHERE tenant_id = ?` leaks data across tenants.
3. **The compliance situation is underspecified.** Sales closed deals with contractual data-handling commitments you don't fully know yet.

---

## Architecture: Three Tiers

```
┌─────────────────────────────────────────────────────────┐
│  Tier 1: Dedicated RDS instances (compliance tenants)    │
│  MegaCorp ── [db.r6g.2xlarge]                           │
│  Acme      ── [db.r6g.2xlarge]                          │
│  GlobalBank── [db.r6g.2xlarge]                          │
└─────────────────────────────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────┐
│  Tier 2: Shared RDS instance (everyone else)            │
│  [db.r6g.4xlarge or r6g.8xlarge]                       │
│  • PostgreSQL RLS enforcing tenant isolation            │
│  • workflow_runs partitioned by tenant_id (hash, 32)   │
│  • 15 large + 180 small/mid tenants today              │
│  • Room for ~970 more tenants at 1,000-tenant target   │
└─────────────────────────────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────┐
│  Tenant Router (app layer)                              │
│  Maps tenant_id → connection string at request time    │
└─────────────────────────────────────────────────────────┘
```

**Total instances: 4.** Within the DevOps constraint.

---

## Why Not the Pure Options

**RLS-only (Option 1):** Doesn't fix the performance problem — `workflow_runs` is still one 290 GB table. RLS adds per-row policy evaluation overhead. It also can't satisfy the enterprise compliance requirements, which almost certainly require physical data separation.

**Schema-per-tenant (Option 2):** Gives you namespace isolation but not process or storage isolation. The vacuum and performance issues persist because PostgreSQL's autovacuum still sees one giant heap. At 1,000 tenants, 1,000 schemas in `pg_catalog` becomes its own overhead. Cross-tenant analytics degrades to `SET search_path` gymnastics or `dblink` queries.

**DB-per-tenant (Option 3):** Violates the DevOps constraint at current scale and is completely unworkable at 1,000 tenants. Cross-tenant analytics becomes a data warehouse problem rather than a query problem.

---

## The Performance Fix (Required Regardless of Isolation Choice)

Partition `workflow_runs` immediately. This is the highest-leverage change and is independent of which isolation tier a tenant lands in.

```sql
-- New partitioned table
CREATE TABLE workflow_runs_v2 (
    id UUID NOT NULL,
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    workflow_id UUID NOT NULL REFERENCES workflows(id),
    status TEXT NOT NULL,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    result JSONB
) PARTITION BY HASH (tenant_id);

-- 32 partitions (adjust based on tenant count growth)
CREATE TABLE workflow_runs_v2_p0  PARTITION OF workflow_runs_v2
    FOR VALUES WITH (MODULUS 32, REMAINDER 0);
-- ... repeat for p1-p31

-- Composite index within each partition
CREATE INDEX ON workflow_runs_v2 (tenant_id, started_at DESC);
CREATE INDEX ON workflow_runs_v2 (tenant_id, status) WHERE status != 'completed';
```

What this fixes:
- **Vacuum**: Each partition is vacuumed independently. Bloat from one tenant doesn't block others.
- **Query performance**: The planner prunes to the relevant partition(s) before scanning. The largest tenant's 8-second dashboard query should drop to under 500ms.
- **Index size**: Per-partition indexes are a fraction of a monolithic index.

The migration is a one-time `INSERT INTO workflow_runs_v2 SELECT * FROM workflow_runs` with a cutover window. Use logical replication or a trigger-based dual-write if you need zero downtime.

---

## RLS on the Shared Instance

Add RLS as a defense layer, not a replacement for application filtering. Keep both — defense in depth:

```sql
ALTER TABLE workflows ENABLE ROW LEVEL SECURITY;
ALTER TABLE workflow_runs ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON workflows
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);

CREATE POLICY tenant_isolation ON workflow_runs
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);

-- Application sets this at connection time:
-- SET app.current_tenant_id = '<uuid>';
```

This means a bug in the ORM that drops the `WHERE tenant_id = ?` clause now returns zero rows instead of all tenants' data.

---

## Compliance: Clarify Before You Migrate

Before provisioning the 3 dedicated instances, get the exact contract clauses from Sales. "Compliance requirements" could mean:

| Requirement | What it changes |
|---|---|
| Data not co-mingled with other tenants | Dedicated DB instance ✓ |
| Data residency in specific AWS region | Dedicated instance + specific region |
| Customer-managed encryption keys | RDS with customer KMS key |
| Right to audit infrastructure | Documentation + access controls |
| SOC 2 Type II scoping | Potentially a shared instance is fine |

Some of these a shared instance handles fine; others require dedicated. Don't over-provision (or under-provision) until you know.

---

## Migration Plan

### Phase 1 — Emergency stabilization (Weeks 1–3)
- Upgrade the shared instance from `r6g.2xlarge` to `r6g.4xlarge` (buys breathing room)
- Add the composite index `(tenant_id, started_at DESC)` on `workflow_runs` immediately (online, no downtime)
- Identify and kill the specific slow queries for the largest tenant's dashboard; cache the results in Redis as a stopgap

### Phase 2 — Partition workflow_runs (Weeks 3–6)
- Create `workflow_runs_v2` partitioned table
- Backfill data in batches (off-peak, to avoid I/O saturation)
- Dual-write new runs to both tables via trigger during migration
- Cut over reads tenant-by-tenant (start with smallest tenants, verify, progress to largest)
- Drop `workflow_runs` after validation

### Phase 3 — Compliance tenant isolation (Weeks 6–10)
- Retrieve exact contract clauses from Sales
- Provision dedicated RDS instances for the 3 enterprise compliance tenants (matching their contractual specs)
- Build tenant routing layer in the application: `get_connection(tenant_id) -> connection_string`
- Migrate each compliance tenant's data to their dedicated instance
- Verify isolation, then remove their data from the shared instance

### Phase 4 — RLS hardening (Weeks 10–14)
- Enable RLS on shared instance tables
- Wire `app.current_tenant_id` into every database session from the application layer
- Run parallel validation: compare RLS-filtered results against application-filtered results for a shadow period
- Keep application-level filtering as a second layer

### Phase 5 — Cross-tenant analytics (Weeks 14–18)
- For the shared instance: analytics queries work natively (service account with RLS bypass)
- For dedicated instances: set up read replicas and a lightweight ETL (could be as simple as `postgres_fdw` on a read-only analytics connection, or a proper pipeline into Redshift/BigQuery if the ops team needs historical depth)

---

## Scaling to 1,000 Tenants

The tiered model handles this cleanly:

- **New small/mid tenants** → land in Tier 2 (shared instance). The partitioned schema absorbs them with no schema changes.
- **New large tenants** → same Tier 2. If the shared instance hits capacity (CPU/memory), add a second shared instance for a "large tenant pool" — still ≤4-6 total instances.
- **New compliance/enterprise tenants** → charge a premium that offsets the dedicated instance cost. Provision with automation (Terraform module + seeding script).

The tenant router becomes the key abstraction. It's a simple lookup table:

```python
TENANT_CONNECTIONS = {
    "megacorp-uuid": "postgresql://...megacorp-rds.../tenantflow",
    "acme-uuid":     "postgresql://...acme-rds.../tenantflow",
    "default":       "postgresql://...shared-rds.../tenantflow",
}

def get_db(tenant_id: str):
    dsn = TENANT_CONNECTIONS.get(tenant_id, TENANT_CONNECTIONS["default"])
    return connection_pool[dsn].get_connection()
```

Once this indirection exists, moving a tenant between tiers is a data migration + a config change, not an architecture change.

---

## What to Watch Out For

1. **Don't schema-per-tenant the 15 large tenants** — I've seen teams do this hoping it helps performance. It doesn't, because it's still one PostgreSQL process. Partitioning is the right fix.

2. **PgBouncer in front of all instances** — connection pooling is non-negotiable before you hit 200+ concurrent connections per instance. Add it in Phase 1 or 2.

3. **The compliance gap is the highest-risk item** — if the contracts say "dedicated hardware" or "single-tenant infrastructure," you may need to provision faster than the plan above. Get those clauses now.

4. **Don't add RLS to the dedicated instances** — RLS is defense-in-depth for the shared instance where cross-tenant bugs are possible. Dedicated instances have no other tenants to leak to; RLS there just adds overhead.

## Response B
## Socratic Protocol: Working Through the Decision

Before recommending, I need to apply the checklist to avoid the failure modes most likely to trip me here: **pattern matching** ("use separate DBs for enterprise — everyone does"), **anchoring** (the first credible answer), and **premature closure** (picking an isolation strategy without noticing the performance and isolation problems are largely orthogonal).

---

### Step 1: Explicitize My Assumptions

| Assumption | Confidence | Risk if wrong |
|---|---|---|
| The compliance clauses require physical DB separation | **Low** — Sales said "I can dig up the exact clauses" | **Critical** — this could pre-determine the answer contractually |
| The 8-second load is caused by cross-tenant index bloat | Medium — plausible from the data | Moderate |
| DevOps's "3-4 instances" is a hard limit | Low — stated as preference | Moderate |
| Schema-per-tenant at 1,000 schemas is operationally viable | Medium | High (catalog bloat, shared autovacuum queue) |
| RLS satisfies enterprise compliance | **Unknown** — depends on those contracts | **Critical** |

**The most dangerous assumption in the room**: that compliance is a tiebreaker that can be evaluated after choosing an approach. Sales closed three enterprise deals with specific contractual data-handling commitments, and those commitments may have already answered the isolation question.

---

### Step 2: The Problem I Almost Misframed

There are **two distinct problems** being conflated:

1. **Performance**: `workflow_runs` (290 GB) is causing slow dashboards and vacuum failures
2. **Isolation**: tenant data separation, compliance, security boundaries

Every option in the evaluation matrix (RLS, schema-per-tenant, db-per-tenant) is primarily an **isolation strategy**. None of them are primarily a performance strategy. The cross-tenant index bloat and vacuum issues are symptoms of missing **table partitioning**, not missing isolation.

This matters because: you can fix the performance crisis immediately, regardless of which isolation model you choose. Conflating the two makes the decision feel more urgent and harder than it is.

---

### Step 3: Steelmanning Each Approach

**Strongest case for RLS:**
Cleanest for cross-tenant analytics (no federation required), scales to 1,000 tenants with no per-tenant operational overhead, no connection pool fragmentation, existing ORM works. PostgreSQL RLS is mature and enforced at the kernel level — not app code.

**Strongest case for schema-per-tenant:**
Per-tenant table statistics improve query planner accuracy (significant for tenants with very different cardinalities). Easier per-tenant schema migrations and customization. Data export/GDPR erasure is straightforward — dump one schema. Doesn't require separate connection management.

**Strongest case for database-per-tenant:**
True physical isolation — no shared buffer pool contamination between noisy-neighbor tenants. The only model that credibly satisfies "physical separation" compliance language. Dedicated autovacuum, dedicated connection pool, complete blast radius containment.

---

### Step 4: What Would Change My Mind

- **The actual contract clauses** — if they say "physically isolated database instance," RLS is off the table for those three clients regardless of technical merit.
- **Autovacuum configuration** — if the vacuum issues are actually misconfiguration (too-low `autovacuum_vacuum_scale_factor` for large tables), partitioning solves it without any isolation change.
- **The analytics dashboard requirement** — cross-tenant aggregation is significantly harder with db-per-tenant and adds latency regardless.

---

## Recommendation

### Phase 0: Immediate Performance Fix (Week 1–2, orthogonal to isolation model)

The vacuum and dashboard latency issues are fixable **now**, before touching the isolation architecture.

```sql
-- Convert workflow_runs to a partitioned table by tenant bucket
-- Group tenants: individual partitions for the 5 enterprise + 15 large tenants,
-- a combined partition for small/mid.

CREATE TABLE workflow_runs_new (
    id UUID NOT NULL,
    tenant_id UUID NOT NULL,
    workflow_id UUID NOT NULL REFERENCES workflows(id),
    status TEXT NOT NULL,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    result JSONB
) PARTITION BY LIST (tenant_id);

-- One partition per enterprise tenant (5 partitions)
CREATE TABLE workflow_runs_megacorp
    PARTITION OF workflow_runs_new FOR VALUES IN ('<megacorp-uuid>');

-- One partition per large tenant (15 partitions)
-- Small/mid tenants share a default partition
CREATE TABLE workflow_runs_default
    PARTITION OF workflow_runs_new DEFAULT;
```

This gives each large/enterprise tenant its own autovacuum queue, its own index, and eliminates cross-tenant index bloat. The 8-second dashboard load drops to sub-second range because queries against `workflow_runs_megacorp` scan only that tenant's ~40 GB partition rather than 290 GB.

Migration: use `pg_partman` for automated partition management. Online migration with `pg_repack` or logical replication into the new table.

---

### Phase 1: Get the Contract Terms Before Choosing an Isolation Model

**Do this before writing architecture docs or committing engineering time.** Ask Sales to retrieve the exact data handling clauses from MegaCorp, Acme, and GlobalBank. The critical question is whether they require:

- **Physical isolation** ("data must reside in a dedicated database instance not shared with any other tenant") → mandates database-per-enterprise-tenant
- **Logical isolation** ("access controls must prevent cross-tenant data access") → satisfied by RLS
- **Data residency** (geographic constraints) → separate concern, handled at the infrastructure layer

If you don't have this answer, you risk either breaching contracts (by choosing RLS when physical isolation was promised) or over-engineering (by building db-per-tenant when logical isolation would have sufficed).

---

### Phase 2: Tiered Hybrid Architecture (pending Phase 1 outcome)

Based on the constraints — DevOps wants ≤3-4 instances, CTO needs to scale to 1,000 tenants — a tiered model is the only realistic path:

```
┌─────────────────────────────────────────────────┐
│  Tier A: Enterprise (5 tenants)                 │
│  1–2 dedicated RDS instances                    │
│  db.r6g.4xlarge per instance                    │
│  Physical isolation, dedicated resources        │
│  Satisfies "physical separation" compliance     │
└─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────┐
│  Tier B: Large (15 tenants) + Small/Mid (180+)  │
│  1–2 shared RDS instances (existing + one new)  │
│  Shared schema with PostgreSQL RLS              │
│  Table partitioning by tenant_id (Phase 0)      │
│  Scales cleanly to 1,000 tenants                │
└─────────────────────────────────────────────────┘
```

**Why not schema-per-tenant for the middle tier?** At 1,000 tenants in 2 years, 1,000 schemas in one PostgreSQL instance creates real operational pain: shared catalog lock contention on DDL, shared autovacuum scheduling, ORM `search_path` management across migrations. The complexity cost exceeds the benefit over RLS + partitioning.

**Why RLS over application-level filtering for the shared tier?**
```sql
-- RLS policy: enforced by Postgres, not bypassable via ORM bugs
ALTER TABLE workflows ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON workflows
    USING (tenant_id = current_setting('app.current_tenant_id')::UUID);

-- App sets this at connection time (not per-query)
SET app.current_tenant_id = '<tenant-uuid>';
```

The security property improves — a bug in ORM query generation can't leak data across tenants because the database enforces isolation regardless. The app-level filtering becomes defense-in-depth rather than the sole barrier.

**Cross-tenant analytics for the internal ops dashboard:**
```sql
-- Works trivially on the shared tier (RLS disabled for internal role)
CREATE ROLE internal_analytics;
ALTER TABLE workflow_runs FORCE ROW LEVEL SECURITY; -- optional: use a bypass policy
GRANT SELECT ON ALL TABLES IN SCHEMA public TO internal_analytics;

-- For enterprise tier data: use a federated query approach
-- (postgres_fdw to each enterprise DB, or ETL into a separate analytics schema)
```

The analytics requirement is the one place db-per-tenant creates real friction. For the 5 enterprise tenant DBs, you'll need either `postgres_fdw` federation or a nightly ETL into a read-only analytics store. Plan for this upfront — don't bolt it on.

---

### Instance Count: DevOps Constraint

| Instance | Purpose | Estimated size |
|---|---|---|
| Shared primary | 180 small + 15 large tenants | db.r6g.4xlarge |
| Shared replica | Read traffic, analytics queries | db.r6g.2xlarge |
| Enterprise cluster A | MegaCorp + Acme | db.r6g.2xlarge (or larger) |
| Enterprise cluster B | GlobalBank (if compliance requires separate) | db.r6g.2xlarge |

That's 3-4 instances. It respects the DevOps preference and gives physical isolation to the tenants who need it.

---

### What I'm Not Confident About

1. **The compliance clauses** — the entire enterprise tier architecture could be wrong if the contracts say something different. This is the highest-risk unknown.
2. **Whether the current vacuum issues are misconfiguration** — it's possible that tuning `autovacuum_vacuum_scale_factor` and `autovacuum_vacuum_cost_delay` on the current instance gives you months of runway before partitioning is needed.
3. **The "cross-tenant index bloat" diagnosis** — this is described but not measured. Confirm with `pg_stat_user_tables` before assuming it's the root cause.

**The check that could disprove this recommendation**: if the compliance contracts require physical isolation for all tenants (not just enterprise), then RLS for the shared tier fails compliance requirements and the whole model collapses toward db-per-tenant with fleet management tooling.

---

### Summary Decision Path

```
Step 1: Implement table partitioning on workflow_runs (fixes performance now)
Step 2: Get the actual contract clauses from Sales (unblocks architecture)
Step 3: Based on Step 2:
  - "Physical separation" required → tiered hybrid with enterprise DB per client
  - "Logical isolation" sufficient → RLS on shared DB, no enterprise tier needed
Step 4: Migrate to RLS on shared tier (replace app-level filtering)
Step 5: Onboard enterprise tenants to dedicated instances with migration tooling
```

Don't let the performance crisis pressure you into making the isolation decision before you have the compliance answer. Partitioning buys the time to get it right.

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
