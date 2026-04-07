I need web search permissions to properly research this. Let me take a different approach—I'll synthesize what I can reason about from first principles and be transparent about what I can and can't verify, then help you think through the decision properly.

## Phase 1: What I'm Confident About vs. Uncertain

**Confident (fundamental CS):**
- Random IDs cause index fragmentation because inserts scatter across pages instead of clustering at leaf boundaries
- Ordered IDs (timestamps + counter) improve cache locality and write performance
- UUIDs v4 are random; UUIDs v1/v7 are time-ordered
- Snowflake/ULID/Nanoid patterns are time-ordered and designed for distributed systems

**Uncertain (needs verification):**
- Whether the 3x index size and 40% slowdown in that blog post are still representative
- If PostgreSQL versions have improved UUID handling
- Whether UUIDv7 is now a practical solution (RFC 9562 was only finalized in 2024)
- What the 2025 consensus actually is

## Phase 2: What the Debate Actually Hinges On

Your team is experiencing a **reconciliation failure**—both developers are probably right *in different contexts*:

1. **The critical details the blog post likely had** (but you didn't mention):
   - What PostgreSQL version? (v12 vs v15+ might differ)
   - Table size when was the data inserted? (Fragmentation is cumulative)
   - What other indexes? (UUIDs hurt more when there are many indexes)
   - Workload pattern? (Random reads vs. sequential scans matter)

2. **Why the anecdote doesn't disprove the blog**: 
   - 500M rows can perform fine with UUIDs *if* the workload doesn't hit the specific pain points (fragmentation from inserts)
   - App-level caching can mask database index miss problems
   - Different hardware, table schemas, or insert patterns

## Phase 3: The Real Analysis for Your Case

Given your constraints:

| Factor | Implication |
|--------|-----------|
| **~10M rows/day at peak** | You'll hit 365M rows/year. At that scale, index performance matters. This is large enough that the UUID criticism becomes real. |
| **Multiple app servers** | You need distributed IDs. Options: (1) distributed sequence coordination, (2) client-side generation |
| **Budget-conscious on storage** | Index size is a real cost. UUID indexes will be ~1.5-2x larger than bigint. At 365M rows, that matters. |
| **IDs in URLs** | Must be URL-safe. Bigint is URL-safe. UUIDs are fine. Snowflake IDs are fine. No blocker here. |

## Phase 4: The Actual Options (with tradeoffs)

**Option A: Snowflake-style ID (e.g., using a library)**
```
Pros:
- Time-ordered → best index performance
- Client-generated → no DB coordination
- Compact (64-bit, fits bigint)
- URL-safe

Cons:
- Requires ID generator logic (clock synchronization matters)
- Not a SQL standard type
- Library dependency + potential bugs
- Collisions possible if not careful with worker IDs
```

**Option B: UUIDv7 (if PostgreSQL 13+)**
```
Pros:
- Time-ordered → much better than v4
- Standard RFC 9562 (finalized 2024)
- Built into database (no external library)
- No clock sync needed beyond NTP

Cons:
- Still ~16 bytes vs 8 bytes for bigint
- Index is still larger than bigint
- Need PostgreSQL 13+ native support or extension
- Real-world performance data is limited (too new)
```

**Option C: UUID v4 (random)**
```
Pros:
- No library needed
- Standard
- Easy

Cons:
- Worst index performance (the blog post was right about this)
- At your scale (10M/day), you'll feel it in 2-3 years
- Indexes will be large
```

**Option D: Distributed sequence (with coordination)**
```
Pros:
- Best performance (bigint is compact and ordered)
- No external library

Cons:
- Requires coordination layer (pgbouncer, custom middleware, or app-level)
- More complex
- Potential bottleneck at scale (sequence contention)
```

## Phase 5: What I'd Actually Recommend

**For your specific case: Use Snowflake-style IDs** (like `github.com/bwmarrin/snowflake` or `github.com/sony/sonyflake`)

Here's why:
1. **The blog post's criticism was justified**: Random UUIDs *will* bite you at 10M/day scale.
2. **UUIDv7 is too risky**: It's brand new (RFC just finalized), PostgreSQL support is evolving, and production data on performance at scale is scarce.
3. **Distributed sequences are complex**: Worth avoiding if you have a simpler option.
4. **Snowflake IDs hit the sweet spot**: 
   - Time-ordered (addresses the cache/fragmentation issue)
   - Client-generated (no DB round-trip, distributed-friendly)
   - Well-proven pattern (Twitter, Discord, etc. use this)
   - Compact (64-bit, fits in bigint column)
   - Mature libraries in all languages

**The catch**: You need to handle worker ID assignment (which server generated this ID?). This is a one-time setup problem, not an ongoing maintenance burden.

---

**Before you decide: Verify these claims**
- Check if your team's blog post is from 2019 vs 2024 (age matters for PostgreSQL performance)
- Test UUIDv7 insertion performance on a sample 100M row table if you want that option
- Look at your actual insertion pattern: Are you doing bulk loads or one-row-at-a-time? (bulk load masks fragmentation)

**What would genuinely help**: Can you share or describe the blog post? The date, PostgreSQL version tested, and exact workload would let me assess whether it's still applicable.