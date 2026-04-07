# Task: arch-04 — Cache invalidation strategy for financial dashboard

## Prompt
You are the backend architect for FinView, a real-time financial dashboard used by
portfolio managers at investment firms. The system displays portfolio values, transaction
history, and reconciliation reports.

Current caching architecture:

```
Client (Browser)                CDN (CloudFront)           App Server           Redis Cache          PostgreSQL
     │                               │                        │                    │                    │
     │── GET /api/portfolio ────────>│                        │                    │                    │
     │                               │── Cache-Control: ─────>│                    │                    │
     │                               │   max-age=60           │── GET portfolio ──>│                    │
     │                               │                        │   TTL: 5 min       │                    │
     │                               │                        │                    │── SELECT ... ─────>│
     │                               │                        │<── cached data ────│                    │
     │<── cached response ───────────│                        │                    │                    │
```

Current cache configuration:
```python
# cache_config.py
CACHE_SETTINGS = {
    "portfolio_summary": {
        "redis_ttl": 300,         # 5 minutes
        "cdn_max_age": 60,        # 1 minute
        "browser_max_age": 30,    # 30 seconds
        "stale_while_revalidate": 120,
    },
    "transaction_history": {
        "redis_ttl": 300,         # 5 minutes
        "cdn_max_age": 120,       # 2 minutes
        "browser_max_age": 60,    # 1 minute
        "stale_while_revalidate": 300,
    },
    "reconciliation_report": {
        "redis_ttl": 300,         # 5 minutes
        "cdn_max_age": 120,       # 2 minutes
        "browser_max_age": 60,    # 1 minute
        "stale_while_revalidate": 300,
    },
    "market_data": {
        "redis_ttl": 15,          # 15 seconds
        "cdn_max_age": 10,        # 10 seconds
        "browser_max_age": 5,     # 5 seconds
        "stale_while_revalidate": 30,
    },
}
```

Data flow for transactions:
```python
# transaction_processor.py
def process_transaction(txn: Transaction):
    db.insert(txn)
    # Update portfolio balance
    portfolio = db.get_portfolio(txn.portfolio_id)
    portfolio.balance += txn.amount
    db.update(portfolio)
    # No cache invalidation — relies on TTL expiry
    logger.info(f"Transaction {txn.id} processed")
```

System requirements (from product spec v2.3):
- Portfolio summaries: "near real-time, within 1-2 minutes of transaction processing"
- Transaction history: "updated within 5 minutes of new transactions"
- Market data overlay: "real-time, sub-second latency from data provider"
- Reconciliation reports: "Operations team uses these to verify end-of-day positions.
  Reports must reflect all transactions processed within the last 30 seconds to support
  intraday reconciliation workflows. Discrepancies trigger automated alerts."
- Dashboard load time: < 2 seconds for the full dashboard
- Availability: 99.9% uptime during market hours (9:30 AM - 4:00 PM ET)

Current pain points:
- Portfolio managers sometimes see stale balances after large trades (up to 5 min delay)
- The operations team has reported "phantom discrepancies" in reconciliation reports
  that resolve themselves after a few minutes — they suspect caching
- During market open (9:30 AM), cache stampede causes DB load to spike 10x
- Redis memory usage is growing; currently at 12 GB of a 16 GB instance

The engineering team is debating two approaches:
1. **Reduce all TTLs** to 30 seconds across the board
2. **Add event-driven cache invalidation** using a pub/sub system triggered on writes

Evaluate both approaches and recommend a cache invalidation strategy. Address each of
the pain points and requirements listed above.


## Response A
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

## Response B
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
