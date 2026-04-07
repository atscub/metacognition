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