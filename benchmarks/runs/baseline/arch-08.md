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