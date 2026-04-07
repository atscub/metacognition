## Premortem Analysis: Feature Flag Decision

### **CRITICAL VERIFICATION FIRST**

I need to surface a major assumption before we go further:

**Marcus proposes "mounting the JSON file as an ECS volume from S3. Changes to S3 propagate without redeploy."**

This is the lynchpin of the in-house option — but **ECS does not support native S3 volume mounting**. This is a huge, fundamental problem. Let me verify what options actually exist:

- **S3 FUSE/s3fs**: Possible, but introduces new failure modes (FUSE daemon crashes, network latency, staleness)
- **Sidecar container sync**: Adds complexity; introduces eventual consistency (flags lag 10-30s after change)
- **Environment variables + redeploy**: Defeats the purpose; you're back to 8-minute deploys
- **S3 as config source (pull-based)**: Application polls S3, but still has staleness/race conditions

This isn't a "nice to have" — this is *the core argument* for building in-house. Without zero-downtime flag changes, the in-house approach loses its main advantage.

---

## Premortem: What Could Go Wrong

### **Option A: LaunchDarkly (BUY)**

| Risk | Likelihood | Impact | Issue |
|------|-----------|--------|-------|
| Integration delays (unforeseen SDK incompatibilities) | **Medium** | Medium | Startup plan SDKs are solid; likely 4-6 hours, not 0.5 |
| Cost growth with user scale | **High** | Medium | $300 → $1000+/month if product succeeds; expected and budgeted |
| Vendor lock-in / hard to migrate away | **Low** | High | Not unique to LaunchDarkly; can always rebuild custom system later |
| Outgrows Starter plan features mid-launch | **Medium** | Medium | May need custom targeting logic as workaround (manageable) |
| Reliability/latency of SSE updates | **Low** | Medium | LaunchDarkly is battle-tested; low risk |

**Biggest real risk:** Cost scales with growth, but that's a "good problem" and expected.

---

### **Option B: Build In-House (MARCUS'S PROPOSAL)**

| Risk | Likelihood | Impact | Reversibility | Severity |
|------|-----------|--------|---|---|
| **S3 mounting doesn't work as described** | **VERY HIGH** | **HIGH** | Hard | 🚨 **CRITICAL** |
| Frontend/backend flags drift out of sync | **HIGH** | **HIGH** | Hard | 🚨 **CRITICAL** |
| No audit trail; can't debug "why did X break?" | **HIGH** | Medium | Hard | **HIGH** |
| Targeting rules engine scope creeps (V2 never ships) | **HIGH** | **HIGH** | Hard | 🚨 **CRITICAL** |
| Marcus is the only one who understands it | **HIGH** | Medium | Hard | **HIGH** |
| Instant rollback isn't instant (cache propagation lag) | **HIGH** | **HIGH** | Hard | 🚨 **CRITICAL** |
| Hash-based percentage targeting has edge cases (null users, collisions) | **Medium** | Medium | Medium | **MEDIUM** |
| JSON file becomes bottleneck if flags checked frequently | **Medium** | Low | Medium | **MEDIUM** |

---

## The Three Structural Problems with In-House

### **1. Frontend-Backend Consistency (ARCHITECTURAL FLAW)**

The team has two **separate deployments**. Marcus's design assumes they can roll out independently:

- **Scenario A**: Backend gets feature flag at 50%; frontend still at 0%
  - Backend exposes API for new feature; frontend UI doesn't call it → wasted backend work
  - Or worse: UI calls API before backend is ready → 500 errors

- **Scenario B**: Frontend rolls out before backend
  - Users see UI for a feature that isn't ready → broken experience, support tickets

**LaunchDarkly solves this**: Both frontend and backend fetch flags from the same source (real-time, SSE). A single flag state is authoritative.

**In-house "solution"**: Coordinate deployments. But your deploy is 8 minutes. Coordinating two deployments = 16+ minutes of risk. And who confirms they're in sync?

### **2. S3 Mounting Doesn't Exist (FOUNDATIONAL PROBLEM)**

Marcus's core value prop is: "Mount JSON file to S3. Changes propagate without redeploy."

