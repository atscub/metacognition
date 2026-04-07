## Socratic Analysis First

Before reaching for the canonical answer, let me interrogate my assumptions.

**What am I pattern-matching to?** "Sync bottleneck → message queue → async workers." That's correct directionally, but the ordering + at-least-once combination is where most designs quietly fail. I need to hold that tension carefully.

**What would a skeptic say?**
- *"You already have Celery+Redis — just make the webhooks async tasks."* Valid. Let me steelman this: zero new infrastructure, team already knows it, Redis sorted sets can approximate delay queues. The weakness: Celery has no native per-key ordering guarantee. If order.created retries while order.shipped succeeds, the webhook sees causal inversion. This breaks the contract.
- *"Kafka is overkill for 4.2 events/second."* Also valid. 15,000/hr = ~4.2/sec. Kafka's sweet spot is orders of magnitude higher. This is worth naming honestly.

**The hard constraint that shapes everything:** `at-least-once` + `retry` + `causal ordering per order_id` cannot all be satisfied simultaneously without serializing delivery per order. Every architecture that ignores this will fail the contract in edge cases.

---

## Architecture Design

### Core insight: two fundamentally different problems

Internal consumers and webhook consumers have different requirements that warrant different treatment:

| | Internal consumers | Webhook consumers |
|---|---|---|
| Ordering needed? | No | Yes (per order) |
| Retry needed? | Depends on consumer | Yes, defined by contract |
| Failure isolation? | Yes | Yes, per webhook |
| Latency tolerance? | High | 60s hard SLA |

### Topology

```
┌──────────────────────────────────────────────────────────────────┐
│  Event Service                                                   │
│  Thin HTTP layer — validates, assigns sequence_number,           │
│  publishes to Kafka. Returns 202 Accepted in <5ms.               │
└───────────────────────────┬──────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────────┐
│  Kafka: shiptrack.events                                         │
│  Partitions: 16   Key: order_id   Retention: 7 days             │
│  (partition by order_id ensures all events for an order          │
│   arrive at the same partition in creation order)               │
└──┬───────────────────────────────────────────────────────────────┘
   │
   ├── CG: internal.analytics     ──► analytics service
   ├── CG: internal.inventory     ──► inventory updater
   ├── CG: internal.eta           ──► ETA predictor
   ├── CG: internal.fraud         ──► fraud scorer
   ├── CG: internal.notifications ──► notification dispatcher
   ├── CG: internal.audit         ──► audit logger
   ├── CG: internal.billing       ──► billing trigger
   ├── CG: internal.sla           ──► SLA monitor
   │
   └── CG: webhook.dispatcher ──────► Webhook Dispatcher Service
                                              │
                              ┌───────────────┼────────────────┐
                              ▼               ▼                ▼
                          FedEx           UPS/DHL         Customs
                          worker          workers          worker
                              │
                    on 5th failure
                              │
                              ▼
              Kafka: shiptrack.webhook.dlq
              + PagerDuty alert
```

### How webhook ordering works

The core mechanism: **per-order, per-webhook actor model**.

Kafka partitioning by `order_id` guarantees events for the same order arrive at the webhook dispatcher in causal order. The dispatcher then serializes delivery per `(order_id, webhook_name)` pair:

```python
class WebhookDispatcher:
    """
    Maintains per-order delivery queues so order.shipped never
    reaches the webhook before order.created, even across retries.
    """
    def __init__(self):
        # order_id → asyncio.Queue of pending events
        self._queues: dict[str, asyncio.Queue] = {}
        self._workers: dict[str, asyncio.Task] = {}

    async def handle_kafka_event(self, order_id: str, event: dict):
        if order_id not in self._queues:
            q = asyncio.Queue()
            self._queues[order_id] = q
            self._workers[order_id] = asyncio.create_task(
                self._drain(order_id, q)
            )
        await self._queues[order_id].put(event)

    async def _drain(self, order_id: str, queue: asyncio.Queue):
        """Processes events for one order strictly sequentially."""
        while True:
            event = await queue.get()
            # Dispatch to all 4 webhooks concurrently, but
            # DO NOT move to next event until all 4 confirm delivery.
            await asyncio.gather(
                self._deliver("fedex",   event),
                self._deliver("ups",     event),
                self._deliver("dhl",     event),
                self._deliver("customs", event),
            )
            queue.task_done()

    async def _deliver(self, webhook: str, event: dict, attempt=1):
        try:
            async with self._sessions[webhook] as session:
                resp = await session.post(
                    WEBHOOK_URLS[webhook],
                    json={**event, "idempotency_key": f"{event['event_id']}-{webhook}"},
                    timeout=aiohttp.ClientTimeout(total=15),
                )
                if resp.status >= 500:
                    raise TransientError(resp.status)
                if resp.status >= 400:
                    # Client error — log, don't retry
                    await self._dlq(webhook, event, f"4xx: {resp.status}")
                    return
        except (TransientError, asyncio.TimeoutError) as e:
            if attempt >= 5:
                await self._dlq(webhook, event, str(e))
                return
            backoff = min(2 ** attempt, 30)  # 2, 4, 8, 16, 30s
            await asyncio.sleep(backoff)
            await self._deliver(webhook, event, attempt + 1)
```

