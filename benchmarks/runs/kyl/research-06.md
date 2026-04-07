## Phase 3: Synthesize

I have enough from official sources plus well-established computer science fundamentals. Let me now give you the full answer.

---

## The verdict: use UUID v7

Both developers are partially right, but they're talking past each other. The developer who showed you the benchmark was almost certainly benchmarking **UUID v4** (random), not UUID v7 (time-ordered). These behave completely differently in a B-tree index. Here's the precise breakdown:

---

## Why UUID v4 is genuinely bad for PostgreSQL

The benchmark your developer showed is correct, and the mechanism is well-understood:

PostgreSQL B-tree indexes are sorted structures. When you insert a new key, it goes into a specific leaf page. If that page is full, it splits — typically at the 50% mark.

With **UUID v4** (fully random): every insert targets a statistically random position across the entire index. At scale, nearly every insert:
1. Hits a different index page → **cache miss** (must load from disk)
2. Causes page splits on already-full pages → **write amplification**
3. Leaves pages ~50% filled after splits → **index bloat** (~2x pages needed)

At 100M rows, the index is far larger than RAM, so cache hit rates collapse. The 3x index size and 40% insert slowdown cited in that benchmark are realistic.

---

## Why UUID v7 eliminates the problem

**UUID v7** (RFC 9562, 2024) is a 128-bit identifier with a 48-bit millisecond timestamp prefix, followed by a version nibble, sub-millisecond precision bits, and randomness.

```
019535d9-3df7-79fb-b466-fa907fa17f9e
│──────────────│    │─────────────────│
 48-bit ms timestamp  version + random
```

Because the timestamp is the high-order bits, UUIDs generated at time T are always greater than those generated at time T-1. This makes insertions **append-only** to the right end of the index — exactly like a bigint serial. No random page access, no pathological splits, pages fill to their natural fill factor (~90%).

**Confirmed:** PostgreSQL 18 added `uuidv7()` as a native built-in (per the release notes I fetched). PostgreSQL 17 and earlier only have `gen_random_uuid()` (v4) — you'd need the `pg_uuidv7` extension or client-side generation.

---

## Option comparison for your requirements

| | UUID v4 | UUID v7 | Snowflake | bigint serial |
|---|---|---|---|---|
| **Storage (key)** | 16 bytes | 16 bytes | 8 bytes | 8 bytes |
| **Index size** | ~3x serial | ~2x serial | ~1x serial | 1x baseline |
| **Insert pattern** | Random → fragmentation | Sequential → no fragmentation | Sequential | Sequential |
| **Distributed gen** | Client-side, no coord | Client-side, no coord | Requires machine ID coord | DB sequence needed |
| **URL-safe** | Yes (36 chars) | Yes (36 chars) | Yes (18-19 digits) | Yes (enumerable) |
| **Globally unique** | Yes | Yes | Yes (with coordination) | No (per-DB) |
| **Standard** | RFC 9562 | RFC 9562 | No standard (many variants) | N/A |

---

## The Snowflake tradeoff your developer is missing

Snowflake IDs are 64-bit integers: 41-bit timestamp + 10-bit machine ID + 12-bit sequence. The performance is identical to bigint serial. But:

**Machine ID coordination is a real problem.** For 3 fixed app servers, it's fine — assign machine IDs 1, 2, 3 in config. But in auto-scaling environments (containers, spot instances, rolling deploys), you need a registration service to hand out machine IDs and handle reclamation. Twitter built Snowflake precisely because they could solve this coordination problem at scale; most teams cannot.

There are also **incompatible implementations** (Sonyflake, KSUID, etc.) — "Snowflake-style" is not a standard.

---

## What the developer who used UUIDs at her previous company was probably experiencing

At 500M rows, UUID v4 would produce visible degradation unless: (a) the access patterns were read-heavy with a hot working set that fit in RAM, (b) they had enough memory to cache most index pages, or (c) they were using time-ordered UUIDs already. Her experience is plausible but doesn't invalidate the benchmark — it just means they weren't in the worst-case scenario.

---

## Recommendation

**Use UUID v7, stored as the native `uuid` type (16 bytes, never `text`).**

For your specific requirements:

- **Distributed generation**: Generate UUID v7 client-side in each app server. No DB round-trip, no machine ID coordination. Uniqueness is probabilistically guaranteed (48-bit timestamp + 74 bits of randomness/counter).
- **Insert performance at 10M rows/day**: Sequential append pattern, no fragmentation. Index will behave like a bigint serial, not UUID v4.
- **Index size**: ~2x bigint serial. On a table with 10M rows/day, this is the honest cost of the 128-bit key — but it's dramatically better than UUID v4's 3x-with-fragmentation.
- **URL-safe**: Strip hyphens → 32-char hex string, URL-safe. Or use a base58/base62 encoding in your application layer to get it down to ~22 chars.

```sql
-- PostgreSQL 18+
CREATE TABLE events (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    ...
);

-- PostgreSQL 17 with pg_uuidv7 extension
CREATE EXTENSION IF NOT EXISTS pg_uuidv7;
CREATE TABLE events (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v7(),
    ...
);

-- Or generate client-side (preferred for distributed systems)
-- and insert without relying on DEFAULT at all
```

**The one case where you'd pick Snowflake instead**: you need 8-byte keys for join fanout (many FK references to this table) and you can commit to static machine IDs. The storage difference — 8 bytes vs 16 bytes per row, plus in every FK column — compounds significantly on tables with billions of rows.

**The one case where you'd pick bigint serial**: it's a single-database, non-distributed service where application servers don't need to pre-generate IDs. Use a `CACHE` clause on the sequence (e.g., `CACHE 100`) to minimize sequence lock contention if you're worried about that.

---

## What to tell each developer

**To the UUID-is-terrible developer**: You're right about UUID v4. You're solving the wrong problem by reaching for Snowflake — UUID v7 has identical index behavior to a sequential bigint and requires no coordination.

**To the UUIDs-are-fine developer**: Your previous experience doesn't contradict the benchmark — context matters. But UUID v7 is the rigorous answer, not "UUIDs are fine."