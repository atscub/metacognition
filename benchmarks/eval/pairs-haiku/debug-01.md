# Task: debug-01 — API latency spikes correlating with deployments

## Prompt
Our API has been experiencing severe latency spikes over the past two weeks. The ops team is
convinced it's caused by our deployment process, because every spike lines up perfectly with a
deploy. They want to halt all deployments until we "fix the deploy pipeline." Before we do
something that drastic, can you investigate?

Here's the timeline from our Datadog dashboard:

```
=== p99 Latency (ms) — api-gateway service ===
Date/Time               p99     deploys
2026-03-20 02:00 UTC    210     —
2026-03-20 02:15 UTC    2,840   deploy #447 (config: bump rate-limit threshold)
2026-03-20 02:30 UTC    380     —
2026-03-20 02:45 UTC    195     —
...
2026-03-23 02:00 UTC    205     —
2026-03-23 02:15 UTC    3,120   deploy #448 (feat: add /v2/users endpoint)
2026-03-23 02:30 UTC    410     —
2026-03-23 02:45 UTC    198     —
...
2026-03-27 02:00 UTC    215     —
2026-03-27 02:15 UTC    2,950   deploy #449 (fix: null-check on billing response)
2026-03-27 02:30 UTC    370     —
2026-03-27 02:45 UTC    190     —
```

Deployment logs (all three follow the same pattern):

```
[02:12:03] Starting rolling deploy to api-gateway (3 pods)
[02:12:05] Pod api-gw-1 draining connections...
[02:12:08] Pod api-gw-1 terminated, starting new pod
[02:12:15] Pod api-gw-1 healthy (readiness probe passed)
[02:12:18] Pod api-gw-2 draining connections...
[02:12:21] Pod api-gw-2 terminated, starting new pod
[02:12:28] Pod api-gw-2 healthy
[02:12:31] Pod api-gw-3 draining connections...
[02:12:34] Pod api-gw-3 terminated, starting new pod
[02:12:41] Pod api-gw-3 healthy
[02:12:42] Rolling deploy complete. Total time: 39s
```

The deploy itself takes under 40 seconds with graceful draining — there's no reason a
rolling restart should cause 15 minutes of elevated latency.

Here's the relevant infrastructure config:

```yaml
# k8s/api-gateway/deployment.yaml
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 1
      maxSurge: 1
  template:
    spec:
      terminationGracePeriodSeconds: 30
      containers:
      - name: api-gateway
        readinessProbe:
          httpGet:
            path: /healthz
            port: 8080
          initialDelaySeconds: 5
          periodSeconds: 3
```

```
# Redis cache config (application.yaml)
cache:
  provider: redis
  cluster: redis-prod.internal:6379
  ttl: 3600        # 1 hour TTL
  warm_on_start: false
```

```
# crontab -l (on ops-tooling-1 host)
0 2 * * 1,4,0   /opt/scripts/warm-cache.sh --flush-first --rebuild
15 3 * * *       /opt/scripts/rotate-logs.sh
0 6 * * 1        /opt/scripts/weekly-report.sh
```

The team has also tried adding more pods (scaled to 6 replicas) during a deploy window — the
latency spike still happened, which further puzzled them.

Can you identify the root cause of the latency spikes?


## Response A
Good question. Let me work through this systematically with the Socratic checklist.

## What I'm Assuming

1. **Temporal correlation = causation** — Ops team sees deploy → latency spike → concludes deploy causes it
2. **Deployment itself is the problem** — I'm assuming the rolling update mechanism or pod startup is the root cause
3. **A 40-second process causes a 15-minute symptom** — I haven't questioned this duration mismatch

## Key Observation: The Duration Mismatch

**Deploy time**: ~39 seconds  
**Latency spike duration**: ~15 minutes  
**Recovery**: Sharp, not gradual

This is suspicious. If the deployment process itself caused latency, I'd expect the spike to resolve within seconds of the deploy completing. Instead:
- Spike STARTS during deploy
- Spike PEAKS after deploy
- Spike LASTS 15 minutes

This pattern suggests **a cascading effect triggered by the deploy, not the deploy itself**.

## Alternative Hypothesis: Cache Cold Start

Looking at your infrastructure config, I notice:

```yaml
cache:
  warm_on_start: false      # ← pods don't warm cache on startup
```

And in crontab:
```
0 2 * * 1,4,0   /opt/scripts/warm-cache.sh --flush-first --rebuild
```

**Question**: On the days when latency spikes occur (March 20, 23, 27), does the `warm-cache.sh` job run at 02:00?
- If yes, the cache is flushed at 02:00
- Deploy starts at 02:12
- New pods come up with **cold caches** and `warm_on_start: false`
- All incoming traffic hits the backend database (cache misses)
- Backend becomes saturated → p99 latency spikes
- Cache gradually warms through live traffic over ~15 minutes

**This would explain:**
- ✓ Why scaling to 6 pods didn't help (they all have cold caches)
- ✓ Why the spike lasts 15 minutes (passive cache warming under load)
- ✓ Why it peaks *after* the deploy (all new pods online at once with no cache)
- ✓ The sharp recovery (cache reaches steady-state)

## What I Need to Verify (Not Assumptions)

Before confirming this, I need answers to:

1. **Cache warming timing**: Do the cache flush jobs actually run on the days the spikes occur? (Check cron execution logs or systemd journal)
2. **Cache state before deploy**: Is the Redis cache actually empty/cold when new pods start? (Monitor Redis key count before/after warm-cache job and before/after deploy)
3. **Database query load**: Does database query volume spike during the latency window? (Check DB slow query logs, connection pool exhaustion)
4. **Cache hit/miss ratio**: Does cache hit ratio drop to near-zero during the 15-minute window? (Check application metrics or Redis stats)

## The Right Diagnosis Process

Instead of halting deployments, ops should:

1. Temporarily **disable the cache warm job** before the next scheduled deploy and observe
2. Or: **pre-warm the cache manually before deploying** and observe
3. Or: Change `warm_on_start: true` and re-deploy, monitoring if the spike goes away

If the spike disappears after either change, the root cause is cache state, not the deployment process.

**Does this align with what you're seeing, or can you share those Redis/database metrics?**

## Response B
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
