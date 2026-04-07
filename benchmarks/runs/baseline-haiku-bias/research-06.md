This is a classic false dichotomy being framed as a binary choice. Both developers are right about their specific claims, but they're optimizing for different things. Let me break down what's actually true:

## The Performance Concerns Are Real, But Conditional

**UUID v4 (random) does create problems:**
- Larger indexes (~2-3x) due to random distribution
- Slower sequential inserts because each write hits different index pages
- Worse cache locality in B-tree traversals
- The blog post benchmark is probably accurate for their scenario

**But those problems matter *proportionally* less at your scale:**
- 10M rows/day = ~3.65B rows/year. The benchmark ran 100M rows (3 months at your rate)
- At 10M rows/day, the difference between "3x index size" and normal might be 50-100GB vs 20-50GB
- Cache misses hurt more on 500B-row tables than 3-5B-row tables
- If you're not hitting the specific bottleneck (index page thrashing), the theoretical overhead doesn't materialize

**The developer who succeeded with UUIDs at scale probably:**
- Had different workload patterns (less insert-heavy, different query patterns)
- Had more hardware/budget to throw at it
- Hit the ceiling anyway but didn't notice or didn't care

## What Actually Matters for Your Decision

You need to be honest about these constraints:

1. **Distributed ID generation**: UUIDs win here (trivial). Snowflake-style IDs require a coordinator or risk collisions. Sequences require database round-trips.

2. **Index size is a real cost**: At your scale, 2-3x index size is $500-1000/month in cloud database costs, compounding. Over 3 years, that's real money if you're budget-conscious.

3. **Insert performance**: "40% slower" matters only if you're CPU-bound on inserts. You're not at 10M rows/day unless you're batching. Batch inserts? UUIDs won't be your bottleneck.

4. **URL-safe**: Both work fine here. UUIDs are standard. Snowflake IDs are smaller and easier on the eye.

## The Real Question You Haven't Asked

**What are you actually optimizing for?**

- **Time to launch + developer velocity?** Use UUIDs. Client-side generation is simpler. You can always migrate later.
- **Long-term cost + operational simplicity?** Use Snowflake-style IDs (or ULID). Smaller, faster, URL-friendly, still distributed.
- **Future growth?** Snowflake-style leaves you with more headroom before you hit the real bottlenecks (tablespace, query performance on huge joins, not index size).

## What I'd Actually Do

**Use a Snowflake variant** (there are good Rust/Go libraries; pick one that matches your stack):

- ✅ Distributed: No database coordination needed
- ✅ Smaller than UUID: ~8 bytes vs ~16 bytes  
- ✅ Faster inserts: Sequential/clustered, locality-friendly
- ✅ URL-safe: 64-bit numbers are clean (or use base62 encoding)
- ✅ Fits your budget constraint better
- ❌ Requires a small library/generator (minor operational overhead)

**If you go Snowflake**, you dodge the index size problem entirely, you get faster inserts, and you're still fully distributed.

**If you go UUID**, you'll probably be fine—but you're betting that the performance overhead won't matter. That's a reasonable bet if you're confident about your scale and if developer experience is more valuable than storage cost. Just don't be surprised if your DBAs complain about index sizes in 18 months.

**Don't use sequences with coordination** unless your app servers are few and proxied through a single connection pool. That's complexity that solves a problem you don't have yet.

---

**Bottom line:** The benchmark was honest, your colleague's experience was real, and you're not wrong to worry about cost. But the choice isn't "performance vs. developer experience"—it's "which distributed ID scheme trades off which costs proportionally best for *your* scenario." Snowflake-style IDs give you the best of both.