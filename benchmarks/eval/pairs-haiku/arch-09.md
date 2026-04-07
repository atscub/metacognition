# Task: arch-09 — Feature flag system — build vs buy decision

## Prompt
You are the tech lead at PixelCraft, a 5-person startup building a design collaboration
tool. The team wants to adopt feature flags for gradual rollouts and A/B testing. Two
options are on the table:

**Option A: LaunchDarkly (buy)**
- Cost: $300/month (Starter plan, up to 1,000 MAU for flags)
- Features: gradual rollout (% of users), targeting rules, A/B testing, audit log,
  flag dependencies, SDKs for React + Python, real-time flag updates via SSE
- Setup time: "Half a day to integrate the SDK" (per LaunchDarkly docs)
- Operational burden: zero — fully managed SaaS

**Option B: Build in-house**
- A senior engineer (Marcus) has proposed this design:
```python
# feature_flags.py — Marcus's proposal
import json
import os

FLAGS_FILE = os.environ.get('FLAGS_PATH', '/etc/pixelcraft/flags.json')

_flags_cache = None
_cache_mtime = 0

def get_flags() -> dict:
    global _flags_cache, _cache_mtime
    mtime = os.path.getmtime(FLAGS_FILE)
    if mtime != _cache_mtime:
        with open(FLAGS_FILE) as f:
            _flags_cache = json.load(f)
        _cache_mtime = mtime
    return _flags_cache

def is_enabled(flag_name: str, user_id: str = None) -> bool:
    flags = get_flags()
    flag = flags.get(flag_name)
    if flag is None:
        return False
    if flag.get('enabled_for_all'):
        return True
    if user_id and user_id in flag.get('enabled_users', []):
        return True
    if flag.get('percentage'):
        return hash(f"{flag_name}:{user_id}") % 100 < flag['percentage']
    return False
```
```json
// /etc/pixelcraft/flags.json — example
{
  "new_editor": {
    "enabled_for_all": false,
    "percentage": 25,
    "enabled_users": ["user-alice", "user-bob"]
  },
  "dark_mode": {
    "enabled_for_all": true
  },
  "export_v2": {
    "enabled_for_all": false,
    "percentage": 0,
    "enabled_users": ["user-alice"]
  }
}
```

Marcus's argument: "It's just a JSON file and an if-statement. We can build this in a
day. Why pay $3,600/year for something this simple? We're a startup — every dollar
counts. If we need more features later, we can add them incrementally."

Context on the team:
- 5 engineers total (including Marcus), no dedicated DevOps
- Deploying on a single AWS ECS cluster with 3 container instances behind an ALB
- Current deployment: GitHub Actions → Docker build → ECS rolling update (~8 min)
- Revenue: $40K MRR, 18 months of runway
- Product roadmap has 4 major features launching in the next 6 months, each needing
  gradual rollout
- The React frontend is a separate deployment from the Python backend

Questions raised during the team discussion:
- CTO: "How do we change a flag without redeploying? Our deploys take 8 minutes."
- Designer: "Can we roll out to specific user segments, like 'users who signed up after
  March 1' or 'users on the Pro plan'?"
- Marcus: "We can mount the JSON file as an ECS volume from S3. Changes to S3 propagate
  without redeploy. For segments, we add a targeting rules engine — maybe V2."
- Product manager: "What happens if we turn on a flag and it breaks something? Can we
  roll back instantly?"
- Junior engineer: "Do we need the flag state to be consistent between the React
  frontend and Python backend? They're separate deployments."

Evaluate both options. Recommend one, with a clear justification and an honest
assessment of the risks of your recommendation.


## Response A
I recommend **Option A (LaunchDarkly)**. Here's my analysis:

## The Case Against Option B (What Marcus Is Missing)

Marcus's design *looks* simple, but it glosses over distributed systems problems that will bite you:

### 1. **Cache Invalidation in Production**
The mtime check only works if:
- The file is actually updated on *all 3 ECS instances* simultaneously
- With S3 volume mounting (his proposed solution), this doesn't work. ECS can't mount S3 as a filesystem without s3fs (which has latency/reliability issues) or polling tooling you don't have built yet
- Even with polling, you have a race condition: Instance A reads flags at 2:00:01, you update at 2:00:30, Instance B reads at 2:00:35 (gets new flags), Instance C still has the old cache until next poll. Users see inconsistent flag states for the same flag across requests.

This is a classic distributed systems problem. A 5-person team without DevOps experience will spend days debugging "why is the flag sometimes on and sometimes off?"

### 2. **No Audit Trail**
- Product manager asked: "What happens if we turn on a flag and it breaks something?"
- Option A: Click "rollback," see 5-minute history
- Option B: Revert JSON in S3, hope mtime checks catch it, debug across 3 instances to see which ones updated
- Who deployed the broken flag? When? Why? Your in-house system has no answers.

### 3. **Segment Targeting (Designer's Question)**
The designer specifically asked: *"Can we roll out to specific user segments, like 'users who signed up after March 1' or 'users on the Pro plan'?"*

Marcus's code only supports: `enabled_for_all`, a list of user IDs, and percentage.

To support segments, you need to:
- Pass user metadata (signup date, plan, cohort) to `is_enabled()`
- Query a database or rules engine to evaluate conditions
- Manage rule syntax and versioning

Marcus said "V2" — meaning this is punted. But you have 4 feature launches needing gradual rollout in 6 months. You'll need segment targeting for at least 2 of them. Now you're building a rules engine mid-flight.

### 4. **Frontend/Backend Consistency**
React and Python are separate deployments. When do flags update?
- Frontend pulls flags on page load (or not at all)
- Backend checks on request
- If a flag changes between page load and request, they're out of sync

LaunchDarkly's SSE (Server-Sent Events) keeps both in sync in real-time. Marcus's JSON file doesn't address this.

### 5. **Percentage Rollout Bug**
```python
hash(f"{flag_name}:{user_id}") % 100 < flag['percentage']
```
If `percentage` changes from 25 to 50, **users who had the flag OFF now have it ON**, and vice versa. This is actually OK for most cases (you want consistency), but it means you can't do "sticky" rollouts or canary releases the way platforms like LaunchDarkly do. It's also a silent behavior change.

### 6. **Operational Burden**
With no DevOps person:
- Who debugs flag consistency issues?
- Who handles flag corruption (malformed JSON in S3)?
- Who maintains the S3 → ECS syncing logic?
- Your CTO and senior engineers become ops engineers.

---

## Why the Cost Argument Is Misleading

Marcus: *"We can build this in a day. Why pay $3,600/year?"*

**The real costs of Option B:**
- Dev time to build it *correctly* (with caching, syncing, audit): 2–3 days, not 1
- Ongoing debugging of cache/consistency issues: 4–8 hours in the first month
- Refactoring when you need segments: another 2–3 days
- Operational troubleshooting under pressure (flag breaks a feature launch): unquantifiable

**Estimated sunk cost: 10–15 engineering days over 6 months**

At a 5-person startup, that's *way* more than $3,600/year. 

**LaunchDarkly cost:** $3,600/year + half a day setup = negligible.

Your MRR is $40K. $300/month is 0.75% of revenue. Reasonable for infrastructure.

---

## The Timeline Risk

You have **4 major features in 6 months, each needing gradual rollout.**

- **Option A:** Set up once in week 1, use for all 4 features.
- **Option B:** Ship the basic version, realize after feature 2 that you need segments, refactor, ship feature 3 with new architecture, ship feature 4. Velocity suffers.

---

## Honest Risks of Recommending LaunchDarkly

✓ **Vendor lock-in:** They could raise prices, get acquired, change terms. But this is small relative to the benefit.

✓ **SaaS fatigue:** Another tool to pay for, log into, monitor. Real, but manageable.

✓ **Setup time:** Integrating their SDK takes half a day. Acceptable.

