Alright, I've worked through this with epistemic humility. The claim "ORMs are bad for Go, use raw SQL" is pattern-matched but **oversimplified**. Let me steelman it first, then show you why your constraints point to a different answer.

## Why Go Is Skeptical of ORMs (Legit Reasons)

The "just use raw SQL" argument comes from real principles:
- **Explicitness**: Go values code you can read and reason about; big ORMs hide execution
- **Performance predictability**: With raw SQL, you see exactly what query runs; ORMs can emit surprising N+1 queries
- **Minimal abstractions**: Go's design philosophy resists frameworks that "make SQL easier"—better to be explicit

These aren't wrong. They're context-specific.

## But "Always Raw SQL" Is Also Wrong

Here's what the colleague's advice **doesn't account for**:

1. **Raw SQL has its own maintenance costs** (not just benefits):
   - 30 tables × CRUD = ~120 queries written and maintained by hand
   - Nullable fields require manual `sql.NullString` handling everywhere
   - Schema changes require hunting through all your query files
   - Type mismatches (query returns `int` but you expect `string`) caught only at runtime
   - The "this is explicit" actually means "this is tedious"

2. **Your team has ORM experience that's being ignored**:
   - You came from Hibernate/SQLAlchemy—that expertise transfers *partially* to modern Go tools
   - Learning Go-specific SQL handling has a real cost
   - "Pragmatic" beats "pure" when the cost is 3 developers' onboarding time

3. **2000 req/s is fast but not "hand-rolled SQL is the only option" fast**:
   - A good ORM/query builder won't be your bottleneck at this load
   - Your bottleneck will likely be database connection pooling, query design, and caching
   - Hand-rolling SQL doesn't magically solve those

4. **Your 10 complex reporting queries are a real edge case**:
   - Not every query fits an ORM well
   - But that's 10 queries, not 120
   - You can use different tools for different jobs

## What I'd Actually Recommend

**Use a layered approach:**

**For your 30 × CRUD tables: GORM (with caveats) or sqlc**

- **GORM** (Medium confidence this is current):
  - If the team wants something that *feels* like Hibernate/SQLAlchemy
  - GORM 2+ is substantially better on performance than earlier versions
  - You can write raw SQL inside GORM when you need to
  - Cost: Some queries can be harder to debug than they should be

- **sqlc** (High confidence):
  - Generates type-safe Go code from hand-written SQL
  - Bridges the gap: you write SQL (explicit, fast), it generates safe Go (type-checked)
  - No runtime magic—pure code generation
  - More "Go-idiomatic" than GORM
  - Cost: More boilerplate, but it's auto-generated

**For your 10 complex reporting queries: Raw SQL with sqlc or database/sql**
- The hand-rolled mapping code here is actually worth the effort (10 queries, not 120)
- sqlc handles this well if you went that route above

## The Decision Framework

Ask yourselves:

1. **Do we want to write SQL explicitly ourselves?**
   - Yes → Use **sqlc** (gold standard for Go)
   - No, we want an abstraction → Use **GORM** with a hard rule: "profile first, don't prematurely optimize around ORM fears"

2. **How much time will we spend on database access code vs. business logic?**
   - If >20% of engineering effort, an ORM/tool buys you real time back
   - If <5%, raw SQL is fine

3. **Will schema changes be frequent?**
   - Yes → An ORM or sqlc saves you hours
   - No → Raw SQL is lower overhead

## What I'd Actually Do (Not Dogmatic, Just Honest)

For your constraints, I'd pick **sqlc** and it's not close:
- You get Go's explicitness (write real SQL, see real queries)
- You get type safety (compile-time errors, no `sql.NullString` juggling)
- You get the ORM benefit (code generation handles the mapping tedium)
- Complex reporting queries work great in sqlc
- The "it's not an ORM" check-mark satisfies the Go community's skepticism

Cost: You write SQL by hand (good), but you learn sqlc's conventions (small onboarding).

**Second choice**: GORM with a discipline rule: profile before optimizing, and write raw SQL for queries where you need it. This is more pragmatic if the team just wants to move fast and has Hibernate muscle-memory.

**Avoid**: 100% raw `database/sql` with hand-rolled mapping for 120 queries. That's not "explicit and simple," that's "repetitive and fragile."

---

**Low confidence I should flag**: I haven't benchmarked GORM or sqlc on a service at 2000 req/s in 2025—this is reasoning about the tools, not measured data. Before you fully commit, run a small proof-of-concept with whichever tool you lean toward and actually load-test it. That will ground the decision better than my reasoning.