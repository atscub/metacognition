## The deploy is not the root cause

The ops team has made a classic correlation/causation error. Here's why, and what's actually happening.

---

### The deploy can't explain 15 minutes of elevated latency

The deploy log is unambiguous:

```
[02:12:03] Starting rolling deploy
[02:12:42] Rolling deploy complete. Total time: 39s
```

A 39-second event does not cause a 15-minute spike. And the team already ran the critical experiment: **scaling to 6 replicas had zero effect.** If the problem were rolling-restart capacity (2 of 3 pods unavailable briefly), doubling the pod count would have reduced it. It didn't. That rules out the deploy mechanism entirely.

---

### The actual culprit: the cache flush cron

Look at the crontab:

```
0 2 * * 1,4,0   /opt/scripts/warm-cache.sh --flush-first --rebuild
```

This runs at **02:00 UTC** — exactly 12 minutes before every deployment in your logs. The `--flush-first` flag **nukes the entire Redis cache** before rebuilding. Combined with this:

```yaml
warm_on_start: false
```

...you get a perfect storm:

```
02:00:00  warm-cache.sh --flush-first fires
          → Redis cache wiped clean
          → --rebuild begins (cache is repopulating, but this takes time)

02:00–02:15  All requests are cache misses → every query hits the database cold
             → p99 latency spikes 10–15x

02:12  Rolling deploy happens (completely coincidental timing)
       → ops team sees deploy + spike, concludes causation

02:30–02:45  Cache has warmed organically through traffic
             → latency returns to baseline
```

The 15-minute recovery window is exactly how long it takes for a cold Redis cache to warm back up to steady-state hit rates under production traffic — not a pod restart recovery.

---

### Why scaling to 6 replicas didn't help

More pods all share the same cold Redis cache. Adding pods increases the *rate* of cache-miss requests hitting your database, which could actually make things marginally worse. The bottleneck is the database under cache-miss load, not pod capacity.

---

### The suspicious timing is likely intentional (and backfiring)

The deployment schedule (02:12) is almost certainly *deliberately* placed 12 minutes after the cache warm job (02:00), probably with the reasoning: "let's deploy after the cache has been refreshed so we start with a clean slate." The problem is `--flush-first` makes the cache *worse* during the rebuild window, not better.

---

### What to actually fix

**Immediate (stop the bleeding):**
- Remove `--flush-first` from the cron. Let the TTL (3600s) expire keys naturally. The `--rebuild` alone will refresh stale entries without creating a thundering herd on the database.

**Proper fix:**
- Enable `warm_on_start: true` so new pods pre-warm before taking traffic. Combined with your readiness probe, pods won't enter rotation until they have a warm cache.

**Or, if you need periodic full flushes:**
- Separate the flush from peak-traffic or deploy windows
- Implement a gradual eviction strategy rather than wiping the entire keyspace at once

---

### Tell the ops team

Do not halt deployments. The deploy pipeline is innocent. Removing `--flush-first` from the cron should eliminate the spikes entirely. You can verify by running the next deploy without that flag and watching the 02:15 p99 in Datadog.