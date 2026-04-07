## Socratic Analysis: Multi-Tenant Database Architecture

Before recommending an approach, I need to surface what I'm assuming vs. what I know, and identify what's **actually blocking the decision**.

### 1. What I'm Assuming (High Risk)

| Assumption | Confidence | Why It Matters | Can I Verify? |
|-----------|-----------|---------------|--------------|
| The compliance clauses don't rule out RLS | **Low** — Sales said legal was "very specific" but didn't share actual language | Could determine whether RLS is viable at all | **No** — Sales needs to provide exact clauses |
| The 8-second dashboard is a filtering/indexing problem, not a query complexity problem | **Medium** — Index bloat is mentioned, but no query plan analysis shown | Determines whether we're solving the right problem | **Partially** — would need to see actual queries and EXPLAIN plans |
| "Ops dashboard aggregates metrics" is straightforward (sums, counts, basic joins) | **Low** — could actually require complex cross-tenant analytics | Major difference in feasibility between RLS and schema-/db-per-tenant | **No** — Product needs to detail the requirements |
| DevOps can't support >4 instances | **Low** — stated as preference, not hard constraint | Could open up db-per-tenant viability | **No** — need to ask about true limits |
| The ORM constraint is a minor implementation detail | **Medium** — some ORMs handle this better than others; depends on the tool | Could flip the difficulty score between RLS and schema-per-tenant | **No** — need to know which ORM and verify its capabilities |
| 1,000 tenants is achievable with any approach | **Low** — very different at scale; schema-per-tenant coordination gets hard; db-per-tenant connection pooling gets nightmarish | Could reveal that one approach is actually a dead-end at scale | **No** — depends on operational model we choose |

### 2. What I Actually Know (From Context)

✓ Current state: 200 tenants, 340GB DB, 290GB in workflow_runs, RLS not yet implemented  
✓ Performance issue: 8s load time on largest tenant's dashboard  
✓ Vacuum/bloat issues: Present  
✓ Scaling target: 1,000 tenants in 2 years  
✓ Stakeholder constraints: Compliance (undetailed), ops aggregation, DevOps preference  

### 3. Critical Questions That Block This Decision

**You need answers to these before proceeding:**

1. **What exactly do the enterprise compliance clauses require?** 
   - "Data isolation," "separate databases," "no shared infrastructure," "cryptographic separation," "audit trail of access"? 
   - These have vastly different architectural implications. RLS might be acceptable for "no cross-tenant access via app code" but not for "legally isolated infrastructure."
   - **Action**: Sales/Legal needs to provide specific clauses, not paraphrasing.

2. **What is the ops dashboard actually doing?**
   - Simple aggregations (count workflows across all tenants)? 
   - Complex cross-tenant analytics (cohort analysis, retention curves)? 
   - Real-time dashboards vs. periodic batch reports?
   - **Why**: Determines feasibility. RLS can do simple aggregations. Schema/db-per-tenant require distributed queries, which get complex fast.

3. **What ORM are you using, and does it support dynamic connection/schema switching?**
   - ORMs like SQLAlchemy can handle schema-per-tenant. Some can't.
   - **Action**: Verify ORM capability before claiming "non-trivial but doable."

4. **Is the 8-second load time actually a filtering problem?**
   - A query plan analysis would show if it's index bloat, sequential scans, or just query complexity.
   - **Action**: Run `EXPLAIN ANALYZE` on the actual slow query. If it's a SeqScan on 290GB, RLS alone won't fix it.

5. **What are DevOps' actual operational limits?**
   - "Prefer 3-4 instances" could mean "yes, we can do 10-15 if needed" or "we'll fight hard against anything more."
   - **Action**: Ask explicitly: "What's the true maximum database instances you'd operationally support?"

### 4. The Steelman for Each Approach

**RLS** — Best if:
- Compliance requires "access control" not "technical isolation"
- Ops dashboard is simple aggregations
- You want minimal operational complexity now

**Worst if:**
- Compliance requires separate databases (it might)
- Query performance is table-size bloat (RLS doesn't shrink 290GB tables)
- Largest tenant queries are complex (RLS adds overhead at scale)

**Schema-per-tenant** — Best if:
- Compliance requires logical separation but not database-level
- You need per-tenant customization (schema drifting)
- Scaling to 1,000 with good coordination

**Worst if:**
- ORM can't handle dynamic schema switching
- Ops dashboard requires cross-schema joins (becomes a maintenance nightmare)
- Enterprise compliance requires isolated database instances

**Database-per-tenant** — Best if:
- Compliance or sales needs "dedicated database" promise
- You can operationally manage 200-1000 connection pools
- Strong isolation is a product differentiator

**Worst if:**
- Ops dashboard needs distributed joins (very complex)
- DevOps can't support the operational load
- Scaling to 1,000 requires too many connections

---

## My Recommendation

**Do not choose yet.** You have a critical-path blocker: **the exact compliance requirements are unknown.**

Here's the decision tree:

```
1. Get compliance clauses from Sales
   ├─ "No cross-tenant access via app" → RLS is viable
   └─ "Separate databases required" → Schema or DB-per-tenant

2. Analyze the actual slow query
   ├─ SeqScan on 290GB → Need to partition/prune, not just filter
   └─ Index bloat, inefficient query → RLS + reindexing fixes it

3. Detail the ops dashboard requirements
   ├─ Simple aggregations → Any approach works
   └─ Cross-tenant joins/analytics → RLS is best, schema-per-tenant is painful

4. Verify ORM capabilities
   ├─ Supports dynamic schema → Schema-per-tenant is easier
   └─ Doesn't → RLS or DB-per-tenant
```

---

## What I'd Recommend *If Forced to Decide Now*

**Short term (next 6 months)**: **RLS + careful performance tuning.**
- Lowest risk, lowest operational complexity
- Fixes the isolation concern with minimal code changes
- Gives you time to gather the missing information
- If compliance requires more isolation, you pivot without having refactored the ORM

**Medium term (6-18 months)**: Reassess based on:
- Actual compliance requirements
- Whether RLS performance is sufficient
- Ops dashboard complexity

**Long term (2-year scale to 1,000 tenants)**: Likely **schema-per-tenant** if you have a solid ops model, or **hybrid** (large tenants get DBs, small ones stay in RLS).

---

## What I'm Uncertain About

🔴 **RED FLAGS** — I don't have enough info to be confident:

1. Compliance requirements are under-specified (this is a BLOCKER)
2. No query analysis of the actual slow query
3. ORM constraints assumed but not verified
4. Ops dashboard requirements assumed simple
5. DevOps constraints stated as preference, not limits

**Before I write a detailed migration plan, you need to:**
- Get Sales to provide actual compliance language
- Run `EXPLAIN ANALYZE` on the slow dashboard query
- Document the ops dashboard spec
- Verify ORM dynamic schema support

Would you like me to draft questions to send to each stakeholder, or do you want to provide the missing details now?