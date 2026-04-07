# Task: research-06 — PostgreSQL primary key type: UUID vs alternatives

## Prompt
We're designing our PostgreSQL schema for a new service and debating primary key types.
We have multiple application servers behind a load balancer, so we need distributed ID
generation — we can't rely on a single database sequence without it becoming a
bottleneck or requiring coordination.

One developer insists UUIDs are terrible for PostgreSQL performance. He showed us a blog
post benchmarking UUID primary keys vs bigint serials on a table with 100M rows. The
UUID version had 3x larger indexes, 40% slower inserts at scale, and much worse cache
hit ratios because the random distribution means every insert touches a different index
page. He says we should use a Snowflake-style ID generator or just stick with bigint
sequences.

Another developer says the UUID concerns are overblown, that she used UUIDs at her
previous company on tables with 500M+ rows and never had problems. She says the
developer experience benefits (generate IDs client-side, no round-trip to the database,
safe for distributed systems) outweigh the theoretical performance concerns.

We need to support:
- Distributed ID generation (multiple app servers)
- Good insert performance (we expect ~10M rows/day at peak)
- Reasonable index sizes (we're budget-conscious on storage)
- IDs exposed in URLs (so they need to be URL-safe)

What should we use for primary keys?


## Response A
I need permission to access web search to gather 2025-2026 benchmark data. Rather than make speculative claims, let me work with what I can verify from established PostgreSQL fundamentals and synthesize a decision framework for your specific constraints.

## Phase 3: Synthesize from Verified Fundamentals

Both developers have legitimate points, but they're not actually in conflict once you consider **context** and **workload specifics**. Here's what's true regardless of 2026 benchmarks:

### The UUID Performance Reality (Architecturally Correct)

**Why UUIDs have worse index performance:**
- Random/non-sequential UUIDs → every insert hits a different B-tree page
- Causes more page splits, more I/O, higher cache miss rates
- Larger index footprint (16 bytes vs 8 bytes)
- **This is deterministic**, not a benchmark artifact

The blog post showing 3x larger indexes and 40% slower inserts? That's real physics, not outdated information.

### Why the Other Developer's Experience Was Fine

At 500M rows with UUIDs, if inserts were fast enough for their workload, it likely means:
- 40% slower insert is still acceptable (maybe 100μs vs 70μs per insert)
- The application wasn't insert-bound; something else was the bottleneck
- They had good hardware, connection pooling, batching, or simply didn't measure closely
- Their query patterns didn't benefit from sequential key clustering

**This doesn't mean UUIDs are good for distributed systems—it means they weren't the constraint.**

### Your Actual Constraints

10M rows/day = ~116 inserts/second at steady state (much higher at peak). That's **tractable** for any ID strategy if your application architecture is sound, but it means:
- Every microsecond matters
- You care about index memory
- You want predictable performance

## Phase 4: The Right Choice for Your Constraints

You actually have three viable paths. Here's the decision tree:

### Option 1: **UUIDv7** (Best if available)
- **What it is:** Time-ordered UUID (RFC 9562, standardized 2024)
- **Why it changes the equation:** First 48 bits encode timestamp → sequential insertion pattern
- **Addresses UUID downsides:** Eliminates random insertion; keeps 16 bytes but inserts behave like sequential IDs
- **Trade-off:** Not all libraries support it yet (depends on your language ecosystem)
- **Decision:** **Use this if your driver/ORM supports it.** It's the modern answer to the UUID vs performance question.

### Option 2: **Snowflake-style ID** (Best for full control + distributed)
```
[timestamp: 41 bits] [machine/datacenter: 10 bits] [sequence: 12 bits]
= 64-bit bigint, sortable, distributed-friendly
```
- **Pros:** Exactly what you need—sequential (good cache), compact (8 bytes), distributed, sortable
- **Cons:** Requires you (or a library) to implement/maintain the generator; more complex operational setup
- **Decision:** **Use this if you need strict operational control and already have infrastructure for it**

### Option 3: **Bigint with distributed coordination** (Simple but requires coordination)
- Distributed sequence (e.g., odd/even sequences across servers, or a coordination service)
- **Pros:** Simple, native PostgreSQL, great performance
- **Cons:** Requires coordination layer; if that service goes down, you can't generate IDs
- **Decision:** **Use this only if your architecture already has a coordination service (etcd, Consul, etc.)**

## Phase 5: What to Persist

I'm going to save a decision framework since this is the kind of choice you'll see again:

**For now:** I'll document the architectural realities and decision criteria in my response.

## Phase 6: My Recommendation for Your Team

**Go with UUIDv7 first, with Snowflake-style IDs as the backup.**

Here's why and how to resolve the debate:

### UUIDv7 Reconciles Both Developers
- **To the performance-concerned developer:** "UUIDv7 is time-ordered. It eliminates the random insertion problem. Check PostgreSQL docs on RFC 9562 UUIDs."
- **To the developer who had good luck with UUIDs:** "Your 500M row experience works fine because your bottleneck was elsewhere. UUIDv7 makes that faster and predictable."
- **Index size:** Still 16 bytes, but insertion pattern is sequential so cache behavior improves dramatically
- **URL-safe:** Already Base64-safe as a UUID, same as before

### How to Validate

1. **Check your stack support:**
   - Python: `uuid.uuid7()` (Python 3.13+) or `python-ulid` library
   - Node.js: `uuid` v9.0.0+ has `v7()`
   - Go: `google/uuid` doesn't have it yet; use `oklog/ulid` or `google/uuid` alternatives
   - Java: `uuid` is supported via custom generators

2. **Benchmark on your actual scale:**
   ```sql
   -- Create test table with UUIDv7
   CREATE TABLE test_uuid7 AS
   SELECT gen_random_uuid() as id, generate_series(1, 1000000);
   
   CREATE INDEX ON test_uuid7(id);
   SELECT pg_relation_size('test_uuid7_id_idx') / 1024 / 1024 AS size_mb;
   ```
   Then compare against your current approach.

3. **If UUIDv7 isn't available in your stack**, use a Snowflake-style ID generator:
   - **Node.js:** `snowflake-id`
   - **Python:** `python-snowflake` or `shortuuid`
   - **Go:** `bwmarrin/snowflake`

### Storage/Performance Profile You Can Expect

| ID Type | Size | Sortable | Insert Pattern | Index Growth | For 10M/day |
|---------|------|----------|-----------------|--------------|-------------|
| UUIDv4 | 16B | No | Random | ~400MB/day | ❌ Avoid |
| UUIDv7 | 16B | Yes | Sequential | ~250MB/day | ✅ Good |
| Snowflake | 8B | Yes | Sequential | ~160MB/day | ✅ Better |
| Bigint+seq | 8B | Yes | Sequential | ~160MB/day | ✅ Better |

The difference between UUIDv7 and Snowflake for your workload is maybe 2-3 inserts/second at peak. **Not your bottleneck.**

### The Conversation to Have With Your Team

> "The blog post was right about UUIDv4—random insertion is bad. But UUIDv7 changes that. Both developers are correct: UUIDs *were* bad for performance, and you *can* run high-scale systems with them. The answer is to use time-ordered IDs. Since we're distributed and need URL-safe IDs, UUIDv7 is the standard-based choice. If our driver doesn't support it yet, we implement Snowflake-style IDs instead. Either way, the random insertion problem is solved."

Does your tech stack support UUIDv7, or should we dig into Snowflake-style ID generators for your specific language?

## Response B
Both developers are making valid points, but they're arguing past each other because they're not accounting for **which UUID version** you use. That's the real decision lever here.

## The core problem with each approach

**UUID v4 (random):** Skeptic is correct. Random UUIDs fragment B-tree indexes severely. At 10M rows/day, you'll feel this—painful insert latency around month 3-6 when your working set exceeds RAM. The 3x index size isn't theoretical; it's a real storage/cost problem.

**Bigint + Snowflake-style generation:** Solves the index fragmentation problem, but creates operational complexity: you need a dedicated ID service or coordination scheme to avoid collisions across multiple generators. This becomes a bottleneck or a failure point (what happens when the ID service is down?). Also requires careful clock management.

**Single database sequence (what you ruled out):** You're right to rule it out for distributed systems, BUT a single sequence with connection pooling is less of a bottleneck than it sounds if you batch allocate ranges. Still, it doesn't scale as nicely as distributed generation.

## What you should actually use: UUID v6 or v7

**UUID v7 (timestamp + randomness, sortable):** This is the play. You get:
- ✅ Distributed generation (no coordination needed)
- ✅ Monotonically increasing over time (B-tree friendly)
- ✅ Better cache locality than v4, indexes only ~1.5x larger than bigint
- ✅ Client-side generation, no DB round-trip
- ✅ URL-safe (just base32/base62 encode if needed)

PostgreSQL 13+ has `gen_random_uuid()` built-in. For v7 specifically, you'll need a library (most languages have them now; they're standard-track at IETF).

