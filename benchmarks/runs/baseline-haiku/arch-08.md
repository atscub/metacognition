I'll recommend a **dual-bucket architecture with traffic-class isolation**—not choosing one algorithm, but running two tuned token buckets in parallel, with configuration management for dynamic updates.

## Core Problem

The fundamental issue is **capacity interference**: batch traffic at 2 AM depletes the same bucket that interactive traffic needs at 9 AM. A single global rate limiter conflates two unrelated traffic patterns. Even with perfect tuning, you're optimizing a compromise that satisfies neither.

## Recommended Architecture

**Separate token buckets per traffic class + per customer:**

```
Interactive bucket: /api/v1/query/*, /api/v1/dashboard/*
Batch bucket:      /api/v1/batch/*, /api/v1/export/*
```

Each customer gets two independent buckets. Batch jobs can't starve interactive traffic, and time-of-day traffic patterns in one class don't affect the other.

### Algorithm: Token Bucket (for both, tuned differently)

Token bucket is the right choice for both, but with parameters that reflect each traffic pattern:

| Dimension | Interactive | Batch |
|-----------|-------------|-------|
| **Max tokens** | 30 | 25 |
| **Refill rate** | 2 tokens/sec | 3 tokens/sec |
| **Burst window** | 2–3 seconds | 5–10 seconds (retries) |
| **Philosophy** | Permit short bursts, block sustained overload | Smooth steady throughput |

**Why token bucket fits both:**
- Interactive: Absorbs the 10–20 req/2s bursts without punishing normal behavior
- Batch: Refill rate of 3/sec ≈ 10,800 req/hour (meets 10,000 target with headroom)
- Low operational overhead (fixed-size state in Redis)
- No per-request logging (unlike sliding window)

---

## Redis Key Design

Use **nested namespacing** to allow dynamic configuration without code deploys:

```
# State keys (per-customer, per-class)
rate_limit:{customer_id}:{class}:tokens         # float, current tokens
rate_limit:{customer_id}:{class}:last_refill   # timestamp

# Config keys (separate defaults + per-customer overrides)
rate_limit:config:{class}:max_tokens         # e.g., 30 (interactive), 25 (batch)
rate_limit:config:{class}:refill_rate        # e.g., 2.0 (interactive), 3.0 (batch)

rate_limit:config:{customer_id}:{class}:max_tokens    # override for premium customer
rate_limit:config:{customer_id}:{class}:refill_rate   # override for premium customer

# Metadata
rate_limit:customer:{customer_id}:tier       # "standard" or "premium", for ops UX
```

**Example for premium customer:**
```bash
SET rate_limit:config:acme-corp:interactive:max_tokens 50      # 50% more burst headroom
SET rate_limit:config:acme-corp:interactive:refill_rate 3.0    # 50% more sustained capacity
```

---

## Implementation

```python
import redis
import time
from enum import Enum

class TrafficClass(Enum):
    INTERACTIVE = "interactive"
    BATCH = "batch"

class DualBucketLimiter:
    def __init__(self, redis_client):
        self.redis = redis_client
        # Defaults (can be overridden per-customer)
        self.defaults = {
            TrafficClass.INTERACTIVE: {"max_tokens": 30, "refill_rate": 2.0},
            TrafficClass.BATCH: {"max_tokens": 25, "refill_rate": 3.0},
        }

    def get_config(self, customer_id: str, traffic_class: TrafficClass) -> dict:
        """Fetch config from Redis, falling back to defaults."""
        config = {}
        for param in ["max_tokens", "refill_rate"]:
            # Try customer-specific override first
            key = f"rate_limit:config:{customer_id}:{traffic_class.value}:{param}"
            val = self.redis.get(key)
            if val:
                config[param] = float(val)
            else:
                # Fall back to class default
                key = f"rate_limit:config:{traffic_class.value}:{param}"
                val = self.redis.get(key)
                config[param] = float(val) if val else self.defaults[traffic_class][param]
        return config

    def allow_request(self, customer_id: str, traffic_class: TrafficClass) -> bool:
        """Check if request is allowed; update bucket state."""
        config = self.get_config(customer_id, traffic_class)
        max_tokens = config["max_tokens"]
        refill_rate = config["refill_rate"]

        tokens_key = f"rate_limit:{customer_id}:{traffic_class.value}:tokens"
        refill_key = f"rate_limit:{customer_id}:{traffic_class.value}:last_refill"
        now = time.time()

        # Get current state
        pipe = self.redis.pipeline()
        pipe.get(tokens_key)
        pipe.get(refill_key)
        tokens, last_refill = pipe.execute()

        tokens = float(tokens) if tokens else max_tokens
        last_refill = float(last_refill) if last_refill else now

        # Refill based on elapsed time
        elapsed = now - last_refill
        tokens = min(max_tokens, tokens + elapsed * refill_rate)

        # Check if request is allowed
        if tokens >= 1:
            tokens -= 1
            pipe = self.redis.pipeline()
            pipe.set(tokens_key, tokens)
            pipe.set(refill_key, now)
            pipe.execute()
            return True
        return False


# Flask middleware
limiter = DualBucketLimiter(redis)

@app.before_request
def check_rate_limit():
    customer_id = get_customer_id(request)  # from auth header, API key, etc.
    
    # Determine traffic class from endpoint
    if request.path.startswith(("/api/v1/query/", "/api/v1/dashboard/")):
        traffic_class = TrafficClass.INTERACTIVE
    elif request.path.startswith(("/api/v1/batch/", "/api/v1/export/")):
        traffic_class = TrafficClass.BATCH
    else:
        # Default to interactive for safety
        traffic_class = TrafficClass.INTERACTIVE

    if not limiter.allow_request(customer_id, traffic_class):
        return (
            jsonify({
                "error": "Rate limited",
                "traffic_class": traffic_class.value,
                "retry_after": 1,  # Rough estimate; batch can wait longer
            }),
            429,
            {"Retry-After": "1"},
        )
```

