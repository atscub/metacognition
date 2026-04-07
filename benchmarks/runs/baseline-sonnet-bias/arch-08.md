## Recommended Architecture: Dual-Algorithm Per-Traffic-Type Limiting

The root cause of all four problems is a single shared bucket across fundamentally incompatible traffic patterns. The fix isn't a better algorithm — it's correct separation of concerns.

---

## Design Overview

```
Request arrives
     │
     ├── /api/v1/query/*, /api/v1/dashboard/*
     │        └── Interactive limiter: Token Bucket
     │                 (burst-tolerant, per-client, short TTL)
     │
     └── /api/v1/batch/*, /api/v1/export/*
              └── Batch limiter: Sliding Window Counter
                       (throughput-enforcing, per-client-per-minute)

Both read limits from: rate:config:{client_id}  ← ops-editable
```

---

## Algorithm Selection

### Interactive traffic → Token Bucket (keep, fix parameters)

Token bucket is correct for bursty traffic. The current implementation has wrong parameters and a race condition, not a wrong algorithm.

- A dashboard opening 15 requests at once should burn through burst capacity and succeed, then refill over the next few seconds. That's exactly what token buckets do.
- Leaky bucket would serialize those 15 requests, adding queuing latency — incompatible with the P99 < 200ms requirement.
- Sliding window log stores every request timestamp in memory — prohibitively expensive at 100 req/s.

Fix the parameters:
```python
# Before: max_tokens=100, refill_rate=10  (bucket is huge, refills slowly)
# After:  max_tokens=30,  refill_rate=15  (smaller burst cap, refills in 2s)
```

30 tokens absorbs a 20-request dashboard burst. At 15/s refill, the bucket recovers in 2 seconds — not 5-10 seconds as currently reported.

### Batch traffic → Sliding Window Counter (per-minute)

Batch traffic is steady and throughput-sensitive, not burst-sensitive. A per-minute counter:
- Enforces `N requests/minute` with ~1-minute granularity — exactly what ETL pipelines need
- Handles retry spikes: if a job spikes to 5 req/s for 10 seconds that's 50 requests; within a 200-request/minute limit, this is fine
- No memory overhead from storing individual timestamps (unlike sliding window log)
- Simple to audit: ops can inspect `KEYS rate:batch:{client}:*` and see exactly what was consumed

---

## Redis Key Design

```
# Interactive: token bucket state
rate:interactive:{client_id}           Hash  {tokens: float, last_refill: float}
TTL: 3600s (auto-expire idle sessions, ensures fresh bucket at morning login)

# Batch: sliding window counter (two active windows at once for smooth rollover)
rate:batch:{client_id}:{unix_minute}   String  (integer count)
TTL: 120s

# Client config (ops-editable without code deploy)
rate:config:{client_id}                Hash  {
    interactive_max_tokens: int,        # burst capacity
    interactive_refill_rate: float,     # tokens/second
    batch_per_minute: int,              # max batch requests/minute
    tier: str                           # "standard" | "premium" | "enterprise"
}
TTL: none

# Tier defaults (fallback when no per-client config)
rate:tier:standard                     Hash  {same fields}
rate:tier:premium                      Hash  {same fields}
rate:tier:enterprise                   Hash  {same fields}
```

Config lookup order: per-client hash → tier hash → hardcoded default. Ops updates a Redis hash; no deployment needed.

---

## Implementation

The current code has a critical race condition: read tokens → compute → write tokens is not atomic. Two simultaneous requests can both read the same token count, both see `tokens >= 1`, and both succeed. Fix with a Lua script executed atomically on Redis.

