Both developers are anchoring on a false dichotomy. The real answer is **UUIDv7** (or ULID), and here's why:

## The actual problem with UUIDs

The blog post your colleague found is almost certainly benchmarking **UUIDv4** (random UUIDs). The performance problems are real and specific to random distribution:

- Random inserts scatter across the entire B-tree index
- Every insert is likely a cache miss at scale — the "hot" page is wherever the random ID lands
- Index pages fill partially then get abandoned (fragmentation)
- Result: 2-3x larger indexes, poor cache hit ratio, slower inserts

**But this is a UUID version problem, not a UUID problem.**

## Time-ordered UUIDs solve this

**UUIDv7** (RFC 9562) is a 128-bit ID with a 48-bit millisecond timestamp prefix, followed by random bits. Because the high bits are time-ordered, inserts are always near the *right edge* of the index — exactly like a sequential bigint.

This eliminates the fragmentation problem entirely. You get:

| Property | UUIDv4 | UUIDv7 | bigint serial | Snowflake |
|---|---|---|---|---|
| Distributed generation | ✓ | ✓ | ✗ | ✓ (with coordination) |
| Sequential inserts | ✗ | ✓ | ✓ | ✓ |
| No DB round-trip | ✓ | ✓ | ✗ | ✓ |
| Index size (vs bigint) | 2-3x larger | ~2x larger | baseline | baseline |
| URL-safe | needs encoding | needs encoding | ✓ (but enumerable) | ✓ (but enumerable) |
| Globally unique | ✓ | ✓ | ✗ | ✓ |

## For your URL requirement

Store as UUID (16 bytes in PostgreSQL), expose as **base64url** (22 chars, no padding):

```
UUID:      018e5e3f-4b2c-7a1d-8f3e-2b1c4d5e6f7a
base64url: AY5eP0sqeh2P-CsMTF5veg
```

Or use **ULID** which is natively URL-safe (26-char Crockford base32) and stores efficiently as UUID in Postgres.

## Practical recommendation

**Use UUIDv7, stored as `uuid` type in PostgreSQL.**

```sql
CREATE TABLE events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(), -- upgrade to uuidv7() in PG17+
    ...
);
```

For PG < 17, generate UUIDv7 in your application layer (every major language has a library). The type stays `uuid` in the schema.

At 10M rows/day (~115 inserts/sec average, with spikes), you will not hit meaningful performance limits with UUIDv7. The index size penalty vs bigint is ~2x (16 vs 8 bytes), which is real but manageable — for 500M rows an index on one column is roughly 8GB vs 4GB.

## When Snowflake IDs make sense instead

Snowflake is worth the operational complexity (assigning node IDs, running a coordination service, or accepting clock-skew risk) only if you need 8-byte IDs specifically — e.g., you're joining against other systems that use bigint, or storage cost is truly critical at your scale.

For a greenfield service: UUIDv7 wins on simplicity, correctness, and performance. Your UUID-skeptic colleague is right about UUIDv4, but solving that by introducing a coordination service is over-engineering for a problem that time-ordered UUIDs already solved.