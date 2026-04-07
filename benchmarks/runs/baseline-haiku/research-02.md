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