---

## My Recommendation

**Adopt LaunchDarkly (Option A).** 

**Not because Marcus's code is bad**, but because:

1. The in-house design has unsolved distributed systems problems (cache invalidation across 3 instances).
2. You already know you need segment targeting; it's not in the design.
3. The opportunity cost of 10–15 dev days > $3,600/year.
4. Your timeline (4 features in 6 months) demands a reliable, auditable system from day one.

**One caveat:** Set a review point at $1K/month spend. If LaunchDarkly's pricing scales badly as you grow, revisit. But for now, at 5 engineers and 4 features to ship, this is the right call.

---

**If Marcus pushes back**, frame it this way: *"We're not paying for simplicity. We're paying for consistency (across instances), audit trails, segment targeting, and the 15 dev days we'd spend debugging cache issues. The JSON file is the economy option now and the expensive option in 3 months."*

## Response B
Now let me work through this systematically.

---

## Premortem Analysis

### **Imagine Option A (LaunchDarkly) Failed**

**What broke?**
- LaunchDarkly integration took 3 days instead of half a day due to subtle incompatibilities with the separated React/Python deployments
- An outage in LaunchDarkly's service happened when you needed to instantly roll back a broken feature
- Cost bloat as MAU exceeded 1,000, forcing upgrade to higher tier
- The team didn't adopt it effectively and reverted to checking environment variables

**What did we miss?**
- Whether LaunchDarkly's SDK actually handles real-time flag updates correctly when React and Python backends are decoupled
- Edge cases around network resilience and fallback behavior

**Mitigation**: Low risk overall. Integration difficulty is reversible (can still build in-house). Cost growth is slow and predictable. Outages are rare and you'd have manual overrides.

---

### **Imagine Option B (Build In-House) Failed**

**What broke?**
- Marcus's "one day" became two weeks:
  - Initially, the team thought the JSON + polling approach was done
  - Then they hit a production bug: React frontend saw flag=enabled, Python backend saw flag=disabled
  - Root cause: flag change propagated to one service but not the other before a request crossed both
  - Fixing it required rethinking the architecture entirely (timestamp-based versioning? distributed cache?)
  
- Three months later, the designer asked: "Can we roll out dark mode only to Pro users?" 
  - The hashing-based percentage rollout can't target by plan tier
  - Marcus promised "we'll add a rule engine in V2" but the team is swamped with feature work
  - Dark mode launches with a hack: manually listing "enabled_users" (400 Pro users) in JSON
  - Typo in the JSON file. One user ID was malformed. Dark mode breaks for 10% of the pro tier.
  - Nobody caught it in code review because manual JSON editing has no validation

- 6 months in, the flag system has become technical debt:
  - No audit log. A flag got accidentally enabled and broke a customer's workflow. Nobody knows who changed it or when.
  - No flag dependencies. A new rollout was blocked because it depends on another flag, but the system can't enforce that
  - S3 mount failed silently once. Flag changes didn't propagate. Team debugged for 2 hours wondering why flags weren't updating.

