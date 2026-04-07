## Socratic Analysis: Cache Invalidation Strategy

Working through the protocol for this high-stakes decision:

### 1. What Am I Assuming?

**High confidence** (verified in session):
- The cache configuration shows reconciliation_report has a 300s Redis TTL but the spec requires 30-second visibility
- Transaction processor does zero cache invalidation
- The system is experiencing observable problems (stale balances, phantom discrepancies)

**Medium confidence** (reasonable inference):
- The 9:30 AM stampede is a predictable load spike
- Cache hit rates are reasonable enough that caching matters

**Low confidence** (not verified, crucial gaps):
- Whether "phantom discrepancies" are *actually* caching vs. a transaction processing race condition
- The frequency and business impact of the stale balance delay
- The team's operational capacity for a pub/sub system
- Whether Redis is failing due to memory *capacity* or *eviction behavior*

### 2. Critical Inconsistency I Notice

The reconciliation_report requirement states: **"must reflect all transactions within the last 30 seconds"** but the TTL is **300 seconds (5 minutes).**

This isn't a subtle trade-off—this is a direct conflict. Either:
- The requirement was added after caching was designed
- The requirement wasn't validated against the cache architecture
- The phantom discrepancies are a *direct consequence of ignoring the actual requirement*

**This changes my analysis fundamentally.** You can't "solve" phantom discrepancies by reducing TTLs from 5 to 1 minute if the requirement is 30 seconds. Both approaches fail the reconciliation report requirement.

### 3. Steelmanning Both Approaches

**For "Reduce TTLs to 30 seconds":**
- Simpler, fewer moving parts, lower operational risk
- Easy to tune incrementally with measurable impact
- No new failure modes (message loss, ordering issues)
- For a financial system, predictability and simplicity matter

**Against:** Still doesn't meet the 30-second reconciliation requirement. Memory pressure will worsen. Cache stampedes remain (just faster stampedes).

---

**For "Event-driven invalidation":**
- Actually achieves the 30-second freshness requirement
- Reduces Redis memory usage significantly
- Prevents cache stampedes entirely
- Solves the problem at the source, not the symptom

**Against:** Introduces complexity, new failure modes (what if pub/sub messages are lost? out of order?), operational burden.

### 4. The Questions I Can't Answer Without More Data

1. **Are phantom discrepancies actually cache-related?** 
   - Could they be transaction ordering bugs, timing issues in the transaction processor, or inconsistent reads?
   - Recommendation: Check the actual error logs—are discrepancies always within 5 minutes of a large trade? Or random?

2. **What's the actual impact of 5-minute staleness on users?**
   - How often do portfolio managers see the stale balance issue?
   - Does it cause incorrect decisions, or is it just annoying?

3. **Can your team operate a pub/sub system reliably?**
   - Do you have Kafka, RabbitMQ, or similar deployed?
   - Who owns alerting/debugging for message loss or ordering issues?

4. **What's causing the Redis memory growth?**
   - Is it eviction (requests exceeding TTL), or just data volume?
   - At 12/16 GB, how close are you to eviction triggering?

---

### 5. My Recommendation: Neither Approach Alone Is Sufficient

**The reconciliation report requirement is the constraint—everything else must serve it.**

**Immediate actions** (high confidence):
1. **Fix the reconciliation_report TTL mismatch:** Change its Redis TTL to **60 seconds max** (to guarantee <30s visibility in worst case)
2. **Verify the phantom discrepancy root cause:** Is it caching, or something else?
3. **Separate concerns:** Don't conflate portfolio_summary staleness (tolerable at 2 minutes) with reconciliation_report accuracy (must be <30s)

**Then choose the path:**

**Path A (Simpler, if the team is ops-constrained):**
- Set reconciliation_report Redis TTL = 60s
- Set transaction_history Redis TTL = 90s  
- Set portfolio_summary Redis TTL = 120s (meets the "1-2 minute" requirement)
- Keep market_data at 15s (actually real-time enough)
- Monitor Redis eviction rates—if they exceed 5% of requests, you have a memory problem, not a TTL problem

**Path B (Recommended, if the team can handle distributed systems):**
- Implement event-driven invalidation **only for transactions** (not all data)
- When a transaction is processed: publish to `portfolio-updates` topic
- Consumers: Redis cache invalidator + portfolio summary renderer
- This solves cache stampedes, freshness guarantees, and memory pressure in one go
- Reconciliation reports become pull-based, not TTL-based—always current
- **Cost:** Adds Kafka/RabbitMQ operational burden, message ordering guarantees must be rock-solid

---

### 6. The Real Issue

You're treating caching as the primary mechanism for ensuring data freshness. **For a financial system, cache should be a performance layer, not a correctness layer.** The reconciliation report shouldn't rely on TTL at all—it should be:
- Computed on-demand from authoritative transaction logs
- Or pulled from a write-through cache that invalidates explicitly when transactions commit

**That's the architectural conversation you should be having first, before optimizing TTL values.**

---

What additional data would help me be more confident?
- Logs showing *when* phantom discrepancies occur relative to transaction timing
- Current cache hit rates and eviction metrics
- Whether you already run any event-driven systems (Kafka, RabbitMQ, SQS)