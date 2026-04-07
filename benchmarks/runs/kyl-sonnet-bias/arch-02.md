## Socratic Protocol Applied

Before recommending, let me work through this explicitly.

---

### Assumptions I'm making — flagged by confidence level

| Assumption | Confidence | Why it matters |
|---|---|---|
| The compliance clauses require physical data isolation | **Low — I haven't read them** | Could instead be about audit logging, encryption, geo-residency, or RBAC. This single unknown could invalidate any architectural choice. |
| The 8-second dashboard is a query performance problem | Medium | Could also be N+1 queries, missing materialized views, or ORM inefficiency — not necessarily fixed by isolation strategy |
| The ORM "doable but non-trivial" engineering estimate is accurate | Medium | Non-trivial migrations often take 3–5x the initial estimate |
| Tenant distribution stays roughly similar at 1,000 tenants | Low | If growth is enterprise-heavy, the math changes dramatically |

---

### Anchoring check — steelmanning each option before committing

**Strongest case for Shared DB + RLS:** The performance problem is solvable with PostgreSQL declarative partitioning by `tenant_id`, *without changing the isolation model at all*. RLS adds defense-in-depth. Cross-tenant analytics is trivial. DevOps stays on 1 instance. This is the simplest path, and complexity bias may be pulling me toward fancier solutions.

**Strongest case for Schema-per-tenant:** Per-tenant vacuuming eliminates the index bloat problem. Tenant data dumps for compliance/offboarding become trivial. The search_path trick is well-understood. You stay on ≤4 RDS instances while getting meaningful logical separation.

**Strongest case for DB-per-tenant:** True physical isolation is the only thing that will satisfy a strict financial services contract (GlobalBank). Connection pooling with PgBouncer handles the connection count. This is the only option that scales each tenant's storage and compute independently.

---

### Critical unknown I must surface before any recommendation

**The Sales comment is the most important signal in this entire problem, and it's the least specified:**

> *"Their legal teams were very specific about data handling, and we agreed to their terms to close the deals. I can dig up the exact clauses if needed."*

You need those clauses **before committing to any architecture**. Here's why:

- If GlobalBank's contract says "dedicated database instance": schema-per-tenant fails. Shared+RLS fails. Only DB-per-tenant passes.
- If it says "logically isolated with row-level access controls and audit logging": shared+RLS with good audit trails might pass.
- If it says "data must not reside in the same physical storage as other customers": you potentially need DB-per-tenant *and* dedicated RDS instances.

Architecting without reading those clauses is building on sand. **This is the one thing I'd block on.**

---

### What I'm NOT recommending, and why

**Option 1 alone (Shared DB + RLS only) without partitioning:** RLS doesn't address the vacuum bloat or query performance problem. Adding RLS to a 290GB table with cross-tenant index bloat makes vacuuming slightly worse (more predicate complexity). The 8-second load survives.

**Option 3 (DB-per-tenant for all 200 tenants):** Violates the DevOps constraint explicitly (200+ RDS instances, not 3-4). Cross-tenant analytics for the internal ops dashboard requires FDW or a separate ETL pipeline — substantial additional work. Ruled out at current scale.

---

### Recommendation: Tiered architecture, with an immediate tactical move

The right answer is not uniform — it matches isolation model to tenant tier. But the most important insight is that **the immediate performance fix is orthogonal to the isolation model decision.**

---

#### Move 0: Fix performance now (0–4 weeks, no isolation model change required)

The vacuum problem and query degradation on `workflow_runs` (290GB, your dominant table) are fixable with declarative partitioning by `tenant_id`. This requires no application code changes — queries with `WHERE tenant_id = ?` get automatic partition pruning.

```sql
-- Create partitioned replacement for workflow_runs
CREATE TABLE workflow_runs_partitioned (
    id UUID NOT NULL,
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    workflow_id UUID NOT NULL REFERENCES workflows(id),
    status TEXT NOT NULL,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    result JSONB,
    PRIMARY KEY (id, tenant_id)  -- partition key must be in PK
) PARTITION BY LIST (tenant_id);

-- Create one partition per enterprise/large tenant explicitly
CREATE TABLE workflow_runs_tenant_megacorp
    PARTITION OF workflow_runs_partitioned
    FOR VALUES IN ('megacorp-uuid-here');

-- Catch-all partition for small tenants initially
CREATE TABLE workflow_runs_small_tenants
    PARTITION OF workflow_runs_partitioned
    DEFAULT;
```

This immediately solves:
- **Vacuum bloat**: each partition is vacuumed independently
- **Query performance**: the largest tenant's dashboard scans one partition, not 340GB
- **Index size**: partition-local indexes, not one bloated cross-tenant index

