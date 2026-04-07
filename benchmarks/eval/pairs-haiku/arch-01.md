# Task: arch-01 — Event dispatch for mixed sync/async consumers

## Prompt
You are the lead engineer at a logistics platform called ShipTrack. The platform emits
four event types: `order.created`, `order.shipped`, `order.delivered`, and
`order.exception`. There are 12 consumers of these events:

- 8 internal async consumers (analytics pipeline, inventory updater, ETA predictor,
  fraud scorer, notification dispatcher, audit logger, billing trigger, SLA monitor)
- 4 external synchronous HTTP webhook consumers belonging to enterprise customers
  (FedEx integration, UPS integration, DHL integration, and a customs broker)

The current implementation uses direct function calls in a synchronous loop:

```python
# current_dispatch.py
import requests
import time

WEBHOOK_URLS = {
    "fedex": "https://fedex-partner.example.com/webhook",
    "ups": "https://ups-integration.example.com/events",
    "dhl": "https://dhl-connect.example.com/shiptrack",
    "customs": "https://broker.example.com/api/events",
}
WEBHOOK_TIMEOUT = 10  # seconds

def dispatch_event(event_type: str, payload: dict):
    # Internal consumers
    analytics.process(event_type, payload)
    inventory.update(event_type, payload)
    eta.recalculate(event_type, payload)
    fraud.score(event_type, payload)
    notifications.send(event_type, payload)
    audit.log(event_type, payload)
    billing.trigger(event_type, payload)
    sla.check(event_type, payload)

    # External webhooks — called synchronously
    for name, url in WEBHOOK_URLS.items():
        try:
            resp = requests.post(url, json={"type": event_type, **payload},
                                 timeout=WEBHOOK_TIMEOUT)
            if resp.status_code >= 400:
                logger.warning(f"Webhook {name} returned {resp.status_code}")
        except requests.Timeout:
            logger.error(f"Webhook {name} timed out after {WEBHOOK_TIMEOUT}s")
        except requests.ConnectionError:
            logger.error(f"Webhook {name} connection failed")
```

Current performance numbers:
- Average event dispatch latency: 2.3 seconds (target: < 200ms)
- P99 latency: 12.8 seconds (when a webhook times out)
- Event throughput: ~800 events/hour (need to support 15,000 events/hour by Q3)
- Webhook delivery success rate: 94% (target: 99.5%)
- The DHL webhook frequently takes 6-8 seconds to respond
- During peak hours (2-4 PM UTC), the dispatch queue backs up and internal consumers
  see delays of up to 45 seconds

The enterprise webhook contracts specify:
- Delivery guarantee: at-least-once
- Maximum delivery latency: 60 seconds from event creation
- Retry policy: up to 5 retries with exponential backoff
- Payload ordering: events for the same order must arrive in causal order

Your infrastructure team has approved the use of Kafka, RabbitMQ, or Redis Streams.
They also have an existing async task runner (Celery with Redis broker).

Design the event dispatch architecture. Specify: the messaging topology, how you handle
the sync webhook consumers without blocking the event loop, your retry and ordering
strategy, and how you meet the throughput target.


## Response A
## Architecture: ShipTrack Event Dispatch

The fundamental problem is that 12 consumers share one execution context, and the slowest one (DHL at 6-8s) gates everything else. The fix is **topology separation by consumer contract**: internal consumers need low latency; external webhooks need durability and retries. These are different requirements and should use different infrastructure.

---

### Topology

```
dispatch_event()
      │
      ▼
Kafka (dual publish, < 5ms)
      │                         │
      ▼                         ▼
shiptrack.events         shiptrack.webhooks
(partitioned by order_id)  (partitioned by order_id)
      │                         │
      ▼                         ▼
8 Consumer groups          Kafka→Celery bridge
(each service independent)       │
                           ┌─────┴──────────┐
                           ▼                ▼
                    webhooks.fast     webhooks.dhl
                    (fedex,ups,         (isolated
                     customs)         worker pool)
                           │                │
                           └────────┬───────┘
                                    ▼
                               webhook.dlq → DB + page
```

---

### Producer: Remove sync from critical path

```python
_producer = Producer({"bootstrap.servers": KAFKA_BROKERS, "acks": "all"})

def dispatch_event(event_type: str, payload: dict):
    envelope = {
        "type": event_type,
        "event_id": str(uuid4()),
        "created_at": time.time(),
        **payload,
    }
    order_id = str(payload.get("order_id", "")).encode()

    _producer.produce("shiptrack.events",   key=order_id, value=json.dumps(envelope).encode())
    _producer.produce("shiptrack.webhooks", key=order_id, value=json.dumps(envelope).encode())
    _producer.flush()  # ~2-5ms with linger.ms=5
```

