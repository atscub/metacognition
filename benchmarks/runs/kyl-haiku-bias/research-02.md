Working through the socratic protocol for this high-cost decision:

---

## What I'm Assuming

1. You've accepted your colleague's framing: "ORMs bad, raw SQL good"
2. That there's a clear winner here (there isn't)
3. That my training knowledge (Feb 2025) is current enough for 2026 Go ecosystem advice

**Confidence check**: Medium-high on Go culture, but I haven't verified recent (2025+) developments in tooling or community sentiment. I should not confidently prescribe without grounding.

---

## My Honest Assessment of the Colleague's Advice

**The advice is real** — Go culture is genuinely skeptical of ORMs. But it's **oversimplified and context-dependent**.

The "ORMs are bad in Go" position often conflates:
- **A philosophical preference**: "Explicit is better than implicit" (fair)
- **A real risk**: ORM reflection overhead + N+1 queries (legitimate for high-throughput systems)
- **With a universal truth**: ORMs are always worse (not true)

**What would change my mind about this?** If I saw:
- Recent benchmarks showing raw SQL is decisively better for your specific query patterns
- Evidence that your team's time cost (maintaining hand-rolled mapping) outweighs any performance gains
- Community shift in Go toward different approaches

I haven't verified these. Let me think through **your actual constraints**:

---

## The Real Calculus for Your Situation

Your workload has two distinct parts:

| 30 CRUD tables | 10 complex reporting queries |
|---|---|
| Repetitive, low variance | 4-5 table joins, aggregations, window functions |
| High velocity (add new queries often) | Low velocity (stable, infrequent changes) |
| Predictable schema mapping | Complex business logic |

**This is key**: A one-size-fits-all tool might be *wrong*. You might want **different tools for different parts**.

---

## Three Approaches Worth Considering

### 1. **Raw `database/sql` + Manual Mapping** (Colleague's Recommendation)

**Pros:**
- Zero overhead, maximum control
- Performance is predictable and measurable
- Simple queries are simple

**Cons:**
- For 30 CRUD tables, you'll write a lot of repetitive code
- Schema changes (adding a column) require touching mapping code in multiple places
- Error-prone: typos in column names, forgotten nullable fields, SQL injection if not careful with parameterization

**Honest assessment**: This works if your team can discipline itself to write good patterns. But for 30 tables, it's tedious. The complexity bias here is toward "raw SQL = control = good," which isn't always true.

**When it's right**: If your queries are so dynamic or unconventional that an ORM would fight you. Doesn't sound like your case.

---

### 2. **sqlc** (Code Generation)

This is the "Go-native" answer, gaining momentum since your colleagues might've last checked.

**How it works:**
- You write SQL queries in `.sql` files
- `sqlc` generates type-safe Go code (structs, query functions, error handling)
- No runtime reflection, no ORM overhead, all type-safe at compile time

**Pros:**
- Type-safe: column name mismatches caught at generation time, not runtime
- Zero runtime overhead (just generated code)
- Schema changes are explicit: regenerate, see what broke
- Good for both CRUD and complex queries
- Your SQL stays readable and portable

**Cons:**
- You still write SQL for every query (but it's in version control, IDE-checked)
- Less abstraction than an ORM — pagination, filtering have to be written per-query (but there are patterns)
- Setup: add `sqlc` to your build pipeline
- Learning curve: small, but different from what Java/Python folks are used to

**Honest assessment**: This might be the sweet spot for you. It gives you Go's philosophy (explicit, generated, type-safe) without the hand-rolled mapping tedium. Widely used (Docker, Shopify, others). Mature enough for 2000 req/s.

**When it's right**: When you want control and type safety but don't want to manually map rows to structs.

---

### 3. **GORM or Similar ORM**

Despite Go culture, modern ORMs exist. You've used Hibernate/SQLAlchemy.

**Pros:**
- Familiar to your Java/Python developers
- Query builder and hooks reduce boilerplate
- Handles complex joins reasonably well
- Schema changes less brittle (ORM introspects)

**Cons:**
- Reflection overhead (measurable, not always negligible)
- Risk of N+1 queries if you're not careful
- Less explicit; behavior surprises are possible
- Go community sees this as "un-idiomatic" (real social cost if you hire)

**Honest assessment**: GORM is battle-tested and works at your scale (2000 req/s is well within its capabilities). The "anti-pattern" label is partly culture, partly real risk if misused. For someone from Java this is home. For your Go team, this is a tradeoff: developer productivity vs. idiomatic Go.

**When it's right**: If your team values familiarity and you're confident you won't fall into ORM pitfalls.

---

## What I'd Actually Recommend

Given your constraints, **I'd lean toward sqlc** because:

1. **Type safety + zero overhead**: You get compile-time safety without runtime cost. Both things you care about.
2. **Fits your workload**: Works equally well for your CRUD tables (generated functions are simple) and complex queries (you write the SQL you'd write anyway).
3. **Fits your team**: Java developers familiar with "generated boilerplate," Python developers used to explicit SQL. Meets both halfway.
4. **Reduces the "tedium" problem**: You write SQL once, generate code. Schema changes surface immediately.
5. **Idiomatic Go**: You can confidently say "yes, we use Go patterns" if that matters for hiring.

**The raw SQL path is defensible** if your team commits to patterns and discipline. But it's the road more often regretted (schema refactors are painful). The colleague's advice is not *wrong*, just incomplete.

**GORM is fine** if familiarity wins over cultural fit. Just be aware of the overhead and make sure you benchmark it under your actual workload.

---

## How to Decide

Before committing, do this:

1. **Prototype both** (sqlc and GORM) on 1-2 of your CRUD tables + 1 complex query. Time yourself. Measure generated code size.
2. **Benchmark** under load (2000 req/s simulation). See if the overhead matters for your actual queries.
3. **Ask the team**: Which felt less painful? What surprised them?

The answer from the prototype will be more valuable than any advice I can give.

---

**Does this change how you're thinking about it?**