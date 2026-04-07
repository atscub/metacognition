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