---

## How This Solves Each Problem

### Problem 1: Interactive users get 429s during dashboard load
**Before:** Token bucket sized for steady traffic; bursts of 10–20 reqs consume all tokens.  
**After:** Interactive bucket max_tokens=30 comfortably absorbs 2-second bursts (20 reqs ≈ 2 sec at peak). Dashboard load fires 10–20 reqs → ~0.5–1 second to refill → no 429s.

### Problem 2: Batch jobs starve interactive traffic during business hours
**Before:** Batch traffic competes for the same bucket; during peak interactive hours, batch jobs get throttled.  
**After:** Separate buckets. Batch refills at 3 tokens/sec (~10.8K req/hr), interactive refills at 2 tokens/sec. No interference. Batch jobs complete reliably; interactive traffic unaffected.

### Problem 3: 2 AM batch export drains the bucket before 9 AM interactive peak
**Before:** Single bucket. Batch consumes everything at night; morning interactive traffic arrives to empty bucket.  
**After:** Separate buckets. Batch bucket independent; if batch job runs at 2 AM and depletes its bucket, the interactive bucket is untouched and ready for 9 AM dashboards.

### Problem 4: Dynamic limits without code deployment
**Before:** Limit changes require code redeploy + service restart.  
**After:** Ops can run:
```bash
redis-cli SET rate_limit:config:acme-corp:interactive:max_tokens 50
redis-cli SET rate_limit:config:acme-corp:batch:refill_rate 4.0
```
Changes apply **immediately** to the next request for that customer. Defaults stay in place for all other customers.

---

## Configuration Interface for Ops

Create a simple admin CLI or API:

```bash
# View current config
bd-rate-limit config get --customer acme-corp --class interactive
# Output: {"max_tokens": 30, "refill_rate": 2.0, "source": "default"}

# Set premium limits
bd-rate-limit config set --customer acme-corp --class interactive --max-tokens 50 --refill-rate 3.0
bd-rate-limit config set --customer acme-corp --class batch --refill-rate 4.0

# Reset to defaults
bd-rate-limit config reset --customer acme-corp

# Monitor current state
bd-rate-limit status --customer acme-corp
# Output:
# interactive: 28.5 / 30 tokens (last refill 2 seconds ago)
# batch: 22.1 / 25 tokens (last refill 0.5 seconds ago)
```

---

## Tuning and Monitoring

**Metrics to track** (emit to Datadog/Prometheus):

```python
# In allow_request():
if tokens >= 1:
    statsd.increment(f"rate_limit.allowed", tags=[
        f"customer:{customer_id}",
        f"class:{traffic_class.value}"
    ])
else:
    statsd.increment(f"rate_limit.rejected", tags=[...])
    
# Periodically log bucket state
statsd.gauge(f"rate_limit.tokens", tokens, tags=[...])
statsd.gauge(f"rate_limit.refill_rate", refill_rate, tags=[...])
```

**Alert conditions:**
- Rejection rate for interactive traffic > 0.5% → burst capacity too low
- Sustained rejection for batch traffic > 1% → refill rate too low
- Per-customer limits drifting (unexpected overrides) → audit

---

## Why Not Other Algorithms?

| Algorithm | Why not for this case |
|-----------|----------------------|
| **Leaky bucket** | Smoother for batch, but harder to tune—punishes all bursts equally. Our batch already accepts 5 req/s spikes; leaky bucket over-constrains. |
| **Sliding window log** | Memory-intensive. For a high-volume customer at 3 req/s (10K/hr), storing every request timestamp in Redis becomes a liability. Token bucket is O(1) space. |
| **Fixed window** | Prone to burst-at-boundary attacks (clock skew). Token bucket is time-continuous. |
| **Distributed fairness (Weighted Fair Queueing)** | Overkill. We don't need precise fairness across customers; we need isolation by traffic class. |

---

## Summary

| Aspect | Design |
|--------|--------|
| **Algorithm** | Token bucket (dual, tuned per traffic class) |
| **Isolation** | Separate buckets per customer + traffic class |
| **Interactive params** | max=30, refill=2/sec (absorbs 2–3s bursts) |
| **Batch params** | max=25, refill=3/sec (~10.8K req/hr, handles retries) |
| **Configuration** | Redis keys with defaults + per-customer overrides; zero-downtime updates |
| **Solves** | Isolation (→ no batch starvation), time-of-day decoupling, burst headroom, dynamic scaling |

This design trades a small amount of complexity (two buckets per customer) for **complete isolation** and **tuning freedom**. Each traffic pattern gets what it needs.