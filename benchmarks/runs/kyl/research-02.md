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