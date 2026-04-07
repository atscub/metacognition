## Recommendation: Tiered Hybrid Architecture

No single option is right here. Each option was designed for a different threat model, and your tenant distribution plus the compliance situation demands a tiered approach. Here's my reasoning.

---

## Before anything else: compliance clause audit

The sales comment is the highest-priority unknown in this problem. "Their legal teams were very specific about data handling" and "we agreed to their terms" could mean:

- **Logical isolation only** (schema-level) → schema-per-tenant satisfies it
- **Physical isolation** (no row of their data lives with another tenant's data on shared storage) → dedicated RDS instance required
- **Data residency** (specific AWS region) → may require separate infrastructure entirely
- **Right to audit** → affects backup structure and access logging
- **Specific retention/deletion guarantees** → affects how partitions and backups work

Pull those clauses before committing to any architecture. If GlobalBank said "dedicated infrastructure" and you build schema-per-tenant, you've broken a contract. Get the exact language this week.

---

## Tiered architecture

```
┌─────────────────────────────────────────────────────────┐
│  Tier 0: Compliance enterprise (MegaCorp, Acme,         │
│  GlobalBank) — dedicated RDS instance each              │
│  (or shared if clauses permit)                          │
├─────────────────────────────────────────────────────────┤
│  Tier 1: Non-compliance enterprise (2 remaining) +      │
│  large tenants (15) — shared RDS, schema-per-tenant     │
├─────────────────────────────────────────────────────────┤
│  Tier 2: Small/mid-market (180 → ~980) — shared RDS,    │
│  shared schema + RLS + partitioning                     │
├─────────────────────────────────────────────────────────┤
│  Analytics replica — logical replication target for     │
│  cross-tenant ops dashboard                             │
└─────────────────────────────────────────────────────────┘
```

**Instance count reality check:** This is 4-6 instances vs DevOps's "prefer 3-4." That preference needs to bend for compliance. A broken enterprise contract costs more than managing two extra RDS instances. Frame it to DevOps: "The compliance clients are paying for dedicated infrastructure whether they know it or not — we already sold it."

---

## Why not the pure options

**Pure RLS (Option 1):** Doesn't solve the performance problem. The 290 GB table is still one physical object. Vacuuming it is still brutal. The largest tenant's dashboard still scans their millions of rows. RLS adds per-query overhead. This buys you security hygiene but not relief.

**Pure schema-per-tenant (Option 2):** 1,000 schemas is painful. DDL migrations become fan-out operations. Cross-tenant analytics requires ugly `UNION ALL` across 1,000 schemas or a separate ETL pipeline. Physical isolation (which you may already owe) isn't possible. You'd still need partitioning inside each schema for the enterprise tenants.

**Pure DB-per-tenant (Option 3):** 200 tenants today, 1,000 in two years — untenable operationally and financially. You'd spend more on RDS instances than on engineering.

---

## The immediate performance fix (do this now, independent of isolation strategy)

The 8-second dashboard load is a partitioning problem, not an isolation problem. Fix it now:

```sql
-- Step 1: Partition workflow_runs by time (the most common filter pattern)
CREATE TABLE workflow_runs_partitioned (
    id UUID NOT NULL,
    tenant_id UUID NOT NULL,
    workflow_id UUID NOT NULL REFERENCES workflows(id),
    status TEXT NOT NULL,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    result JSONB
) PARTITION BY RANGE (started_at);

-- Monthly partitions — tune granularity to your retention needs
CREATE TABLE workflow_runs_2026_01 
    PARTITION OF workflow_runs_partitioned
    FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');
-- etc.

-- Composite index: tenant_id first, then time
-- This serves "give me tenant X's recent runs" in O(partition size)
CREATE INDEX ON workflow_runs_2026_01 (tenant_id, started_at DESC);
CREATE INDEX ON workflow_runs_2026_01 (tenant_id, status) 
    WHERE status IN ('running', 'pending');  -- partial index for dashboard
```

For the enterprise tenants specifically, add a **hash sub-partition** layer:

```sql
CREATE TABLE workflow_runs_enterprise_2026_01
    PARTITION OF workflow_runs_2026_01
    FOR VALUES IN ('<enterprise_tenant_id>')
    -- later, move this partition to the dedicated instance
```

This alone should drop the dashboard query from 8s to under 500ms for the large tenant, because the planner eliminates 95%+ of partitions. Vacuum also becomes tractable — you can vacuum monthly partitions individually, and drop old partitions instead of running `DELETE`.

---

## Migration plan

### Phase 0: Performance triage (week 1-2)
- Partition `workflow_runs` by `started_at` range (monthly buckets)
- Add composite indexes `(tenant_id, started_at DESC)` per partition
- Run `ANALYZE` on new indexes
- Verify dashboard query plan hits partition pruning
- **Does not change application code** — ORM queries work unchanged

### Phase 1: Compliance client isolation (weeks 3-6)
- Get the exact contract language (do this in week 1 in parallel with Phase 0)
- Provision dedicated RDS instances for the 3 compliance clients
- Migrate their data: logical replication → cutover → verify → decommission from shared
- Update connection routing in the application (connection string by tenant tier, not per-tenant)

```python
# Minimal application change: tier-based routing
TENANT_TIER_CONNECTIONS = {
    "megacorp": dedicated_megacorp_pool,
    "acme": dedicated_acme_pool,
    "globalbank": dedicated_globalbank_pool,
    # all others: shared_pool
}

def get_connection(tenant_id: str):
    return TENANT_TIER_CONNECTIONS.get(tenant_id, shared_pool)
```

### Phase 2: Add RLS to shared DB (weeks 4-6, parallel with Phase 1)
Defense-in-depth. The app filtering isn't going away, but a misrouted query shouldn't be able to return another tenant's data.

```sql
ALTER TABLE workflows ENABLE ROW LEVEL SECURITY;
ALTER TABLE workflow_runs ENABLE ROW LEVEL SECURITY;

-- App sets this at connection time via SET LOCAL
CREATE POLICY tenant_isolation ON workflows
    USING (tenant_id = current_setting('app.tenant_id')::UUID);

CREATE POLICY tenant_isolation ON workflow_runs
    USING (tenant_id = current_setting('app.tenant_id')::UUID);
```

```python
# In the ORM session setup
with db.transaction():
    db.execute("SET LOCAL app.tenant_id = %s", [tenant_id])
    # all queries in this transaction are now RLS-filtered
```

### Phase 3: Large tenant schema isolation (weeks 6-10)
Move the 15 large tenants + 2 non-compliance enterprise tenants to schema-per-tenant on a dedicated "large tier" RDS instance. This gives them:
- Independent vacuum
- No cross-tenant index bloat
- Namespace isolation

```python
# ORM change: set search_path at connection checkout
def get_large_tenant_connection(tenant_id: str) -> Connection:
    conn = large_tier_pool.checkout()
    conn.execute(f"SET search_path TO tenant_{tenant_id_to_slug(tenant_id)}, public")
    return conn
```

Schema migration is a DDL fan-out — write a script that runs your migration files against each schema. This is the engineering investment they flagged, but it's bounded at ~17 schemas.

### Phase 4: Analytics infrastructure (weeks 8-12)
For the ops team dashboard, use logical replication to a dedicated analytics replica:

```
All tier instances → logical replication → analytics_db (read-only)
```

The analytics DB uses the shared schema structure (denormalized with tenant metadata), not the tiered structure. The ops dashboard queries hit only the analytics replica.

Alternatively, if you want simpler operations: pg_foreign_data_wrapper to federate queries across instances into a single analytics schema. This is lower throughput but zero additional infra.

---

## Scaling to 1,000 tenants

- **Small/mid pool** handles ~980 tenants fine with partitioning and RLS. Hash-partition `workflow_runs` by `tenant_id` within the time partitions if needed.
- **Large tier** (schema-per-tenant): 200 schemas is operationally fine. Use a migration runner that parallelizes DDL across schemas.
- **Enterprise tier**: at 1,000 total tenants you probably have 25-50 enterprise clients. Each compliance contract should be priced to include dedicated infrastructure costs. The compliance tier scales by adding instances, not by re-architecting.

---

## Decision summary

| Concern | Solution |
|---|---|
| 8s dashboard load | Time-range partitioning on `workflow_runs` — **do immediately** |
| Vacuum bloat | Partitioning enables partition-level vacuum; old partitions can be dropped |
| Compliance isolation | Dedicated RDS per compliance client (pending clause review) |
| Cross-tenant analytics | Logical replication to analytics replica |
| 1,000 tenants | Small/mid pool scales with partitioning; large/enterprise tiers add instances |
| DevOps instance count | 4-6 instances — negotiate with DevOps against compliance contract risk |
| ORM changes | Tier-based connection routing (minimal); schema search_path for large tier |

The most important thing you can do this week is two things in parallel: start the partitioning work (no coordination required, purely additive), and get those contract clauses from legal. Everything else flows from those two.