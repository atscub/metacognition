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

## Response B
## Recommended Architecture: Dual-Class Rate Limiting with Lua-Atomic Token Buckets

The core insight is that you have two fundamentally different contracts: **burst tolerance** for interactive and **throughput guarantee** for batch. These need separate rate limiters, not a single shared one. Three of your four problems disappear the moment you stop sharing quota between traffic classes.

---

## Algorithm Selection

| Traffic class | Algorithm | Reason |
|---|---|---|
| Interactive | Token bucket | Accommodates bursts naturally; idle time refills the bucket for next dashboard load |
| Batch | Token bucket (conservative params) | Accommodates retry spikes; leaky bucket would hard-throttle retries at 5 req/s, causing ETL failures |

Sliding window log is eliminated: memory cost scales with request volume, not client count. At 100 req/s interactive, storing per-request timestamps in Redis becomes expensive fast.

---

## Critical Bug in Current Code: Race Condition

Before anything else — the current implementation has a TOCTOU race. Two concurrent requests both read `tokens=1`, both see `>= 1`, both decrement. You're double-spending tokens. Fix this with a Lua script (atomic on Redis):

```lua
-- scripts/token_bucket.lua
-- KEYS: [tokens_key, ts_key]
-- ARGV: [now, max_tokens, refill_rate, ttl]

local tokens_key, ts_key = KEYS[1], KEYS[2]
local now = tonumber(ARGV[1])
local max_tokens = tonumber(ARGV[2])
local refill_rate = tonumber(ARGV[3])
local ttl = tonumber(ARGV[4])

local tokens = tonumber(redis.call('GET', tokens_key))
local last_ts = tonumber(redis.call('GET', ts_key))

if tokens == nil then tokens = max_tokens end
if last_ts == nil then last_ts = now end

local elapsed = math.max(0, now - last_ts)
tokens = math.min(max_tokens, tokens + elapsed * refill_rate)

if tokens >= 1.0 then
    tokens = tokens - 1.0
    redis.call('SET', tokens_key, tokens)
    redis.call('SET', ts_key, now)
    redis.call('EXPIRE', tokens_key, ttl)
    redis.call('EXPIRE', ts_key, ttl)
    return {1, math.floor(tokens)}   -- allowed, remaining
else
    -- Return seconds until 1 token is available
    local retry_after = math.ceil((1.0 - tokens) / refill_rate)
    return {0, retry_after}          -- denied, retry_after_seconds
end
```

One round-trip. No pipeline read-then-write gap.

---

## Redis Key Design

```
# Rate limit state — short TTL (expire if client goes quiet)
rl:{client_id}:i:tokens        FLOAT   TTL: 3600s   # interactive bucket
rl:{client_id}:i:ts            FLOAT   TTL: 3600s   # interactive last-refill timestamp
rl:{client_id}:b:tokens        FLOAT   TTL: 3600s   # batch bucket
rl:{client_id}:b:ts            FLOAT   TTL: 3600s   # batch last-refill timestamp

# Client configuration — persistent, writable by ops without code deploy
cfg:{client_id}                HASH    no TTL
  i_max        50              # interactive burst capacity
  i_rate       20.0            # interactive tokens/sec refill
  b_max        300             # batch burst capacity (handles retry spikes)
  b_rate       3.0             # batch tokens/sec (~10,800/hour)
  tier         standard

# Tier defaults — fallback when no per-client config exists
cfg:tier:standard              HASH
  i_max 30, i_rate 15.0, b_max 150, b_rate 3.0

cfg:tier:premium               HASH
  i_max 100, i_rate 40.0, b_max 600, b_rate 6.0

cfg:tier:enterprise            HASH
  i_max 500, i_rate 120.0, b_max 2000, b_rate 12.0
```

Ops updates limits: `HSET cfg:{client_id} i_max 200 i_rate 60.0` — no deploy needed.

---

## Implementation

