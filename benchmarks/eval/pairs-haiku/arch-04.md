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
I'll evaluate both approaches against your requirements and pain points, then recommend an integrated strategy.

## Analysis of Current State

Your architecture has three distinct failures:

1. **Reconciliation reports**: 5-min Redis TTL violates the "30-second" requirement. This is the direct cause of phantom discrepancies—operations team is seeing cached data from 4.5 minutes ago.

2. **No write-triggered invalidation**: Transactions are processed (DB updated) but caches aren't touched. Portfolio managers wait for TTL expiry, not for data consistency.

3. **Cache stampede at market open**: All caches expire on a timer → simultaneous DB load spikes. This gets *worse* if you reduce TTLs uniformly.

4. **Memory pressure**: 12/16 GB is dangerous; you're one eviction storm away from losing hot data and cascading slowdowns.

---

## Option 1: Reduce All TTLs to 30s

| Requirement | Impact |
|---|---|
| Portfolio summaries (1-2 min) | ✓ Met, but over-cached |
| Transaction history (5 min) | ✓ Met, but over-cached |
| Reconciliation (30 sec) | ✗ Unreliable (cache could be 29.9s stale) |
| Market data (sub-second) | ✗ Still 30s behind (not real-time) |
| Cache stampede | ✗ **Worse**—revalidations happen every 30s instead of 5 min |
| Memory | ✓ Slight improvement, but won't solve 12GB issue |

**Verdict**: Reduces staleness but doesn't solve structural problems. Makes stampede worse. Won't meet reconciliation requirement reliably.

---

## Option 2: Event-Driven Invalidation Alone

| Requirement | Impact |
|---|---|
| Portfolio summaries | ✓ Immediate update, ~0s staleness |
| Transaction history | ✓ Immediate update, ~0s staleness |
| Reconciliation (30 sec) | ✓ Can be immediate or configurable |
| Market data (sub-second) | ✗ Still depends on data provider latency, not cache |
| Cache stampede | ✓ Eliminates simultaneous revalidations |
| Memory | ✗ No direct benefit; could increase churn if invalidation is noisy |

**Verdict**: Solves write staleness, eliminates stampede. But market data is a separate problem (data provider latency, not cache policy), and doesn't address memory growth.

---

## Recommended Hybrid Strategy

### 1. **Event-Driven Invalidation (Primary)**

Implement pub/sub on transaction writes:

```python
# transaction_processor.py (updated)
def process_transaction(txn: Transaction):
    db.insert(txn)
    portfolio = db.get_portfolio(txn.portfolio_id)
    portfolio.balance += txn.amount
    db.update(portfolio)
    
    # Invalidate affected caches immediately
    invalidate_cache([
        f"portfolio:{txn.portfolio_id}",
        f"transactions:{txn.portfolio_id}",
        f"reconciliation:{txn.portfolio_id}",  # reconciliation depends on this txn
    ])
    
    # Publish event for real-time subscribers (WebSocket, etc.)
    event_bus.publish("transaction.processed", txn)
```

### 2. **Differentiated TTLs by Data Type**

```python
CACHE_SETTINGS = {
    "portfolio_summary": {
        "redis_ttl": 120,         # 2 min (safety net; data usually fresh via events)
        "cdn_max_age": 30,        # short CDN cache (most freshness is from redis)
        "browser_max_age": 10,
        "stale_while_revalidate": 60,
    },
    "transaction_history": {
        "redis_ttl": 300,         # 5 min (lower write frequency; allows reuse)
        "cdn_max_age": 60,
        "browser_max_age": 30,
        "stale_while_revalidate": 120,
    },
    "reconciliation_report": {
        # NEW STRATEGY: No redis TTL; invalidate on write + expire nightly
        "redis_ttl": 30,          # Ultra-short safety net
        "cdn_max_age": 5,         # Very short CDN (operations team refreshes frequently)
        "browser_max_age": 0,     # No browser cache (no-cache)
        "must_revalidate": True,  # Operations needs freshness guarantee
    },
    "market_data": {
        "redis_ttl": 5,           # Real-time data; minimal cache
        "cdn_max_age": 1,         # Mostly for burst protection
        "browser_max_age": 1,
        "stale_while_revalidate": 10,
    },
}
```

### 3. **Solve the Reconciliation Problem Specifically**

