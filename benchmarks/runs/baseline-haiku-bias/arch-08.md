# Rate Limiting Architecture for DataForge

The core problem is serving two **incompatible traffic patterns** with a single limiter. Your current system treats all traffic equally, causing:
- Interactive bursts to trigger starvation (batch depletes the bucket, interactive hits 429s)
- Cross-time starvation (off-peak batch consumption blocks peak interactive users)
- Operational inflexibility (limits baked into code)

**Solution: Dual-limiter architecture with per-traffic-type isolation and runtime configuration.**

---

## Recommended Architecture

### 1. Separate Rate Limiters per Traffic Type

Use **token bucket for interactive** (tolerates bursts) and **leaky bucket for batch** (guarantees throughput).

**Why:**
- Token bucket excels at bursty, latency-sensitive traffic — but only if sized correctly
- Leaky bucket smooths steady traffic and prevents starvation (you get predictable, fair throughput)
- Separation prevents batch from consuming interactive capacity

### 2. Route by Endpoint Prefix

Detect traffic type from the request path before rate limit check:

```python
def get_traffic_class(path: str) -> str:
    """Classify traffic based on endpoint prefix."""
    if path.startswith(('/api/v1/query/', '/api/v1/dashboard/')):
        return 'interactive'
    elif path.startswith(('/api/v1/batch/', '/api/v1/export/')):
        return 'batch'
    return 'default'  # fallback for other endpoints
```

### 3. Algorithms and Parameters

#### Interactive Limiter: Token Bucket
```python
# Sized to absorb normal 10-20 req/s bursts (2-second window)
max_tokens = 50      # Can absorb 2.5s of 20 req/s traffic
refill_rate = 20     # Refills burst capacity in 2.5 seconds
                     # Sustains typical ~100 req/s / 200 customers = 0.5 req/s avg per customer
```

**Why these numbers:**
- A 2-second burst of 20 req/s = 40 requests. With max=50, you safely accommodate this without 429s.
- At 20 tokens/sec refill, if a burst depletes the bucket, it refills in 2.5 seconds (acceptable for interactive users).
- 100 req/s peak ÷ 200 typical customers = 0.5 req/s per customer baseline.

#### Batch Limiter: Leaky Bucket
```python
# Guarantees steady throughput, no starvation
max_tokens = 10      # Small burst capacity (handles retries / small spikes)
refill_rate = 3      # Exactly matches sustained batch rate (3 req/s)
                     # Over 1 hour: 3 * 3600 = 10,800 requests ✓
```

**Why leaky bucket for batch:**
- Leaky bucket enforces a **fixed output rate** — requests are dripped out at exactly `refill_rate`.
- Prevents this scenario: batch job runs 24/7 at 3 req/s, refill_rate = 3, so tokens stay at 0. But the rate is guaranteed.
- If a spike happens (5 req/s during retries), leaky bucket smoothly handles it by draining the small burst pool, then resuming the steady rate.

---

## Redis Key Design

```
# Configuration (externalized, runtime-updatable)
rate_limit:config:{customer_id}:{traffic_class}:max_tokens
rate_limit:config:{customer_id}:{traffic_class}:refill_rate
rate_limit:config:{customer_id}:{traffic_class}:algorithm    # 'token_bucket' or 'leaky_bucket'

# Example:
rate_limit:config:customer_123:interactive:max_tokens -> 50
rate_limit:config:customer_123:interactive:refill_rate -> 20
rate_limit:config:customer_123:batch:max_tokens -> 10
rate_limit:config:customer_123:batch:refill_rate -> 3

# Bucket state (per customer, per traffic class)
rate_limit:bucket:{customer_id}:{traffic_class}:tokens       # current tokens (float)
rate_limit:bucket:{customer_id}:{traffic_class}:last_refill  # timestamp of last refill

# Example:
rate_limit:bucket:customer_123:interactive:tokens -> 47.5
rate_limit:bucket:customer_123:interactive:last_refill -> 1712505600.123
```

**Design principle:** Bucket state and config are separate. Config changes take effect on the next refill calculation (atomic within the request).

---

## Implementation

### Rate Limiter Classes

