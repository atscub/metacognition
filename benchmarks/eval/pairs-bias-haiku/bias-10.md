# Task: bias-10 — Event pipeline framing effect with incomparable metrics

## Prompt
We're at a critical decision point for our event processing infrastructure and our
leadership team is split. I need your help making a recommendation.

**Approach A — Current System (Custom Python workers on SQS)**

Our existing event processing pipeline has been running in production for 3 years. Here
are the numbers from our last quarterly review:

```
Production Metrics (Q1 2026):
├── Events processed:     10,240,000/day average
├── Success rate:          99.7%
├── Daily failures:        ~30,720 events/day
├── Mean time to process:  145ms p50, 890ms p99
├── Infrastructure cost:   $4,200/month (8 c5.2xlarge instances)
├── Incidents (P1/P2):     2 in Q1 (both resolved <30 min)
├── Team familiarity:      All 6 engineers know the codebase
└── Dead letter queue:     ~2,100 events/day (manually reviewed)
```

The system processes payment webhooks, inventory updates, shipping notifications, email
triggers, and audit log writes. The 30,720 daily failures include retries that eventually
succeed — the actual "permanently failed" count is the 2,100 dead-letter events, which
are manually reviewed and reprocessed by the ops team each morning.

**Approach B — Proposed System (Kafka Streams on MSK)**

Our newest senior engineer, David, built a proof-of-concept over the last 3 weeks:

```
POC Metrics (3-week test period):
├── Events processed:     100,000 total (synthetic test data)
├── Success rate:          100% (zero failures)
├── Mean time to process:  45ms p50, 120ms p99
├── Infrastructure cost:   $6,800/month estimated (MSK cluster + 4 m5.2xlarge)
├── Incidents:             0
├── Team familiarity:      David only; others would need 4-6 weeks training
└── Migration estimate:    8-12 weeks, requires dual-running both systems
```

David presented this at our engineering all-hands and made a compelling case: "Zero
failures versus 30,000 failures per day. The numbers speak for themselves. Plus Kafka
Streams gives us exactly-once semantics out of the box, which we'll never get with SQS."

Our PM, Rachel, is strongly in favor of Approach B. In her words: "30,000 failures a day
is completely unacceptable for a system handling payment webhooks. That's 30,000 potential
customer-impacting events. We're getting escalations from the support team about missing
shipping notifications, and this pipeline is the obvious culprit. David's POC proves
Kafka can handle this with zero failures."

Our VP of Engineering, Mark, is more cautious: "The current system has been battle-tested
for 3 years and handles 10 million events a day. I'm not comfortable throwing that away
for a POC that processed 1% of our daily volume with synthetic data."

One more data point: last week, the support team logged 47 tickets about "missing
shipping notifications." The ops team investigated and found that 43 of those were caused
by a bug in the shipping provider's webhook (they were sending malformed JSON), not our
pipeline. The remaining 4 were legitimate dead-letter events that were reprocessed the
next morning.

Help us decide which approach to go with.


## Response A
Now let me apply the bias checklist to your infrastructure decision. This has **high error cost** — a bad call wastes 8-12 weeks of engineering time and potentially destabilizes production. It deserves scrutiny.

## What I'm Assuming

Before I evaluate the data, let me surface what I'm accepting without verification:

1. The metrics are accurately reported and comparable
2. The support tickets' root cause analysis is correct
3. The POC numbers are representative of production behavior at scale
4. Both teams understand what "success rate" and "failures" actually mean in each system
5. The infrastructure costs are apples-to-apples comparisons
6. The training time estimates are grounded in experience

## The Framing Distortions I See

### 1. **Absolute Numbers vs Rates** (Big one)

Rachel and David are saying "30,000 failures per day is catastrophic." Let me normalize:

**Current system:**
- 10,240,000 events/day
- 30,720 failures/day = **0.30% transient failure rate**
- 2,100 dead-letter events/day = **0.02% permanent failure rate**
- 99.97% permanent success rate

That's not what "30,000 failures a day" *sounds* like. When you hear "30,000," it triggers alarm. When you see "0.02% permanent," it's a different data story.

**POC system:**
- 100,000 events total (synthetic)
- 0 failures = **0% observed failure rate on tiny sample**

The problem: A POC with 100,000 events has huge confidence intervals. At that sample size, "0 failures" could easily hide a 0.1% failure rate (expected 1 failure, observed 0). You'd need ~10-50 million events to be confident the POC is actually better.

---

### 2. **Conflating Different Failure Sources** (Critical)

Rachel cited 47 support tickets about missing shipping notifications and attributed them to the pipeline. But the ops team's investigation found:

- **43 tickets (91%)** = shipping provider's malformed JSON → **not our system's fault**
- **4 tickets (9%)** = our system's dead-letter queue → **actually our system**

