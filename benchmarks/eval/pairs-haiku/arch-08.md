# Task: arch-08 — Rate limiting algorithm for mixed interactive and batch traffic

## Prompt
You are designing the rate limiting system for DataForge, a data processing API. The API
serves two fundamentally different traffic patterns from the same set of customers:

**Interactive traffic** (user-facing dashboards):
- Bursty: a user opens a dashboard and fires 10-20 requests in 2 seconds, then idles
- Latency-sensitive: P99 must be < 200ms, including rate limiter overhead
- Volume: ~100 requests/second peak across all users
- Pattern: 80% of traffic comes during business hours (9 AM - 6 PM)
- Endpoint prefix: `/api/v1/query/*`, `/api/v1/dashboard/*`

**Batch traffic** (ETL pipelines, data exports):
- Steady: consistent throughput for hours at a time
- Throughput-sensitive: needs to process 10,000 requests/hour reliably
- Latency-tolerant: individual request latency up to 5 seconds is acceptable
- Volume: ~3 requests/second sustained, 24/7
- Endpoint prefix: `/api/v1/batch/*`, `/api/v1/export/*`

Current implementation (single global rate limiter):
```python
# rate_limiter.py
import redis
import time

class TokenBucketLimiter:
    def __init__(self, redis_client, max_tokens=100, refill_rate=10):
        """
        max_tokens: bucket capacity
        refill_rate: tokens added per second
        """
        self.redis = redis_client
        self.max_tokens = max_tokens
        self.refill_rate = refill_rate

    def allow_request(self, client_id: str) -> bool:
        key = f"rate_limit:{client_id}"
        now = time.time()

        pipe = self.redis.pipeline()
        pipe.get(f"{key}:tokens")
        pipe.get(f"{key}:last_refill")
        tokens, last_refill = pipe.execute()

        tokens = float(tokens) if tokens else self.max_tokens
        last_refill = float(last_refill) if last_refill else now

        elapsed = now - last_refill
        tokens = min(self.max_tokens, tokens + elapsed * self.refill_rate)

        if tokens >= 1:
            tokens -= 1
            pipe = self.redis.pipeline()
            pipe.set(f"{key}:tokens", tokens)
            pipe.set(f"{key}:last_refill", now)
            pipe.execute()
            return True
        return False

# Applied globally to all endpoints:
limiter = TokenBucketLimiter(redis, max_tokens=100, refill_rate=10)

@app.before_request
def check_rate_limit():
    client_id = get_client_id(request)
    if not limiter.allow_request(client_id):
        return jsonify({"error": "Rate limited"}), 429
```

Problems reported:
1. During business hours, interactive users burst through their token bucket, get rate
   limited for 5-10 seconds, then the bucket refills. Users see intermittent 429 errors
   on dashboard load.
2. Batch jobs run steadily at 3 req/s but occasionally spike to 5 req/s during retries.
   The token bucket accommodates this fine, but the batch traffic competes with
   interactive traffic for the same bucket, and during business hours batch jobs get
   throttled, causing ETL pipeline failures.
3. A single enterprise customer's batch export consumed their entire rate limit at 2 AM,
   and when their team opened dashboards at 9 AM, the bucket was depleted. Interactive
   requests were blocked for the first 10 seconds.
4. The ops team wants to give premium customers higher limits without deploying code
   changes.

The engineering team is debating which algorithm to use:
- **Token bucket**: current approach, good for bursts but problematic as described
- **Sliding window log**: precise but memory-intensive for high-volume clients
- **Leaky bucket**: smooth output rate, good for steady traffic, punishes bursts

Recommend a rate limiting architecture. Specify the algorithm(s), the data structures,
how limits are configured, and how the system handles the problems listed above.
Include the Redis key design.


## Response A
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

## Response B
## First Principles Breakdown

Let me work through this systematically.

### Step 1: State the Problem Without Jargon

We have two groups of people using the same API differently:
- **Group A** (dashboard users): wants to open a page and fire 20 requests fast, then wait
- **Group B** (batch jobs): wants to send 3 requests per second steadily all day

We're currently treating them identically, so when Group A bursts, it either hits a limit and blocks itself, or it's fine but then Group B's steady traffic gets blocked. We can't satisfy both at once with one rule.

### Step 2: Atomic Components

| Component | Reality |
|-----------|---------|
| **Input** | Customer ID, request type, current time |
| **Output** | Allow or reject the request |
| **Real constraints** | (1) Interactive P99 < 200ms, (2) Batch must handle 2.8 req/sec sustained reliably, (3) Backend capacity is shared |
| **Inherited assumption** | One rate limiter, one limit per customer, token bucket is right |
| **Core question** | Should all requests from a customer compete equally? |

