## First Principles Decomposition

### Step 1: State the problem without jargon

"Multiple customers send requests. Some requests must respond quickly and arrive in bursts. Others can wait but need reliable throughput for hours. Right now, all requests from a customer share one counter, so the bursty ones and the steady ones steal capacity from each other. When the counter runs out, the wrong traffic gets blocked."

### Step 2: Atomic components

**Inputs:** Request + endpoint prefix (traffic type signal) + customer identity + current time + stored usage state

**Outputs:** Allow/deny decision + (optional) retry-after signal, within sub-millisecond overhead for interactive

**Real constraints vs assumed:**
- Real: Interactive P99 < 200ms total → rate limiter overhead must be <5ms
- Real: Batch needs 2.78 req/s sustained, tolerates 5s latency
- Real: Premium customers need configurable limits without code deploy
- **Assumed (wrong):** One counter per customer is required → this is the root cause of all four problems
- **Assumed (wrong):** A different algorithm will fix this → it won't; resource contention is a configuration problem, not an algorithm problem

### Step 3: Question each component

| Component | Challenge | Finding |
|---|---|---|
| Single bucket per customer | Required? | No. Nothing in the requirements mandates it. |
| Token bucket algorithm | Wrong choice? | No — it's correct for bursts. Wrong *parameters*, wrong *scope*. |
| `get` → compute → `set` pipeline | Atomic? | **No.** Two concurrent requests read the same token count and both decrement — this is a TOCTOU race. Silent correctness bug. |
| `max_tokens=100, refill_rate=10` | For whom? | Hardcoded for no one in particular. Ignores both traffic patterns. |

**Key insight from decomposition:** No algorithm change fixes problems 2 and 3. Those are caused by two traffic types sharing a counter — a structural problem. The solution is separation, not a smarter algorithm.

### Step 4: Rebuild from fundamentals

**Core transformation:** `(customer_id, traffic_type, time) → allow/deny` via isolated, atomically-updated per-type state.

Minimum viable design:
1. Classify traffic type from endpoint prefix
2. Look up per-(customer, type) state
3. Update atomically
4. Apply limits from configuration, not code

Production additions, justified one at a time:
- Two buckets per customer (eliminates contention)
- Lua script for atomicity (fixes race condition)
- Redis-backed config (enables ops-time limit changes)
- Tuned parameters per traffic type (matches actual patterns)

---

## Recommended Architecture

### The core diagnosis

All four reported problems share one cause: **a single shared counter forces two traffic types with incompatible SLAs to compete for the same resource.** This is not fixable by changing the algorithm. Leaky bucket would make interactive *worse* (punishes bursts by design). Sliding window log is more precise but still shared. The fix is structural.

### Algorithm: Token bucket for both, separate namespaces

Token bucket is correct for both patterns — the algorithm isn't the problem. What changes:

| | Interactive | Batch |
|---|---|---|
| Bucket capacity | 30 tokens | 60 tokens |
| Refill rate | 15 tokens/sec | 3 tokens/sec |
| Rationale | Absorbs 20-req burst with headroom; refills in 2s | Sustains 3 req/s, absorbs 5 req/s retry spikes for ~20s |
| Redis namespace | `rl:{cid}:interactive` | `rl:{cid}:batch` |

The sliding window log is strictly more precise than token bucket but requires O(requests) memory per client rather than O(1). At 100 req/s across all interactive users, that's non-trivial. Token bucket at O(1) per client wins on the interactive latency constraint.

Leaky bucket is correct for batch (smooth output), but it requires a queue — you'd need to delay rather than reject, which adds infrastructure complexity. Token bucket with a steady refill rate approximates the same behavior with simpler infrastructure and a clean reject-with-retry-after path.

### Redis key design

```
# Per-customer, per-type state (2 fields each, stored as hash)
rl:{client_id}:interactive        HSET tokens <float> last_refill <timestamp>
rl:{client_id}:batch              HSET tokens <float> last_refill <timestamp>

# Per-customer limit overrides (optional, falls through to tier defaults)
rl:config:{client_id}             HSET interactive_max 50 interactive_rate 25
                                            batch_max 120 batch_rate 6

# Tier defaults (ops-managed, no code deploy needed)
rl:config:tier:premium            HSET interactive_max 50 interactive_rate 25 ...
rl:config:tier:standard           HSET interactive_max 30 interactive_rate 15 ...

# Customer → tier mapping (loaded at auth time, short TTL cache)
rl:tier:{client_id}               STRING "premium"  TTL 300s
```

Ops changes a customer's limits with `HSET rl:config:{client_id} interactive_max 80` — no deploy, takes effect on next request within 300s (tier cache TTL).

### Atomicity fix (the silent bug)

The current code reads in one pipeline, writes in another — two concurrent requests can both read `tokens=1`, both subtract 1, both write `tokens=0`, and both return `True`. Fix with a Lua script, which Redis executes atomically:

```lua
-- rate_limit.lua
local key = KEYS[1]
local now = tonumber(ARGV[1])
local max_tokens = tonumber(ARGV[2])
local refill_rate = tonumber(ARGV[3])

local data = redis.call('HMGET', key, 'tokens', 'last_refill')
local tokens = tonumber(data[1]) or max_tokens
local last_refill = tonumber(data[2]) or now

-- Refill
local elapsed = now - last_refill
tokens = math.min(max_tokens, tokens + elapsed * refill_rate)

if tokens >= 1.0 then
    tokens = tokens - 1.0
    redis.call('HMSET', key, 'tokens', tokens, 'last_refill', now)
    redis.call('EXPIRE', key, 86400)
    return {1, tokens}   -- allowed, tokens remaining
end

-- Return time until 1 token is available
local wait = (1.0 - tokens) / refill_rate
return {0, wait}         -- denied, seconds to wait
```

