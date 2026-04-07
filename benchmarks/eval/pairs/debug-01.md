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

## Response B
## Applying Socratic Mode First

Before presenting a hypothesis, let me explicitly stress-test the ops team's framing.

**The ops team's hypothesis:** Deploys cause the latency spikes.

**What makes me suspicious of that framing immediately:**

> *Authority bias alert* — the ops team has a confident narrative backed by "perfect" correlation. Perfect correlations in production incidents are often a sign that two independent events share a schedule, not a causal link.

Let me apply the Socratic checklist before going further.

---

## The Analysis

### 1. What am I assuming?

The ops team is assuming *correlation implies causation* here. Their evidence: every spike lines up with a deploy. But let me ask — **what else lines up with the deploys?**

Looking at the deploy timestamps: all three start at `02:12` UTC. Deploys happen in a maintenance window, around 02:00–02:30 UTC. Now look at the crontab:

```
0 2 * * 1,4,0   /opt/scripts/warm-cache.sh --flush-first --rebuild
```

This runs at **02:00 UTC on Sundays, Mondays, and Thursdays**. March 23 is a Monday — that's a direct overlap. But March 20 and 27 are Fridays, so the cron doesn't fire those days. I'll come back to this.

### 2. What would disprove the "deploy causes spike" theory?

The strongest disconfirming evidence is already in the data:

- **The deploy takes 39 seconds. The spike lasts ~15–30 minutes.** A rolling restart that finishes at 02:12:42 cannot directly cause elevated latency that persists until 02:30.
- **Scaling to 6 replicas made no difference.** If the rolling restart itself caused a capacity shortfall (one pod down at a time), doubling replicas would have reduced the spike. It didn't. This rules out the capacity explanation almost entirely.

This means the deploy is at best a *trigger* for something else, not the direct cause.

### 3. What else could explain the symptoms?

**The spike duration (~15–30 min) and the "more pods didn't help" observation point to one thing: a cold Redis cache.**

Here's the mechanism:

```
warm_on_start: false     ← pods do NOT pre-warm cache on startup
--flush-first            ← cron flushes Redis before rebuilding
```

When Redis is flushed (all keys gone), *every single request* is a cache miss and hits the database directly. Adding more pods makes this *worse* — more pods, more concurrent cache-miss requests hammering the DB. This exactly matches the observed behavior.

**Why does it resolve in ~15–30 minutes?** Because the cache rebuilds organically as requests come in. Once enough hot keys are re-cached, latency recovers. The TTL is 1 hour, so nothing expires during the spike window — the issue is entirely about cold-start, not expiry.

### 4. The Two-Culprit Hypothesis

There are likely **two separate flush events**, and deploys share a maintenance window with the cache warm cron:

| Date | Day | Cron at 02:00? | Deploy at 02:12? | Result |
|------|-----|----------------|------------------|--------|
| Mar 20 | Fri | No | Yes | Spike |
| Mar 23 | Mon | **Yes** | Yes | Spike |
| Mar 27 | Fri | No | Yes | Spike |

Since all three show spikes — including Fridays when the cron doesn't run — the **deploy pipeline itself is likely also flushing Redis**, probably as a "cache bust on deploy" step in the deployment script. The cron with `--flush-first --rebuild` is doing the *right* thing (flush then immediately rebuild). The deploy is probably doing `--flush-first` without the rebuild.

The cron on March 23 explains why that spike might be slightly higher (3,120ms) — a double-flush, or the cache was already partially flushed at 02:00 before the deploy hit at 02:12.

### 5. What should be investigated to confirm?

**High priority — look for these immediately:**

1. **Read the deploy pipeline scripts** — look for any `FLUSHALL`, `FLUSHDB`, `redis-cli flush`, or cache invalidation calls that run during deploy steps.
2. **Check if the 02:00 Datadog reading truly represents the 01:45–02:00 window** — if Datadog p99 is trailing-window, a cache flush at exactly 02:00 would appear in the 02:15 reading, making the cron the true trigger even on non-flush-cron days if the deploy doesn't flush.
3. **Look at database query rate during the spike window** — if this theory is right, you'll see DB query volume spike 10–20x at 02:12 (or 02:00 on cron days).
4. **Check Redis cache hit rate in the same window** — you should see it drop to near zero.

### 6. Why halting deployments is the wrong fix

The ops team is trying to eliminate the *correlated* variable (deploys), not the *causal* variable (cold cache). Even if they halted deploys:
- The cron-triggered cold start on Mon/Thu/Sun would still cause spikes at 02:00
- The problem returns the moment they resume deploying

---

## Root Cause (Medium-High Confidence)

**The Redis cache is being flushed during or immediately before deploys, with no cache pre-warming step. The resulting cache stampede sends every request to the database cold for 15–30 minutes until the cache rebuilds organically. Pod count is irrelevant because the bottleneck is downstream of all pods.**

The deploy itself (rolling restart, graceful drain) is not the problem. The problem is a side effect in the deploy pipeline.

---

## Recommended Investigation Steps

1. `grep -r "flush\|FLUSH\|invalidat" /path/to/deploy-pipeline/` — find the cache flush call
2. Check Datadog: plot *Redis cache hit rate* and *DB query rate* on the same timeline as these incidents
3. Check Redis `INFO stats` snapshots or slow log from around 02:00–02:30 on those dates

## If Cache Flush Is Confirmed, the Fix Is:

```yaml
# Option A: warm on pod start
cache:
  warm_on_start: true    # pre-warm before pod goes healthy

# Option B: don't flush during deploys — use key versioning instead
# cache:v2:user:123 (new deploy uses new namespace, old keys expire naturally)

# Option C: add a pre-deploy warm step
# [02:12:00] pre-warm new cache namespace
# [02:12:30] begin rolling restart (new pods hit warm cache)
```

**Do not halt deployments.** Fix the cache cold-start. The deploy pipeline is innocent on the restart side — it's the cache management that needs work.

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