Migrate with zero downtime: rename old table, backfill in batches, swap. Buys 6–12 months of runway while the strategic decision is made properly.

---

#### Strategic architecture: Three tiers

**Tier 1 — Small/mid-market (180 tenants)**: Shared PostgreSQL DB + RLS + partitioning

These tenants collectively represent ~5% of your run volume (10K runs/month combined). A single well-partitioned RDS instance handles them comfortably to 1,000 tenants. RLS provides defense-in-depth on top of application filtering — belt and suspenders.

```sql
-- RLS policy (enforces isolation at DB layer even if app code has a bug)
ALTER TABLE workflows ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON workflows
    USING (tenant_id = current_setting('app.tenant_id')::uuid);
```

Cross-tenant analytics for the ops dashboard: just bypass RLS with a superuser/analytics role that sets no tenant context. Trivial.

**Tier 2 — Large tenants (15 tenants)**: Schema-per-tenant within a dedicated "large tenant" RDS instance

These 15 tenants generate 200K runs/month combined — meaningful load, but not so extreme that they need physical DB separation. Schema-per-tenant gives:
- Independent vacuum per schema
- Clean tenant backup/restore (pg_dump one schema)
- Clear separation without 15 separate RDS instances

Engineering change: set `search_path` per connection after auth. This is the "non-trivial but doable" work they called out.

```python
# After tenant authentication
conn.execute(f"SET search_path TO tenant_{tenant_id_slug}, public")
```

Cross-tenant analytics: query via `information_schema` or iterate schemas. Slightly more complex but manageable with a schema registry table.

**Tier 3 — Enterprise tenants (5 tenants, *pending contract review*)**: DB-per-tenant

These 5 tenants generate 2M runs/month combined and have compliance requirements. With 5 tenants, 5 RDS instances is within the DevOps constraint (≤4 was a preference, not a hard limit — worth a conversation since 5 enterprise clients likely pay for the operational overhead).

If the contracts require physical isolation, this is the only compliant option. If they don't, schema-per-tenant on a dedicated enterprise instance is simpler.

Cross-tenant analytics: FDW (foreign data wrappers) or — better — a lightweight ETL job that pushes aggregated metrics (not raw data) to a separate analytics store. The ops dashboard likely needs counts and durations, not raw JSONB.

---

#### At 1,000 tenants (2-year horizon)

| Tier | Current | 2-year projection | DB instances |
|---|---|---|---|
| Small/mid | 180 tenants | ~850 tenants | 1–2 sharded shared DBs |
| Large | 15 tenants | ~100 tenants | 1 dedicated large-tenant DB |
| Enterprise | 5 tenants | ~50 tenants | Depends on contracts |

The shared DB for small/mid shards horizontally by tenant range when needed — application routes connections by tenant ID range. This is the only tier that requires sharding logic, and you won't need it until ~500+ small tenants or data growth forces it.

---

#### Migration sequence

```
Phase 0 (now):        Partition workflow_runs by tenant_id
                      ↓
Phase 1 (1-3 mo):     Read compliance contracts
                      Add RLS to shared tables (belt-and-suspenders)
                      ↓
Phase 2 (2-4 mo):     Stand up enterprise RDS instances (or schema tier)
                      Migrate 5 enterprise tenants
                      ↓
Phase 3 (4-8 mo):     Stand up large-tenant RDS instance
                      Migrate 15 large tenants (schema-per-tenant)
                      ↓
Phase 4 (ongoing):    New tenants land in correct tier at onboarding
```

---

### Where I'd push back on the problem framing

The DevOps constraint ("prefer not to manage more than 3-4 database instances") is understandable but should be re-examined in light of the compliance commitments already made. If GlobalBank's contract requires a dedicated instance, that commitment was made before this architectural conversation happened. The answer isn't to squeeze GlobalBank into a shared model that violates their contract — it's to revisit the operational preference.

Also: the internal ops analytics dashboard is best served long-term by a **separate read replica or OLAP store** rather than running aggregation queries against the same database serving live tenant traffic. At 2M runs/month and growing, you don't want internal dashboards competing with tenant queries for IOPS.

---

### What I'm genuinely uncertain about

- Whether PostgreSQL RLS overhead on the small-tenant shared DB is acceptable at 850 tenants with heavy concurrent query load — this needs benchmarking, not assumption.
- Whether the ORM can cleanly support three different connection strategies (shared, schema search_path, separate connection string) without creating a maintenance nightmare. This depends on which ORM and whether they've abstracted connection acquisition.
- The actual compliance clauses. I've flagged this repeatedly because it's the one thing that can make any of this irrelevant.

**The compliance contract review is not optional and should happen before Phase 2. Everything else can proceed in parallel.**