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