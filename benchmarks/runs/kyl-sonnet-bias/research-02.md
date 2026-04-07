## Socratic Protocol — Working Through This

Before recommending, I want to flag my failure modes and work through the question carefully.

---

### Checking the Premise (Authority Bias Alert)

Your colleague's advice — "ORMs are anti-pattern in Go, use raw `database/sql`" — is a **real opinion held by real Go developers**, so I need to steelman it before evaluating it:

**Strongest case for raw `database/sql`:**
- Go's culture prizes explicit, readable code; ORMs hide what's happening
- ORM query generation often prevents index usage in non-obvious ways
- N+1 query problems are easy to miss when you're not reading actual SQL
- Your 10 complex reporting queries need raw SQL anyway — now you have two access patterns
- `database/sql` is stdlib; zero dependencies, forever stable

That's a genuinely coherent position. But it conflates **"don't use an ORM"** with **"write everything in `database/sql`"** — and that conflation is the problem. The option space is much richer.

---

### What Am I Assuming? (Anchoring Check)

Let me surface my assumptions before I recommend anything:

1. *That "ORM overhead" matters at 2000 req/s.* — I need to examine this.
2. *That the Go ecosystem I know from training is still current.* — My cutoff is August 2025; I haven't verified library state in this session.
3. *That your team's Java/Python ORM background makes ORM-like tools preferable.* — Maybe their Go instincts have evolved; I shouldn't assume.
4. *That "type safety" and "raw SQL" are in tension.* — Actually they're not, which is the key insight.

---

### Performance Reality Check (Pattern Matching vs. Reasoning)

**The claim that ORMs are bad for performance is largely a myth at your scale.**

Let me reason through it: at 2000 req/s with, say, 2 queries per request, you're running ~4000 queries/second. The overhead of ORM marshaling is measured in **microseconds**. Your queries — especially the 10 reporting queries with 4-5 table joins and window functions — will take **milliseconds**. The ratio is roughly 1000:1. ORM overhead is not your bottleneck.

The *real* ORM performance problems are:
- **N+1 queries** — fetching a list then querying each item individually
- **SELECT \*** — loading columns you don't need
- **Query generation that defeats indexes** — especially common with GORM's complex join behavior

These are *correctness* problems disguised as performance problems. You can have them with any tool if you're not careful.

**What I'm less confident about:** I don't have benchmark data from this session. If you need sub-millisecond p99 latency at this scale, the calculus changes. But nothing in your description suggests that.

---

### The Actual Option Space

Your colleague framed this as ORM vs. raw SQL. The real options in Go for PostgreSQL:

| Tool | What It Is | Fit for Your Case |
|---|---|---|
| `database/sql` (bare) | Standard library, manual row scanning | Tedious for 30 tables; not recommended |
| `sqlx` | Thin wrapper adding struct scanning via field tags | Lower friction than bare `database/sql`, but still hand-written SQL with no compile-time checking |
| **`sqlc`** | **Code generator: you write SQL, it emits type-safe Go** | **Strong fit — see below** |
| `GORM` | Full ORM, most popular, query builder API | Works fine, but complex queries fight the API; escape hatches to raw SQL feel inconsistent |
| `ent` | Schema-as-code, codegen-heavy, Facebook-origin | High learning curve, opinionated; probably overkill unless you want graph-style traversal |
| `pgx` (direct) | PostgreSQL-specific driver, lower level than `database/sql` | Best performance, excellent PostgreSQL feature access, but more manual |
| `squirrel` / `goqu` | Query builders — compose SQL programmatically | Good for dynamic queries; combine well with `sqlc` for the parts `sqlc` can't handle |

---

### My Recommendation: `sqlc` + `pgx`

**Why this fits your stated constraints:**

**Type safety:** `sqlc` reads your `.sql` query files + your schema and generates Go functions with fully typed parameters and result structs. If a query references a column that doesn't exist, the generator fails. If you rename a column, every query using it breaks at `go generate` time — compile error, not runtime panic. This is as close to "catch errors at compile time" as Go gets for database code.

**Maintainability:** Your team writes SQL (which all three of you are comfortable with), not a query builder DSL or an ORM API. When a schema changes, you update the SQL file, re-run `sqlc generate`, and fix compile errors. No hand-rolled mapping code.

**Performance:** `pgx` is the highest-performance PostgreSQL driver in Go. `sqlc` generates thin wrappers — there's no reflection at query time, no dynamic query building. The generated code is essentially what you'd write by hand, but without the tedium.

**Complex queries:** Your 10 reporting queries are just `.sql` files. Window functions, CTEs, aggregations — `sqlc` handles them. You get back a typed result struct without writing a single `rows.Scan(...)` call.

**Where `sqlc` has friction:**
- Dynamic queries (e.g., "filter by any combination of 5 optional fields") are awkward — `sqlc` expects fixed queries. For these, combine with `squirrel` or use GORM's query builder selectively.
- Requires a code generation step in your build process (`make generate` or `go generate`). This is a workflow change your team needs to internalize.
- Schema migrations are separate — use `golang-migrate`, `goose`, or `atlas`. `sqlc` doesn't manage migrations.

---

### What Would Change My Recommendation?

- **If your filtering requirements are highly dynamic** (e.g., user-configurable report builders with arbitrary WHERE clauses): lean more toward a query builder like `squirrel`, or `GORM` for the CRUD parts.
- **If your team strongly prefers not having a code generation step**: `sqlx` is the next best option — same SQL-writing workflow, struct scanning via tags, no codegen, but you lose compile-time query validation.
- **If you need PostgreSQL-specific features heavily** (LISTEN/NOTIFY, COPY, custom types, logical replication): `pgx` directly, even for some queries.

---

### On Your Colleague's Advice

I'd push back on it — not because it's wrong about ORMs, but because it presents a false binary. The correct statement is closer to: *"Don't use a traditional ORM if you want control and performance in Go — but don't use bare `database/sql` either, because that's genuinely painful at scale. Use a tool that lets you write SQL while eliminating the manual mapping boilerplate."*

`sqlc` is that tool for most Go + PostgreSQL services in 2025. It's worth evaluating seriously before defaulting to the two extremes.

---

### Confidence Level

**Medium-high.** `sqlc` + `pgx` has been the emerging consensus in the Go community through my training data, and the reasoning above holds regardless of recency. What I can't verify in this session: whether `sqlc` has added features or changed its API significantly, whether a newer tool has emerged. Before committing, I'd recommend reading the current `sqlc` docs and checking its GitHub issues for known pain points specific to your use case (especially dynamic filtering).