```python
# rate_limiter.py
import redis
import time
import functools
from dataclasses import dataclass
from enum import Enum

class TrafficClass(Enum):
    INTERACTIVE = "i"
    BATCH = "b"

INTERACTIVE_PREFIXES = ('/api/v1/query/', '/api/v1/dashboard/')
BATCH_PREFIXES = ('/api/v1/batch/', '/api/v1/export/')

@dataclass
class LimitConfig:
    max_tokens: float
    refill_rate: float  # tokens per second

@dataclass
class LimitResult:
    allowed: bool
    tokens_remaining: int
    retry_after: int    # seconds, only meaningful when allowed=False

class DataForgeLimiter:
    TIER_DEFAULTS = {
        'standard':   LimitConfig(i_max=30,  i_rate=15.0,  b_max=150,  b_rate=3.0),
        'premium':    LimitConfig(i_max=100, i_rate=40.0,  b_max=600,  b_rate=6.0),
        'enterprise': LimitConfig(i_max=500, i_rate=120.0, b_max=2000, b_rate=12.0),
    }
    TOKEN_BUCKET_TTL = 3600
    CONFIG_CACHE_TTL = 60  # seconds; trade-off: ops changes take up to 60s to propagate

    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self._lua = redis_client.register_script(
            open('scripts/token_bucket.lua').read()
        )
        self._config_cache: dict[str, tuple[float, LimitConfig, LimitConfig]] = {}

    @staticmethod
    def classify(path: str) -> TrafficClass:
        if any(path.startswith(p) for p in INTERACTIVE_PREFIXES):
            return TrafficClass.INTERACTIVE
        if any(path.startswith(p) for p in BATCH_PREFIXES):
            return TrafficClass.BATCH
        return TrafficClass.INTERACTIVE  # default: apply interactive limits

    def _get_config(self, client_id: str) -> tuple[LimitConfig, LimitConfig]:
        """Returns (interactive_config, batch_config). Cached for CONFIG_CACHE_TTL."""
        cached = self._config_cache.get(client_id)
        if cached and (time.time() - cached[0]) < self.CONFIG_CACHE_TTL:
            return cached[1], cached[2]

        raw = self.redis.hgetall(f"cfg:{client_id}")
        if raw:
            tier_defaults = self.TIER_DEFAULTS.get(
                raw.get(b'tier', b'standard').decode(), 
                self.TIER_DEFAULTS['standard']
            )
            i_cfg = LimitConfig(
                max_tokens=float(raw.get(b'i_max', tier_defaults.i_max)),
                refill_rate=float(raw.get(b'i_rate', tier_defaults.i_rate)),
            )
            b_cfg = LimitConfig(
                max_tokens=float(raw.get(b'b_max', tier_defaults.b_max)),
                refill_rate=float(raw.get(b'b_rate', tier_defaults.b_rate)),
            )
        else:
            defaults = self.TIER_DEFAULTS['standard']
            i_cfg = LimitConfig(defaults.i_max, defaults.i_rate)
            b_cfg = LimitConfig(defaults.b_max, defaults.b_rate)

        self._config_cache[client_id] = (time.time(), i_cfg, b_cfg)
        return i_cfg, b_cfg

    def check(self, client_id: str, traffic_class: TrafficClass) -> LimitResult:
        i_cfg, b_cfg = self._get_config(client_id)
        cfg = i_cfg if traffic_class == TrafficClass.INTERACTIVE else b_cfg

        prefix = f"rl:{client_id}:{traffic_class.value}"
        result = self._lua(
            keys=[f"{prefix}:tokens", f"{prefix}:ts"],
            args=[time.time(), cfg.max_tokens, cfg.refill_rate, self.TOKEN_BUCKET_TTL],
        )

        allowed, second_value = int(result[0]), int(result[1])
        if allowed:
            return LimitResult(allowed=True, tokens_remaining=second_value, retry_after=0)
        else:
            return LimitResult(allowed=False, tokens_remaining=0, retry_after=second_value)
```

