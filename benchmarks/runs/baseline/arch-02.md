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