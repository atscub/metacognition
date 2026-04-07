## Premortem: LaunchDarkly vs. In-House Feature Flags

---

### Step 1: State the Plan

**What we're deciding**: Ship feature flags infrastructure for PixelCraft — either integrate LaunchDarkly or build Marcus's JSON-file system.

**Success looks like**:
- 4 major features launch over 6 months with safe gradual rollouts
- Flags can be toggled instantly without 8-minute redeploys
- React frontend and Python backend read consistent flag state
- Product team can target segments ("Pro plan users", "signed up after March 1")
- Something breaks → kill switch in seconds, not minutes

**Key assumptions being made for Option B**:
- "One day to build" estimate is realistic
- S3 → ECS volume propagation gives near-real-time flag updates
- Incremental V2 improvements (segment targeting, A/B testing) will actually ship
- A Python file is sufficient for a React + Python stack

---

### Step 2: Imagine Option B Failed

I'm imagining it's October. PixelCraft chose to build in-house. Here's what happened:

**Technical failures that materialized:**

**1. S3-mounted ECS volumes don't work the way Marcus described.**
ECS does not natively mount S3 as a hot-reloadable filesystem. You'd need EFS (a different service), or a polling sidecar container that fetches from S3 on an interval. Neither was in Marcus's original design. When the CTO asked "how do we change a flag without redeploying," the team discovered this gap the week the first major feature launched. Three days were spent retrofitting a sidecar. The fix worked, but during a critical 25% rollout of the new editor, changing the percentage required a config push that took 4–6 minutes to propagate to all 3 ECS instances — meaning some users were on 25%, some on the old 0%, simultaneously.

**2. Python's `hash()` is non-deterministic.**
```python
hash(f"{flag_name}:{user_id}") % 100 < flag['percentage']
```
Python's built-in `hash()` uses random seed salting since Python 3.3 (`PYTHONHASHSEED`). Across the 3 ECS container instances — each a separate process — the same user gets a *different* hash result. Users randomly flicker in and out of the rollout cohort on each request. This is caught in QA two weeks after launch, but not before some users experience the feature intermittently. The fix (switch to `hashlib.md5`) is one line, but the incident erodes trust in the system.

**3. The React frontend has no flag system.**
Marcus built a Python module. But the React app is a separate deployment. Nobody built a JS equivalent. For the first two feature launches, the frontend hardcoded feature availability, coupling it to backend flag state via API. This worked badly: the frontend showed UI elements that the backend had flagged off, creating errors. A minimal JS client was hacked together in a week — a third implementation surface that drifts from the Python version.

**4. "V2 segment targeting" never shipped.**
In Month 2, the designer asks for a rollout targeted to "Pro plan users." Marcus is now on the critical path for Feature #3. The targeting rules engine is added to the backlog. It's still there in Month 6. Every "targeted rollout" during this period is done by manually listing user IDs in the JSON, which the PM manages in a spreadsheet.

**5. No audit log, no A/B analysis.**
When a flag change caused elevated error rates in Month 3, the team spent 45 minutes figuring out *who* changed the `export_v2` flag from 10% to 100% and *when*. The answer was in git history — if someone committed the JSON change. One change was made directly in the S3 console. No record existed.

**6. Engineering opportunity cost was the real bill.**
The "one day build" took 4 days for the initial version, 3 more days for the ECS sidecar fix, 5 days for the JS client, and ongoing maintenance interruptions across 6 months. Rough total: ~3 weeks of senior engineer time. At $150K/year, that's ~$8,600 in salary cost — 2.4 years of LaunchDarkly Starter. And PixelCraft shipped one fewer product feature.

---

### Step 2: Imagine Option A Failed

**1. They outgrew the 1,000 MAU Starter plan faster than expected.**
At $40K MRR, PixelCraft may already be near or above 1,000 monthly active users interacting with flagged code. The next tier is typically $200–300 more per month. Manageable, but the budget conversation needs to happen upfront.

**2. Two SDK integrations (React + Python) took longer than half a day.**
Realistically 1–2 days for both integrations, tests, and rollout. Not a crisis — just calibrate expectations.

**3. LaunchDarkly becomes load-bearing infrastructure.**
If PixelCraft ever wants to migrate away, every flag call in the codebase is coupled to the LD SDK. Wrapping calls behind a thin interface (`is_enabled(flag, user)`) from day one makes future migration tractable.

---

### Step 3: Risk Assessment