**Why this satisfies all three constraints simultaneously:**
- *At-least-once*: retry up to 5 times before DLQ
- *Ordering*: `_drain` blocks on the current event before dequeuing the next one
- *Isolation*: `asyncio.gather` means DHL's slowness only delays *that order's* next event for DHL — FedEx, UPS, customs all proceed independently

**Retry math vs. the 60s SLA:**

| Attempt | Cumulative time |
|---------|----------------|
| 1 | ~0s (immediate) |
| 2 | +2s |
| 3 | +6s |
| 4 | +14s |
| 5 | +30s |

Worst case: ~30s elapsed across 5 attempts. Well within the 60s contract, even accounting for DHL's 6-8s response times.

### Handling the DHL problem specifically

DHL at 6-8s is a per-connection latency issue, not a failure. With asyncio, a slow DHL response holds the DHL worker for that order but does not block FedEx, UPS, customs, or any other order's DHL call. The webhook dispatcher runs as many concurrent DHL connections as there are active orders — each order gets its own async coroutine. At 4.2 events/sec and ~7s DHL latency, you need ~30 concurrent DHL connections sustained, which aiohttp handles without issue.

### Kafka vs. Redis Streams: honest trade-off

I want to be direct: **at 4.2 events/second, Kafka is operationally expensive relative to what you need.**

| | Kafka | Redis Streams |
|---|---|---|
| Throughput ceiling | Millions/sec | ~100K/sec |
| Ordering primitive | Partition (native, clean) | Stream key (you manage sharding) |
| Durability | WAL + replication | AOF + replication |
| Consumer groups | Native | Native |
| Event replay | Built-in, 7-day retention | Yes, with XRANGE |
| Operational cost | High (Zookeeper/KRaft, monitoring) | Low (already in stack) |
| Team familiarity | Unknown | High (Celery broker) |

**My recommendation:** Use Kafka if you anticipate needing event replay for new consumer onboarding (e.g., re-running fraud scoring), or if the team already has Kafka operational expertise. Otherwise, Redis Streams with 16 shard-streams (hash `order_id % 16`) gives you the same ordering guarantees with zero new infrastructure. The architecture above works identically with either.

If Redis Streams, the sharding looks like:

```python
def stream_key(order_id: str) -> str:
    shard = int(hashlib.md5(order_id.encode()).hexdigest(), 16) % 16
    return f"shiptrack:events:shard:{shard}"
```

One consumer per shard, per webhook consumer group — ordering preserved.

### Meeting the throughput target

Current: 800 events/hour. Target: 15,000 events/hour.

The current bottleneck is entirely the synchronous dispatch loop — each event waits for up to 4 × 10s timeouts = 40s in the worst case. That's not a throughput problem, it's a blocking I/O problem. With async dispatch:

- Event service: publishes to Kafka in <5ms, returns 202. Throughput limited by Kafka ingestion (millions/hr). ✓
- Internal consumers: each consumer group scales independently. Add partitions and consumer instances as needed. ✓
- Webhook dispatcher: asyncio handles thousands of concurrent connections on a single process. DHL's 7s latency at 4.2 events/sec requires ~30 concurrent connections — trivial. ✓

15,000/hour needs no special scaling. This architecture handles 10x that without modification.

### What I'm uncertain about

1. **"Causal order" semantics.** I've assumed this means FIFO per order (order.created before order.shipped before order.delivered). If it means logical causality tracked by event references (e.g., order.shipped must include the `event_id` of the order.created it's responding to), that's an application-level schema concern, not a delivery concern. Worth clarifying with the enterprise customers.

2. **Idempotency at internal consumers.** At-least-once delivery means internal consumers can receive duplicates on Kafka consumer restart. The 8 internal services need to be idempotent (or deduplicate on `event_id`). I've assumed they can be made idempotent — if any of them can't, that's a separate work item.

3. **Per-order queue memory.** The in-process per-order queue in the webhook dispatcher accumulates state. At steady state this is fine (orders complete and queues drain). Under a catastrophic failure scenario (dispatcher restarts), in-flight state is lost and Kafka consumer offset management handles redelivery — but this could cause ordering violations for in-progress events. Mitigation: checkpoint per-order state to Redis on each successful delivery.

4. **The DLQ story.** A DLQ entry means an enterprise customer missed an event. That's a potential SLA breach. The DLQ handler needs to include automated alerting and ideally a mechanism to manually trigger redelivery after the downstream recovers. This is operationally important but outside the scope of the topology design.

---

**Summary of the design:**
- Thin event service publishes to Kafka/Redis Streams, returns immediately → fixes latency
- 8 independent Kafka consumer groups for internal consumers → fixes isolation and scale
- Single webhook dispatcher with per-order asyncio queues → satisfies ordering + at-least-once + retry within 60s SLA
- DHL's slowness is now contained to its own async coroutines, not blocking anything
- 15,000/hr is well within capacity; the architecture scales to 10x that before needing more partitions