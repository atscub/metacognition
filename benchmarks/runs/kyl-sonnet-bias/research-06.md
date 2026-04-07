---

## Phase 4: Answer

Both developers are right about different things, and the debate is partly a false dichotomy because it's centered on a problem that UUID v7 solves. Here's the full picture:

---

### Why Developer 1 is right — about UUID v4

The blog post benchmarks are real and the mechanism is correct. UUID v4 is 128 bits of cryptographic randomness. Every insert lands at a pseudorandom position in the B-tree index. This means:

- **Cache thrashing**: Index pages get evicted before they're reused, so every insert hits disk
- **Page splits**: No spatial locality → the index tree constantly splits interior nodes rather than appending to the right leaf
- **Bloat**: A fragmented tree with many half-full pages is physically larger than a dense sequential one — the "3x larger" claim is plausible, not exaggerated, at scale with UUID v4

At 10M rows/day, this would become a real operational problem within months.

**However:** This analysis is obsolete if you use UUID v7.

---

### Why Developer 2 is right — about the value of client-side IDs

The distributed-generation benefit is genuine:
- No DB round-trip to get an ID
- IDs can be created before a transaction, included in events/logs before insert
- No single sequence bottleneck
- Safe to generate IDs in multiple app servers simultaneously

Her "no problems" experience is also likely real — but survivorship bias applies. If her tables were read-heavy, had generous RAM for buffer cache, or sat on NVMe storage, the UUID v4 cost was absorbed by hardware. At higher write rates or tighter budgets, it shows.

---

### The actual answer: **UUID v7**

UUID v7 was finalized in RFC 9562 and is now in **PostgreSQL 18** (released September 2025) as a native function:

```sql
-- PostgreSQL 18+
SELECT uuidv7();
-- → 019535d9-3df7-79fb-b466-fa907fa17f9e
```

UUID v7 structure: `[48-bit millisecond timestamp][12-bit sub-ms][62-bit random]`

The timestamp prefix means **all new inserts land at the right end of the B-tree** — exactly the same insertion pattern as a `BIGSERIAL`. This eliminates the fragmentation and cache miss problems entirely.

If you're on **PostgreSQL 17**, use the `pg_uuidv7` extension (github: `fboulnois/pg_uuidv7`) which provides the same function.

---

### Comparing your four options against your requirements

| | UUID v4 | UUID v7 | Snowflake/bigint | BIGSERIAL |
|---|---|---|---|---|
| Distributed generation | Yes | Yes | Yes (with lib) | No |
| Insert perf at 10M/day | Poor | Good | Excellent | Excellent |
| Index size vs bigint | ~3x (fragmented) | ~2x (inherent 128-bit) | 1x | 1x |
| URL-safe | Yes (hex) | Yes (hex) | Yes (base10) | Yes |
| Storage per ID | 16 bytes | 16 bytes | 8 bytes | 8 bytes |
| Temporal sortable | No | Yes | Yes | Yes |
| Ecosystem/tooling | Excellent | Good, growing | OK | Excellent |

---

### Recommendation for your constraints

**Use UUID v7.** It directly addresses every concern:

- **Distributed generation**: Generate IDs in application code with no DB round-trip
- **Insert performance**: Near-sequential B-tree behavior at 10M rows/day is fine
- **Index size**: You'll pay ~2x vs bigint (unavoidable for 128-bit), but not the 3x fragmentation penalty of v4
- **URL-safe**: Strip hyphens for 32-char hex, or base64url-encode for 22 chars if you want shorter URLs

For PostgreSQL 18 (current as of April 2026):
```sql
CREATE TABLE orders (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    ...
);
```

For PostgreSQL 17:
```sql
CREATE EXTENSION IF NOT EXISTS pg_uuidv7;
CREATE TABLE orders (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v7(),
    ...
);
```

---

### When to choose Snowflake/64-bit instead

Only if storage cost is a hard constraint. Snowflake IDs are 8 bytes vs 16 bytes — indexes will be half the size. The tradeoff: you need a machine-ID coordination mechanism (each app server gets a unique ID), and IDs are not globally unique in the UUID sense (they're unique within your system only). If you're running 3 app servers behind a load balancer, this is operationally simple but still requires a bit of bootstrapping.

---

### The meta-point

The developer showing UUID v4 benchmarks is fighting a battle that was already won. The question isn't "UUID vs bigint" — it's "which UUID version?" and "do the index-size economics matter for our budget?" In 2026, UUID v7 with PostgreSQL 18 is the default right answer for most distributed systems.

Sources:
- [PostgreSQL 18 Release Notes](https://www.postgresql.org/docs/18/release-18.html)
- [PostgreSQL 18 UUID Functions](https://www.postgresql.org/docs/18/functions-uuid.html)
- [PostgreSQL 17 UUID Functions](https://www.postgresql.org/docs/17/functions-uuid.html)