### Step 3: Question the Inherited Approach

- **Single limiter**: Is it required? No. It's the root cause of the problem.
- **Token bucket**: Does it work for *both* patterns? No. It's designed for bursts, which helps interactive but starves batch when they collide.
- **Same limits for different traffic**: Why? Inherited from "everyone is a customer, apply the same rule." But the traffic patterns are incompatible.

### Step 4: Rebuild from Fundamentals

What *must* be true?

1. **No single customer can monopolize backend capacity** — this is load-bearing
2. **Interactive bursts shouldn't starve batch** — this is the actual problem
3. **Batch needs predictable throughput** — this is a hard requirement
4. **Limiter overhead must be < 10ms** — interactive latency SLO

What *could* solve this?

**Separate the traffic into two pools with different algorithms.**

Instead of one bucket per customer, have:
- **Interactive quota**: allows bursts (token bucket with high max_tokens)
- **Batch quota**: allows steady throughput (different algorithm, different numbers)

Neither starves the other because they're separate pools.

---

## Recommended Architecture

### Core Insight: Traffic-Type-Aware Rate Limiting

**Separate limits for interactive and batch traffic**, with different algorithms tuned to each pattern's SLO.

```
Customer "Acme":
  ├─ Interactive quota: 200 tokens, refill 20/sec
  │  └─ Allows: burst of 200 (10 seconds of normal load), then refills to sustain 20 req/sec
  └─ Batch quota: 6 req/sec sustained (360 req/hour)
     └─ Allows: steady 6 req/sec, no burst benefit
```

---

### Algorithm Choice

| Traffic Type | Algorithm | Why |
|---|---|---|
| **Interactive** | **Token Bucket (async refill)** | Allows bursts (accommodates dashboard load), refills quickly (users resume after 1-2 seconds) |
| **Batch** | **Fixed Window Counter** (or leaky bucket) | Steady throughput without burst penalties, predictable behavior |

**Why not the same algorithm?** Token bucket is designed to allow you to "borrow" tokens (burst), then refill slowly. This is perfect for interactive. But for batch, there's no need to burst, and borrow-then-wait is painful for 10,000 requests/hour — it's better to just enforce a steady rate per second.

---

### Redis Key Design

```python
# Interactive traffic (token bucket)
"rl:interactive:{customer_id}:tokens"        # float, current tokens
"rl:interactive:{customer_id}:last_refill"   # float, timestamp of last refill
"rl:interactive:{customer_id}:config"        # hash: max_tokens, refill_rate_per_sec

# Batch traffic (fixed window counter)
"rl:batch:{customer_id}:request_count"       # int, requests in current window
"rl:batch:{customer_id}:window_start"        # int, unix timestamp of window start
"rl:batch:{customer_id}:config"              # hash: max_per_window, window_duration_sec

# Global config (allows deployment-free changes)
"rl:config:customers"                        # hash: customer_id → tier
"rl:config:tier:{tier}"                      # hash: interactive_max_tokens, interactive_refill_rate, batch_rate, batch_window_sec
```

---

### Implementation: Dual-Limiter Design

