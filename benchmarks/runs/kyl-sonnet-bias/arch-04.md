## Socratic Mode: Working Through the Decision

Before recommending, let me run the protocol — because this is an architectural decision with high compounding cost if wrong.

---

### Step 1: Explicit Assumptions Audit

Here's what I'm assuming before reasoning:

| Assumption | Confidence | Risk if Wrong |
|---|---|---|
| "Reduce all TTLs" means uniformly 30s across all data types | Medium — the phrasing is ambiguous | Could mean something more targeted |
| Cache stampede at 9:30 AM is caused by synchronized TTL expiry | Medium — it's the most likely cause, but cold cache at startup is an alternative explanation | Changes the fix entirely |
| "Phantom discrepancies" in reconciliation are *definitely* caused by caching | Medium — the ops team *suspects* caching; we don't have confirmation | Could be a bug in reconciliation logic |
| Both approaches are mutually exclusive | **Low — I almost fell into this trap** | The framing is a false binary |
| Event-driven invalidation fully solves the freshness problem | Low — there's still a CDN layer I need to account for | Significant false comfort |

---

### Step 2: The Number the Problem Statement Buries

Let me do the arithmetic on reconciliation reports under the *current* configuration before evaluating either fix:

```
Worst-case staleness for reconciliation_report:
  Redis TTL:               300s (5 min)
  CDN max-age:             120s (2 min)
  Browser max-age:          60s (1 min)
  stale_while_revalidate:  300s (5 min)

Total worst-case stale window: up to ~780 seconds (~13 minutes)
```

The product spec requires data within **30 seconds**. The current system can legally serve data that's **13 minutes old**. This isn't a tuning problem — it's a structural mismatch. I need to hold this finding carefully because it changes what "fix" even means.

---

### Step 3: Steelmanning Both Approaches Before Critiquing

**Strongest case for Approach 1 (uniform 30s TTL):**
- Zero new infrastructure. In a 99.9% uptime system during market hours, adding a pub/sub dependency is a new failure mode.
- Simple to reason about, simple to debug.
- No distributed transaction risk (write succeeds, invalidation message fails → silent consistency violation).
- Uniformity prevents misconfiguration of individual endpoints.

This is a genuinely reasonable position for a team that values operational simplicity and has limited distributed systems expertise. I shouldn't dismiss it.

**Strongest case for Approach 2 (event-driven invalidation):**
- Invalidation is precise: only affected cache keys are busted, not the entire namespace on a timer.
- Eliminates staleness-on-write entirely (modulo propagation latency) rather than just bounding it.
- Actually *reduces* cache churn — keys stay warm until they're genuinely stale, which helps with stampede.

---

### Step 4: Where Each Approach Fails

**Approach 1 fails on four counts:**

**Stampede gets worse, not better.** This is the critical flaw. At 30s TTL, keys turn over 120× per hour instead of 12×. The 9:30 AM spike would be catastrophic — every 30 seconds, all keys expire simultaneously and every request races to the DB. The current 10× spike becomes structural. Approach 1 directly contradicts fixing this pain point.

**Reconciliation still breaks the requirement.** Even at 30s Redis TTL, the CDN (`cdn_max_age: 30s`) + `stale_while_revalidate: 30s` = 60+ seconds of possible staleness. The requirement is 30 seconds. The CDN layer is still violating it. Approach 1 doesn't fix this.

**Market data gets slower.** Current Redis TTL for market data is 15s. Uniform 30s makes it worse.

**Memory isn't addressed.** Redis at 75% utilization is a concern. Shorter TTLs don't reduce key count at any given moment — they just turn over faster. This doesn't help memory unless the root cause is long-lived keys (which we don't know without investigation).

**Approach 2 fails on two counts, which must be addressed in the recommendation:**

**The CDN layer is not invalidated.** Event-driven invalidation of Redis solves Redis. But CDN still serves stale responses for `cdn_max_age` seconds after a write. For reconciliation reports at CDN max-age=120s, you can have perfect Redis invalidation and still serve 2-minute-old data to the browser. CloudFront has an invalidation API, but it's asynchronous (can take seconds to minutes to propagate) and has cost implications at high call rates.

**Stampede on invalidation.** If a hot portfolio key is invalidated when a large trade lands, every concurrent request for that key misses and hammers the DB simultaneously. Invalidation creates a new stampede vector — this needs a separate solution (probabilistic early expiration, request coalescing, or a cache-aside lock).

---

### Step 5: What Would Change My Mind?

- If the cache stampede at 9:30 AM is caused by *cold cache at startup* (not TTL expiry), then Approach 1's stampede problem is less severe — but the reconciliation math still breaks it.
- If the CDN can be configured for *cache-tag-based invalidation* (CloudFront supports this via cache invalidation APIs), the CDN concern for Approach 2 is solvable.
- If the Redis memory growth is caused by *unbounded key patterns* (e.g., per-user, per-date combinatorial explosion), neither approach fixes it — it needs a key design audit.

---

## Recommendation: Differentiated Strategy (Neither Approach Alone)

The debate is a false binary. The right architecture is **event-driven invalidation as the primary mechanism, with differentiated TTLs as safety nets** — applied per data type based on its actual requirements.

### Fix 1: Event-driven invalidation on the write path