**Reality**: ECS does not support S3 volume mounting. Options:
- **S3 FUSE**: Introduces a daemon that can crash, has network latency, is a new operational surface
- **Sidecar sync**: Eventual consistency; your flags lag 10-30 seconds behind S3
- **Polling**: Application reads S3 every X seconds; still has staleness
- **Environment vars**: Back to 8-minute redeploy cycle (defeats purpose)

This is not "Marcus didn't think of it" — it's a **hard technical limitation**. The proposal is built on a false assumption.

### **3. Scope Creep on Targeting Rules (SCHEDULE RISK)**

Designer asks: "Can we target 'users on Pro plan'?" 

Marcus's answer: "V2."

But your roadmap needs this **now** (4 major launches in 6 months). Building a targeting engine:
- Requires schema definition (what's a "segment"?)
- Requires evaluating segments (DB queries? cached list of user IDs?)
- Requires segment consistency between frontend & backend
- Requires rollback of segment definitions
- Probably a 2-3 week project

Meanwhile, LaunchDarkly has this on Day 1.

---

## Summary: Risks by Decision

### **If you buy LaunchDarkly, worst case:**
- Integration takes 1 day instead of 4 hours (minor slip)
- Cost is $300/month vs. budgeted engineer time
- You're operationally dependent on their SaaS (but they're mature + uptime SLAs)

### **If you build in-house, worst case:**
- Launch 1 (Month 1): Flags work, but frontend/backend diverge during rollout → user-facing bugs
- Launch 2 (Month 2): Targeting rules needed, Marcus is 2 weeks deep in scope creep
- Launch 3 (Month 3): S3 FUSE daemon crashes during critical rollout, no one knows how to restart it
- Launch 4 (Month 4): Flags are cached; rollback takes 5 minutes instead of instant; damage already done
- By Month 6: Junior engineer and product manager avoid touching flags; all changes go through Marcus

---

## Recommendation

**Recommend: BUY LaunchDarkly**

### Why

1. **The in-house option is built on false assumptions.** S3 mounting doesn't work natively; Marcus hasn't verified this. You'd either discover it in week 1 (after committing) or worse, mid-launch.

2. **Frontend-backend consistency is a structural problem** you cannot solve in a JSON file. You need a shared, real-time source of truth. LaunchDarkly provides this; a local JSON file doesn't.

3. **You don't have the operational headroom.** A 5-person team deploying 4 major features in 6 months needs their tools to *work* — not need constant care. Building a feature flags system is a side project that will pull Marcus away from product work.

4. **Cost is not the constraint.** $300/month ($3,600/year) is 0.9% of your MRR. The cost of Marcus being 20% blocked on flag infrastructure for 6 months is way higher. (Rough math: if Marcus is worth $200K/year, that's $20K in lost productivity. LaunchDarkly costs $3.6K.)

5. **Speed to market matters in a startup.** You're shipping 4 major features. Every day a launch is delayed costs runway. LaunchDarkly gets you rolling in 4-6 hours; in-house takes 1-2 weeks (once S3 mounting problem surfaces).

### Honest Risks of This Recommendation

- **Cost scales with growth** (acceptable: plan for it in Series A conversation)
- **You're dependent on LaunchDarkly's uptime** (acceptable: they have 99.95% SLA; you can add a fallback)
- **Vendor lock-in** (acceptable: you can rebuild on top of in-house system in 12 months if needed, but you won't need to)

---

## What To Do Monday Morning

1. **Have Marcus verify the S3 mounting approach** with one of these:
   - Build a small test on ECS (30 min) to confirm S3 FUSE works
   - Check internal Slack / docs if anyone's done this before
   - If it's not tested, that's a red flag for the in-house approach

2. **Get a cost breakdown for LaunchDarkly upgrades** as you scale to 10K → 100K MAU. Budget it into your Series A plan.

3. **Block 4 hours for LaunchDarkly SDK integration** this sprint. Get it in before the first major launch.

4. **Document the flag release process** (who changes flags, how, approval flow) — this matters more than the tool.

**The bottom line**: A mature SaaS tool (especially one purpose-built for this) beats a custom solution when you're shipping fast and your team is small. Revisit this decision in 18 months if you want to own the system.