```python
import redis
import time
from typing import Tuple

class DualLimiter:
    """Separates interactive and batch traffic into independent rate limits."""
    
    def __init__(self, redis_client):
        self.redis = redis_client
        self.LUA_INTERACTIVE = """
        local key_tokens = KEYS[1]
        local key_refill = KEYS[2]
        local now = tonumber(ARGV[1])
        local max_tokens = tonumber(ARGV[2])
        local refill_rate = tonumber(ARGV[3])
        
        local tokens = tonumber(redis.call('GET', key_tokens) or max_tokens)
        local last_refill = tonumber(redis.call('GET', key_refill) or now)
        
        local elapsed = now - last_refill
        tokens = math.min(max_tokens, tokens + elapsed * refill_rate)
        
        if tokens >= 1 then
            tokens = tokens - 1
            redis.call('SET', key_tokens, tokens)
            redis.call('SET', key_refill, now)
            return 1
        end
        return 0
        """
        
        self.LUA_BATCH = """
        local key_count = KEYS[1]
        local key_window = KEYS[2]
        local now = tonumber(ARGV[1])
        local max_per_window = tonumber(ARGV[2])
        local window_duration = tonumber(ARGV[3])
        
        local window_start = tonumber(redis.call('GET', key_window) or now)
        local count = tonumber(redis.call('GET', key_count) or 0)
        
        -- If we've moved to a new window, reset
        if now - window_start > window_duration then
            window_start = now
            count = 0
            redis.call('DEL', key_count)
        end
        
        if count < max_per_window then
            count = count + 1
            redis.call('INCR', key_count)
            redis.call('SETEX', key_window, window_duration + 1, window_start)
            return 1
        end
        return 0
        """

    def get_tier_config(self, customer_id: str) -> dict:
        """Fetch customer limits from config (allows runtime changes)."""
        tier = self.redis.hget("rl:config:customers", customer_id)
        if not tier:
            tier = "default"
        
        config = self.redis.hgetall(f"rl:config:tier:{tier}")
        return {
            "interactive_max_tokens": float(config.get("interactive_max_tokens", 200)),
            "interactive_refill_rate": float(config.get("interactive_refill_rate", 20)),
            "batch_max_per_second": float(config.get("batch_max_per_second", 6)),
        }

    def allow_request(self, customer_id: str, traffic_type: str) -> bool:
        """
        Check rate limit for a request.
        traffic_type: "interactive" or "batch"
        """
        now = time.time()
        config = self.get_tier_config(customer_id)
        
        if traffic_type == "interactive":
            keys = [
                f"rl:interactive:{customer_id}:tokens",
                f"rl:interactive:{customer_id}:last_refill",
            ]
            args = [
                now,
                config["interactive_max_tokens"],
                config["interactive_refill_rate"],
            ]
            result = self.redis.eval(self.LUA_INTERACTIVE, 2, *keys, *args)
            return bool(result)
        
        elif traffic_type == "batch":
            keys = [
                f"rl:batch:{customer_id}:request_count",
                f"rl:batch:{customer_id}:window_start",
            ]
            args = [
                now,
                config["batch_max_per_second"],
                1.0,  # 1-second window
            ]
            result = self.redis.eval(self.LUA_BATCH, 2, *keys, *args)
            return bool(result)
        
        return False


# Usage:
limiter = DualLimiter(redis_client)

@app.before_request
def check_rate_limit():
    customer_id = get_customer_id(request)
    traffic_type = get_traffic_type(request)  # "interactive" or "batch"
    
    if not limiter.allow_request(customer_id, traffic_type):
        return jsonify({"error": "Rate limited"}), 429

def get_traffic_type(request):
    """Classify request based on endpoint."""
    if request.path.startswith(("/api/v1/query", "/api/v1/dashboard")):
        return "interactive"
    elif request.path.startswith(("/api/v1/batch", "/api/v1/export")):
        return "batch"
    return "default"
```

---

### How This Fixes Each Problem

| Problem | Old System | New System |
|---------|-----------|-----------|
| **Interactive bursts get throttled** | Token bucket is shared; burst starves refill | Interactive has its own 200-token bucket; bursts freely, refills to 20 req/sec |
| **Batch jobs get throttled during business hours** | Batch competes with interactive for same tokens | Batch has separate quota (6 req/sec); interactive bursts don't affect it |
| **Batch export at 2 AM consumes the bucket, interactive blocked at 9 AM** | Single bucket shared across time; no separation | Batch quota resets every second; batch consumption never affects interactive |
| **Ops needs to change limits without deploying** | Limits are hardcoded in `TokenBucketLimiter.__init__` | Limits in Redis hashes (`rl:config:tier:*`); ops updates at runtime |

---

### Operational Configuration

```python
# Set up tier configs in Redis (ops team can do this anytime)
redis.hset("rl:config:tier:free", mapping={
    "interactive_max_tokens": "50",
    "interactive_refill_rate": "5",
    "batch_max_per_second": "2",
})

redis.hset("rl:config:tier:pro", mapping={
    "interactive_max_tokens": "200",
    "interactive_refill_rate": "20",
    "batch_max_per_second": "6",
})

redis.hset("rl:config:tier:enterprise", mapping={
    "interactive_max_tokens": "500",
    "interactive_refill_rate": "50",
    "batch_max_per_second": "15",
})

# Assign customers to tiers
redis.hset("rl:config:customers", mapping={
    "acme": "pro",
    "megacorp": "enterprise",
    "startup": "free",
})
```

---

### Why This Works

1. **Latency**: Lua scripts are atomic in Redis; no round-trips. Overhead is sub-millisecond.
2. **Fairness**: Interactive and batch quotas are independent; neither can starve the other.
3. **Predictability**: Batch gets a fixed per-second rate, no penalty for previous interactive activity.
4. **Operability**: Change tier configs at runtime without code or deployment.
5. **Scalability**: One Redis key per (customer, traffic_type); number of keys is O(customers × 2), manageable even at scale.

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