`acks=all` + replication factor 3 means the event is durable before returning. Target: **< 5ms** vs. current 2.3s average.

---

### Internal Consumers: Independent offset tracking

Each of the 8 services runs a standard Kafka consumer in its own process. No logic changes — just replace direct calls with a poll loop:

```python
_consumer = Consumer({"group.id": "analytics", ...})
_consumer.subscribe(["shiptrack.events"])
while True:
    msg = _consumer.poll(1.0)
    if msg and not msg.error():
        analytics.process(msg["type"], msg)
        _consumer.commit(asynchronous=False)
```

Each group has independent offsets. If billing falls behind during a deploy, analytics is unaffected.

---

### Webhook Delivery: Celery with per-destination queue isolation

```python
@app.task(
    bind=True,
    max_retries=5,
    acks_late=True,       # at-least-once: re-enqueue on worker crash
)
def deliver_webhook(self, name: str, payload: dict):
    try:
        resp = requests.post(WEBHOOK_URLS[name], json=payload, timeout=15)
        resp.raise_for_status()
    except (requests.Timeout, requests.ConnectionError, requests.HTTPError) as exc:
        if time.time() - payload["created_at"] > 55:
            deliver_webhook_dlq.apply_async(args=[name, payload, str(exc)])
            return
        # Exponential backoff: 30s → 60s → 120s → 240s → 480s
        raise self.retry(exc=exc, countdown=30 * (2 ** self.request.retries))
```

DHL gets a **dedicated queue and worker pool** (`webhooks.dhl`). This is the critical isolation decision: DHL's 6-8s response time cannot be allowed to queue-starve FedEx/UPS/customs, which respond in < 500ms. Separate queues = separate concurrency budgets.

```python
WEBHOOK_QUEUES = {
    "dhl":     "webhooks.dhl",   # 2 workers, isolated
    "fedex":   "webhooks.fast",
    "ups":     "webhooks.fast",
    "customs": "webhooks.fast",
}
```

---

### Ordering Guarantee

The causal ordering contract is met by a chain of three properties:

1. **Kafka partitioning by `order_id`**: all events for one order land on one partition, consumed in offset order
2. **Bridge publishes tasks sequentially**: one event at a time, commits only after all 4 `apply_async` calls succeed
3. **Celery FIFO queue**: tasks arrive in submission order; workers pull in FIFO order

The one edge case is retry interleaving — if event N fails and retries after event N+1 delivered. Include `sequence_num` (Kafka offset) in the payload; webhook partners can use idempotency keys and reject out-of-order delivery. Document this in the webhook contract.

---

### Technology Choice: Kafka over alternatives

| | Kafka | RabbitMQ | Redis Streams |
|---|---|---|---|
| Native partition ordering | Yes | No (need exclusive consumers) | Yes |
| Independent consumer groups | Yes, built-in | Requires separate queues | Yes |
| Log replay on consumer lag | Yes | No | Limited |
| Throughput at 15k events/hour | Massive headroom | Adequate | Adequate |

Redis Streams would work at this scale, but Kafka's consumer group model maps cleanly to 8 independent services and the ordering guarantee is simpler to reason about. The existing Celery+Redis stack handles webhook retry state, which is where Redis earns its place.

---

### Throughput Math

15,000 events/hour = **4.2 events/second**. This is trivially within capacity:

- Kafka: ~1M msgs/sec capacity
- 4 webhooks × 4.2 events/sec = 16.7 webhook calls/sec
- Celery at `--concurrency=20` × 2 workers = 40 concurrent outbound HTTP requests — 2x headroom even if every call takes 500ms

---

### Expected Metrics After Migration

| Metric | Current | After |
|---|---|---|
| Avg dispatch latency | 2.3s | < 5ms |
| P99 latency | 12.8s | < 10ms |
| Webhook success rate | 94% | > 99.5% |
| Peak internal consumer delay | 45s | < 1s |
| Webhook SLA compliance (60s) | Breached on DHL timeout | Met; DLQ + page on breach |

---

### Migration Path (5 weeks, zero downtime)

1. **Week 1** — Deploy Kafka, dual-write alongside old `dispatch_event`. Validate events appear in both paths.
2. **Week 2** — Migrate internal consumers to Kafka. Remove 8 direct function calls from the loop.
3. **Week 3** — Deploy webhook bridge + Celery workers. Shadow mode: fire webhooks from both paths, compare delivery receipts with partners.
4. **Week 4** — Cut over webhooks to Kafka/Celery path. Remove synchronous webhook loop.
5. **Week 5** — Remove dual-write. Retire old `dispatch_event`.

Each step is independently rollbackable. Partners see no change in payload shape, only improved reliability.

## Response B
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
