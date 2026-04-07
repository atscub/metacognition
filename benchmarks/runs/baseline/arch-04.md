## Cache Invalidation Analysis for FinView

### The Core Problem

Before evaluating either option, the architecture has a fundamental contract violation: reconciliation reports require data within 30 seconds, but the current stack has **5-min Redis TTL + 2-min CDN + 1-min browser = up to 8 minutes of potential staleness**. No TTL reduction alone can fix this cleanly.

Additionally, `process_transaction()` has no cache invalidation at all — so every TTL starts from the last cache warm, not from the last write.

---

## Option 1: Reduce All TTLs to 30 Seconds

### What it fixes
Reduces worst-case staleness. Simpler to ship.

### Why it fails each pain point

**Stale portfolio balances** — Partially mitigated, but still up to 30s stale. More importantly, a transaction processed at second 1 of a 30s window gives you the full 30s window of wrong data. TTL reduction doesn't change the write-to-invalidation gap.

**Phantom reconciliation discrepancies** — The 30-second spec requirement is a write-latency SLA, not a polling frequency. With stacked CDN (30s) + browser (30s), worst-case is still 60s from write to user seeing accurate data. The requirement is broken by design unless you eliminate CDN caching for this endpoint.

**Cache stampede at market open** — **This gets worse.** You're currently sustaining a 10x DB spike with ~5-min TTLs. At 30s, the same keys expire 10× more often. With 1,000 concurrent users at 9:30 AM open, you'd push DB load significantly higher. This is the most critical regression risk.

**Redis memory growth** — No impact. Memory usage is driven by key count and value size, not TTL. Shorter TTLs don't reduce peak memory (keys still exist until expiry), and higher DB load may increase key churn overhead.

**Summary:** Option 1 is the wrong lever for every problem it's supposed to solve, and actively worsens the stampede.

---

## Option 2: Event-Driven Cache Invalidation

This is architecturally correct but needs to be applied with precision. The recommendation below is this approach with three additions: **CDN bypass rules** for sensitive endpoints, **background refresh** to kill the stampede, and **per-data-type TTL strategy**.

---

## Recommended Architecture

### Fix 1: Invalidate on Write

```python
# transaction_processor.py
import redis
import json

r = redis.Redis()

def process_transaction(txn: Transaction):
    db.insert(txn)
    portfolio = db.get_portfolio(txn.portfolio_id)
    portfolio.balance += txn.amount
    db.update(portfolio)

    # Invalidate affected caches immediately
    r.publish("cache_invalidation", json.dumps({
        "keys": [
            f"portfolio:{txn.portfolio_id}",
            f"reconciliation:{txn.portfolio_id}:{today()}",
            f"transaction_history:{txn.portfolio_id}",
        ],
        "reason": "transaction_written",
        "txn_id": txn.id,
    }))
    logger.info(f"Transaction {txn.id} processed, invalidation published")
```

```python
# cache_invalidation_worker.py
def handle_invalidation(message):
    payload = json.loads(message["data"])
    for key in payload["keys"]:
        r.delete(key)
    # Optionally: trigger background recomputation here
```

This closes the write-to-visibility gap from "up to TTL" to "within seconds."

### Fix 2: Remove CDN Caching for Reconciliation and Per-User Data

The CDN is a shared cache — it serves one user's response to every subsequent user. Portfolio summaries and reconciliation reports are user/portfolio-scoped. CDN caching is either wrong (serving User A's data to User B) or ineffective (cache-busting per user negates CDN benefits).

```python
# response_headers.py
CACHE_HEADERS = {
    "portfolio_summary": {
        # Private: CDN won't cache; browser can
        "Cache-Control": "private, max-age=30, stale-while-revalidate=60",
    },
    "reconciliation_report": {
        # No caching anywhere — 30s write SLA can't survive CDN
        "Cache-Control": "no-store",
        "CDN-Cache-Control": "no-store",  # CloudFront-specific override
    },
    "transaction_history": {
        "Cache-Control": "private, max-age=30, stale-while-revalidate=120",
    },
    "market_data": {
        # CDN is the wrong transport for sub-second data — see Fix 4
        "Cache-Control": "no-store",
    },
}
```

### Fix 3: Probabilistic Early Expiration to Kill the Stampede

The 9:30 AM spike is a thundering herd: keys set at open expire together, and hundreds of requests hit the DB simultaneously. Two mitigations:

**Jitter on TTL:** Spread expiry times so keys don't all expire simultaneously.

```python
import random

def set_cache(key: str, value, base_ttl: int):
    # ±15% jitter prevents synchronized expiry
    jitter = random.uniform(0.85, 1.15)
    actual_ttl = int(base_ttl * jitter)
    r.setex(key, actual_ttl, serialize(value))
```

**Probabilistic Early Expiration (PER):** When a key is approaching expiry, probabilistically trigger a background refresh so the cache never actually goes cold under load.

