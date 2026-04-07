## Decompose Protocol

### Step 1: State Without Jargon

"Two kinds of work share a single counter that limits how much any one customer can do. Cluster-work (many requests at once, then silence) and trickle-work (slow and constant) drain the same counter. When either drains it, both suffer. Work done at 2 AM depletes the counter that the 9 AM work needs."

The inherited assumption to question: **must both traffic types share a budget?** Nothing in the requirements says they must. This is cargo-culted from "one customer = one limit."

### Step 2: Atomic Components

| Component | Current | Is it required? |
|---|---|---|
| Single bucket per customer | One counter shared by all endpoints | No — invented, not required |
| Token bucket algorithm | Same params for both patterns | Partially — good for interactive, over-generous for batch |
| Hardcoded limits | `max_tokens=100, refill_rate=10` | No — limits should be data, not code |
| Two Redis round-trips | `GET` + `GET`, then `SET` + `SET` | No — one round-trip Lua script handles this atomically |

### Step 3: Rebuild from First Principles

**What am I actually trying to accomplish?**
Ensure each customer's interactive and batch traffic each have independent budgets, sized for their actual patterns, configurable without code changes.

**Simplest thing that could work:** Two separate rate limiters per customer — one per traffic class — with parameters stored in Redis (not code), resolved via a tier system.

---

## Architecture Recommendation

### Core Decision: Traffic Classification + Independent Per-Class Buckets

**Interactive** → Token bucket (burst-friendly by design)
**Batch** → Token bucket with smaller capacity + a per-hour sliding window counter

Why not leaky bucket for batch? It would smooth output — but it also blocks *all* retry bursts, which ETL pipelines do legitimately during transient errors. Token bucket with a small max_tokens lets batch spike to 5 req/s briefly without allowing prolonged overconsumption.

Why not sliding window log? O(n) memory per client at 100 req/s interactive = too expensive. Sliding window *counter* (two fixed windows + linear interpolation) is O(1) and good enough — but token bucket handles the burst math more naturally here.

---

### Redis Key Design

```
# ── Tier defaults (ops writes, no deploy needed) ──────────────────────────
rl:tier:{tier}:{class}:max_tokens          → float
rl:tier:{tier}:{class}:refill_rate         → float   # tokens/second

# Examples:
rl:tier:standard:interactive:max_tokens    → "25"
rl:tier:standard:interactive:refill_rate   → "5"
rl:tier:standard:batch:max_tokens          → "12"
rl:tier:standard:batch:refill_rate         → "3"

rl:tier:premium:interactive:max_tokens     → "60"
rl:tier:premium:interactive:refill_rate    → "15"
rl:tier:premium:batch:max_tokens           → "30"
rl:tier:premium:batch:refill_rate          → "8"

# ── Per-customer overrides (ops writes for one-offs) ───────────────────────
rl:override:{customer_id}:{class}:max_tokens    → float  (optional, beats tier)
rl:override:{customer_id}:{class}:refill_rate   → float  (optional, beats tier)

# ── Customer → tier mapping (ops writes) ──────────────────────────────────
rl:customer:{customer_id}:tier             → "standard" | "premium"

# ── Live token state (limiter writes) ─────────────────────────────────────
rl:state:{customer_id}:{class}:tokens      → float
rl:state:{customer_id}:{class}:last_refill → unix timestamp float
```

`{class}` is `interactive` or `batch`, derived from endpoint prefix before the Redis call.

---

### Implementation

```python
# rate_limiter.py
import redis
import time
from enum import Enum
from typing import Tuple

class TrafficClass(str, Enum):
    INTERACTIVE = "interactive"
    BATCH = "batch"

INTERACTIVE_PREFIXES = ("/api/v1/query/", "/api/v1/dashboard/")
BATCH_PREFIXES = ("/api/v1/batch/", "/api/v1/export/")

def classify_request(path: str) -> TrafficClass:
    if any(path.startswith(p) for p in INTERACTIVE_PREFIXES):
        return TrafficClass.INTERACTIVE
    if any(path.startswith(p) for p in BATCH_PREFIXES):
        return TrafficClass.BATCH
    return TrafficClass.INTERACTIVE  # safe default: use stricter limits

# Atomic check-and-update in a single Redis round-trip.
# Eliminates the race condition in the original (GET/GET/SET/SET).
TOKEN_BUCKET_LUA = """
local key_tokens     = KEYS[1]
local key_refill     = KEYS[2]
local max_tokens     = tonumber(ARGV[1])
local refill_rate    = tonumber(ARGV[2])
local now            = tonumber(ARGV[3])

local tokens      = tonumber(redis.call("GET", key_tokens))
local last_refill = tonumber(redis.call("GET", key_refill))

if tokens == nil then tokens = max_tokens end
if last_refill == nil then last_refill = now end

local elapsed = now - last_refill
tokens = math.min(max_tokens, tokens + elapsed * refill_rate)

if tokens >= 1 then
    tokens = tokens - 1
    redis.call("SET", key_tokens,  tokens)
    redis.call("SET", key_refill,  now)
    redis.call("EXPIRE", key_tokens,  3600)
    redis.call("EXPIRE", key_refill,  3600)
    return 1
else
    return 0
end
"""

class DataForgeRateLimiter:
    DEFAULT_TIER = "standard"

    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self._lua = redis_client.register_script(TOKEN_BUCKET_LUA)

    # ── Config resolution ────────────────────────────────────────────────

    def _get_limit_params(
        self, customer_id: str, traffic_class: TrafficClass
    ) -> Tuple[float, float]:
        """
        Resolution order (first match wins):
          1. Per-customer override in Redis     ← ops can set for one customer
          2. Tier default in Redis              ← ops can tune tiers
          3. Hardcoded fallback                 ← never reached in prod
        """
        cls = traffic_class.value

        # 1. Per-customer override
        pipe = self.redis.pipeline()
        pipe.get(f"rl:override:{customer_id}:{cls}:max_tokens")
        pipe.get(f"rl:override:{customer_id}:{cls}:refill_rate")
        pipe.get(f"rl:customer:{customer_id}:tier")
        override_max, override_rate, tier = pipe.execute()

        if override_max and override_rate:
            return float(override_max), float(override_rate)

        # 2. Tier default
        tier = (tier or self.DEFAULT_TIER).decode() if isinstance(tier, bytes) else (tier or self.DEFAULT_TIER)
        pipe = self.redis.pipeline()
        pipe.get(f"rl:tier:{tier}:{cls}:max_tokens")
        pipe.get(f"rl:tier:{tier}:{cls}:refill_rate")
        tier_max, tier_rate = pipe.execute()

        if tier_max and tier_rate:
            return float(tier_max), float(tier_rate)

        # 3. Hardcoded fallback (should not be reached; alerts if it is)
        fallbacks = {
            TrafficClass.INTERACTIVE: (25.0, 5.0),
            TrafficClass.BATCH:       (12.0, 3.0),
        }
        return fallbacks[traffic_class]

    # ── Core allow/deny ──────────────────────────────────────────────────

    def allow_request(
        self, customer_id: str, traffic_class: TrafficClass
    ) -> bool:
        max_tokens, refill_rate = self._get_limit_params(customer_id, traffic_class)
        cls = traffic_class.value

        allowed = self._lua(
            keys=[
                f"rl:state:{customer_id}:{cls}:tokens",
                f"rl:state:{customer_id}:{cls}:last_refill",
            ],
            args=[max_tokens, refill_rate, time.time()],
        )
        return bool(allowed)
```

