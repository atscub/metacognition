## Cache Invalidation Strategy for FinView

### TL;DR

Approach 1 (reduce all TTLs) makes two of your four pain points *worse*. Approach 2 (event-driven) is the right foundation but incomplete — you need it combined with per-data-type cache policy differentiation, stampede mitigation, and a WebSocket replacement for market data.

---

## Why Approach 1 Fails

Reducing all TTLs to 30s across the board:

**Stampede gets worse, not better.** Your 10x DB spike at market open happens precisely because all cache entries expire together. At 30s TTLs, you'd stampede every 30 seconds throughout market hours, not just at open.

**Reconciliation still breaks.** The requirement is data reflecting the last 30 seconds. With 30s Redis TTL + 120s CDN + 60s browser, worst-case staleness is still ~3.5 minutes. You'd have to eliminate CDN and browser caching entirely for reconciliation, which breaks dashboard load time.

**Market data regresses.** Your market data TTL is already 15s Redis / 10s CDN / 5s browser. A global 30s floor makes it *more* stale.

**DB load increases substantially** with no correctness guarantee in return. Cache hit rates drop; you traded headroom for a problem you haven't solved.

---

## Why Approach 2 (Event-Driven) is the Right Foundation

Write-through invalidation eliminates the correctness gap. When `process_transaction` completes, the cache reflects that fact immediately rather than at the next TTL boundary. This is the only architecture that can satisfy the reconciliation requirement.

```python
# transaction_processor.py — with invalidation
def process_transaction(txn: Transaction):
    db.insert(txn)
    portfolio = db.get_portfolio(txn.portfolio_id)
    portfolio.balance += txn.amount
    db.update(portfolio)

    # Publish invalidation event
    cache_bus.publish("invalidate", {
        "keys": [
            f"portfolio:{txn.portfolio_id}",
            f"transactions:{txn.portfolio_id}",
            "reconciliation:current",  # scope as needed
        ],
        "reason": "transaction_committed",
        "txn_id": txn.id,
    })
    logger.info(f"Transaction {txn.id} processed, cache invalidated")
```

But event-driven alone is not enough — you still need to answer: invalidate *which* layers?

---

## Recommended Strategy: Differentiated by Data Type

### 1. Portfolio Summaries — requirement: 1-2 min

The multi-layer cache (Redis + CDN + browser) means invalidating Redis alone leaves CDN serving stale for another 60s. Two options:

**Option A** (simpler): Keep CDN TTL at 60s, invalidate Redis on write, accept up to 90s staleness total. Satisfies the 1-2 min requirement with margin.

**Option B** (tighter): Issue a CloudFront programmatic invalidation on write. Takes 15-30s, costs $0.005/1000 paths — acceptable given transaction frequency. Use surrogate keys (`Cache-Tag: portfolio-{id}`) for targeted purging rather than path-based invalidation.

```python
CACHE_SETTINGS["portfolio_summary"] = {
    "redis_ttl": 600,          # Safety net only; invalidate on write
    "cdn_max_age": 60,         # Keep; CDN invalidation handles freshness
    "browser_max_age": 30,
    "stale_while_revalidate": 60,
}
```

### 2. Reconciliation Reports — requirement: <30s, **currently broken**

This is your most critical gap. Current worst case: 300s + 120s + 60s = ~8 minutes stale. Required: 30 seconds. The entire CDN and browser caching layer must be bypassed for the operations team.

```python
CACHE_SETTINGS["reconciliation_report"] = {
    "redis_ttl": 30,           # Short; invalidate on every write anyway
    "cdn_max_age": 0,          # Cache-Control: no-store
    "browser_max_age": 0,
    "stale_while_revalidate": 0,
}
```

Serve ops team responses with `Cache-Control: no-store, private`. Redis still provides value (30s protects against thundering herd within the ops tooling), but invalidate it on every transaction commit. At that point the 30s TTL is just a fallback, not the primary freshness mechanism.

### 3. Transaction History — requirement: 5 min

Current architecture actually satisfies this *if* you add write invalidation. The Redis TTL is fine; the issue is that `process_transaction` never invalidates. Add the event, leave the TTLs.

```python
CACHE_SETTINGS["transaction_history"] = {
    "redis_ttl": 300,          # Unchanged; invalidate on write
    "cdn_max_age": 120,        # Unchanged
    "browser_max_age": 60,
    "stale_while_revalidate": 300,
}
```

