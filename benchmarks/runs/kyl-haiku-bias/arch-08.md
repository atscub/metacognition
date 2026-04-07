Now let me work through the decomposition:

## Step 1: Problem Without Jargon

The system prevents customers from using it too much. But customers use it in two totally different ways: quick bursts during the day, and steady work around the clock. When you force the same limit on both, the steady traffic blocks the bursty traffic during peak hours, *and* the bursty traffic blocks steady traffic at night. They're starving each other.

## Step 2: Atomic Components

| Component | Details |
|-----------|---------|
| **Input** | A request (customer ID, endpoint, timestamp) |
| **Output** | Allow or reject this request |
| **Real constraints** | Can't let one customer monopolize the API; interactive P99 < 200ms; batch needs 10k req/hour sustained; ops wants config without deploys |
| **Assumed constraints** | One rate limit per customer (across all endpoints); one algorithm fits both patterns; must be globally applied |
| **Core transformation** | "Does this request fit within what this customer should be doing *right now*?" |

## Step 3: Question the Assumptions

**"Do all requests from a customer share one bucket?"**  
No. There's no law that says batch traffic and interactive traffic must share a limit. The constraint is "prevent *one customer* from monopolizing capacity," not "give each customer one bucket."

**"Does one algorithm work for both patterns?"**  
Not here. Token bucket is great for bursts (interactive) but mediocre for steady throughput (batch). Leaky bucket is great for steady (batch) but punishes bursts (interactive). Forcing one to handle both is like using a hammer for both nails and screws—possible, but neither job is done well.

**"What if I removed the 'single limiter'?"**  
Batch and interactive wouldn't interfere. Each would be optimized for its actual constraint. Problem solved—but nobody's been asking for removal, they've been asking for the "right algorithm."

**Why does the current system mix them?**  
Simplicity: easier to maintain one limiter than two. But that simplicity trades correctness for ease of implementation.

---

## Step 4: Rebuild from First Principles

**Core problem:** Prevent a customer from consuming all API capacity and starving other customers.

**Simplest version:** Track usage, compare against a budget, reject if over. That's it.

**What do I add for production?**

| Requirement | Why | Implication |
|-------------|-----|-------------|
| Low latency for interactive (< 200ms) | Users see the dashboard slowly | Token bucket / leaky bucket (not sliding window log) |
| Handle interactive bursts (10-20 req in 2s) | Users fire rapid requests | Token bucket with burst capacity |
| Steady throughput for batch (10k req/hr = 2.8 req/s) | ETL must process reliably | Leaky bucket or token bucket with lower refill rate |
| Separate interactive and batch limits | They have different constraints and arrival patterns | **Separate buckets per traffic type** |
| Config without deploys | Ops needs to tune limits | External config (DB, Redis hashes, or config service) |

**The fundamental insight:** I don't need to pick one algorithm. I need *two* limiters per customer—one for interactive traffic, one for batch. Each optimized for its pattern.

---

## My Recommendation

### Architecture: **Dual-Rate-Limiting with Traffic-Type Separation**

#### 1. **Separate Rate Limits by Traffic Type**

Each customer gets **two independent buckets**:

```
Interactive bucket:   burst-optimized (token bucket)
  - Capacity: 30 tokens (handles 3x spike: 10-20 req in 2s)
  - Refill: 5 tokens/second
  - Supports 9 AM–6 PM peak, off-hours decay doesn't penalize

Batch bucket:         throughput-optimized (leaky bucket)
  - Capacity: 100 tokens (smooths occasional retries)
  - Refill: ~3.33 tokens/second (exactly 10k req/hour)
  - Runs 24/7, steady consumption
```

**Why this works:**
- Batch traffic at 3 req/s fits cleanly in batch bucket, never blocks interactive
- Interactive bursts fit in their bucket without competing
- Off-hours batch work doesn't drain interactive capacity for 9 AM
- Each bucket is sized for its actual traffic pattern

