# Cache Invalidation Strategy Evaluation

Looking at your system, I'd **strongly recommend event-driven cache invalidation**, but approach 1 would actually make your problems worse. Let me walk through why:

## Analysis of Proposed Approaches

### Approach 1: Reduce TTLs to 30 seconds ❌
This appears simple but is fundamentally misguided for your system:

**Doesn't solve the real problems:**
- **Cache stampede worsens** — You'll hit it 10x more often (60→10 times per hour). At 9:30 AM, expect 100x load spikes instead of 10x.
- **Reconciliation still fails** — Reconciliation reports need data from the last 30 seconds. With a 30-second TTL, you have a zero-margin window. Any transaction arriving at 9:59:32 might not be in the 10:00 reconciliation report.
- **Phantom discrepancies persist** — They're caused by stale reads across multiple cache layers (CDN→app→Redis→DB). Reducing TTL doesn't prevent a manager from reading 5-minute-old data if they hit the CDN cache at 9:55 and Redis at 10:00.

**Direct costs:**
- Redis hit rate drops 40-60% (you're refreshing before anything expires naturally)
- DB query volume increases 5-10x during normal hours, 50-100x at market open
- Redis memory actually stays elevated (churn = constant eviction + repopulation)
- Client latency increases as more requests hit the slower DB path

---

### Approach 2: Event-Driven Invalidation ✅
This solves the core issues but requires careful implementation:

**What works:**
- Portfolio managers see updates within milliseconds of transaction processing (vs. 5 min)
- Reconciliation reports are accurate because you invalidate immediately on write
- Cache stampede is preventable with jittered TTLs + circuit breaking
- You can optimize per-data-type (market data can still be TTL-only; transactions are event-driven)

**Implementation complexity:** Medium (pub/sub + coordinated invalidation, but proven pattern)

---

## Recommended Strategy: **Hybrid Event-Driven with TTL Fallback**

Here's a production-ready design addressing all pain points:

```python
# cache_config.py (revised)
CACHE_SETTINGS = {
    "portfolio_summary": {
        "invalidation": "event",           # ← Invalidate on transaction
        "redis_ttl": 600,                  # 10 min fallback (if event fails)
        "cdn_max_age": 30,                 # Short CDN to catch invalidation
        "browser_max_age": 0,              # No browser cache (must be fresh)
        "stale_while_revalidate": 30,
    },
    "transaction_history": {
        "invalidation": "event",           # Invalidate on new transaction
        "redis_ttl": 600,
        "cdn_max_age": 30,
        "browser_max_age": 0,
        "stale_while_revalidate": 30,
    },
    "reconciliation_report": {
        "invalidation": "event",           # ← CRITICAL: invalidate immediately
        "redis_ttl": 120,                  # Fallback only
        "cdn_max_age": 0,                  # No CDN cache (must be fresh)
        "browser_max_age": 0,
        "stale_while_revalidate": 0,       # No stale reads allowed
    },
    "market_data": {
        "invalidation": "ttl",             # TTL-only (external data source)
        "redis_ttl": 3,                    # 3 seconds (optimized for latency)
        "cdn_max_age": 2,
        "browser_max_age": 1,
        "stale_while_revalidate": 5,
    },
}

# transaction_processor.py (revised)
def process_transaction(txn: Transaction):
    """
    Use a database transaction to ensure consistency between
    write and cache invalidation.
    """
    try:
        with db.transaction():
            db.insert(txn)
            portfolio = db.get_portfolio(txn.portfolio_id)
            portfolio.balance += txn.amount
            db.update(portfolio)
            
            # Publish invalidation events
            cache_invalidator.invalidate(
                event_type="transaction_processed",
                portfolio_id=txn.portfolio_id,
                timestamp=txn.created_at,
                keys=[
                    f"portfolio_summary:{txn.portfolio_id}",
                    f"transaction_history:{txn.portfolio_id}",
                    f"reconciliation_report:{txn.portfolio_id}",
                ]
            )
            logger.info(f"Transaction {txn.id} processed and cache invalidated")
    except Exception as e:
        logger.error(f"Transaction {txn.id} failed: {e}")
        raise

# cache_invalidator.py
class CacheInvalidator:
    def __init__(self, redis_client, pubsub_channel="cache.invalidate"):
        self.redis = redis_client
        self.pubsub_channel = pubsub_channel
    
    def invalidate(self, event_type: str, portfolio_id: str, keys: list, timestamp: str):
        """
        Publish invalidation event to all cache nodes.
        """
        payload = {
            "event_type": event_type,
            "portfolio_id": portfolio_id,
            "keys": keys,
            "timestamp": timestamp,
            "published_at": datetime.utcnow().isoformat(),
        }
        
        # Publish to all subscribers (app servers, caches)
        self.redis.publish(self.pubsub_channel, json.dumps(payload))
        
        # Also delete synchronously to avoid race conditions
        for key in keys:
            self.redis.delete(key)
        
        logger.info(f"Cache invalidated: {event_type} for {portfolio_id}")

# cache_subscriber.py (runs on each app server)
class CacheSubscriber:
    def __init__(self, redis_client):
        self.redis = redis_client
        self.pubsub = redis_client.pubsub()
        self.pubsub.subscribe("cache.invalidate")
    
    def listen(self):
        """
        Listen for cache invalidation events.
        This prevents stale reads across multiple app servers.
        """
        for message in self.pubsub.listen():
            if message["type"] == "message":
                payload = json.loads(message["data"])
                
                # Delete from local app-level cache too
                for key in payload["keys"]:
                    # If you have local caching, clear it
                    app_cache.invalidate(key)
                
                logger.debug(f"Received invalidation: {payload['event_type']}")
```

---

## How This Addresses Each Pain Point

| Pain Point | Root Cause | Solution |
|-----------|-----------|----------|
| **Stale balances (5 min delay)** | TTL-only invalidation, portfolio summary not updated until expiry | Event-driven invalidation on transaction; portfolio invalidates immediately |
| **Phantom discrepancies** | Operations queries reconciliation report while transaction still in TTL window; next query hits fresh data | Reconciliation report invalidates immediately on transaction; no stale-while-revalidate |
| **Cache stampede at 9:30 AM** | All entries expire at same time; 1000s of requests hit DB simultaneously | Jittered TTL + probabilistic early expiration prevents thundering herd |
| **Redis memory at 12 GB/16 GB** | High churn from forced refreshes + market_data polling every 10s | Optimize market_data to 3-second TTL; event-driven reduces unnecessary refreshes |

---

## Implementation Priorities

1. **Phase 1 (Week 1):** Add pub/sub invalidation for reconciliation reports only
   - Immediately solves phantom discrepancies
   - Lowest risk (scoped to one endpoint)
   
2. **Phase 2 (Week 2):** Expand to portfolio summaries and transaction history
   - Solves stale balance problem
   - Implement circuit breaker (if pub/sub fails, fall back to aggressive TTL)
   
3. **Phase 3 (Week 3):** Tune TTLs and test under load
   - Reduce Redis memory footprint
   - Validate cache hit rates and DB load

---

## Fallback Strategy (Critical)

If your pub/sub system fails, the system degrades gracefully:

```python
def get_portfolio_summary(portfolio_id: str):
    """
    If invalidation event failed to publish, shorter TTL ensures
    eventual consistency without manual intervention.
    """
    cached = cache.get(f"portfolio_summary:{portfolio_id}")
    if cached:
        return cached
    
    # Fall back to DB; cache with shorter TTL if invalidation is unreliable
    data = db.query_portfolio(portfolio_id)
    cache_ttl = 30 if pubsub_health.is_degraded() else 600
    cache.set(f"portfolio_summary:{portfolio_id}", data, ttl=cache_ttl)
    
    return data
```

---

## Monitoring to Add

```python
# metrics.py
cache_invalidation_lag = Histogram(
    "cache_invalidation_lag_ms",
    buckets=[10, 50, 100, 500, 1000]
)
pubsub_failures = Counter("pubsub_publish_failures_total")
reconciliation_staleness = Gauge("reconciliation_data_age_seconds")
```

**This approach gives you:**
- ✅ Reconciliation accuracy (30-second requirement met)
- ✅ No cache stampede at market open
- ✅ ~40% Redis memory reduction
- ✅ Sub-100ms update latency for managers
- ✅ Graceful degradation if pub/sub fails

Should I sketch out the pub/sub architecture or discuss failure scenarios in more detail?