```python
# transaction_processor.py
def process_transaction(txn: Transaction):
    db.insert(txn)
    portfolio = db.get_portfolio(txn.portfolio_id)
    portfolio.balance += txn.amount
    db.update(portfolio)
    
    # Invalidate affected cache keys immediately
    cache.delete(f"portfolio_summary:{txn.portfolio_id}")
    cache.delete(f"reconciliation_report:{txn.portfolio_id}:{today()}")
    
    # Publish to invalidation topic for CDN and browser cache busting
    pubsub.publish("cache.invalidate", {
        "keys": [f"portfolio:{txn.portfolio_id}", f"reconciliation:{today()}"],
        "timestamp": utcnow()
    })
    
    logger.info(f"Transaction {txn.id} processed, caches invalidated")
```

Keep TTLs as **safety nets** (in case a write path is missed), but not as the primary freshness mechanism.

### Fix 2: Reconciliation reports must bypass CDN

This is non-negotiable given the math. The CDN layer structurally cannot meet a 30-second requirement. Two options:

**Option A (simpler):** Add `Cache-Control: no-store` or serve reconciliation reports through a path that CloudFront is configured to pass through (`/api/reconciliation/*` excluded from CDN caching). The App Server → Redis path with event-driven invalidation gets you to near-zero staleness.

**Option B (if CDN is needed for availability):** Use CloudFront cache tag invalidation on every transaction write. This is viable at low transaction volume but will create cost and latency issues under load. Prefer Option A.

### Fix 3: Cache stampede requires a separate mechanism

Neither approach alone fixes this. The right tool is **probabilistic early expiration (PER)** — recompute a cache entry slightly before it expires, with some probability that increases as TTL approaches zero:

```python
def get_with_per(key, ttl, fetch_fn, beta=1.0):
    """Probabilistic Early Recomputation to prevent stampedes."""
    cached = redis.get(key)
    if cached:
        remaining_ttl = redis.ttl(key)
        # Recompute early with probability proportional to how close we are to expiry
        if -beta * math.log(random.random()) < (ttl - remaining_ttl):
            return cached  # Serve cached, let someone else recompute
    return fetch_fn()  # Cache miss or chosen to recompute early
```

Additionally, **warm the cache before market open** (9:20-9:30 AM window) for the top N portfolios by activity, so market open doesn't cause a cold-cache spike.

### Fix 4: Investigate Redis memory before assuming a fix

12 GB of 16 GB (75%) needs a root-cause investigation before prescribing a fix:

```bash
redis-cli --bigkeys  # Find largest keys
redis-cli info keyspace  # Key count by DB
redis-cli debug sleep 0; redis-cli object help  # Check for unbounded key patterns
```

The likely culprits: per-user or per-date key patterns creating combinatorial explosion, or stale keys from deprecated features. Once identified, add a memory policy (`allkeys-lru` if not set) and fix the key patterns.

---

## Revised Cache Settings

```python
CACHE_SETTINGS = {
    "portfolio_summary": {
        "redis_ttl": 120,              # Safety net only — event-driven invalidation is primary
        "cdn_max_age": 30,             # Reduced; CDN invalidation API called on writes
        "browser_max_age": 10,
        "stale_while_revalidate": 30,  # Reduced — keeps UI responsive during revalidation
    },
    "transaction_history": {
        "redis_ttl": 300,              # Acceptable — 5-min requirement met by TTL alone
        "cdn_max_age": 60,
        "browser_max_age": 30,
        "stale_while_revalidate": 120,
    },
    "reconciliation_report": {
        "redis_ttl": 60,               # Safety net only
        "cdn_max_age": 0,              # ← BYPASS CDN — 30-second requirement is incompatible
        "browser_max_age": 0,          # No browser caching — operations users need live data
        "stale_while_revalidate": 0,
    },
    "market_data": {
        "redis_ttl": 15,               # Unchanged — already tuned for sub-second latency
        "cdn_max_age": 10,
        "browser_max_age": 5,
        "stale_while_revalidate": 10,  # Reduced
    },
}
```

---

## Pain Point Resolution Summary

| Pain Point | Root Cause | Fix |
|---|---|---|
| Stale balances after large trades (up to 5 min) | No invalidation on writes | Event-driven invalidation on `process_transaction` |
| Phantom reconciliation discrepancies | CDN (120s) + stale_while_revalidate (300s) serving old data | Remove reconciliation from CDN; event-driven Redis invalidation |
| 9:30 AM stampede (10× DB spike) | Synchronized TTL expiry (and cold cache) | PER algorithm + pre-market cache warming |
| Redis memory at 75% | Unknown — needs investigation | Root-cause audit with `redis-cli --bigkeys` before acting |

---

## Confidence Calibration

- **High confidence**: Reconciliation reports cannot meet 30s requirement with current CDN config. The math is definitive.
- **High confidence**: Uniform 30s TTL worsens the stampede problem. This is a logical consequence of the mechanism.
- **Medium confidence**: Event-driven invalidation + CDN bypass for reconciliation is the right fix. I'm reasoning from standard patterns; the specific pub/sub implementation depends on what infrastructure they already run.
- **Lower confidence**: Redis memory root cause. I've described a diagnostic path, not a guaranteed fix.
- **Explicit uncertainty**: I don't know if the 9:30 AM stampede is TTL-driven or cold-cache-driven. The mitigation (PER + cache warming) addresses both, but the relative contribution matters for sizing the solution.