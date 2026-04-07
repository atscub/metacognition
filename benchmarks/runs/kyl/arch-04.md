## Socratic Mode: Running the Protocol First

Before recommending anything, let me surface my assumptions and check them.

---

### Assumptions I'm making (flagging confidence levels)

- **High confidence**: The pain points and requirements are real and accurately transcribed.
- **Medium confidence**: CloudFront invalidation API is available and usable. Redis pub/sub or a similar bus (Kafka, Redis Streams) can be added.
- **Low confidence**: The team has equal implementation capacity for both options. Redis memory growth is from key volume, not value size.

---

### Failure mode check before I proceed

**Anchoring risk**: The team framed this as a binary — TTL reduction vs. pub/sub. That framing could anchor me into picking one when the real answer is neither, or both, or something else. I'll actively resist.

**Pattern matching risk**: "Event-driven invalidation is the modern best practice" is a thing I might reach for reflexively. Let me earn that conclusion rather than assume it.

**Authority bias risk**: The product spec sets requirements. I should check whether those requirements are internally consistent before accepting them as constraints.

---

### Are the requirements internally consistent?

Start here, because if they're not, neither option solves the problem.

**Reconciliation reports** spec says:
> "Reports must reflect all transactions processed within the last 30 seconds to support intraday reconciliation workflows."

Current reconciliation cache config:
- Redis TTL: 300s
- CDN max-age: 120s
- Browser: 60s
- stale-while-revalidate: 300s

**This is not a minor gap. The current config allows up to ~8 minutes of staleness (300s Redis + 120s CDN + 60s browser + overlap from SWR). The requirement is 30 seconds. This is an active correctness bug causing the "phantom discrepancies."** The operations team is not imagining things.

**Portfolio summaries** spec says "within 1-2 minutes." Current worst-case: Redis 300s + CDN 60s + browser 30s = could be 5+ minutes before a fresh read lands in browser. Also a real gap, but smaller.

**Market data** spec says "sub-second latency from data provider." Current CDN max-age is 10s, browser is 5s. This requirement cannot be met by any TTL-based CDN strategy. I'll flag this separately.

The requirements are not internally consistent with the current architecture. Fix that first — then evaluate the two options.

---

### Now evaluate Option 1: Reduce all TTLs to 30 seconds

**Steelman (strongest version)**: Simple, no new infrastructure, self-healing, bounded staleness, and reduces Redis memory faster due to faster eviction.

Now actively look for what would make this the *wrong* choice:

**Problem 1 — Stampede gets worse, not better.**
The current 9:30 AM stampede comes from synchronized TTL expiry. If you reduce TTL from 300s to 30s, the cache expires 10× more often. You now have a stampede every 30 seconds instead of every 5 minutes. The cache hit rate collapses. DB load doesn't spike at open — it spikes constantly. This is the opposite of what you want.

**Problem 2 — Reconciliation requirement still fails.**
A transaction processed at T=1s with a 30s TTL might not be visible until T=31s. The 30-second freshness window is a *maximum*, not a guarantee. The requirement says "within the last 30 seconds" — which demands near-instant invalidation on write, not just a short TTL.

**Problem 3 — Undifferentiated treatment of fundamentally different data.**
Transaction history doesn't change often. Portfolio summaries change on trades. Reconciliation reports need near-instant accuracy. Market data needs a different channel entirely. Treating them identically is a design smell.

**Problem 4 — CDN invalidation is not instantaneous.**
CloudFront propagation takes 10–30 seconds globally. Reducing max-age to 30s means CDN frequently re-validates, increasing origin load — but a 30s CDN TTL still doesn't guarantee freshness, and the invalidation cost and latency are real.

**Verdict**: Option 1 makes the stampede materially worse, doesn't actually meet the reconciliation requirement, and collapses cache efficiency across the board. Reject as stated.

---

### Evaluate Option 2: Event-driven cache invalidation via pub/sub

**Steelman**: Invalidation happens immediately on write, per-entity (only the affected portfolio, not all portfolios), TTLs become safety fallbacks rather than the primary freshness mechanism, no unnecessary churn on unchanged data.

Now actively look for what would make this insufficient:

**Problem 1 — CDN is outside your invalidation path.**
Even if you instantly invalidate Redis when a transaction is processed, CloudFront is holding a cached response with `Cache-Control: max-age=120`. Calling the CloudFront invalidation API costs money ($0.005/1,000 paths after the first 1,000/month), takes time to propagate, and doesn't help browsers that already have the cached version.

For reconciliation specifically: if the CDN is in the path, event-driven Redis invalidation alone doesn't fix the phantom discrepancy problem.

**Problem 2 — Pub/sub adds a failure mode.**
If the pub/sub event is dropped (network partition, consumer lag, deployment restart), the cache is never invalidated and you silently serve stale data indefinitely until TTL expires. You need the TTL fallback, which means the system degrades gracefully but the guarantees weaken.

**Problem 3 — Doesn't address stampede.**
Cache invalidation events could cause their own thundering herd: N clients all miss simultaneously after an invalidation, rush to the DB, and generate N identical queries before the cache is repopulated. This is the "cache stampede on invalidation" variant of the same problem.

**Problem 4 — `transaction_processor.py` has no transactional guarantee on cache invalidation.**
```python
def process_transaction(txn: Transaction):
    db.insert(txn)
    db.update(portfolio)
    # publish invalidation event here — but what if this fails?
```
If the pub/sub publish fails after the DB write succeeds, you have stale cache and no retry. This requires at-least-once delivery guarantees and idempotent cache updates.

**Verdict**: Event-driven invalidation is clearly superior to uniform TTL reduction, but it's not sufficient alone. The CDN layer and stampede problem need separate treatment.

---

### What the team isn't considering: data classification

The frame of "one caching strategy for the whole system" is itself the problem. These four data types have fundamentally different characteristics:

| Data type | Change frequency | Staleness tolerance | User impact of stale data |
|---|---|---|---|
| Portfolio summary | On each trade | 1–2 min max | High — portfolio managers make decisions on this |
| Transaction history | Append-only, never changes once written | 5 min acceptable | Medium — historical, not decision-critical |
| Reconciliation reports | Continuous intraday | **30 seconds max** | Critical — triggers automated alerts |
| Market data | Continuous, sub-second | Sub-second | Requires a different architecture entirely |

Market data cannot be served correctly through a CDN with any TTL. This needs WebSockets, SSE, or a direct streaming connection. No cache invalidation strategy solves a latency requirement that CDN propagation itself violates. Flag this to the team as a separate architectural problem.

---

## Recommendation: Differentiated hybrid strategy

### 1. Event-driven invalidation for correctness-critical data

For `portfolio_summary` and `reconciliation_report`:

```python
# transaction_processor.py — revised
def process_transaction(txn: Transaction):
    with db.transaction():
        db.insert(txn)
        portfolio = db.get_portfolio(txn.portfolio_id)
        portfolio.balance += txn.amount
        db.update(portfolio)
        # Write invalidation event to outbox table in same transaction
        db.insert_outbox_event("invalidate", {
            "keys": [
                f"portfolio:{txn.portfolio_id}",
                f"reconciliation:{txn.portfolio_id}:{today()}"
            ]
        })
    # Separate process reads outbox and publishes to Redis pub/sub
    # At-least-once delivery; consumers are idempotent
```

The outbox pattern (transactional outbox) gives you atomicity: the invalidation event is committed with the DB write or neither happens. A separate relay process publishes to Redis pub/sub. Consumers delete the Redis key on receipt.

### 2. Fix the CDN layer per data type

Reconciliation reports **must not be served from CDN cache**. The 30-second requirement is incompatible with CDN caching at any reasonable TTL:

```python
# For reconciliation_report endpoint
response.headers["Cache-Control"] = "no-store, must-revalidate"
response.headers["Surrogate-Control"] = "no-store"  # CloudFront-specific bypass
```

Keep CDN for portfolio_summary but reduce max-age to 30s and use `Surrogate-Key` / CloudFront invalidation tags so you can surgically invalidate by portfolio ID on write.

For transaction_history (append-only, 5-minute tolerance is fine): keep current TTLs. This data doesn't change. No event-driven invalidation needed.

### 3. Fix the stampede with probabilistic early expiration + cache warming

