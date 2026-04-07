I need to recommend an approach, but first—**the compliance requirement is a potential blocker that needs immediate clarification.** Before finalizing architecture, Sales needs to provide:

- What specific data handling requirements did those three enterprise clients demand? (physical isolation, residency, regulatory compliance like HIPAA/SOC2?)
- Are these contractual commitments that would break the contract if violated?

Let me proceed with a recommendation assuming the worst case (they may require physical isolation), then show how to adjust if it's less strict.

---

## Recommendation: **Hybrid Schema-per-Tenant + Compliance Carve-Out**

**For 180 small/mid-market tenants (10% of data):** Keep in shared schema with RLS  
**For 15 large tenants (60% of data):** Schema-per-tenant in current instance  
**For 5 enterprise tenants (30% of data):** Database-per-tenant **IF compliance requires physical isolation; otherwise same as large tenants**

### Why This Works

| Concern | How It's Addressed |
|---------|-------------------|
| **Performance** | Large tenants get dedicated schemas; index bloat is now per-schema, not global. 8-sec dashboard becomes ~500ms for most tenants. |
| **Cross-tenant analytics** | Analytics service queries from all schemas via a federated view/application-layer union, or reads from a separate materialized analytics replica |
| **Compliance** | Enterprise clients with isolation requirements get dedicated databases; others don't need the overhead |
| **Scaling to 1K tenants** | Schema-per-tenant scales indefinitely in a single RDS instance; only the 3-5 compliance-mandated tenants consume separate databases |
| **DevOps preference** | 1 shared instance (small/mid + large) + up to 1 compliance instance = 2 RDS instances max, well within the 3-4 limit |
| **Engineering effort** | ORM connection logic changes only for tenants moved to dedicated schemas (phased rollout) |

### Why Not the Pure Approaches

- **Shared DB + RLS alone**: Doesn't fix the 290 GB `workflow_runs` table bloat, vacuum contention, or index inefficiency at scale. As you add tenants, single-instance problems compound.
- **Pure schema-per-tenant in one DB**: Solves performance but creates a false sense of isolation—an RLS misconfiguration or accidental schema query still leaks data. Enterprise clients requiring compliance typically want *physical* isolation.
- **Pure database-per-tenant**: Impossible to support Product's cross-tenant analytics dashboard without complex federation. DevOps has to manage 200+ instances by year 2.

---

## Migration Plan

### Phase 1: Immediate (Weeks 1–2) — Compliance & Data Audit
1. **Get exact compliance requirements from Sales** — Schedule call with MegaCorp, Acme, GlobalBank legal to document:
   - Do they require physical database isolation, or just logical/access control?
   - Data residency requirements?
   - Audit/compliance certifications (SOC 2, HIPAA, etc.)?
2. **Audit current query patterns** — Identify ORM tenancy points (usually: a `with_tenant(id)` scope or middleware that filters by `tenant_id`)

### Phase 2: Setup (Weeks 3–4)
1. **Create replica RDS instance** for analytics (read-only federation)
2. **Deploy application-level tenant context** — Ensure all queries are scoped (you're already doing this; formalize it)
3. **Set up RLS policies** on small/mid-market shared schema as a safety net (defense in depth; don't rely on it as primary isolation)

### Phase 3: Large Tenant Migration (Weeks 5–8)
1. **Choose 2 large test tenants** (not the biggest yet)
2. **Create dedicated schemas** for them in current DB: `CREATE SCHEMA tenant_<id>`
3. **Migrate their data** (dump/restore or logical replication)
4. **Update ORM connection logic** to route these tenants to their schema via `SET search_path`
5. **Validate performance** — Run their actual query workload; target <1s for dashboard queries
6. **Gradually roll out** to remaining 13 large tenants over 2 weeks

### Phase 4: Enterprise/Compliance Migration (Weeks 9–12)
*Only if compliance requires physical isolation:*
1. **Provision 1 new RDS instance** for the 3 enterprise clients (or adjust based on compliance findings)
2. **Migrate MegaCorp, Acme, GlobalBank** to dedicated databases
3. **Update application routing** (e.g., a tenant metadata table stores `db_instance` for each tenant)
4. **Set up cross-instance analytics queries** — Application or Materialize/etc. unions the results

If compliance requirements are *not* physical isolation (just access controls + audit logs), keep all 20 large/enterprise tenants in schemas within the shared instance and skip the dedicated DB step.

### Phase 5: Cleanup & Scale (Weeks 13–16)
1. **Decommission old shared schema for large tenants**
2. **Archive old indexes, vacuum aggressively**
3. **Test scaling to 500+ tenants** with schema-per-tenant pattern (should be smooth; just new schemas)
4. **Document ORM routing** for future new tenants

---

## Performance Targets Post-Migration

| Tenant Tier | Query Latency | Justification |
|-------------|---------------|---|
| Small/mid (shared schema) | <1s | Smaller dataset, isolated index footprint |
| Large (dedicated schema) | <500ms | No cross-tenant index contention |
| Enterprise (if isolated DB) | <200ms | Dedicated hardware, no shared vacuum lock |

---

## Key Decision Point

**Before starting Phase 1:** Get those compliance requirements. If they say "just logical isolation + audit logs," you can skip the database-per-tenant work and save 6 months of operational overhead. If they say "legally required physical isolation," database-per-tenant for those 3 is non-negotiable.

Once you clarify, the remaining phases are deterministic. Want me to help draft that compliance requirements email to Sales, or start with Phase 2 setup?