### Implementation

```python
# rate_limiter.py
import redis
import time
from enum import Enum
from functools import lru_cache

RATE_LIMIT_SCRIPT = """..."""  # lua above

class TrafficType(Enum):
    INTERACTIVE = "interactive"
    BATCH = "batch"

INTERACTIVE_PREFIXES = ("/api/v1/query/", "/api/v1/dashboard/")
BATCH_PREFIXES = ("/api/v1/batch/", "/api/v1/export/")

DEFAULT_LIMITS = {
    TrafficType.INTERACTIVE: {"max_tokens": 30, "refill_rate": 15},
    TrafficType.BATCH:       {"max_tokens": 60, "refill_rate": 3},
}

TIER_MULTIPLIERS = {
    "premium":  2.0,
    "standard": 1.0,
    "free":     0.5,
}

class TwoLaneLimiter:
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self._script = redis_client.register_script(RATE_LIMIT_SCRIPT)

    def classify(self, path: str) -> TrafficType | None:
        if any(path.startswith(p) for p in INTERACTIVE_PREFIXES):
            return TrafficType.INTERACTIVE
        if any(path.startswith(p) for p in BATCH_PREFIXES):
            return TrafficType.BATCH
        return None  # unclassified — caller decides fallback behavior

    def _get_limits(self, client_id: str, traffic_type: TrafficType) -> dict:
        # 1. Check per-customer override
        config_key = f"rl:config:{client_id}"
        prefix = traffic_type.value
        override = self.redis.hmget(
            config_key, f"{prefix}_max", f"{prefix}_rate"
        )
        if override[0] and override[1]:
            return {"max_tokens": float(override[0]), "refill_rate": float(override[1])}

        # 2. Fall through to tier
        tier = self.redis.get(f"rl:tier:{client_id}") or b"standard"
        tier = tier.decode()
        multiplier = TIER_MULTIPLIERS.get(tier, 1.0)
        base = DEFAULT_LIMITS[traffic_type]
        return {
            "max_tokens":  base["max_tokens"]  * multiplier,
            "refill_rate": base["refill_rate"] * multiplier,
        }

    def allow_request(self, client_id: str, path: str) -> tuple[bool, float]:
        """Returns (allowed, retry_after_seconds)"""
        traffic_type = self.classify(path)
        if traffic_type is None:
            return True, 0  # unclassified traffic passes; instrument separately

        limits = self._get_limits(client_id, traffic_type)
        key = f"rl:{client_id}:{traffic_type.value}"

        result = self._script(
            keys=[key],
            args=[time.time(), limits["max_tokens"], limits["refill_rate"]],
        )
        allowed, value = int(result[0]), float(result[1])
        return bool(allowed), (0.0 if allowed else value)


# Flask integration
limiter = TwoLaneLimiter(redis_client)

@app.before_request
def check_rate_limit():
    client_id = get_client_id(request)
    allowed, retry_after = limiter.allow_request(client_id, request.path)
    if not allowed:
        response = jsonify({"error": "Rate limited", "retry_after": retry_after})
        response.headers["Retry-After"] = str(int(retry_after) + 1)
        response.headers["X-RateLimit-Type"] = limiter.classify(request.path).value
        return response, 429
```

### How each problem is resolved

**Problem 1 — Interactive users see 429s on dashboard load.**
Root cause: batch traffic depletes the shared bucket before the burst arrives. Fix: interactive bucket is now isolated. The 30-token capacity absorbs a 20-request burst with 10 tokens left. Refill at 15/s means the bucket is full again in under 1 second of idle. Users will not see 429s under normal burst patterns.

**Problem 2 — Batch jobs throttled during business hours.**
Root cause: batch and interactive share a bucket. Fix: separate buckets. Batch at 3 req/s sustained against a 60-token bucket (20s of burst capacity) will never be throttled unless a client genuinely exceeds its allocation. Interactive traffic is invisible to the batch limiter.

**Problem 3 — 2AM batch export depletes bucket; 9AM team blocked for 10 seconds.**
Root cause: one bucket, no traffic type isolation. Fix: batch operations deplete `rl:{cid}:batch`. At 9AM, `rl:{cid}:interactive` is at full capacity (30 tokens) — it was never touched. The team's dashboards load without delay.

**Problem 4 — Premium limits require code deploy.**
Fix: `redis-cli HSET rl:config:{client_id} interactive_max 80 interactive_rate 40 batch_max 200 batch_rate 10`. Takes effect within the tier cache TTL (300s). Revert with `DEL rl:config:{client_id}`. No deploy, no restart.

### What this architecture deliberately does not do

- **No queuing for batch.** Batch clients get a reject with `Retry-After`. This is simpler and sufficient since batch jobs already retry. Queuing adds infrastructure (workers, memory pressure) with no benefit here.
- **No sliding window log.** It's more precise but O(requests) memory per client vs O(1). At the stated volumes the precision difference doesn't matter — the extra infrastructure cost does.
- **No cross-lane borrowing.** A premium customer with unused batch capacity cannot lend it to interactive. That sharing is what caused problem 3. Isolation is a feature, not a limitation.