#### 2. **Algorithm Choice per Bucket**

**Interactive bucket: Token Bucket**
```python
# Optimized for bursts, low overhead
class TokenBucketLimiter:
    """Token bucket for bursty traffic."""
    def __init__(self, capacity, refill_rate_per_sec):
        self.capacity = capacity
        self.refill_rate = refill_rate_per_sec
```

**Batch bucket: Leaky Bucket (via Sliding Window Counter)**
```python
# Leaky bucket = constant outflow rate
# Implement as token bucket with high refill rate and lower capacity
# OR sliding window counter for exact rate control
class LeakyBucketLimiter:
    """Sliding window: allows exact rate, smooth output."""
    def __init__(self, rate_per_second, window_size_seconds):
        self.rate = rate_per_second
        self.window = window_size_seconds
```

Why token bucket for interactive: Fast Redis operations (2 commands), low latency overhead.  
Why leaky bucket for batch: Prevents spike starvation, ensures customers get consistent throughput over hours.

#### 3. **Redis Key Design**

```
Customer-specific buckets:

rate_limit:cust_{customer_id}:interactive:tokens
rate_limit:cust_{customer_id}:interactive:last_refill
rate_limit:cust_{customer_id}:interactive:capacity
rate_limit:cust_{customer_id}:interactive:refill_rate

rate_limit:cust_{customer_id}:batch:tokens
rate_limit:cust_{customer_id}:batch:last_refill
rate_limit:cust_{customer_id}:batch:window_start
rate_limit:cust_{customer_id}:batch:requests_in_window

Configuration (separate, ops-writable):
config:rate_limits:interactive:capacity
config:rate_limits:interactive:refill_rate
config:rate_limits:batch:rate_per_second
config:rate_limits:batch:window_seconds
config:rate_limits:batch:burst_capacity
```

#### 4. **Traffic Type Routing**

```python
def get_bucket_type(request):
    """Route to the correct bucket based on endpoint."""
    if request.path.startswith('/api/v1/query') or request.path.startswith('/api/v1/dashboard'):
        return 'interactive'
    elif request.path.startswith('/api/v1/batch') or request.path.startswith('/api/v1/export'):
        return 'batch'
    # default to interactive for safety
    return 'interactive'

@app.before_request
def check_rate_limit():
    client_id = get_client_id(request)
    bucket_type = get_bucket_type(request)
    
    if bucket_type == 'interactive':
        limiter = interactive_limiter
    else:
        limiter = batch_limiter
    
    if not limiter.allow_request(client_id):
        return jsonify({"error": "Rate limited"}), 429
```

#### 5. **Handling the Four Original Problems**

| Problem | Current Symptom | This Architecture | Why It Works |
|---------|-----------------|-------------------|--------------|
| **#1: Interactive burst throttling** | Users see 429 on dashboard load during peak | Separate bucket with 30-token capacity lets 10-20 req bursts through | Token bucket refills at 5 tok/s, burst capacity is 3x typical spike |
| **#2: Batch spiking under interactive load** | ETL fails during 9 AM peak when interactive competes | Batch has its own bucket, isolated from interactive peak | No competition—batch can run at 3 req/s steadily regardless of interactive traffic |
| **#3: Off-hours batch starves 9 AM interactive** | Enterprise export at 2 AM depletes bucket; 9 AM interactive blocked | Off-hours batch consumption never touches interactive bucket | Completely separate limits; interactive bucket refills fresh daily (or doesn't matter if off-hours) |
| **#4: Ops wants config without deploys** | Must change code, redeploy | Capacity/rate stored in Redis config keys, watched by limiter on startup or cached with short TTL | Redis hashes at `config:rate_limits:{type}:*` read by limiter, no code deploy needed |

---

### Implementation Sketch