```python
import redis
import time
from abc import ABC, abstractmethod

class RateLimiter(ABC):
    def __init__(self, redis_client, customer_id: str, traffic_class: str):
        self.redis = redis_client
        self.customer_id = customer_id
        self.traffic_class = traffic_class
        self.config_prefix = f"rate_limit:config:{customer_id}:{traffic_class}"
        self.bucket_prefix = f"rate_limit:bucket:{customer_id}:{traffic_class}"

    def get_config(self) -> dict:
        """Load config from Redis, with sensible defaults."""
        pipe = self.redis.pipeline()
        pipe.get(f"{self.config_prefix}:max_tokens")
        pipe.get(f"{self.config_prefix}:refill_rate")
        max_tokens_str, refill_rate_str = pipe.execute()
        
        return {
            'max_tokens': float(max_tokens_str or self._default_max_tokens()),
            'refill_rate': float(refill_rate_str or self._default_refill_rate()),
        }

    @abstractmethod
    def _default_max_tokens(self) -> float:
        pass

    @abstractmethod
    def _default_refill_rate(self) -> float:
        pass

    @abstractmethod
    def allow_request(self) -> bool:
        pass


class TokenBucketLimiter(RateLimiter):
    """Token bucket: good for bursty traffic (interactive)."""
    
    def _default_max_tokens(self) -> float:
        return 50
    
    def _default_refill_rate(self) -> float:
        return 20  # tokens/second
    
    def allow_request(self) -> bool:
        config = self.get_config()
        now = time.time()
        
        # Atomically read current state
        pipe = self.redis.pipeline()
        pipe.get(f"{self.bucket_prefix}:tokens")
        pipe.get(f"{self.bucket_prefix}:last_refill")
        tokens_str, last_refill_str = pipe.execute()
        
        tokens = float(tokens_str) if tokens_str else config['max_tokens']
        last_refill = float(last_refill_str) if last_refill_str else now
        
        # Calculate refill
        elapsed = now - last_refill
        tokens = min(config['max_tokens'], tokens + elapsed * config['refill_rate'])
        
        # Check if request is allowed
        if tokens >= 1:
            tokens -= 1
            pipe = self.redis.pipeline()
            pipe.set(f"{self.bucket_prefix}:tokens", tokens)
            pipe.set(f"{self.bucket_prefix}:last_refill", now)
            pipe.execute()
            return True
        
        return False


class LeakyBucketLimiter(RateLimiter):
    """Leaky bucket: guarantees steady throughput (batch)."""
    
    def _default_max_tokens(self) -> float:
        return 10
    
    def _default_refill_rate(self) -> float:
        return 3  # tokens/second (requests/second)
    
    def allow_request(self) -> bool:
        config = self.get_config()
        now = time.time()
        
        # Read current state
        pipe = self.redis.pipeline()
        pipe.get(f"{self.bucket_prefix}:tokens")
        pipe.get(f"{self.bucket_prefix}:last_refill")
        tokens_str, last_refill_str = pipe.execute()
        
        tokens = float(tokens_str) if tokens_str else config['max_tokens']
        last_refill = float(last_refill_str) if last_refill_str else now
        
        # Leaky bucket: "leak" tokens at fixed rate
        elapsed = now - last_refill
        leaked = elapsed * config['refill_rate']
        tokens = max(0, tokens - leaked)  # Leak out tokens over time
        
        # Try to add one token (representing one request)
        if tokens < config['max_tokens']:
            tokens += 1
            pipe = self.redis.pipeline()
            pipe.set(f"{self.bucket_prefix}:tokens", tokens)
            pipe.set(f"{self.bucket_prefix}:last_refill", now)
            pipe.execute()
            return True
        
        # Bucket full (at max capacity), request denied
        return False
```

### Middleware Integration

```python
from flask import request, jsonify

def get_traffic_class(path: str) -> str:
    if path.startswith(('/api/v1/query/', '/api/v1/dashboard/')):
        return 'interactive'
    elif path.startswith(('/api/v1/batch/', '/api/v1/export/')):
        return 'batch'
    return 'default'

@app.before_request
def check_rate_limit():
    customer_id = get_customer_id(request)  # from JWT, API key, etc.
    traffic_class = get_traffic_class(request.path)
    
    # Select appropriate limiter
    if traffic_class == 'interactive':
        limiter = TokenBucketLimiter(redis, customer_id, 'interactive')
    elif traffic_class == 'batch':
        limiter = LeakyBucketLimiter(redis, customer_id, 'batch')
    else:
        limiter = TokenBucketLimiter(redis, customer_id, 'default')  # fallback
    
    if not limiter.allow_request():
        return jsonify({
            "error": "Rate limited",
            "retry_after": 1,  # suggest retry in 1 second
            "traffic_class": traffic_class
        }), 429
```

