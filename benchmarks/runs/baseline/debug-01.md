## The deploy is not the cause — it's a scheduling coincidence.

The latency spikes are almost certainly caused by the **Redis cache being flushed cold** right before the deploy window.

### The smoking gun

Look at the crontab:
```
0 2 * * 1,4,0   /opt/scripts/warm-cache.sh --flush-first --rebuild
```

This runs at **02:00 UTC** — the same low-traffic window the team chose for deploys. The `--flush-first` flag explicitly nukes the cache before rebuilding it. During the rebuild, every request is a cache miss and hits the origin/database directly.

Cross-reference the timeline:
- `02:00` — cron fires, cache flushed. p99 still looks OK (the 02:00 Datadog reading was captured *before* traffic degraded).
- `02:12` — deploy starts (pods draining, restarting).
- `02:15` — Datadog interval captures the spike: cache is cold, rebuild still running. p99 blows up to ~3,000ms.
- `02:30` — cache partially rebuilt, p99 falls to ~380ms.
- `02:45` — cache fully warm again, p99 back to ~200ms.

The deploy and the cache flush are **both scheduled in the same maintenance window**. They always co-occur, which makes them look causally linked when they're not.

### Why the other evidence confirms this

| Observation | If deploy caused it | If cache flush caused it |
|---|---|---|
| Spike lasts ~15 minutes | Rolling restart took 39s — doesn't fit | Cache rebuild time — fits |
| Scaling to 6 pods didn't help | More pods = less load per pod, should help | Cache miss affects all pods equally — no improvement expected |
| `warm_on_start: false` | Irrelevant | New pods get no local pre-warming, amplifies cold-cache load |

A rolling update that gracefully drains connections and passes readiness probes in 39 seconds has no mechanism to cause 15 minutes of elevated p99. But a cache flush that empties 3,600 seconds worth of TTL in one shot does.

### The fix

**Do not halt deployments.** Instead:

1. **Remove `--flush-first` from the cron job**, or replace it with a swap strategy (build new cache entries alongside old ones, then atomically cut over).
2. **Separate the maintenance windows** so the cache warm job doesn't run within 20 minutes of a scheduled deploy.
3. **Verify**: run a deploy on a day/time when the warm-cache cron is not scheduled — if the spike disappears, you have confirmation.

The deploy pipeline is clean. The cache eviction strategy is the problem.