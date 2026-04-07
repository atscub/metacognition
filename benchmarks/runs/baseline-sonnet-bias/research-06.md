Both developers are right about different things, and the debate is framing a false dichotomy. The real answer is **UUID v7**.

## Why both sides are partially correct

**The UUID critic is right** — but specifically about UUID v4. Random UUID v4 causes genuine B-tree pathology:
- Every insert hits a random index page → no cache locality
- Pages are constantly split → fragmentation, wasted space
- Index height grows faster → more I/O per lookup
- 16 bytes vs 8 bytes doubles the index entry size

At 100M rows this is measurable. His benchmark is valid.

**The UUID defender is right** — but she probably used UUID v7 or a time-ordered variant without realizing it, or worked on a team that never hit the write amplification wall. UUID v4 on 500M rows with heavy inserts would eventually hurt.

## The actual options and tradeoffs

| Type | Size | Sequential? | Distributed? | Notes |
|---|---|---|---|---|
| `bigserial` | 8B | Yes | No | Requires DB coordination — bottleneck |
| UUID v4 | 16B | No | Yes | The performance villain |
| **UUID v7** | **16B** | **Yes** | **Yes** | Time-ordered, best of both |
| ULID | 16B | Yes | Yes | UUID v7 equivalent, different encoding |
| Snowflake ID | 8B | Yes | Conditional | Needs node ID coordination |

## Recommendation: UUID v7

UUID v7 is time-ordered (monotonically increasing timestamp in high bits, random suffix) which eliminates the entire B-tree fragmentation problem. Sequential inserts mean:
- New rows append to the "right edge" of the index
- Hot pages stay in cache
- No random page splits

PostgreSQL 17 has native `uuidv7()`. If you're on older versions, the `pg_uuidv7` extension is well-maintained.

```sql
-- PostgreSQL 17+
CREATE TABLE events (
    id uuid DEFAULT uuidv7() PRIMARY KEY,
    ...
);

-- Older PostgreSQL with pg_uuidv7 extension
CREATE EXTENSION IF NOT EXISTS pg_uuidv7;
CREATE TABLE events (
    id uuid DEFAULT uuid_generate_v7() PRIMARY KEY,
    ...
);
```

For URLs, UUID v7 without hyphens is 32 hex chars — fine. If you want shorter, encode the 16 bytes as base64url (22 chars) at the application layer, or use ULID encoding (26 Crockford base32 chars). Don't change the storage type for this — handle it in your ID formatting layer.

## Why not Snowflake IDs?

Snowflake (64-bit integer) is smaller and great, but "distributed" is misleading — each node needs a unique node ID assigned somehow. You still need coordination (a config file, a registration service, environment variables per server). If a node ID collides, you get duplicate primary keys. The coordination problem doesn't disappear, it just moves to deployment config.

UUID v7 needs zero coordination. Each app server generates IDs independently with no risk of collision.

## Bottom line

Your 10M rows/day (~115/s average, maybe 1000/s at peak) is well within comfortable range for UUID v7. You get:
- Distributed generation with no coordination
- Sequential inserts (near-bigserial B-tree performance)
- ~2x larger index entries than bigint (16B vs 8B) but no fragmentation tax
- Standard UUID format, URL-safe, widely supported in ORMs and clients

The developer who showed the blog post was reading a 2015-era benchmark comparing UUID v4 to bigint, which was the right comparison at the time. UUID v7 didn't exist then. That benchmark is no longer the relevant reference.