```python
# rate_limiter.py

INTERACTIVE_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local max_tokens = tonumber(ARGV[2])
local refill_rate = tonumber(ARGV[3])

local data = redis.call('HMGET', key, 'tokens', 'last_refill')
local tokens = tonumber(data[1]) or max_tokens
local last_refill = tonumber(data[2]) or now

local elapsed = now - last_refill
tokens = math.min(max_tokens, tokens + elapsed * refill_rate)

if tokens >= 1 then
    tokens = tokens - 1
    redis.call('HMSET', key, 'tokens', tokens, 'last_refill', now)
    redis.call('EXPIRE', key, 3600)
    return 1
end
return 0
"""

BATCH_LUA = """
local key = KEYS[1]
local limit = tonumber(ARGV[1])

local count = redis.call('INCR', key)
if count == 1 then
    redis.call('EXPIRE', key, 120)
end
if count <= limit then
    return 1
end
return 0
"""

class DataForgeLimiter:
    def __init__(self, redis_client):
        self.redis = redis_client
        self._interactive_script = redis_client.register_script(INTERACTIVE_LUA)
        self._batch_script = redis_client.register_script(BATCH_LUA)

    def _get_config(self, client_id: str) -> dict:
        config = self.redis.hgetall(f"rate:config:{client_id}")
        if not config:
            tier = "standard"
            config = self.redis.hgetall(f"rate:tier:{tier}") or {}
        return {
            "interactive_max_tokens": int(config.get("interactive_max_tokens", 30)),
            "interactive_refill_rate": float(config.get("interactive_refill_rate", 15)),
            "batch_per_minute": int(config.get("batch_per_minute", 200)),
        }

    def allow_interactive(self, client_id: str) -> bool:
        config = self._get_config(client_id)
        result = self._interactive_script(
            keys=[f"rate:interactive:{client_id}"],
            args=[time.time(), config["interactive_max_tokens"], config["interactive_refill_rate"]],
        )
        return bool(result)

    def allow_batch(self, client_id: str) -> bool:
        config = self._get_config(client_id)
        minute_bucket = int(time.time() // 60)
        result = self._batch_script(
            keys=[f"rate:batch:{client_id}:{minute_bucket}"],
            args=[config["batch_per_minute"]],
        )
        return bool(result)


INTERACTIVE_PREFIXES = ("/api/v1/query/", "/api/v1/dashboard/")
BATCH_PREFIXES = ("/api/v1/batch/", "/api/v1/export/")

@app.before_request
def check_rate_limit():
    client_id = get_client_id(request)
    path = request.path

    if path.startswith(INTERACTIVE_PREFIXES):
        if not limiter.allow_interactive(client_id):
            return jsonify({"error": "Rate limited", "type": "interactive"}), 429

    elif path.startswith(BATCH_PREFIXES):
        if not limiter.allow_batch(client_id):
            return jsonify({"error": "Rate limited", "type": "batch"}), 429
```

---

## How Each Problem Is Resolved

**Problem 1: Dashboard 429s during bursts.**
`max_tokens=30, refill_rate=15` absorbs a 20-request dashboard burst and refills in ~2 seconds. Before: `refill_rate=10` meant 10 second recovery. Now it's 2 seconds. If even this is too long, increase `max_tokens` for premium tiers without touching code.

**Problem 2: Batch competes with interactive traffic.**
Completely separate keys. A batch job draining `rate:batch:{client}:*` has zero effect on `rate:interactive:{client}`. They don't share tokens.

**Problem 3: 2 AM batch depletes 9 AM interactive bucket.**
Impossible with separate buckets. The interactive bucket has `TTL: 3600s` — if a client is idle for an hour (as they would be overnight), the key expires and the bucket starts fresh at `max_tokens` when the first morning request arrives. No bleed-over.

**Problem 4: Premium limits without code deploys.**
```bash
# Ops sets premium limits directly in Redis:
redis-cli HSET rate:config:enterprise-acme-corp \
    interactive_max_tokens 100 \
    interactive_refill_rate 50 \
    batch_per_minute 600

# Or update the tier defaults affecting all premium customers:
redis-cli HSET rate:tier:premium interactive_max_tokens 60
```
Takes effect on the next request. No deployment.

---

## Defaults by Tier

| Tier | Interactive max_tokens | Interactive refill/s | Batch per minute |
|------|----------------------|---------------------|-----------------|
| standard | 30 | 15 | 200 |
| premium | 60 | 30 | 400 |
| enterprise | 100 | 50 | 600 |

These map to: standard gets ~10,000 batch req/hour, premium 24,000, enterprise 36,000. The stated requirement of 10,000/hour is met at the standard tier.

---

## What to Watch Out For

**Config read latency.** `_get_config` currently does a Redis round-trip on every request. At 100 interactive req/s this is an extra 100 reads/second. Add a local TTL-60s LRU cache keyed on `client_id` — config changes take up to 60 seconds to propagate, which is acceptable for limit changes.

**Smooth sliding window rollover.** The batch counter resets hard at the minute boundary. A client using 190/200 requests in minute N can burst 200 more at the start of minute N+1. If this matters, implement a true sliding window: weight the previous minute's count by `(60 - elapsed_seconds) / 60` and add to the current count. Adds one more Redis read but eliminates the boundary exploit.

**The Lua scripts assume Redis single-node or same slot.** If you're on Redis Cluster, ensure `rate:interactive:{client_id}` and `rate:config:{client_id}` hash to the same slot using hash tags: `rate:interactive:{client_id}` naturally handles this since the curly-brace portion is the slot key.