Reconciliation reports are special—they must reflect the last 30 seconds AND be fast:

```python
# reconciliation_handler.py
class ReconciliationCache:
    def __init__(self, redis_client):
        self.redis = redis_client
    
    def get_report(self, portfolio_id, as_of_timestamp=None):
        """
        Always hit the DB for reconciliation.
        Cache only for 10-second bursts to prevent multiple queries in rapid succession.
        """
        cache_key = f"reconciliation:{portfolio_id}:{as_of_timestamp or 'latest'}"
        cached = self.redis.get(cache_key)
        
        if cached:
            return cached
        
        # Always recompute—don't rely on stale cache
        report = self._compute_report(portfolio_id, as_of_timestamp)
        self.redis.setex(cache_key, 10, report)  # Cache for 10s burst protection only
        return report
    
    def invalidate(self, portfolio_id):
        """Invalidate all reconciliation cache entries for this portfolio."""
        self.redis.delete(f"reconciliation:{portfolio_id}:*")
```

### 4. **Cache Stampede Prevention**

Add jitter to TTL expirations and use probabilistic early revalidation:

```python
import random

def get_with_stale_refresh(key, ttl, revalidation_threshold=0.8):
    """
    Return cached value. If close to expiry, revalidate in background.
    Prevents thundering herd.
    """
    cached = redis.get(key)
    remaining_ttl = redis.ttl(key)
    
    # If >80% through TTL, trigger background refresh
    if cached and remaining_ttl < (ttl * (1 - revalidation_threshold)):
        background_queue.enqueue(revalidate_cache, key)
    
    return cached or fetch_from_db(key)
```

### 5. **Memory Management**

```python
# Configure Redis eviction policy
redis.config_set("maxmemory-policy", "allkeys-lru")  # Evict least-recently-used
redis.config_set("maxmemory", "14gb")                # Leave 2GB headroom

# Monitor and alert
monitor_redis_memory(threshold_percent=85)  # Alert at 85% full
```

---

## Addressing Each Pain Point

| Pain Point | Solution |
|---|---|
| **Stale balances (5 min)** | Event-driven invalidation → immediate consistency |
| **Phantom discrepancies** | Reconciliation-specific cache strategy + 30s TTL safety net |
| **Cache stampede at 9:30 AM** | Probabilistic early revalidation + jitter prevents synchronized expiry |
| **Memory growth** | LRU eviction + monitoring; reconciliation cache shorter TTLs reduce memory pressure |

---

## Implementation Roadmap

1. **Phase 1** (Week 1): Implement event-driven invalidation for portfolio & transaction caches
2. **Phase 2** (Week 2): Refactor reconciliation cache handler with the "always recompute" strategy
3. **Phase 3** (Week 2): Deploy cache stampede prevention (early revalidation + jitter)
4. **Phase 4** (Week 3): Monitor, tune TTLs based on observed hit rates and staleness metrics

---

## Why This Works

- **Event-driven invalidation** solves the root cause (write staleness) without architectural over-engineering
- **Differentiated TTLs** acknowledge that not all data has the same staleness tolerance
- **Reconciliation special case** ensures operations team gets the guarantee they need
- **Stampede prevention** spreads load, avoiding the 10x spike
- **Memory strategy** ensures you don't evict cache under load

This is a proven pattern in high-frequency trading systems where accuracy and availability matter equally. You trade some engineering complexity for strict consistency guarantees.

## Response B
## Socratic Analysis: Cache Invalidation Strategy

Working through the protocol for this high-stakes decision:

### 1. What Am I Assuming?

**High confidence** (verified in session):
- The cache configuration shows reconciliation_report has a 300s Redis TTL but the spec requires 30-second visibility
- Transaction processor does zero cache invalidation
- The system is experiencing observable problems (stale balances, phantom discrepancies)

**Medium confidence** (reasonable inference):
- The 9:30 AM stampede is a predictable load spike
- Cache hit rates are reasonable enough that caching matters

**Low confidence** (not verified, crucial gaps):
- Whether "phantom discrepancies" are *actually* caching vs. a transaction processing race condition
- The frequency and business impact of the stale balance delay
- The team's operational capacity for a pub/sub system
- Whether Redis is failing due to memory *capacity* or *eviction behavior*

### 2. Critical Inconsistency I Notice