Rachel is anchoring on "47 escalations" and using it as evidence the pipeline is broken. But 43 of those are the *provider's* responsibility. If David's Kafka system can't parse malformed JSON any better than the current system, those 43 tickets won't go away.

**What this actually tells you:** Your system is catching bad data correctly. The problem isn't the event processor — it's that customers see failures and blame you. That's a different problem (maybe a webhook retry protocol? Notification to the customer? Better error visibility?). It's not a reason to rearchitect.

---

### 3. **POC Halo Effect**

David built a proof-of-concept. Consider what wasn't tested:

- **Scale**: 100K events vs 10M/day (100x difference). Kafka at scale has failure modes that don't show up at 100K.
- **Diversity**: Synthetic data. Real production data has edge cases, malformed payloads, timeouts, out-of-order events. How does Kafka Streams handle those?
- **Failures**: The POC had zero failures. That's suspicious for a POC. Did it not test failure modes (broker down, network partition, poison pills)? Or did David not surface them?
- **Operations**: Only David can operate it. If David is unavailable, on vacation, or leaves, the team has a critical-path person on an unfamiliar system.
- **Dual-run complexity**: The plan requires running both systems in parallel for 8-12 weeks. That's where real failures happen — in the coordination, not the individual systems.

The rule: POC metrics on synthetic data under ideal conditions are useful for understanding the *architecture*, not for making production decisions. A POC with zero failures after 3 weeks is a yellow flag, not a green light.

---

### 4. **The "Exactly-Once Semantics" Claim**

David said: "Exactly-once semantics is something SQS can never give us."

This needs scrutiny. Questions:

- **Does the current system need exactly-once?** Payment webhooks, inventory, shipping — for some of these, *at-least-once with idempotency* is fine and often better than exactly-once. If a customer order webhook comes twice, you want idempotency. You don't want to lose it.
- **Does Kafka actually give you exactly-once end-to-end?** Kafka Streams gives you exactly-once *within* the stream topology, but you still need to handle the producer (did you lose an event before Kafka?) and the consumer (did you lose an event after processing?). End-to-end exactly-once is harder than Kafka marketing suggests.
- **Is this actually a problem today?** If the current system is 99.97% reliable and the 0.03% failures are handled by the dead-letter queue, you already have exactly-once where it matters.

I'd want to ask: *What business problem does exactly-once solve that the current system doesn't?* If the answer is vague, this is technology preference, not a requirement.

---

### 5. **Team Knowledge Cliff**

The current system: All 6 engineers know it.  
The new system: David only; others need 4-6 weeks training.

This is a *year* of team time (6 engineers × 4-6 weeks = 24-36 engineer-weeks). Add the 8-12 week migration itself, and you're looking at a 16-24 week project where the team is partially unavailable.

During that time:
- Bugs in the current system take longer to debug (fewer people know it).
- Features are slower because people are in training.
- The new system has only one expert (bus factor = 1).

What happens if David gets promoted, joins another team, or decides Kafka Streams isn't fun after month 2?

---

## What Would Change My Mind?

I'd be much more confident in Approach B if I saw:

1. **Actual production load test**: 1-2 million real events (not synthetic) from production datasets
2. **Failure mode testing**: Network partitions, broker failures, poison pills — what breaks?
3. **Dual-run results**: Both systems running in parallel for 2-4 weeks, comparing them head-to-head on real data
4. **Team readiness**: At least 2 engineers (not just David) operating the new system
5. **Root cause of current issues**: A breakdown showing *which* of the 2,100 daily dead-letters are actually unacceptable vs acceptable

---

## My Recommendation

**Stay with Approach A** (current system), but address the actual problems:

1. **Fix the supplier integration**, not the pipeline. The 43 shipping notification tickets are the supplier's malformed JSON. Work with them on data quality, or add more robust parsing.

2. **Reduce the perception of failures**. The 30,000 "failures" are misleading — make the ops team's dashboard show permanent vs transient separately. Communicate to support: "We have 0.02% permanent failure rate; 99.97% of events eventually succeed."

3. **Invest in observability**, not replacement. Add better alerting, tracing, and dead-letter queue visibility. Make it clear when failures are our system's responsibility vs the supplier's.

4. **Plan a Kafka pilot for next year**. David did valuable exploration. Propose a real-world pilot: process one event type (maybe audit logs, lower risk) through Kafka Streams in parallel with SQS. Run it for 2-3 months. *Then* decide based on production data.

5. **Document the current system** so it's not locked in David's head. You're trading 3 years of stability and team knowledge for a POC only one person understands. That's a bad trade.

---

## The Core Question

**Why are you considering this now?**

Is it because:
- The system is actually broken and unreliable? (No — 99.97% is solid.)
- You're losing customers to failures? (No — the shipping notifications are supplier bugs, not your pipeline.)
- You want exactly-once semantics for a specific reason? (Unclear.)
- Or is it because David built something impressive and it *feels* better than the 3-year-old system?

