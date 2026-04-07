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
Your colleague's claim is oversimplified. The real answer for Go + PostgreSQL in 2026 is **sqlc + pgx**, not raw `database/sql`. Here's why, and how to think about the tradeoffs.

---

## The actual Go database landscape

There are four meaningfully different approaches, not two:

| Approach | Examples | Type safety | SQL control | Boilerplate |
|---|---|---|---|---|
| Raw stdlib | `database/sql` | Runtime errors | Full | Very high |
| Thin wrapper | `sqlx`, `pgx` | Runtime errors | Full | Medium |
| **SQL codegen** | **`sqlc`** | **Compile-time** | **Full** | **Low** |
| Full ORM | GORM, `ent`, `bun` | Partial | Partial | Very low |

---

## Why your colleague is partially right

Full ORMs (GORM especially) have a real bad reputation in Go for good reasons:

- **N+1 queries** from lazy loading are harder to see and prevent than in Hibernate
- **Generated SQL is opaque** — you can't easily review what hits the DB
- **Complex queries fight the ORM** — your 10 reporting queries with window functions will become either ugly ORM workarounds or raw SQL escape hatches anyway, defeating the purpose
- Go's type system historically made ORM APIs awkward (lots of `interface{}`, reflection)

But "use raw `database/sql`" throws away real tools. Writing `rows.Scan(&id, &name, &email, &createdAt, ...)` for 30 tables, handling `sql.NullString` for every nullable field, and keeping that in sync with schema changes is exactly the maintenance burden you're trying to avoid.

---

## What you should actually use

### Primary: `sqlc` + `pgx/v5`

**sqlc** is code generation in the right direction: you write SQL, it generates Go. Example:

```sql
-- queries/users.sql

-- name: GetUser :one
SELECT id, name, email, created_at FROM users WHERE id = $1;

-- name: ListActiveUsersByTenant :many
SELECT id, name, email FROM users
WHERE tenant_id = $1 AND active = true
ORDER BY created_at DESC
LIMIT $2 OFFSET $3;
```

sqlc generates:
```go
// Generated — do not edit

type GetUserRow struct {
    ID        int64
    Name      string
    Email     string
    CreatedAt time.Time
}

func (q *Queries) GetUser(ctx context.Context, id int64) (GetUserRow, error) { ... }
func (q *Queries) ListActiveUsersByTenant(ctx context.Context, arg ListActiveUsersByTenantParams) ([]ListActiveUsersByTenantRow, error) { ... }
```

What you get:
- **Compile-time type safety** — wrong parameter types are caught by `go build`
- **No manual `Scan()` calls** — generated code handles all mapping
- **Nullables handled correctly** — `pgtype.Text` instead of `sql.NullString` (with pgx)
- **Your exact SQL runs** — no ORM translation layer, no surprises
- **Schema evolution is safe** — change the schema, update the query, regenerate, fix compile errors

Your complex reporting queries work identically — just put them in `.sql` files and sqlc generates the same type-safe wrappers.

**pgx/v5** (not the standard `lib/pq`) gives you:
- Native PostgreSQL types (arrays, JSONB, ranges, enums)
- `pgxpool` for connection pooling — critical at 2000 req/s
- Better performance than `lib/pq` for your volume

### Setup sketch

```yaml
# sqlc.yaml
version: "2"
sql:
  - engine: "postgresql"
    queries: "./queries"
    schema: "./migrations"
    gen:
      go:
        package: "db"
        out: "./internal/db"
        sql_driver: "pgx/v5"
```

```
queries/
  users.sql
  orders.sql
  reports.sql     ← your complex window function queries go here too
migrations/
  001_initial.sql
  002_add_orders.sql
internal/db/      ← generated, never hand-edited
  users.sql.go
  orders.sql.go
  reports.sql.go
```

---

## Performance at 2000 req/s

This is comfortably within range for Go + PostgreSQL. The bottleneck will be your database, not the Go layer. What actually matters:

1. **Connection pooling** — use `pgxpool`, size it to your PostgreSQL `max_connections` (typically 20-50 connections handles 2000 req/s fine with good query performance)
2. **Query efficiency** — indexes, query plans. sqlc doesn't help here but doesn't hurt either
3. **N+1 avoidance** — sqlc forces you to write explicit queries, so N+1 is visible and deliberate

Full ORMs can add 2-5x overhead from reflection and query building. sqlc adds effectively zero overhead — it's just Go calling pgx.

---

## What to use for the few edge cases

| Situation | Tool |
|---|---|
| Dynamic filters (search with optional WHERE clauses) | [`squirrel`](https://github.com/Masterminds/squirrel) query builder, or generate multiple sqlc queries |
| One-off admin scripts | `pgx` directly |
| Migrations | [`golang-migrate`](https://github.com/golang-migrate/migrate) or [`goose`](https://github.com/pressly/goose) — separate from sqlc |

For your 30-table CRUD service, the dynamic filter case will come up maybe 5-10% of queries. You can handle those with `squirrel` while keeping everything else in sqlc. Don't let the edge case drive the whole architecture.

---

## The transition from Hibernate/SQLAlchemy

For your teammates: sqlc is closer to MyBatis (SQL in files, mapped to typed functions) than Hibernate or SQLAlchemy. The key mental shift is that there's no "entity object" you mutate — queries are functions that take parameters and return structs. This is idiomatic Go and your team will find it easy to reason about.

---

## Summary

- **Use sqlc + pgx/v5** as your primary approach
- Your complex reporting queries are a feature of this choice, not an exception to it
- The performance concerns at 2000 req/s are real but solved by connection pooling, not by avoiding ORMs
- Your colleague is right that full ORMs are problematic in Go, but wrong that the alternative is raw `database/sql`

## Response B
## Applying the Socratic Protocol

Let me work through this before answering, because "ORMs bad, use raw SQL" is a claim I should stress-test rather than confirm or deny reflexively.

---

### Step 1: Examine the premise

**Is "ORMs are an anti-pattern in Go" accurate?**

Steelmanning your colleague's position (its strongest form):
- Go philosophy prizes explicitness. Traditional ORMs generate SQL invisibly, which violates that.
- GORM (Go's most popular ORM, and likely what they mean) has real problems: unpredictable query generation, N+1 bugs that are easy to miss, "magic" hooks, and reflection-based mapping overhead.
- Your 10 complex reporting queries — 4-5 table joins with window functions — are often *impossible* to express cleanly in ORM query DSLs. You end up writing raw SQL anyway, so why not everywhere?
- ORM query generation makes performance profiling harder: you don't know what SQL will run until runtime.

This is a legitimate argument **specifically against GORM-style ORMs**.

**But the claim contains a false dichotomy.** "ORMs bad" doesn't imply "raw `database/sql` only." There's a third category your colleague may not have mentioned: **code-generating tools** and **struct-scanning helpers** that let you write SQL and still get type safety and ergonomic mapping.

---

### Step 2: Map the actual option space

The Go database layer isn't "ORM vs raw SQL." It's a spectrum:

| Tool | What it is | Type safety | SQL control | Boilerplate |
|---|---|---|---|---|
| `database/sql` | stdlib, manual row scanning | Runtime only | Full | Very high |
| `sqlx` | Extends stdlib with struct scanning | Runtime | Full | Medium |
| `pgx` | Native PostgreSQL driver | Runtime | Full | Medium-high |
| `squirrel` | Query builder (constructs SQL) | Runtime | High | Low-medium |
| **`sqlc`** | **Code gen from SQL + schema** | **Compile time** | **Full** | **Very low** |
| `ent` | Schema-as-code, generates client | Compile time | Medium | Low |
| GORM | Traditional ORM | Runtime | Low-medium | Very low |
| `bun` | Lighter ORM/query builder (pgx-backed) | Runtime | Medium-high | Low |

---

### Step 3: Check my assumptions about your constraints

**"2000 req/s requires avoiding ORM overhead"** — I should flag this is probably wrong framing.

At 2000 req/s, your bottleneck will almost certainly be:
1. PostgreSQL query execution time
2. Network round-trips
3. Connection pool saturation

Not struct mapping overhead. Even GORM's reflection cost is negligible at this load. The *real* performance risk from ORMs is **SQL quality** — N+1 queries, missing indexes, generating `SELECT *` when you need specific columns, or generating suboptimal joins. That's a SQL correctness problem, not a raw-vs-ORM binary.

**"Hard to maintain hand-rolled mapping code"** — this is a genuine concern, and it's precisely where the choice matters most.

---

### Step 4: What fits your actual context

Your specifics point clearly toward **`sqlc` with `pgx`**:

**Why sqlc fits:**
- You write SQL. All 30 tables' CRUD, all 10 reporting queries — plain `.sql` files. Your team that's comfortable with SQL keeps working in SQL.
- sqlc reads your schema and your queries, then generates Go functions with typed inputs and typed output structs. `GetUserByID(ctx, id) (User, error)` — compile-time checked, no hand-rolling.
- Nullable fields are handled in generated code (via `pgtype` or `sql.Null*` types — you configure this).
- Schema evolution: update migration, run `sqlc generate`, fix compile errors. The compiler tells you where queries broke.
- Complex reporting queries are just... more SQL. sqlc generates the same way for a 5-line CRUD query and a 50-line window function query.
- Generated code is readable, plain Go — no magic, no reflection at runtime.

**Why pgx over lib/pq:**
- Native PostgreSQL wire protocol support (pipelining, COPY, better type mapping)
- Actively maintained; lib/pq is in maintenance mode
- sqlc supports pgx as its backend

**What to do about GORM:**
Your Java colleagues' Hibernate instinct will pull toward GORM. Resist it. GORM is the Go tool that most resembles Hibernate, and it carries similar failure modes: lazy-loading confusion, unclear what SQL runs, raw() escapes for anything complex. The fact that you *already know* your complex queries need raw SQL is a signal that an ORM buys you less here than it would in a simpler CRUD-only service.

---

### Step 5: Where I'm less certain (flag for verification)

**Medium confidence claims — verify before committing:**
- sqlc's nullable field handling and PostgreSQL-specific type support: the details change across versions. Check the current sqlc docs (specifically `pgx/v5` mode vs `database/sql` mode — pgx/v5 mode is newer and preferred).
- `ent` (by Meta) is a legitimate alternative if your data has complex relationship traversal patterns — it's more mature than when it launched. Worth a look if your schema is heavily relational graph-style.
- `bun` has gained traction as a GORM alternative that's lighter and pgx-backed. If you want something slightly more ORM-like than sqlc, it's worth evaluating.

These are things I know from training data but haven't verified against current docs in this session. The Go ecosystem moves, and library maturity/community consensus can shift.

---

### Direct answer

**Your colleague is half-right.** The insight — "GORM-style ORMs create problems in Go" — is sound. The conclusion — "therefore use raw `database/sql`" — skips the better option.

**Recommendation: sqlc + pgx.**

You write SQL (what your team already knows), get compile-time type safety (what you want), zero hand-rolled mapping (what you want to avoid), and full control over every query that gets sent to PostgreSQL (what actually matters for performance). Your 10 complex reporting queries fit naturally — they're just SQL files that sqlc generates typed wrappers for.

Setup: define your schema in migration files (use `golang-migrate` or `goose`), write `.sql` files with named queries and `-- name:` annotations, run `sqlc generate`, use the generated code. When the schema changes, regenerate and fix compile errors.

The one place to set expectations: sqlc requires discipline about keeping query files organized as the codebase grows. 30 tables of CRUD is ~120-150 queries (CRUD = 4 ops minimum). You'll want a convention for file layout early (e.g., one file per table, or one file per domain area).

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
