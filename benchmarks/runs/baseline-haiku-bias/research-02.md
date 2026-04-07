The "ORMs are an anti-pattern in Go" take is **partially true but overstated**. It's a reaction to seeing ORMs hide expensive queries and create N+1 problems, which are real concerns. But it conflates "bad ORM usage" with "all ORMs." The real issue is that Go devs coming from Java/Python expect ORMs to abstract SQL away—then get surprised when invisible queries tank performance.

Here's what actually matters for your situation:

## The Real Tradeoffs

**Raw SQL + database/sql:**
- ✅ Perfect visibility into queries, easy to optimize for your 2000 req/s load
- ✅ No surprises from hidden N+1 queries or automatic loading strategies
- ❌ 30 simple CRUD queries become ~300 lines of `rows.Scan()` boilerplate
- ❌ NULL field handling is verbose and easy to get wrong
- ❌ When schema changes (rename column, add field), you update SQL *and* code—easy to desync
- ❌ Zero compile-time safety: typos in column names only fail at runtime

**GORM (traditional ORM):**
- ✅ Reduces boilerplate significantly
- ✅ Decent compile-time safety (though query builder chains aren't type-checked)
- ✅ Easy schema migrations with model tags
- ❌ Default behavior can hide N+1 queries (requires discipline to avoid)
- ❌ Complex queries (your 10 reporting queries) are awkward to express in DSL, you'll drop back to raw SQL anyway
- ❌ Migrations can drift from actual schema over time

**sqlc (query-first approach):**
- ✅ You write SQL, it generates type-safe Go code—best of both worlds
- ✅ No runtime overhead or hidden queries—it's literally code generation
- ✅ Excellent for your 30 CRUD queries: write one query, get back a typed function with correct NULL handling
- ✅ Your complex reporting queries are native SQL anyway—they're where sqlc shines
- ✅ Type-safe: schema changes break the build immediately
- ❌ Requires SQL file maintenance (separate .sql files for each query)
- ❌ Learning curve if team hasn't used it (but lower than GORM complexity)
- ❌ Database-specific (PostgreSQL support is excellent, but less flexible than some ORMs)

## My Recommendation for Your Situation

**Use sqlc** with this strategy:

1. **CRUD operations (30 queries)**: Write parameterized SQL in `.sql` files, let sqlc generate type-safe accessors. You get compile-time safety, zero boilerplate, and clear visibility into what queries run.

2. **Complex reports (10 queries)**: Write native SQL with window functions, aggregations, whatever you need. sqlc handles it—generate a typed function that populates your structs automatically. No ORM DSL pain.

3. **Schema evolution**: When you add a column or rename a field, your SQL queries break the build. Fix the SQL, regenerate, code updates automatically. Can't accidentally desync.

4. **Performance**: Full visibility. Every query is explicit SQL you wrote. No hidden N+1 queries, no "framework magic." You can see exactly what's hitting the database and tune it.

### Why NOT the alternatives for you:

- **Raw database/sql**: You'll hate the boilerplate at scale (30 CRUD queries × 20 lines each), and your Hibernate/SQLAlchemy background will make you miss type safety.
- **GORM**: Your complex reporting queries will push you to raw SQL anyway. You end up maintaining both GORM and raw SQL, which is the worst of both worlds. Plus GORM's DSL (`.Preload()`, `.Where()`, etc.) won't buy you much if you're writing SQL for the hard queries.
- **ent**: Overkill for "fairly standard CRUD." Great for heavily relational graphs, but adds complexity you don't need.

## Practical Setup

```go
// Example with sqlc generated code
user, err := db.GetUserByID(ctx, userID)  // Type-safe, clear, no N+1s
orders, err := db.ListOrdersByUserID(ctx, db.ListOrdersByUserIDParams{
    UserID: userID,
    Limit:  pageSize,
    Offset: offset,
})  // Pagination is explicit in your SQL

// For complex reports—still just SQL:
report, err := db.ComplexMonthlyMetrics(ctx, db.ComplexMonthlyMetricsParams{
    StartDate: startDate,
    EndDate:   endDate,
})
```

You control every query, get compile-time safety, and zero runtime magic. This is the Go way.

**Start here**: Read the [sqlc docs](https://sqlc.dev), write your first 3 CRUD queries to get a feel for it, then commit to it. The pattern is easy, and the productivity gain over raw SQL + the safety gain over GORM is real.