Don't just let TTLs expire synchronously. Use **probabilistic early recomputation** (XFetch algorithm):

```python
def get_with_early_expiry(key, ttl, recompute_fn, beta=1.0):
    value, expiry = redis.get_with_ttl(key)
    if value is None:
        value = recompute_fn()
        redis.set(key, value, ttl)
        return value
    
    # Probabilistically recompute before expiry to prevent stampede
    remaining = expiry - time.time()
    if -beta * math.log(random.random()) * avg_recompute_time >= remaining:
        # Recompute in background, serve current cached value
        background_task(recompute_fn, key, ttl)
    
    return value
```

Additionally, **pre-warm the cache before 9:30 AM ET** for the top N portfolios by AUM. A scheduled job at 9:25 AM populates Redis with fresh data before the stampede window.

### 4. Fix Redis memory

At 12/16 GB, you're approaching the limit. Two actions:

- **Set eviction policy to `allkeys-lru`** if not already set — this ensures Redis evicts least-recently-used keys under memory pressure rather than erroring.
- **Audit key proliferation**: run `redis-cli --bigkeys` and `redis-cli --scan` to find if you have unbounded key growth (e.g., per-user-per-session keys that never expire). Event-driven invalidation helps here too — keys are deleted on write rather than lingering until TTL.

---

### Revised cache config reflecting this strategy

```python
CACHE_SETTINGS = {
    "portfolio_summary": {
        "redis_ttl": 300,              # Safety fallback only; event-driven invalidation is primary
        "cdn_max_age": 30,             # Reduced; use Surrogate-Key for surgical invalidation
        "browser_max_age": 0,          # Force revalidation; rely on CDN/Redis
        "stale_while_revalidate": 60,
        "invalidation": "event_driven",
    },
    "transaction_history": {
        "redis_ttl": 300,              # Unchanged — append-only, low churn
        "cdn_max_age": 120,
        "browser_max_age": 60,
        "stale_while_revalidate": 300,
        "invalidation": "ttl_only",    # No event-driven needed
    },
    "reconciliation_report": {
        "redis_ttl": 25,               # Must be < 30s; event-driven clears it faster
        "cdn_max_age": 0,              # NO CDN CACHING — Cache-Control: no-store
        "browser_max_age": 0,
        "stale_while_revalidate": 0,
        "invalidation": "event_driven",
    },
    "market_data": {
        # Remove from this config entirely.
        # Serve via WebSocket/SSE from a streaming data provider connection.
        # TTL-based caching cannot meet sub-second latency requirements.
    },
}
```

---

### Addressing each pain point directly

| Pain point | Root cause | Fix |
|---|---|---|
| Stale portfolio balances (up to 5 min) | No invalidation on write; Redis TTL 300s | Event-driven invalidation on `process_transaction`; CDN Surrogate-Key invalidation |
| Phantom reconciliation discrepancies | Cache TTL 300s+; CDN 120s; requirement is 30s | `no-store` on CDN; Redis TTL 25s; event-driven invalidation; outbox pattern for atomicity |
| Cache stampede at 9:30 AM | Synchronized TTL expiry; no pre-warming | Probabilistic early expiration (XFetch); scheduled pre-warm job at 9:25 AM |
| Redis memory at 12/16 GB | Likely key proliferation + long TTLs on stale data | Audit with `--bigkeys`; `allkeys-lru` eviction; event-driven invalidation reduces lingering keys |

---

### What I'm uncertain about (honesty checkpoint)

- **Medium confidence** on the CloudFront Surrogate-Key invalidation approach — verify your CloudFront distribution supports this. Some CDN configs require specific headers. Test invalidation propagation latency in your actual environment before relying on it for the reconciliation use case. If it's too slow, `no-store` is the safer fallback.
- **Low confidence** on Redis memory root cause — I don't have visibility into your key patterns. Run `redis-cli --bigkeys` before assuming eviction policy changes alone will help.
- The outbox pattern adds an async relay step. If your team isn't familiar with it, **Redis Streams with consumer groups** is a simpler entry point that gives you at-least-once delivery with less infrastructure.

The market data architecture issue is a separate conversation, but don't let it get buried — it's a category error in the current design, and no cache tuning fixes it.