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