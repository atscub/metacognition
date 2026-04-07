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