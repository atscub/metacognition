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