### 4. Market Data — requirement: sub-second

**This cannot be solved with caching.** Your current 15s Redis TTL already violates "sub-second latency from data provider" — you're serving data that's up to 15 seconds old and calling it real-time.

Replace polling with a streaming connection:

```
Browser ←── WebSocket/SSE ──── App Server ←── Market Data Feed (direct)
```

Remove market data from Redis entirely. The CDN is irrelevant for streaming. This frees roughly whatever market data is consuming in your 12 GB Redis footprint, and it's the only architecture that actually satisfies the requirement.

---

## Fixing the Cache Stampede

The stampede at 9:30 AM is a TTL synchronization problem. Three complementary fixes:

**1. TTL jitter on write.** When populating a cache entry, add ±15% random offset:

```python
import random

def cache_set(key, value, base_ttl):
    jitter = random.uniform(-0.15, 0.15)
    actual_ttl = int(base_ttl * (1 + jitter))
    redis.setex(key, actual_ttl, value)
```

This spreads expirations across a window rather than synchronizing them.

**2. Cache warming before market open.** At 9:25 AM, a scheduled job pre-populates portfolio summaries for all active managers. Entries are fresh when 9:30 AM hits.

```python
# cron: 9:25 AM ET weekdays
def warm_portfolio_cache():
    active_portfolios = db.get_active_portfolios()
    for portfolio_id in active_portfolios:
        data = db.compute_portfolio_summary(portfolio_id)
        cache_set(f"portfolio:{portfolio_id}", data, base_ttl=300)
```

**3. Probabilistic early refresh (XFetch / "dogpile prevention").** When a cache entry is within a threshold of expiry, the first request that detects it triggers recomputation while others continue serving the existing value:

```python
def get_with_early_refresh(key, compute_fn, ttl, beta=1.0):
    cached = redis.get(key)
    if cached:
        remaining_ttl = redis.ttl(key)
        # Probabilistically refresh as TTL approaches 0
        if random.random() < beta * (1 - remaining_ttl / ttl):
            if redis.set(f"lock:{key}", "1", nx=True, ex=5):
                # Won the lock — recompute in background
                threading.Thread(target=lambda: refresh_cache(key, compute_fn, ttl)).start()
        return cached
    return compute_fn()
```

---

## Fixing Redis Memory Growth

At 12 GB of 16 GB, you have headroom issues. Likely causes and fixes:

**Audit what's consuming memory** before optimizing blindly:
```bash
redis-cli --bigkeys
redis-cli memory doctor
```

**Immediate wins:**
- Removing market data from Redis (should be WebSocket anyway) likely reclaims meaningful space
- Reconciliation reports with 300s TTL: if these are large payloads, this adds up. Validate whether per-request caching is even appropriate or if a single "current report" key suffices.

**Set an eviction policy** to prevent unbounded growth:
```
maxmemory-policy allkeys-lru
```

Without this, Redis will error on new writes when full rather than evicting stale entries. LRU eviction is a reasonable safety net.

**Compress large cached objects.** If reconciliation reports or transaction history payloads are multi-KB, gzip before storing:

```python
import gzip, json

def cache_set_compressed(key, value, ttl):
    payload = gzip.compress(json.dumps(value).encode())
    redis.setex(key, ttl, payload)
```

---

## Summary: What to Change

| Data Type | Redis TTL | CDN | Browser | Invalidation |
|---|---|---|---|---|
| Portfolio summary | 600s (safety net) | 60s | 30s | On every transaction write |
| Transaction history | 300s (safety net) | 120s | 60s | On every transaction write |
| Reconciliation | 30s (safety net) | **no-store** | **no-store** | On every transaction write |
| Market data | **removed** | **removed** | **removed** | WebSocket/SSE |

**Additionally:**
1. Add TTL jitter (±15%) on all cache writes
2. Add 9:25 AM cache warming job for portfolio summaries
3. Set `maxmemory-policy allkeys-lru` on Redis
4. Run `redis-cli --bigkeys` to identify memory culprits

The event-driven approach is correct. The mistake would be treating it as a complete solution without also fixing the CDN layer for reconciliation and replacing caching with streaming for market data.