```python
import redis
import time

class DualRateLimiter:
    def __init__(self, redis_client):
        self.redis = redis_client
        self.config_ttl = 60  # cache config for 60s
        self._config_cache = {}
        self._config_cache_time = {}
    
    def get_config(self, bucket_type):
        """Fetch config from Redis with caching."""
        if time.time() - self._config_cache_time.get(bucket_type, 0) < self.config_ttl:
            return self._config_cache[bucket_type]
        
        config_key = f"config:rate_limits:{bucket_type}"
        config = self.redis.hgetall(config_key)
        self._config_cache[bucket_type] = config
        self._config_cache_time[bucket_type] = time.time()
        return config
    
    def allow_request(self, client_id: str, bucket_type: str) -> bool:
        config = self.get_config(bucket_type)
        
        if bucket_type == 'interactive':
            return self._token_bucket(client_id, bucket_type, config)
        else:  # batch
            return self._leaky_bucket(client_id, bucket_type, config)
    
    def _token_bucket(self, client_id, bucket_type, config):
        """Token bucket for interactive traffic."""
        capacity = int(config.get(b'capacity', 30))
        refill_rate = float(config.get(b'refill_rate', 5))
        
        key = f"rate_limit:{client_id}:{bucket_type}"
        now = time.time()
        
        pipe = self.redis.pipeline()
        pipe.hgetall(key)
        token_data = pipe.execute()[0]
        
        tokens = float(token_data.get(b'tokens', capacity))
        last_refill = float(token_data.get(b'last_refill', now))
        
        elapsed = now - last_refill
        tokens = min(capacity, tokens + elapsed * refill_rate)
        
        if tokens >= 1:
            tokens -= 1
            self.redis.hset(key, mapping={
                'tokens': tokens,
                'last_refill': now
            })
            return True
        return False
    
    def _leaky_bucket(self, client_id, bucket_type, config):
        """Leaky bucket (sliding window) for batch traffic."""
        rate_per_sec = float(config.get(b'rate_per_second', 2.78))  # 10k/hr
        window_sec = int(config.get(b'window_seconds', 3600))
        
        key = f"rate_limit:{client_id}:{bucket_type}"
        now = time.time()
        window_start = now - window_sec
        
        # Remove old requests outside window
        self.redis.zremrangebyscore(key, '-inf', window_start)
        
        # Count requests in window
        count = self.redis.zcard(key)
        allowed_in_window = int(rate_per_sec * window_sec)
        
        if count < allowed_in_window:
            self.redis.zadd(key, {str(now): now})
            self.redis.expire(key, window_sec)
            return True
        return False
```

---

### For Ops: Configuration

Create Redis config hashes (one-time setup, then modify at runtime):

```bash
# Interactive rate limits
HSET config:rate_limits:interactive capacity 30 refill_rate 5

# Batch rate limits (3 req/s = 10,800 req/hour, safe margin below 10k)
HSET config:rate_limits:batch rate_per_second 2.78 window_seconds 3600 burst_capacity 100
```

Ops can adjust without code change:
```bash
# If batch needs more headroom:
HSET config:rate_limits:batch rate_per_second 4.0

# If interactive peak handling needed:
HSET config:rate_limits:interactive capacity 50 refill_rate 7
```

---

### Trade-offs

| Trade-off | This Design | Alternative |
|-----------|-------------|-------------|
| **Complexity** | Two limiters + routing logic | Single limiter is simpler to reason about (but doesn't work) |
| **Redis ops per request** | 3-4 commands (token bucket) or 2-3 (leaky) | Same as current (2-3) |
| **Latency overhead** | < 5ms (unchanged from current) | No improvement vs current |
| **Fairness** | Per-customer, per-traffic-type (precise) | Global (crude) |
| **Burstiness** | Handled well for interactive | Leaky bucket adds latency if you try to burst |

This design prioritizes **correctness and independence** over simplicity. The batch traffic gets its guaranteed throughput, interactive gets its low latency, and they never interfere.