The reconciliation_report requirement states: **"must reflect all transactions within the last 30 seconds"** but the TTL is **300 seconds (5 minutes).**

This isn't a subtle trade-off—this is a direct conflict. Either:
- The requirement was added after caching was designed
- The requirement wasn't validated against the cache architecture
- The phantom discrepancies are a *direct consequence of ignoring the actual requirement*

**This changes my analysis fundamentally.** You can't "solve" phantom discrepancies by reducing TTLs from 5 to 1 minute if the requirement is 30 seconds. Both approaches fail the reconciliation report requirement.

### 3. Steelmanning Both Approaches

**For "Reduce TTLs to 30 seconds":**
- Simpler, fewer moving parts, lower operational risk
- Easy to tune incrementally with measurable impact
- No new failure modes (message loss, ordering issues)
- For a financial system, predictability and simplicity matter

**Against:** Still doesn't meet the 30-second reconciliation requirement. Memory pressure will worsen. Cache stampedes remain (just faster stampedes).

---

**For "Event-driven invalidation":**
- Actually achieves the 30-second freshness requirement
- Reduces Redis memory usage significantly
- Prevents cache stampedes entirely
- Solves the problem at the source, not the symptom

**Against:** Introduces complexity, new failure modes (what if pub/sub messages are lost? out of order?), operational burden.

### 4. The Questions I Can't Answer Without More Data

1. **Are phantom discrepancies actually cache-related?** 
   - Could they be transaction ordering bugs, timing issues in the transaction processor, or inconsistent reads?
   - Recommendation: Check the actual error logs—are discrepancies always within 5 minutes of a large trade? Or random?

2. **What's the actual impact of 5-minute staleness on users?**
   - How often do portfolio managers see the stale balance issue?
   - Does it cause incorrect decisions, or is it just annoying?

3. **Can your team operate a pub/sub system reliably?**
   - Do you have Kafka, RabbitMQ, or similar deployed?
   - Who owns alerting/debugging for message loss or ordering issues?

4. **What's causing the Redis memory growth?**
   - Is it eviction (requests exceeding TTL), or just data volume?
   - At 12/16 GB, how close are you to eviction triggering?

---

### 5. My Recommendation: Neither Approach Alone Is Sufficient

**The reconciliation report requirement is the constraint—everything else must serve it.**

**Immediate actions** (high confidence):
1. **Fix the reconciliation_report TTL mismatch:** Change its Redis TTL to **60 seconds max** (to guarantee <30s visibility in worst case)
2. **Verify the phantom discrepancy root cause:** Is it caching, or something else?
3. **Separate concerns:** Don't conflate portfolio_summary staleness (tolerable at 2 minutes) with reconciliation_report accuracy (must be <30s)

**Then choose the path:**

**Path A (Simpler, if the team is ops-constrained):**
- Set reconciliation_report Redis TTL = 60s
- Set transaction_history Redis TTL = 90s  
- Set portfolio_summary Redis TTL = 120s (meets the "1-2 minute" requirement)
- Keep market_data at 15s (actually real-time enough)
- Monitor Redis eviction rates—if they exceed 5% of requests, you have a memory problem, not a TTL problem

**Path B (Recommended, if the team can handle distributed systems):**
- Implement event-driven invalidation **only for transactions** (not all data)
- When a transaction is processed: publish to `portfolio-updates` topic
- Consumers: Redis cache invalidator + portfolio summary renderer
- This solves cache stampedes, freshness guarantees, and memory pressure in one go
- Reconciliation reports become pull-based, not TTL-based—always current
- **Cost:** Adds Kafka/RabbitMQ operational burden, message ordering guarantees must be rock-solid

---

### 6. The Real Issue

You're treating caching as the primary mechanism for ensuring data freshness. **For a financial system, cache should be a performance layer, not a correctness layer.** The reconciliation report shouldn't rely on TTL at all—it should be:
- Computed on-demand from authoritative transaction logs
- Or pulled from a write-through cache that invalidates explicitly when transactions commit

**That's the architectural conversation you should be having first, before optimizing TTL values.**

---

What additional data would help me be more confident?
- Logs showing *when* phantom discrepancies occur relative to transaction timing
- Current cache hit rates and eviction metrics
- Whether you already run any event-driven systems (Kafka, RabbitMQ, SQS)

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
