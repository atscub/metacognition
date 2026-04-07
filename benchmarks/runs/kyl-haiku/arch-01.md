I need to work through this carefully before jumping to a architecture recommendation. Let me run the protocol:

## 1. What am I assuming?

Going in, I'm assuming:
- The 200ms latency target applies to **event publication**, not delivery to all 12 consumers
- That internal and external consumers have fundamentally different SLA/timing requirements
- That the bottleneck is synchronous blocking on slow webhooks, not the queue itself
- That "at-least-once delivery" is the hard constraint on external webhooks

**But I'm not certain about these.** Let me question them.

## 2. What would disprove my assumptions?

- If the 200ms target *includes* webhook delivery, the entire approach changes
- If all 12 consumers truly have equal priority, a single shared queue might be simpler (though slower)
- If the ordering requirement is global (not per-order), we lose options like sharding by order ID

**Let me ask you three clarifying questions before designing:**

1. **On the 200ms latency target**: Does this need to include delivery to external webhooks, or is it sufficient that internal consumers receive the event within 200ms (webhooks can be slower, up to 60s)?

2. **On ordering**: "Events for the same order must arrive in causal order" — does this mean webhooks must never receive an `order.delivered` before `order.shipped`? (I assume yes, but confirming.)

3. **On the DHL timeout**: When DHL takes 6-8 seconds, should we **wait** for a response (honouring the retry contract), or should we **fail fast at some timeout** and retry asynchronously?

---

**Provisional architecture (pending your answers):**

If the 200ms target is **internal-only** (webhooks can take up to 60s), here's the skeleton:

```
Event arrives
  ↓
[Write to WAL] ← Instant ack to caller (< 10ms)
  ↓
┌─────────────────────────────────────────────────┐
│ Split into two paths                             │
└─────────────────────────────────────────────────┘
│
├─→ FAST PATH: Internal Consumers (Sync)
│   • analytics, inventory, eta, fraud, notifications, audit, billing, sla
│   • Direct function calls or Celery tasks
│   • Complete within 100-150ms
│   • No retries needed (if a consumer fails, alert ops, replay from WAL)
│
├─→ GUARANTEED PATH: External Webhooks (Async)
│   • Separate queue per customer (fedex, ups, dhl, customs)
│   • Kafka topic or Redis Streams (durable, replayable)
│   • Async worker handles retries (5x exponential backoff)
│   • DHL on own worker (sharded by customer) so it doesn't block others
│   • Ordered by order_id using partition/stream key
│   • Completes within 60s SLA
│
└─→ Monitor: If fast path > 150ms, alert (degradation)
```

**Core trades I'm weighing:**

| Choice | Pros | Cons |
|--------|------|------|
| **Separate external queue** | Fast path unblocked, can retry webhooks independently, can scale webhook workers separately | Extra infrastructure, more complexity |
| **Single shared queue** | Simpler, one pipeline | Slow webhooks block internal consumers (recreates current problem) |
| **Kafka for webhooks** | Durable, replayable, partition by order_id | Operational overhead (ZK, brokers, monitoring) |
| **Redis Streams for webhooks** | Simpler than Kafka, already using Redis | Less fault-tolerant if Redis fails |
| **Celery tasks for webhooks** | Already have it | Task ack != delivery guarantee (need custom durability layer) |

**The crux question:** Is the 200ms target total latency to all 12 consumers, or just to get the event published and internal consumers started?

If the former, we may need to rethink the whole approach (webhooks would need to be on a completely separate write path, which they are anyway — just spelled out more clearly). If the latter (which I suspect), the architecture above works.

What's your answer to those three questions?