## Recommendation: LaunchDarkly (Option A)

The instinct behind Marcus's proposal is right — the *concept* is simple. But the *execution* at your specific stack has enough sharp edges that the in-house path will cost more than $3,600/year in engineer time before you get to feature parity. Here's the breakdown.

---

## What Marcus's Design Gets Right

- Core flag evaluation logic is correct and readable.
- File-based caching with mtime is a legitimate pattern.
- For a single-process, single-instance backend it would work fine.

## Where It Breaks Against Your Actual Stack

### 1. The hash function has a correctness bug

```python
hash(f"{flag_name}:{user_id}") % 100 < flag['percentage']
```

Python's built-in `hash()` is **process-randomized** since Python 3.3 (PYTHONHASHSEED). With 3 ECS container instances, user-alice might get `True` on instance 1 and `False` on instance 2 — on the same request if the ALB routes differently. You'd need `hashlib.md5` or `mmh3` for a stable, deterministic hash. Not a hard fix, but it's a real bug that would surface as intermittent, hard-to-reproduce behavior during a rollout.

### 2. S3 volume mounting on ECS is non-trivial

Marcus's proposed fix for "no redeploy" is "mount the JSON file from S3." ECS doesn't natively mount S3 objects. Your options are:
- **EFS** (mount a shared filesystem) — requires provisioning an EFS volume, security groups, mount targets per AZ, IAM policies. No dedicated DevOps means this lands on Marcus.
- **Sidecar sync container** — a container that polls S3 and writes to a shared volume — adds operational complexity and a new failure mode.
- **SSM Parameter Store** — actually the cleanest fit here, but requires rewriting the loader.

None of these is a half-day job for a team without DevOps experience.

### 3. The React frontend is unaddressed

Marcus's proposal is a Python module. Your React frontend is a **separate deployment**. To get flag state into the browser, you need either:
- A `/api/flags` endpoint (you build it, including auth, caching, serialization)
- A separate JS implementation of the same file-reading logic (impossible in a browser)
- A client-side flag store synced from that API

LaunchDarkly ships a React SDK that connects directly to their edge network. This is the question the junior engineer raised — cross-deployment consistency — and it's genuinely hard to solve cleanly in-house.

### 4. Three instances + polling = inconsistent flag state window

Even if you solve the S3 mount problem, each instance polls independently based on file mtime. During a flag change, you'll have a window (seconds to minutes depending on poll interval) where instance 1 is serving `new_editor: true` and instances 2–3 are serving `new_editor: false`. For most flags this is acceptable. For a flag change triggered by an incident ("turn this off NOW") it's not — which is the product manager's exact concern.

LaunchDarkly uses SSE (server-sent events) to push flag changes to all connected SDK instances in ~100–200ms.

### 5. Segment targeting is a now requirement, not a V2 nice-to-have

The designer asked about "users who signed up after March 1" or "users on the Pro plan." Marcus deferred this. But you have 4 major feature launches in 6 months, and your PM will ask for this targeting on launch #1. Building a rules engine that evaluates arbitrary user attributes against flag conditions is **not incremental** — it's a different problem from the current `enabled_users` list. LaunchDarkly does this with custom attributes you pass at evaluation time.

---

## True Cost Comparison

| | LaunchDarkly | In-House (realistic) |
|---|---|---|
| Year 1 cost | $3,600 | 1–2 weeks Marcus = ~$6K–12K at loaded cost |
| Frontend support | Included (React SDK) | ~3 days to build flags API |
| Segment targeting | Included | ~1 week to build rules engine |
| Cross-instance consistency | ~100ms (SSE) | Best-effort (polling interval) |
| Audit log | Included | Build or skip |
| Instant rollback | Yes | Depends on S3 sync latency |
| Ongoing maintenance | Zero | Ongoing (you own it) |

At $40K MRR, $300/month is 0.75% of revenue. You have 4 launches in 6 months. Marcus's time is worth more on product than on infrastructure.

---

## Honest Risks of Going with LaunchDarkly

**Vendor dependency.** If LaunchDarkly has an outage, flag evaluations fall back to SDK-cached values (stale but functional). Flag *changes* won't propagate. Acceptable for a startup; would matter more at scale.

**Pricing cliff.** The Starter plan covers 1,000 MAU for flags. If you grow past that, the next tier is a significant jump. Check your current MAU now and model growth. If you're at 800 MAU, you're 6–12 months from a pricing conversation.

**Lock-in.** The LaunchDarkly SDK wraps your flag calls behind their API. Migration later means touching every `ldClient.variation()` call. Mitigate this with a thin wrapper:

```python
# flags.py — wrap the SDK so you can swap implementations later
from ldclient import get as ld_get

def is_enabled(flag_name: str, user: dict) -> bool:
    return ld_get().variation(flag_name, user, False)
```

This keeps the SDK isolated to one file and makes a future migration mechanical, not architectural.

---

## Decision

**Go with LaunchDarkly.** The in-house approach has a real hash bug, leaves the React frontend unsolved, and requires non-trivial infrastructure work (EFS or equivalent) that a team without dedicated DevOps will underestimate. Marcus's intuition that "it's just a JSON file and an if-statement" is true for the happy path. The unhappy paths — 3 instances, separate frontend, segment targeting, instant rollback — are where the complexity lives.

The $3,600/year is a deliberate trade: you're buying back Marcus's time for product work during your highest-velocity 6-month window. That's the right call at your current stage.