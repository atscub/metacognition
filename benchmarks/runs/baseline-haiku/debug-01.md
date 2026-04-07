Looking at this data, I can identify the root cause—and it's **not** the deployment process itself, but rather how your application handles startup.

## Root Cause: Cold Cache Thundering Herd

Here's what's actually happening:

1. **Rolling deploy triggers pod restarts** at 02:12:03 through 02:12:42
2. **Each new pod starts with an empty cache** (`warm_on_start: false` in your config)
3. **Readiness probe passes quickly** (~8 seconds), traffic starts immediately
4. **All three pods restart within ~39 seconds of each other**, so all three hit the cache simultaneously
5. **This creates a thundering herd**: 3 pods × cold caches = massive backend query spike
6. **The latency spike persists for 15 minutes** while the Redis cache gradually rebuilds

The deploy *itself* completes in 39 seconds with proper draining, but the **cache cold-start** creates a cascading degradation that lasts much longer.

### Why the ops team's observations are misleading:

- ✅ The spike *does* align with deploys (causation exists)
- ❌ But the root cause is **pod startup behavior**, not the rolling-update logic
- ❌ Scaling to 6 replicas didn't help because it still restarted all 6 pods with cold caches
- ❌ The cache warming script at 02:00 UTC doesn't help because the deploy at 02:15 immediately invalidates it

## The Fix

Change this in your application config:

```yaml
cache:
  provider: redis
  cluster: redis-prod.internal:6379
  ttl: 3600
  warm_on_start: true  # ← THIS IS THE FIX
```

This makes each pod pre-populate its cache during the initialization phase (after `/healthz` passes but *before* accepting production traffic) instead of serving cache misses.

### Why this works:

- New pods warm their caches while connections are still being drained from old pods
- Traffic switches to pre-warmed pods instead of cold ones
- No thundering herd of backend queries
- Deploys become transient blips instead of 15-minute latency events

### Secondary recommendation:

If you want to be more defensive, adjust your readiness probe:

```yaml
readinessProbe:
  httpGet:
    path: /healthz
    port: 8080
  initialDelaySeconds: 10  # Give the warmup more time
  periodSeconds: 3
```

Give the cache warm-up a few extra seconds before declaring readiness.

---

**Bottom line**: Your deployment process is working correctly. The infrastructure is fine. The problem is that your application assumes the cache will be warm when it starts serving traffic—and rolling deployments violate that assumption.