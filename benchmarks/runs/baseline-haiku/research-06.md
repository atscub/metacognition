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