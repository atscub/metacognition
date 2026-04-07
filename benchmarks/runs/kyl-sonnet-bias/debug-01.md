## Applying Epistemic Humility Before Diagnosing

Let me work through the Socratic checklist before accepting the ops team's framing.

---

### 1. Challenge the Premise: Is the deploy actually *causing* the spikes?

The ops team's reasoning is: **deploy → spike, therefore deploy causes spike.**

That's a classic post hoc fallacy. Before accepting it, I need to ask: **what else could correlate with deploys at 02:12 UTC?**

Let me examine the full evidence set without anchoring on the deploy hypothesis.

---

### 2. What Does the Evidence Actually Show?

**What supports "deploy is the cause":**
- 3/3 spikes co-occur with deploys. Correlation is perfect.

**What *contradicts* "deploy mechanics are the cause":**

| Observation | What It Rules Out |
|---|---|
| Spike lasts ~15 minutes, deploy takes 39 seconds | Pod drain/terminate/restart mechanics can't explain 15 minutes of latency |
| Scaling to 6 replicas didn't reduce the spike | Not a capacity problem during rolling restart |
| With `maxUnavailable: 1` on 3 replicas, 67% capacity is always available | Traffic load per pod only increases ~50% — insufficient to cause 10-15x latency |
| Spike self-resolves cleanly every time | No persistent damage from the deploy itself |

The deploy mechanics are almost certainly **not** the root cause. Something else that *co-occurs* with deploys is.

---

### 3. Actively Search for Disconfirming Evidence — What Else Happens at 02:00-02:15 UTC?

Now I look at everything in the data I was given, not just the deploy logs.

The crontab on `ops-tooling-1`:

```
0 2 * * 1,4,0   /opt/scripts/warm-cache.sh --flush-first --rebuild
15 3 * * *       /opt/scripts/rotate-logs.sh
```

**`warm-cache.sh --flush-first --rebuild` runs at 02:00 UTC on Sundays, Mondays, and Thursdays.**

And in `application.yaml`:
```yaml
cache:
  provider: redis
  ttl: 3600
  warm_on_start: false   # ← THIS
```

---

### 4. The Root Cause: Two Compounding Factors

**Primary cause (all three events):** `warm_on_start: false`

A rolling deploy replaces all 3 pods within 39 seconds. Every pod starts with a **cold in-process cache**. With `warm_on_start: false`, they make no attempt to pre-populate from Redis on startup. For the next ~15 minutes, every request that would have been an in-process cache hit now falls through to Redis — and potentially to the database if Redis also misses. This is a **cache miss storm** that resolves organically as traffic naturally repopulates the cache.

This explains why **6 replicas didn't help:** 6 cold pods is just 6 pods simultaneously hammering Redis and the database instead of 3. More replicas with cold caches is not a fix — it may actually be worse.

**Contributing factor (March 23 only — the largest spike at 3,120ms):**

March 23 is a **Monday**. The warm-cache script runs at **02:00** that day, with `--flush-first` — meaning it **explicitly flushes Redis** before rebuilding it. By 02:12 when the deploy starts, Redis has only had 12 minutes to rebuild from scratch. The deploy then cold-starts all pods simultaneously.

Result: cold in-process caches *and* a partially-rebuilt Redis cache = the worst-case spike (3,120ms vs. ~2,900ms on the Fridays when Redis was warm).

March 20 and March 27 are Fridays — the warm-cache script doesn't run, Redis stays warm, but the in-process cache cold-start still causes a significant spike.

---

### 5. Confidence Assessment

| Claim | Confidence | Basis |
|---|---|---|
| Deploy mechanics (39s restart) aren't the direct cause | **High** | 15-min spike duration, more-replicas-no-help, math on capacity |
| `warm_on_start: false` causes cold-start miss storm | **High** | Explicit config, consistent with all 3 events, explains duration |
| March 23 spike is larger because of Redis flush | **Medium** | Cron schedule matches, `--flush-first` flag is explicit — but I can't see how long the rebuild takes |
| 15-minute warm-up duration | **Medium** | Consistent across events, but I don't know the application's cache access patterns |

---

### 6. The Ops Team's Causal Error

They observed:
> deploy at 02:12 → spike at 02:15 → resolved by 02:30-02:45

And concluded: **fix the deploy pipeline.**

The actual chain is:
> deploy replaces all pods → all pods cold-start with `warm_on_start: false` → in-process cache is empty across all pods → 15 minutes of miss storms → cache fills organically → normal latency resumes

The deploy is a **trigger**, not the **mechanism**. Halting deployments would stop the spikes temporarily, but any future deploy — or any rolling restart for any reason — would reproduce them.

---

### Recommended Fix

**Immediate (removes the latency spike):**
Set `warm_on_start: true` so each pod pre-populates its in-process cache from Redis before accepting traffic. Combine with the readiness probe — the pod should only pass `/healthz` after the cache is warm.

**Also worth addressing:**
Separate the `warm-cache.sh --flush-first` run from your deployment windows. Running a full Redis flush at 02:00 and deploying at 02:12 on the same day (Mondays) is asking for trouble even with warmed pods.

**What halting deploys would actually accomplish:**
Nothing — it removes the trigger, not the mechanism. The first deploy you do run after "fixing the pipeline" would produce an identical spike, because the pipeline was never broken.