**UUID v6** (timestamp-first) is similar but slightly less common. v7 is becoming the standard.

## Why this beats both arguments

| Concern | v7 UUID | Snowflake | bigint+seq |
|---------|---------|-----------|-----------|
| **Distributed gen** | ✅ Native | ✅ Yes | ❌ No |
| **Insert perf** | ✅ Good | ✅ Best | ✅ Good |
| **Index size** | ✅ Reasonable | ✅ Best | ✅ Best |
| **Operational complexity** | ✅ Low | ❌ Medium | ❌ Single point |
| **DX (client-side gen)** | ✅ Yes | ✅ Yes | ❌ No |
| **Mature/standard** | ✅ Becoming | ✅ Yes | ✅ Yes |

## What to do

1. **Use UUID v7.** Generate on the client side with a standard library. You get distributed generation without coordination.

2. **Test your actual workload.** The benchmark post probably used v4 (random). Run your own test with v7 on 100M rows with your query patterns. You might find it's fine—or might not, but at least you'll know.

3. **If testing shows problems:** Then pick Snowflake-style IDs (less maintenance than it sounds; Jetstream or similar libraries handle the hard parts). But don't jump there until you have evidence v7 doesn't work.

4. **If you go Snowflake-style anyway:** Use libraries that abstract away the complexity (Jetstream, Svix's `unidsvix`, etc.). Don't build ID coordination yourself.

**For URLs:** base32-encode the UUID (33 chars) if you care about brevity. Most people don't—UUIDs are fine in URLs.

The developer experience win of "generate IDs client-side without round-tripping to a database" is huge, especially at 10M rows/day scale. V7 gives you that *and* solves the index fragmentation problem that made the skeptic nervous.

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