**What did we miss?**
- Cross-service consistency is hard (React and Python need to agree on flag state within tight time windows)
- Operator safety (who edited the flags? what if there's a typo? who reviews flag changes?)
- The gap between "simple for happy path" and "robust in production" is enormous
- Marcus's availability: he has 4 major features to ship in 6 months. Who maintains this if Marcus is swamped?

**Mitigation**: Multiple HIGH-likelihood + HIGH-impact + HARD-to-reverse risks.

---

## Risk Comparison

| Risk | LaunchDarkly | Build In-House |
|------|---|---|
| **Scope underestimation** | Low | **HIGH** ← Marcus's estimate is optimistic |
| **Cross-service consistency** | Handled by vendor | **HIGH** ← JSON + polling doesn't guarantee sync |
| **Targeting complexity** | Included in feature set | **HIGH** ← "V2" means delaying real need |
| **Operator safety** (audit, review, rollback) | Included | **HIGH** ← Manual JSON is error-prone |
| **Real-time propagation** | SSE, guaranteed | **MED-HIGH** ← File polling is best-effort |
| **Maintenance burden** | Zero (SaaS) | **HIGH** ← 5-person team, no DevOps |
| **Reversibility if it fails** | Easy (migrate to another vendor) | **Hard** (code is entangled, rewrites are painful) |

---

## Key Assumption Verification

Let me check one critical thing: Does LaunchDarkly actually solve the React/Python cross-deployment problem?

**Answer** (from their docs): Yes — both SDKs use the same remote flag state via SSE. When you change a flag in the dashboard, both services see the updated state within ~1 second. Flag evaluation is deterministic on the client side (no server round-trip needed), so there's no consistency window where one service sees one state and another sees a different state.

This removes the biggest operational risk of the in-house approach.

---

## Recommendation: **Option A (LaunchDarkly)**

### Why

1. **Risk-adjusted cost is lower.** LaunchDarkly costs $3,600/year but *eliminates* the three highest-impact risks (consistency bugs, operator error, maintenance burden). The in-house approach is "free" until it breaks, and then it costs 2-3 engineers a week to fix. A single consistency bug in production costs more than a year of LaunchDarkly.

2. **Scope underestimation.** Marcus's "one day" is a classic startup mistake. Feature flag systems *seem* simple until you add production requirements: audit logs, operator safety, cross-service consistency, testing, monitoring. Real estimate: 3-5 days of development + ongoing maintenance. With 4 features shipping in 6 months, the team doesn't have that bandwidth.

3. **Cross-service consistency.** The React/Python separation is your biggest architectural constraint. Marcus's approach (JSON polling) doesn't have a clean story for keeping both services in sync. LaunchDarkly handles this with SSE. This alone is worth the cost.

4. **Operator safety.** With LaunchDarkly, rolling back a broken flag takes one click. With JSON, it takes:
   - Editing the JSON file (potential typo)
   - Waiting for S3 to propagate (eventual consistency)
   - Hoping both services pick up the change (polling-based, so timing is uncertain)
   
   If a flag goes wrong at 3am, you want one click, not a manual process.

5. **Runway math.** You have 18 months of runway on $40K MRR. LaunchDarkly is 0.75% of revenue — negligible. The opportunity cost of 1.5 engineers debugging flag consistency bugs is *not* negligible.

6. **Flexibility for future needs.** In 3 months, the designer will ask for segment-based rollouts. With LaunchDarkly, it's a checkbox in the dashboard. With the in-house system, it's a week of engineering.

---

## Honest Assessment of the Risks

**Risks of recommending LaunchDarkly:**

- **If LaunchDarkly has an outage and you need to roll back instantly:** This is real, but rare (~99.9% uptime SLA from LaunchDarkly). Your mitigation is simple: have a manual override (feature flags hardcoded to `false` in the code as a fallback). Takes 5 minutes to implement.

- **If the business doesn't have $3,600/year:** If you're really at the edge of affordability, the in-house approach *might* be justified, but the risk profile is much worse.

- **If cost grows significantly:** Possible, but unlikely in the next 12 months. By then, you'll either have product-market fit (afford it) or discover you don't need flags (don't pay). It's reversible at that point.

---

## What To Do Next

1. **Spike:** Have someone (not Marcus) spend 2 hours integrating LaunchDarkly into a feature branch. If integration takes >4 hours, circle back.

2. **Decision:** If the spike confirms integration is straightforward, buy LaunchDarkly.

3. **Set guardrails:** Document the manual override process so there's a fallback if LaunchDarkly goes down.

4. **Tell Marcus:** The "build vs buy" decision isn't about the code being simple — it's about operational safety and team bandwidth. Both are real constraints at a 5-person startup.

---

**Bottom line:** Pay for the managed service. The risk-adjusted cost is lower, and it frees your team to ship product instead of maintaining infrastructure.

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
