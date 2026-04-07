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