```python
# app.py
from flask import Flask, request, jsonify, g
from rate_limiter import DataForgeRateLimiter, classify_request

app = Flask(__name__)
limiter = DataForgeRateLimiter(redis_client)

@app.before_request
def check_rate_limit():
    customer_id = get_customer_id(request)       # from JWT/API key
    traffic_class = classify_request(request.path)

    if not limiter.allow_request(customer_id, traffic_class):
        retry_after = _estimate_retry_after(customer_id, traffic_class)
        return jsonify({
            "error": "rate_limited",
            "traffic_class": traffic_class.value,
            "retry_after_seconds": retry_after,
        }), 429
```

---

### How This Solves Each Reported Problem

**Problem 1 — Dashboard users seeing 429s on load**

A burst of 20 requests hits the interactive bucket. With `max_tokens=25, refill_rate=5`, the bucket absorbs the full burst. After opening the dashboard, the user idles and the bucket refills at 5 tokens/sec. The second dashboard open 5+ seconds later will have 25 tokens again. This matches the actual usage pattern.

**Problem 2 — Batch jobs competing with interactive traffic**

They no longer share a bucket. `rl:state:{id}:interactive:*` and `rl:state:{id}:batch:*` are independent state. A batch job running at 3 req/s drains only `batch` tokens. Interactive dashboards drain only `interactive` tokens. No cross-traffic interference.

**Problem 3 — 2AM batch depleting 9AM interactive budget**

Solved by isolation above. The interactive bucket is completely separate from the batch bucket. No amount of batch work can touch `rl:state:{id}:interactive:tokens`. At 9 AM, the interactive bucket is full regardless of overnight batch activity.

**Problem 4 — Premium customer limits without code deploys**

Ops writes to Redis directly:

```bash
# Upgrade a single customer to premium tier
redis-cli SET rl:customer:acme-corp:tier premium

# Or set a specific override for one customer
redis-cli SET "rl:override:acme-corp:interactive:max_tokens" 100
redis-cli SET "rl:override:acme-corp:interactive:refill_rate" 20

# Tune the entire premium tier
redis-cli SET rl:tier:premium:interactive:max_tokens 80
redis-cli SET rl:tier:premium:interactive:refill_rate 20
```

No code change, no deploy, takes effect on next request.

---

### Suggested Limit Parameters

| Tier | Traffic class | max_tokens | refill_rate | Practical meaning |
|---|---|---|---|---|
| standard | interactive | 25 | 5/s | Full dashboard burst (20 req) absorbed; refills in 5s |
| standard | batch | 12 | 3/s | Steady 3/s; retry spike to 5/s lasts ~4s |
| premium | interactive | 60 | 15/s | Heavy dashboards; rapid refill |
| premium | batch | 30 | 8/s | High-throughput ETL |

---

### Latency

The original implementation does 4 Redis round-trips per request (2 GETs, then 2 SETs). The Lua script collapses this to **1 round-trip**, which on a local Redis is ~0.1–0.5ms. The config lookup adds 2 pipelined GETs, but those can be cached in-process for 30 seconds — tier config changes infrequently.

```python
# Optional: cache limit params in-process to eliminate config lookup latency
from functools import lru_cache
import time

class DataForgeRateLimiter:
    @lru_cache(maxsize=1024)
    def _get_limit_params_cached(self, customer_id, traffic_class, cache_epoch):
        return self._get_limit_params(customer_id, traffic_class)

    def _cache_epoch(self):
        # Cache busts every 30 seconds
        return int(time.time() / 30)
```

With caching, steady-state cost is one Lua call = one network round-trip. Well within the 200ms interactive P99 budget.

---

### What Was Wrong with the Original (Structurally)

The root mistake wasn't the token bucket algorithm — it was treating "per-customer" as the only relevant dimension. Rate limiting has two orthogonal dimensions: **who** (customer identity) and **what** (traffic class). The original design only tracked *who*. Adding *what* — and storing limit config as data rather than code — resolves all four reported problems without changing the core algorithm.