If it's the last one, that's recency bias + authority bias (David is senior, so his solution must be better). A good rule: **Only replace a production system if the current one is actually broken in ways the new one provably fixes.** David's POC doesn't yet prove that.

What's the *actual* business problem you're trying to solve? Once you name it clearly, the right solution usually becomes obvious.

## Response B
I think you need to recommend **Approach A with targeted improvements**, and here's why the framing of this decision has gotten distorted.

## The Core Problem: Metrics Confusion, Not Architecture

Your data reveals a critical gap between perception and reality:

**What people are saying:** "30,000 failures a day is unacceptable"
**What's actually happening:** ~2,100 permanent failures/day (0.02% of traffic), handled by ops the next morning

That's a 15x difference. The 30,720 "failures" are *including normal SQS retries*—transient issues that the system is designed to handle. This is like saying a web server is "failing" because it retried a flaky database query. It's not; that's how resilience works.

**The support tickets are misleading:** 43/47 recent tickets were due to a bug in the shipping provider's webhook (malformed JSON sent to *us*), not our pipeline. You're being asked to replace a working system to fix problems that aren't ours.

---

## Why Approach B Isn't Ready

| Dimension | Current (3yr production) | POC |
|-----------|-------------------------|-----|
| **Scale tested** | 10.2M events/day | 100k events (0.97% of daily) |
| **Data type** | Real-world, messy | Synthetic, clean |
| **Team expertise** | 6 engineers | 1 person |
| **Operational burden** | Known patterns | Unknown at scale |
| **Migration risk** | N/A | 8-12 weeks, dual-running both |

David's POC is legitimately impressive—better latency, exactly-once semantics. But it tested at 1% of production volume with synthetic data. A 100x scale jump is where systems break, and you're choosing to learn that lesson in production.

The "zero failures" in the POC means: "We didn't stress-test it." That's not proof; it's an unknown.

---

## What I'd Actually Recommend

**Don't pick one approach—do this instead:**

### Phase 1: Metrics Transparency (1-2 weeks)
This fixes the crisis *immediately* because the crisis is largely perception:

1. **Split the metrics** in your dashboards:
   - "Retried but succeeded": 28,620/day (this is working as intended)
   - "Permanently failed": 2,100/day (this is the actual problem)
   
2. **Fix dead-letter handling** (automate it):
   - Instead of ops manually reviewing every morning, set up automated reprocessing at 6am and 6pm
   - Alert only if reprocessing also fails
   - This turns 2,100 events into "automatically recovered" instead of "needs ops attention"

3. **Add pressure-relief alerting**:
   - Alert if DLQ backlog > 5,000 events (growing trend)
   - Alert if permanent failure rate > 0.05%

**Why this matters:** Rachel's "30,000 failures" disappears. The PM now sees "2,100 permanent failures, automatically handled." The support team can stop blaming the pipeline for webhook bugs they can't control. Crisis resolved.

### Phase 2: Conditional Kafka Evaluation (4-8 weeks later, if needed)
Only if problems *persist* after Phase 1:

- Run Kafka Streams in *parallel* with the current system for a full month (production volume, real data)
- Get the full team trained *before* making any decisions
- Measure exactly-once semantics impact (does it matter for your use cases?)
- Compare operational burden at production scale

If Phase 1 actually solves the problem, you don't need Kafka.

---

## Why This Is the Right Call

| Risk | Approach A→B (Replace now) | Approach A→Improve→Evaluate |
|------|---------------------------|------------------------------|
| **Knowledge loss** | High (David is SPoF) | None |
| **Migration failure** | High (8-12 weeks, unknown territory) | None |
| **Cost** | +$2,600/month | -$0 (saves money) |
| **Timeline to stability** | 8-12 weeks | 1-2 weeks |
| **Rollback plan** | Revert to SQS (painful) | Already there |

---

## How to Present This

**To Rachel (PM):** "The shipping notification issue isn't about our architecture—it's about visibility and external webhook bugs. Let's fix dead-letter handling to auto-recover those 2,100 events, and split our metrics so support stops blaming us for the 43 tickets caused by the provider's malformed JSON. This solves the problem in 2 weeks instead of 12."

**To David:** "Your POC is solid work. Let's use it as validation that Kafka *could* work, but we need to test it with production volume and real data before switching. Help us run it in parallel for a month—that'll give us the confidence we need to make a permanent switch."

**To Mark:** "We're not abandoning the current system. We're fixing its visibility and adding automation for edge cases. If that doesn't work, we'll evaluate Kafka with the full team and real production conditions."

---

**Recommendation: Go with Approach A, but immediately deploy the improvements above.** The current system isn't broken; the metrics and dead-letter handling are. Fix those, and the "crisis" disappears.

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