```python
# app.py (Flask middleware)
limiter = DataForgeLimiter(redis_client)

@app.before_request
def check_rate_limit():
    client_id = get_client_id(request)  # from API key / JWT
    traffic_class = DataForgeLimiter.classify(request.path)
    result = limiter.check(client_id, traffic_class)

    if not result.allowed:
        response = jsonify({
            "error": "rate_limited",
            "traffic_class": traffic_class.value,
            "retry_after": result.retry_after,
        })
        response.status_code = 429
        response.headers['Retry-After'] = str(result.retry_after)
        response.headers['X-RateLimit-Class'] = traffic_class.value
        return response

    # Attach remaining tokens for response headers
    g.rl_remaining = result.tokens_remaining
    g.rl_class = traffic_class.value

@app.after_request
def add_rate_limit_headers(response):
    if hasattr(g, 'rl_remaining'):
        response.headers['X-RateLimit-Remaining'] = g.rl_remaining
        response.headers['X-RateLimit-Class'] = g.rl_class
    return response
```

---

## How Each Problem is Solved

**Problem 1 — Interactive 429s on dashboard load**

With separate interactive bucket, the batch traffic no longer drains tokens that dashboards need. Burst parameters are tuned for the observed pattern: a user firing 20 requests in 2 seconds needs `max_tokens >= 20`. With `i_max=30` and `i_rate=15`, after a 20-request burst ~10 tokens remain and refill at 15/s — the next dashboard load 5 seconds later has a full bucket.

**Problem 2 — Batch competes with interactive**

Fully separate key namespaces: `rl:{id}:i:*` vs `rl:{id}:b:*`. The token pools are independent. Batch retries spiking to 5 req/s (vs 3 sustained) burn through `b_max=300` tokens rather than interactive quota. At `b_rate=3.0`, the bucket refills to accommodate the 3 req/s steady state baseline.

**Problem 3 — 2 AM batch depletes 9 AM interactive quota**

Impossible with separate buckets. The enterprise batch export drains `rl:{id}:b:tokens` to zero at 2 AM. The interactive bucket `rl:{id}:i:tokens` is completely untouched. At 9 AM, the interactive bucket has been refilling for 7 hours and is at full capacity.

**Problem 4 — Dynamic limits for premium customers**

```bash
# Give enterprise customer higher interactive burst (no deploy):
redis-cli HSET cfg:acme-corp i_max 500 i_rate 120.0 tier enterprise

# Temporarily boost a customer during a migration:
redis-cli HSET cfg:startup-x b_max 2000 b_rate 10.0
```

Changes propagate within `CONFIG_CACHE_TTL` (60 seconds by default, tunable). No restart, no deploy.

---

## Parameter Tuning Reference

| Tier | Interactive burst | Interactive refill | Batch burst | Batch refill | Batch capacity/hour |
|---|---|---|---|---|---|
| Standard | 30 tokens | 15/s | 150 tokens | 3.0/s | 10,800 |
| Premium | 100 tokens | 40/s | 600 tokens | 6.0/s | 21,600 |
| Enterprise | 500 tokens | 120/s | 2,000 tokens | 12.0/s | 43,200 |

Batch burst headroom (`b_max`) is set to ~50x the per-second rate to absorb retry storms without triggering 429s. At `b_rate=3.0`, a 5 req/s retry spike burns `(5-3) * duration` extra tokens — the headroom covers several minutes of elevated retries before throttling.

---

## What This Does Not Cover

- **Per-endpoint limits**: If a single expensive endpoint (e.g., `/api/v1/export/full-dump`) needs tighter limits, add a third key dimension: `rl:{client_id}:{class}:{endpoint_group}:tokens`. Add only if needed — the classification overhead is real.
- **Global capacity limits**: If total system load matters (not just per-client), add a global key `rl:global:i:tokens` checked in parallel with the per-client check. Return 429 if either fails.
- **Redis HA**: If Redis goes down, you need a decision: fail open (allow all) or fail closed (deny all). For an API, fail open with a logged alert is typically correct — a Redis outage shouldn't take down the API entirely.

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
