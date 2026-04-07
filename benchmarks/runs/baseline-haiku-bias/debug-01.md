Looking at this data, I can identify the root cause—and it's **not** the deployment process itself. Let me walk through the evidence:

## The Smoking Gun: Cache Cold-Starts

Your application config has this critical setting:

```yaml
cache:
  provider: redis
  warm_on_start: false  # ← THIS IS THE PROBLEM
```

When each pod restarts during a rolling deploy:
1. Old pod drains and terminates (clean)
2. New pod starts with an **empty cache**
3. New pod serves requests against a cold cache → **cache misses** → database hits → latency spike
4. Cache gradually warms as requests populate it (~15 minutes for a 3600s TTL to stabilize)

This explains **all** your observations:

| Observation | Root Cause |
|---|---|
| Spikes last ~15 min | Time needed for cache to naturally warm via incoming traffic |
| Perfect correlation with deploys | Each deploy restarts all 3 pods sequentially; pods 2 & 3 restart while 1 is still warming |
| Scaling to 6 replicas didn't help | You just created more cold caches warming in parallel—the aggregate latency impact stayed the same |
| Deploy logs look fine | The deploy **is** fine; the problem is what happens **after** the pod starts, not during the restart |

## The Confirmation: Your Crontab

```
0 2 * * 1,4,0   /opt/scripts/warm-cache.sh --flush-first --rebuild
```

This exists for a reason—it's evidence that cache warming is already a known operational concern in your system. But it only runs 3 days a week, leaving most deploys without pre-warmed caches.

## The Fix (Ranked by Impact)

**Highest Priority:**
```yaml
cache:
  warm_on_start: true  # Pre-populate cache on pod startup
```

This is the complete fix. Pods start with warm caches, eliminating cold-start latency entirely.

**Secondary improvements:**
- Add a pre-cache-warming script to your pod startup (if `warm_on_start` isn't available)
- Adjust `maxSurge: 1` to restart fewer pods concurrently if you need a staged rollout
- Consider making `warm-cache.sh` run before **every** deploy, not just 3x/week

**Do NOT:**
- Halt deployments (the deploy isn't the problem; the cache strategy is)
- Add more pods (doesn't solve the cold-start issue)
- Increase readiness probe delays (pods are actually healthy; latency is from cold cache, not pod readiness)

The ops team's correlation is correct—deploys do cause spikes—but they've confused correlation with causation. The spike comes from cache cold-starts during the deploy, not from the deployment orchestration itself.