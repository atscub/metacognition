# Task: research-02 — Go database access: ORM vs raw SQL

## Prompt
I'm starting a new Go microservice that talks to PostgreSQL. I've heard ORMs are bad
for performance and you should use raw SQL. But writing raw SQL for every query seems
tedious and error-prone — we'd need to manually map result rows to structs, handle
nullable fields, and keep queries in sync with schema changes.

Our service has about 30 tables with fairly standard CRUD operations (create user,
update order status, list items with pagination and filtering). On top of that we have
maybe 10 complex reporting queries that join 4-5 tables with aggregations and window
functions.

The team is 3 Go developers. Two of us came from Java (used Hibernate) and one from
Python (used SQLAlchemy). We're all comfortable writing SQL but would prefer not to
maintain a bunch of hand-rolled mapping code.

We need to pick a database access approach and commit to it since it'll be hard to
change later. Our main concerns are: type safety (catch errors at compile time, not
runtime), performance (this service handles ~2000 req/s), and maintainability (easy
to add new queries and modify existing ones when the schema evolves).

A colleague told us "just use database/sql with raw queries, ORMs are an anti-pattern
in Go." Is that right? What should we use?


## Response A
Your colleague isn't wrong so much as **incomplete**. The "ORMs are bad in Go" sentiment is real, but it's a reaction to *misuse*, not a categorical truth. Here's the nuance:

## Why Go developers are skeptical of ORMs

Go's philosophy emphasizes **explicitness** — you tend to write more code that's easier to reason about. That pushes people toward raw SQL:
- You can see exactly what query will run (no magical query generation surprises)
- You control the database calls (no hidden N+1 queries buried in relationships)
- Performance is predictable — you're not paying for features you don't use

**But** this only matters if you're actually falling into those pitfalls. For your workload, you're probably not.

## Why an ORM makes sense for *your* situation

**Your 30 CRUD tables** are exactly what ORMs excel at. You could hand-write:
```go
// Boilerplate you'd repeat 30+ times with raw SQL
rows, err := db.QueryContext(ctx, `
  SELECT id, name, email, created_at FROM users WHERE id = $1
`)
if err != nil { ... }
defer rows.Close()
var u User
if rows.Next() {
  if err := rows.Scan(&u.ID, &u.Name, &u.Email, &u.CreatedAt); err != nil { ... }
}
```

Or with an ORM:
```go
var u User
db.WithContext(ctx).First(&u, id)
```

The ORM version isn't magic — it's just saved boilerplate. And because your team already knows this pattern from Java/Python, adoption cost is near-zero.

**Your 10 reporting queries** can stay as hand-written SQL in the ORM (most ORMs let you escape to raw SQL for complex stuff). You keep the complex logic explicit and performant.

## Performance at 2000 req/s

This is well within ORM territory. You're not hitting the scaling edge where latency-per-query matters more than dev velocity. ORM overhead is typically 5-10% vs raw SQL on simple queries — that matters at Google scale, not at your scale.

## The real tradeoff matrix

| Approach | CRUD boilerplate | Reporting queries | Type safety | N+1 risk | Learning curve |
|----------|------------------|-------------------|------------|----------|-----------------|
| **Raw SQL** | High (repeat 30x) | Clean & explicit | Medium (string column names) | You own it | Low |
| **GORM** | Minimal | Can mix raw SQL | High (compile-time) | Easy to hit, easy to avoid | Medium (for your team: low) |
| **sqlc** | High (code-gen) | Clean | Highest (compile-checked) | None | Medium-high |

## My recommendation: **GORM with discipline**

- Use GORM for all 30 CRUD tables — it's boring, reliable, and your team already knows the pattern
- Write raw SQL for your 10 reporting queries (GORM's `db.Raw()` is perfectly fine)
- Set one rule: **never use GORM associations** (the `db.Preload()` stuff that hides N+1s). Load data explicitly with raw SQL if you need joins
- Your team's ORM experience actually gives you an advantage — you won't accidentally abuse features

Alternative: **sqlc** if you want absolute confidence in query correctness (compile-time verification of schema). But that's overkill if you have decent tests and schema migration discipline.

**Don't do:** Hand-write 30 CRUD implementations with `database/sql`. That's "optimizing" by optimizing for the wrong thing (line count) at the cost of maintainability. The colleague's advice works for greenfield services with 2-3 carefully-tuned queries, not for "fairly standard CRUD."

What's your instinct after hearing the tradeoffs?

## Response B
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