| Risk | Option | Likelihood | Impact | Reversibility |
|------|--------|-----------|--------|---------------|
| S3→ECS propagation doesn't work as assumed | B | **High** | **High** | Hard — requires redesign mid-launch |
| Python `hash()` non-determinism causes rollout flicker | B | **High** | Medium | Easy fix, but already in prod |
| React frontend has no flag system | B | **High** | **High** | Hard — parallel build required |
| "V2 segments" never ship during 6-month sprint | B | **High** | **High** | Impossible to recover lost launches |
| No audit log when a flag breaks something at 2am | B | **High** | Medium | Painful but eventually fixable |
| Build cost 5–10× Marcus's estimate | B | **High** | **High** | Sunk cost — time already spent |
| Outgrow 1,000 MAU Starter plan | A | Medium | Low | Easy — upgrade plan |
| LD becomes expensive at scale (>50K MAU) | A | Low | Medium | Manageable — abstract behind interface |
| Two SDK integrations take 2 days not half a day | A | Medium | Low | Irrelevant at this scale |

---

### Step 4: Mitigation Plan

**If you choose Option A (LaunchDarkly):**
- **Verify current MAU count** before committing to Starter. If you're above 800 active users hitting flagged features, budget for the next tier from day one.
- **Wrap the SDK** behind a thin interface from the start:
  ```python
  # flags.py — wraps LD SDK
  def is_enabled(flag_name: str, user_context: dict) -> bool:
      return ld_client.variation(flag_name, user_context, False)
  ```
  This means a future migration (if ever needed) touches one file, not every callsite.
- **Integration scope**: Budget 1–2 days for React SDK + Python SDK + basic CI/CD flag cleanup procedure, not half a day.

**If you choose Option B (build):**
- Before committing, Marcus must **demonstrate** that the S3→ECS propagation works in the actual ECS environment, not describe how it might work. This is a falsifiable claim. Run the experiment first.
- Replace `hash()` with `hashlib.md5(f"{flag_name}:{user_id}".encode()).hexdigest()` before shipping anything.
- Scope the React implementation *in parallel* as part of the initial build — it's not optional.
- Explicitly tell the designer that segment targeting is not in the initial scope and will not be available for the first 2 feature launches. Get sign-off.

---

### Step 5: Recommendation

**Choose Option A: LaunchDarkly.**

Marcus's framing — "it's just a JSON file and an if-statement" — is accurate for the code he wrote. It's not accurate for the system PixelCraft actually needs, as revealed by the team's own questions:

| Team question | Marcus's system | LaunchDarkly |
|--------------|-----------------|--------------|
| Change flags without 8-min redeploy? | Not solved — requires unreliable S3/EFS sidecar | Real-time SSE updates, built-in |
| Segment targeting (Pro plan, signup date)? | "V2 — maybe" | Available day one |
| Instant rollback? | ~4–6 min ECS propagation lag | <1 second |
| Consistent state across React + Python? | Two separate systems that can diverge | Single source of truth, two official SDKs |
| Who changed the flag and when? | Whatever's in git (maybe) | Full audit log |
| A/B testing? | Not in scope | Available |

**The real cost comparison:**

Marcus frames this as $3,600/year vs. $0. The actual comparison:

- **Option A**: $3,600/year + 1–2 days of integration = ~$4,400 total Year 1
- **Option B**: $0/year + ~3 weeks of senior engineer time + ongoing maintenance tax during your most critical 6-month shipping period = ~$9,000–12,000 in salary cost, plus the product features you didn't ship while Marcus was building flag infrastructure

At $40K MRR, $300/month is **0.75% of monthly revenue**. That is unambiguously the right tradeoff for a team that has no dedicated DevOps, 4 major launches ahead, and zero margin for infrastructure distractions.

**The correct principle here**: "Buy when it's commodity infrastructure, build when it's your product." Feature flag infrastructure is a solved problem. LaunchDarkly's core value is not the flag storage — it's the operational correctness (consistent hashing, real-time propagation, cross-SDK consistency) that takes months to get right. Marcus's system has at least three correctness bugs in its current form. PixelCraft's competitive advantage is its design collaboration product, not its feature flag system.

**One honest risk of the recommendation**: If PixelCraft grows to 50K+ MAU, LaunchDarkly pricing jumps significantly (enterprise territory). Mitigate by wrapping the SDK now so a future swap is one module rewrite, not a codebase-wide change. You're not locked in — you're renting optionality while you focus on shipping product.

---

**Bottom line**: Buy LaunchDarkly, spend a day integrating it, and put Marcus back on product work. The in-house system as described is not a day's work — it's a month's work to reach the quality bar that LaunchDarkly ships on day one.