```python
def get_cache_per(key: str, beta: float = 1.0):
    """
    Fetch from cache, triggering early recompute as expiry approaches.
    beta > 1 = more aggressive early recompute.
    """
    data = r.get(key)
    if data is None:
        return None
    
    value, computed_at, ttl = deserialize(data)
    remaining = r.ttl(key)
    
    # Probabilistically recompute early as TTL shrinks
    if -beta * ttl * math.log(random.random()) > remaining:
        return None  # Treat as cache miss → triggers recompute
    
    return value
```

Pre-warm critical portfolio keys at 9:25 AM before market open so the first wave of requests hits warm caches:

```python
# scheduler.py
@schedule("25 9 * * 1-5", tz="America/New_York")  # 9:25 AM weekdays
def prewarm_market_open():
    for portfolio_id in db.get_active_portfolios():
        warm_cache(f"portfolio:{portfolio_id}")
```

### Fix 4: Market Data Off HTTP/CDN Entirely

Sub-second latency is structurally incompatible with HTTP request-response + CDN. Even a 1-second CDN TTL violates the spec, and CDN round-trips alone consume 50–200ms.

Market data should be pushed over **WebSocket or SSE**, not polled:

```python
# market_data_ws.py
async def market_data_stream(websocket, portfolio_id: str):
    async for tick in market_data_provider.subscribe(portfolio_id):
        # Serve directly from provider stream, no caching layer
        await websocket.send(json.dumps(tick))
```

Redis can still be used as a "last known good" value for initial page load, but updates must be pushed. Remove market data from the CDN configuration entirely.

### Fix 5: Redis Memory

The 12/16 GB usage needs investigation before the new invalidation strategy changes the pattern:

```bash
# Audit key distribution
redis-cli --scan --pattern "*" | awk -F: '{print $1}' | sort | uniq -c | sort -rn

# Find largest keys
redis-cli --bigkeys

# Check memory per key type
redis-cli memory usage <key>
```

Event-driven invalidation will help here: with proactive invalidation, you can safely raise Redis TTLs (they become safety nets, not primary mechanisms). Longer TTLs mean fewer cache-miss-driven writes and lower key churn. But also audit for:
- User-session-scoped keys that never get invalidated
- Large serialized objects (consider field-level caching for portfolios with many positions)
- Eviction policy — use `allkeys-lru` if you haven't already

---

## Revised Cache Configuration

```python
CACHE_SETTINGS = {
    "portfolio_summary": {
        "redis_ttl": 300,         # Safety net only; invalidation-on-write is primary
        "cdn_cache": False,       # Private data; CDN bypass via Cache-Control: private
        "browser_max_age": 30,
        "stale_while_revalidate": 60,
        "invalidation_events": ["transaction.written", "position.updated"],
    },
    "transaction_history": {
        "redis_ttl": 300,         # Safety net; invalidated on new transaction
        "cdn_cache": False,
        "browser_max_age": 30,
        "stale_while_revalidate": 120,
        "invalidation_events": ["transaction.written"],
    },
    "reconciliation_report": {
        "redis_ttl": 60,          # Short safety net
        "cdn_cache": False,       # Cache-Control: no-store
        "browser_cache": False,
        "invalidation_events": ["transaction.written"],
        # Note: ops users should have consistent read guarantees;
        # consider bypassing Redis too and reading from DB replica
    },
    "market_data": {
        "redis_ttl": 5,           # Last-known-good for initial load only
        "cdn_cache": False,
        "transport": "websocket", # Not HTTP polling
    },
}
```

---

## Pain Point Resolution Summary

| Pain Point | Root Cause | Fix |
|---|---|---|
| Stale balances (up to 5 min) | No invalidation on write | Publish invalidation event in `process_transaction()` |
| Phantom reconciliation discrepancies | 8-min staleness chain; CDN shared cache | `no-store` on reconciliation + write-triggered invalidation |
| Cache stampede at 9:30 AM | Synchronized TTL expiry | TTL jitter + PER + pre-warming at 9:25 AM |
| Redis memory (12/16 GB) | Key proliferation; needs audit | Audit key patterns; event-driven allows longer safety-net TTLs |
| Market data sub-second SLA | CDN/HTTP polling architecture | Migrate to WebSocket/SSE push |

---

## What to Ship First

The stampede and reconciliation bugs are the highest-severity issues. Suggested order:

1. **Add `r.publish()` in `process_transaction()`** + invalidation worker — closes the write-visibility gap for portfolio and reconciliation
2. **Add `Cache-Control: no-store` on reconciliation endpoints** — immediately stops CDN from serving stale reports
3. **Add TTL jitter** — 30 lines of code, significant stampede reduction
4. **Redis memory audit** — before the above changes shift key patterns
5. **WebSocket for market data** — larger change, can be parallelized with above

Option 1 (reduce all TTLs) makes the stampede worse and doesn't meet the reconciliation SLA. Option 2 is the right direction, but the CDN bypass rules and market data transport change are necessary complements — pub/sub alone doesn't fix shared-cache correctness problems.