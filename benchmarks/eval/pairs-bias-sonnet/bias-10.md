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
## Recommendation: Stay on SQS — but fix the right problems

The data here is being misread in ways that are driving the disagreement. Let me untangle it, then give a concrete recommendation.

---

### The numbers are not what they appear to be

**Rachel's framing is wrong.** "30,000 failures/day" is not 30,000 customer-impacting events. Those are transient retry failures that eventually succeed. The actual permanent failure rate is:

```
2,100 DLQ events / 10,240,000 processed = 0.021% permanent failure rate
```

That's **not** a broken system. That's well within acceptable range for a high-volume event pipeline.

**The support ticket investigation destroys the migration case.** Of 47 "missing shipping notification" tickets:
- 43 were caused by your shipping provider sending malformed JSON — **not your pipeline**
- 4 were legitimate, resolved the next morning

The pipeline is not causing customer escalations. The bug was upstream. Migrating to Kafka would not have changed this outcome.

**David's POC proves very little.** 100,000 synthetic events is 1% of one day's volume. Synthetic data won't contain the malformed payloads, edge cases, and unexpected traffic patterns that are responsible for your 2,100 DLQ events. "Zero failures on clean test data" is not a valid comparison to "99.7% success on real production traffic."

---

### The real problems to solve

Two legitimate operational pain points exist in the current system:

1. **2,100 manual DLQ reviews every morning** — this is real toil
2. **Malformed upstream payloads** — needs defensive handling, not a new infrastructure

Both are solvable without a $31,200/year infrastructure increase and an 8-12 week migration.

---

### What to do instead

**Short term (2-4 weeks):**
- Analyze the 2,100 daily DLQ events — categorize by failure type. Likely a small number of patterns account for most of it. Fix those.
- Add schema validation at ingestion for the shipping webhook endpoint to fail fast on malformed JSON and return the error to the provider rather than silently dead-lettering.
- Automate DLQ reprocessing for events that match known-safe retry patterns. Eliminate or reduce the manual morning review.

**Medium term:** If DLQ volume is significantly reduced and the team still sees value in exactly-once semantics (specifically for payment webhooks), evaluate Kafka for that event type only — not a wholesale migration. But do this with realistic load testing at 10M+ events/day, not synthetic data.

---

### On Mark and Rachel's positions

Mark is right to be skeptical of the POC but should be careful: "battle-tested for 3 years" is not a reason to avoid improvement. The question is whether improvement is actually needed here.

Rachel is right that manual DLQ review is a real problem, but she's drawn the wrong causal chain from support tickets to infrastructure. The data doesn't support the conclusion.

David built something impressive in 3 weeks, but the better use of his Kafka expertise right now is reducing the 2,100 DLQ events through better failure analysis and upstream validation — not a platform migration.

---

### TL;DR

**Don't migrate.** The 30K "failures" aren't customer-impacting, the 47 support tickets were mostly a provider bug, and the POC isn't a valid comparison. Fix the actual problems: reduce DLQ volume, handle malformed payloads, automate reprocessing. Revisit Kafka in 6 months with real load data if you still see a case for it.

## Response B
## Socratic Analysis: SQS vs. Kafka Infrastructure Decision

I'm going to work through the bias checklist before giving a recommendation, because this decision has several framing effects that are doing significant work in shaping how the leadership team sees it.

---

### Step 1: Normalize the Numbers to Comparable Scales

The single most important analytical move here is decomposing the "30,720 failures/day" headline.

**Current system — what the numbers actually say:**

| Metric | Raw Number | Rate |
|--------|-----------|------|
| Daily events | 10,240,000 | — |
| Transient failures (retries that succeed) | ~28,620/day | 0.28% |
| Permanent failures (DLQ, reviewed manually) | ~2,100/day | **0.021%** |
| Eventual success rate | — | **99.979%** |

The 30,720 number David cited includes retries that eventually succeed. The actual permanent failure rate — the number that represents events that customers never received — is **2,100/day, or 0.021%**. That's a 99.979% eventual delivery rate.

**POC — what the numbers actually say:**

| Metric | Raw Number | Notes |
|--------|-----------|-------|
| Events tested | 100,000 total | ~1% of one day's production volume |
| Data type | Synthetic | No malformed payloads, no real diversity |
| Duration | 3 weeks | ~4,762 events/day — vastly below production |
| Failures | 0 | Expected: synthetic data won't have the edge cases that cause production failures |

These numbers are not comparable. A 100% success rate on 100K synthetic events tells you almost nothing about behavior at 10.24M real events/day. You haven't yet seen what the Kafka system does when it receives the shipping provider's malformed JSON.

---

### Step 2: Diagnose the Support Ticket Root Cause

This is the most important empirical fact in the entire problem statement, and it's being ignored in the leadership debate:

> **47 support tickets about missing shipping notifications**
> - 43 caused by shipping provider's malformed JSON (upstream bug, not your pipeline)
> - 4 were legitimate DLQ events, reprocessed next morning

Rachel's statement — *"30,000 potential customer-impacting events... David's POC proves Kafka can handle this with zero failures"* — contains a chain of inferences that don't hold up:

1. The escalations were attributed to the pipeline, but the investigation shows 91% were caused by an upstream provider.
2. Kafka's exactly-once semantics would not have prevented malformed JSON from the shipping provider — it would have failed (or DLQ'd) those events too, just differently.
3. The 4 legitimate events were already being handled by your existing DLQ process. They were reprocessed the next morning. The question is whether overnight delay is an acceptable SLA for those events — not whether the pipeline is "broken."

**The business case for migration rests on a root cause that doesn't exist.** The shipping notification escalations are a vendor problem, not a pipeline problem.

---

### Step 3: Active Bias Inventory

**Framing bias in David's presentation:**
- Used absolute failures (30,720) instead of rates (0.3% transient / 0.021% permanent)
- Compared zero failures on synthetic test data to real production failures — an apples-to-oranges comparison
- "Zero failures" in a POC is the expected outcome; the question is what happens under adversarial conditions

**Confirmation bias in Rachel's analysis:**
- The 47 support tickets felt like evidence for the pipeline being broken, and the Kafka POC felt like the solution — but the investigation broke this causal chain
- She's anchored on the 30,000 number without checking whether it's the right number to optimize

**Sycophancy risk for me:** David built something impressive, it's a shiny new system, and there's social pressure at an all-hands. The "modern" answer is to recommend Kafka. I need to actively resist this.

**Authority bias risk:** Mark (VP Eng) is being cautious — I shouldn't just agree with him because he's the most senior voice of skepticism. His position needs to stand on its own merits.

**Steelmanning the Kafka migration (strongest version):**
- Exactly-once semantics genuinely matters for payment webhook idempotency at scale
- 45ms vs 145ms p50 latency is a real difference for time-sensitive payment flows
- Kafka's consumer group model and replay capability are architecturally superior for event sourcing patterns
- MSK is managed infrastructure — the $2,600/month delta buys SLA guarantees from AWS
- As volume grows, SQS per-message costs may scale worse than MSK's fixed cluster cost
- The 2,100 DLQ events/day representing a manual ops burden every morning is a real (if not urgent) cost

---

### Step 4: What I'm Confident About vs. What I'm Not

**High confidence (derivable from the data given):**
- The "30,000 failures" number is misleading as presented
- The majority of customer-reported issues were upstream vendor bugs
- The POC is insufficient evidence to validate production readiness
- A migration that leaves 5 of 6 engineers unfamiliar with the system creates real operational risk

**Medium confidence (reasonable inference, not proven):**
- The 2,100 DLQ events/day are acceptable under the current manual review workflow — but I don't know if any of those represent time-sensitive payments where overnight reprocessing causes real harm
- Kafka would likely perform better at 5-10x current volume — but I don't know if that growth is on your roadmap

**Low confidence (I don't have enough information):**
- Whether exactly-once semantics is a genuine hard requirement for your payment webhooks, or a nice-to-have
- Whether the current system has hit any architectural limits (dead-end scaling paths, operational debt)
- What the actual engineering cost of the migration is — 8-12 weeks of how many engineers' time?

---

### Step 5: The Recommendation

**Don't frame this as binary.** The leadership debate is stuck on "keep current system vs. replace with Kafka" — but there's a third path that's likely better.

#### What I'd actually recommend:

**Short term (next 4-6 weeks): Fix the actual problem**

The 47 support tickets are a vendor problem. Get the shipping provider to fix their webhook or add a malformed-JSON handler upstream that alerts them and fails gracefully. This addresses the immediate escalation pressure without touching infrastructure.

**Medium term (next quarter): Evaluate honestly, not emotionally**

If there's a genuine case for Kafka, it needs to be validated with real data:
- Replay production traffic (not synthetic) against the POC at full daily volume
- Include malformed payloads, burst patterns, and edge cases
- Measure the DLQ behavior — does Kafka eliminate the 2,100 manual events, or does it just route them differently?
- Quantify the business impact of overnight DLQ reprocessing for payment events specifically

**Long term: Migrate selectively if warranted**

If the production replay validates Kafka's advantages, migrate the highest-value subset first — likely payment webhooks, where exactly-once semantics and latency matter most. Leave the lower-stakes event types (shipping notifications, email triggers) on SQS until the team has operational experience with MSK.

#### How to respond to each stakeholder:

**To Rachel:** The support escalations were caused by the shipping provider's malformed JSON, not the pipeline. Before committing to an 8-12 week migration, the ops team should confirm: of the 2,100 daily DLQ events, how many are time-sensitive enough that overnight reprocessing causes customer harm? That's the actual business case to validate.

**To David:** The POC is genuinely promising. The right next step is a production replay test at scale with real event diversity. 100K synthetic events can't tell us what happens at 10.24M real events. If the system holds up under that, the migration case is much stronger.

**To Mark:** Your instinct is correct. The current system's 99.979% eventual delivery rate is good. The question worth answering is whether the 0.021% permanent failure rate causes real business harm — and whether that harm justifies the cost and risk of migration. That's a business question, not a technology question.

---

### The one thing I'd flag most directly

The framing of "30,000 failures per day" in David's presentation, and Rachel's adoption of it, is analytically incorrect and has distorted the leadership conversation. The permanent failure rate is 0.021%, not 0.3%. That doesn't mean the current system is optimal — but it means the urgency of the problem has been significantly overstated, and the root cause of the customer escalations has been misattributed. Any decision made under that framing is likely to be wrong.

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