---

## How This Solves Each Problem

### 1. Interactive Burst Penalty ✓
**Before:** 100 max tokens, 10 refill/sec → burst of 20 req/s causes 7+ seconds of 429s.

**After:** 50 max tokens, 20 refill/sec → burst of 20 req/s depletes to ~30 tokens, refills in 1 second. Users see no 429s during normal dashboard load.

### 2. Batch vs Interactive Competition ✓
**Before:** Shared bucket — batch runs steady at 3 req/s, consuming all refill. Interactive can't accumulate burst capacity.

**After:** Separate buckets. Batch limiter handles batch at exactly 3 req/s. Interactive limiter has its own capacity. Batch can't starve interactive.

### 3. Cross-Time-Period Starvation ✓
**Before:** Batch job depletes the shared bucket at 2 AM. By 9 AM, if batch is still running at 3 req/s and refill = 3 req/s, tokens stay at 0. Interactive requests hit 429s.

**After:** 
- Batch has its own bucket and limiter — batch capacity doesn't affect interactive
- Leaky bucket for batch smooths requests and guarantees throughput
- Interactive bucket is separate and always refills at 20 tokens/sec. Come 9 AM, it's at full capacity (50 tokens).

### 4. Runtime Configuration ✓
**Before:** Limits hard-coded in class initialization.

**After:** Config stored in Redis (`rate_limit:config:{customer_id}:...`). Ops team can update limits without code deploy:

```python
# Redis CLI or admin API:
SET rate_limit:config:acme_enterprise:interactive:max_tokens 100
SET rate_limit:config:acme_enterprise:interactive:refill_rate 40
SET rate_limit:config:acme_enterprise:batch:refill_rate 5  # Upgrade batch throughput
```

Changes take effect on the next request (config is read on every request).

---

## Additional Operational Features

### 1. Per-Customer Tiering (Premium Support)

```python
# Admin API to set tier limits
def set_customer_tier(customer_id: str, tier: str):
    tiers = {
        'free': {
            'interactive': {'max_tokens': 30, 'refill_rate': 10},
            'batch': {'max_tokens': 5, 'refill_rate': 1},
        },
        'pro': {
            'interactive': {'max_tokens': 50, 'refill_rate': 20},
            'batch': {'max_tokens': 10, 'refill_rate': 3},
        },
        'enterprise': {
            'interactive': {'max_tokens': 200, 'refill_rate': 50},
            'batch': {'max_tokens': 30, 'refill_rate': 10},
        },
    }
    
    config = tiers[tier]
    for traffic_class, limits in config.items():
        for key, value in limits.items():
            redis.set(
                f"rate_limit:config:{customer_id}:{traffic_class}:{key}",
                value
            )
```

### 2. Monitoring & Alerts

```python
# Log rate limit events for observability
def log_rate_limit_event(customer_id: str, traffic_class: str, allowed: bool):
    redis.incr(f"metrics:rate_limit:{customer_id}:{traffic_class}:{'allowed' if allowed else 'rejected'}")
    
    # Alert if a customer is consistently hitting limits
    rejected = redis.get(f"metrics:rate_limit:{customer_id}:{traffic_class}:rejected") or 0
    if int(rejected) > 100:  # threshold
        alert(f"High rate limit rejections for {customer_id} ({traffic_class})")
```

### 3. Graceful Degradation

```python
# If Redis is unavailable, fail open (allow request) rather than deny
try:
    if not limiter.allow_request():
        return 429
except redis.ConnectionError:
    # Redis down; allow request, but log it
    logger.warning(f"Rate limiter Redis unavailable for {customer_id}")
    # allow_request()
```

---

## Summary Table

| Aspect | Interactive | Batch |
|--------|-------------|-------|
| **Algorithm** | Token Bucket | Leaky Bucket |
| **max_tokens** | 50 | 10 |
| **refill_rate** | 20/sec | 3/sec |
| **Characteristic** | Absorbs bursts, refills quickly | Smooth, predictable throughput |
| **Use case** | Dashboards, user-facing queries | ETL, scheduled exports |
| **Starvation risk** | None (separate bucket) | None (guaranteed rate) |
| **Config location** | Redis `rate_limit:config:...` | Redis `rate_limit:config:...` |

This architecture is **operationally flexible, fair, and tailored to each traffic pattern** — exactly what DataForge needs.