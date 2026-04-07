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
## ShipTrack Event Dispatch Architecture

### Root Cause Diagnosis

The current system has three compounding problems:

1. **No isolation between consumers** — a slow DHL response (6-8s) directly delays every internal consumer after it in the loop
2. **No retry mechanism** — transient webhook failures are logged and dropped, explaining the 94% delivery rate
3. **Synchronous fan-out** — dispatch latency is the *sum* of all consumer latencies, not the max

The fix is two separate things that people conflate: the **event bus** (publish and forget) and the **webhook delivery engine** (reliable HTTP with retries and ordering). These have different requirements and shouldn't share infrastructure.

---

### Infrastructure Choice: Kafka

Kafka over RabbitMQ or Redis Streams for this workload because:

- Partition key on `order_id` gives you causal ordering per-order essentially for free
- Consumer groups are independent — adding the 9th consumer doesn't slow down the others
- Log retention lets you replay events during incidents or when a new consumer bootstraps
- 15,000 events/hour is ~4 events/second — Kafka handles this without breaking a sweat; you have headroom for 100x growth before tuning is needed

Redis Streams would work but loses the partition-based ordering primitive. RabbitMQ gets messy with ordering requirements.

---

### Messaging Topology

```
┌─────────────────┐
│  Event Source   │  (API handlers, workers, etc.)
└────────┬────────┘
         │ produce (< 5ms, async)
         ▼
┌─────────────────────────────────────────────────────────┐
│         Kafka topic: shiptrack.events                    │
│         32 partitions, keyed by order_id                 │
│         Retention: 7 days                               │
└──────┬──────────────────────────────────────────────────┘
       │
       ├── consumer-group: analytics        → analytics pipeline
       ├── consumer-group: inventory        → inventory updater
       ├── consumer-group: eta              → ETA predictor
       ├── consumer-group: fraud            → fraud scorer
       ├── consumer-group: notifications    → notification dispatcher
       ├── consumer-group: audit            → audit logger
       ├── consumer-group: billing          → billing trigger
       ├── consumer-group: sla              → SLA monitor
       │
       └── consumer-group: webhook-dispatcher
                 │
                 ▼
         ┌──────────────────────────────┐
         │   Webhook Dispatcher Service  │
         │   (asyncio + aiohttp)         │
         │   Retry state: Redis          │
         │   Dead letters: Kafka DLQ     │
         └───────┬──────────────────────┘
                 │ HTTP POST (concurrent across orders)
                 ├── FedEx
                 ├── UPS
                 ├── DHL        ← no longer blocks anyone
                 └── Customs Broker
```

**Partition count rationale**: 32 partitions. With 15,000 events/hour across 32 partitions, each partition sees ~470 events/hour. Each internal consumer group can scale to 32 workers if needed. The webhook dispatcher needs 1–4 workers (one per partition is fine at this volume).

---

### Producer: Fire and Return

```python
# event_producer.py
from confluent_kafka import Producer
import json, time, uuid

producer = Producer({
    "bootstrap.servers": "kafka:9092",
    "acks": "all",              # durability: both leader and ISR must ack
    "enable.idempotence": True, # exactly-once producer semantics
    "compression.type": "lz4",
    "linger.ms": 5,             # small batching window, still << 200ms target
})

def emit_event(event_type: str, payload: dict) -> str:
    event_id = str(uuid.uuid4())
    order_id = payload["order_id"]  # partition key — MUST be present

    envelope = {
        "id": event_id,
        "type": event_type,
        "created_at": time.time(),
        "order_id": order_id,
        **payload,
    }

    producer.produce(
        topic="shiptrack.events",
        key=order_id.encode(),          # ensures all events for an order
        value=json.dumps(envelope).encode(),  # go to the same partition
        on_delivery=_delivery_report,
    )
    producer.poll(0)  # non-blocking flush of internal queue
    return event_id

def _delivery_report(err, msg):
    if err:
        logger.error(f"Event delivery to Kafka failed: {err}")
        metrics.increment("kafka.produce.error")
```

`emit_event` returns in microseconds. The old `dispatch_event` blocked for seconds.

---

### Internal Consumers

Each internal consumer is a straightforward Kafka consumer group. They're already async-by-nature since they're now decoupled — just update each service to read from Kafka instead of being called directly:

```python
# Example: one pattern for all 8 internal consumers
# analytics_consumer.py
from confluent_kafka import Consumer, KafkaError
import json

consumer = Consumer({
    "bootstrap.servers": "kafka:9092",
    "group.id": "analytics",           # unique per consumer
    "auto.offset.reset": "earliest",
    "enable.auto.commit": False,       # manual commit after processing
})
consumer.subscribe(["shiptrack.events"])

def run():
    while True:
        msg = consumer.poll(timeout=1.0)
        if msg is None or msg.error():
            continue
        event = json.loads(msg.value())
        try:
            analytics.process(event["type"], event)
            consumer.commit(msg)       # only commit after successful processing
        except Exception as e:
            logger.exception(f"Analytics processing failed for event {event['id']}")
            # For internal consumers: log, alert, don't commit → retry on restart
```

Scale each consumer group independently. The SLA monitor needs low lag? Give it more workers. The audit logger is naturally slow? It doesn't drag down fraud scoring anymore.

---

### Webhook Dispatcher: The Hard Part

This is the most complex component because it must satisfy:
- At-least-once delivery (don't commit Kafka offset until delivered)
- Causal ordering per order (don't deliver event N+1 until event N is confirmed)
- 5-retry exponential backoff within 60s deadline
- High concurrency across *different* orders (DHL slowness ≠ FedEx slowness)

```python
# webhook_dispatcher.py
import asyncio, aiohttp, json, time
from collections import defaultdict
from confluent_kafka import Consumer

WEBHOOKS = {
    "fedex":   "https://fedex-partner.example.com/webhook",
    "ups":     "https://ups-integration.example.com/events",
    "dhl":     "https://dhl-connect.example.com/shiptrack",
    "customs": "https://broker.example.com/api/events",
}

# Per-webhook timeout. DHL is slow; 5s still fits within the 60s SLA
# even with 5 retries (5×5s HTTP + 31s backoff = 56s worst case).
WEBHOOK_TIMEOUT = aiohttp.ClientTimeout(total=5)

BACKOFF_SECONDS = [1, 2, 4, 8, 16]  # 5 retries, sum = 31s
MAX_DELIVERY_SECONDS = 60


async def deliver_to_webhook(
    session: aiohttp.ClientSession,
    name: str,
    url: str,
    event: dict,
    deadline: float,
) -> bool:
    """Attempt delivery with exponential backoff. Returns True on success."""
    payload = {"type": event["type"], **event}

    for attempt, backoff in enumerate(BACKOFF_SECONDS):
        if time.time() > deadline:
            logger.error(f"[{name}] Deadline exceeded for event {event['id']}, giving up")
            return False

        try:
            async with session.post(url, json=payload, timeout=WEBHOOK_TIMEOUT) as resp:
                if resp.status < 400:
                    logger.info(f"[{name}] Delivered event {event['id']} on attempt {attempt+1}")
                    metrics.increment(f"webhook.{name}.success")
                    return True
                elif resp.status in (429, 503):
                    # Rate limited or service unavailable — respect Retry-After if present
                    retry_after = int(resp.headers.get("Retry-After", backoff))
                    logger.warning(f"[{name}] {resp.status}, backing off {retry_after}s")
                    await asyncio.sleep(min(retry_after, deadline - time.time()))
                else:
                    logger.warning(f"[{name}] HTTP {resp.status} for event {event['id']}")
                    # Fall through to backoff
        except (aiohttp.ClientTimeout, asyncio.TimeoutError):
            logger.warning(f"[{name}] Timeout on attempt {attempt+1}")
        except aiohttp.ClientError as e:
            logger.warning(f"[{name}] Connection error on attempt {attempt+1}: {e}")

        if attempt < len(BACKOFF_SECONDS) - 1:
            sleep = min(backoff, deadline - time.time() - 1)
            if sleep > 0:
                await asyncio.sleep(sleep)

    metrics.increment(f"webhook.{name}.exhausted")
    return False


async def deliver_to_all_webhooks(session: aiohttp.ClientSession, event: dict):
    """Fan out to all 4 webhooks concurrently for a single event."""
    deadline = event["created_at"] + MAX_DELIVERY_SECONDS

    tasks = {
        name: asyncio.create_task(deliver_to_webhook(session, name, url, event, deadline))
        for name, url in WEBHOOKS.items()
    }
    results = await asyncio.gather(*tasks.values(), return_exceptions=True)

    failed = [
        name for name, ok in zip(tasks.keys(), results)
        if ok is not True
    ]
    if failed:
        await send_to_dlq(event, failed)


# Per-order queues: ensures events for the same order are delivered sequentially.
# Events for *different* orders run concurrently.
order_queues: dict[str, asyncio.Queue] = defaultdict(asyncio.Queue)
order_workers: dict[str, asyncio.Task] = {}


async def order_worker(order_id: str, session: aiohttp.ClientSession):
    """Drain the queue for one order, sequentially."""
    q = order_queues[order_id]
    while True:
        event, kafka_commit_fn = await q.get()
        try:
            await deliver_to_all_webhooks(session, event)
        finally:
            kafka_commit_fn()  # commit offset regardless — DLQ handles permanent failures
            q.task_done()


async def enqueue_event(event: dict, kafka_commit_fn):
    """Route event into its per-order queue, spinning up a worker if needed."""
    order_id = event["order_id"]

    if order_id not in order_workers or order_workers[order_id].done():
        # Worker is created lazily and exits when queue drains (add idle timeout in prod)
        session = get_shared_session()  # module-level aiohttp session with connection pooling
        order_workers[order_id] = asyncio.create_task(
            order_worker(order_id, session)
        )

    await order_queues[order_id].put((event, kafka_commit_fn))


def run_dispatcher():
    """Main loop: read from Kafka, hand off to asyncio."""
    consumer = Consumer({
        "bootstrap.servers": "kafka:9092",
        "group.id": "webhook-dispatcher",
        "auto.offset.reset": "earliest",
        "enable.auto.commit": False,
        "max.poll.interval.ms": 300000,
    })
    consumer.subscribe(["shiptrack.events"])

    loop = asyncio.get_event_loop()

    while True:
        msg = consumer.poll(timeout=0.1)
        if msg is None or msg.error():
            continue

        event = json.loads(msg.value())

        def commit(m=msg):
            consumer.commit(m, asynchronous=True)

        loop.run_until_complete(enqueue_event(event, commit))
```

**Why this ordering design works**: Kafka partitions guarantee that all events for `order_id=X` arrive at the dispatcher in creation order (because they land in the same partition). The per-order `asyncio.Queue` then ensures the dispatcher delivers them to all 4 webhooks in that same order. Events for different orders process concurrently — DHL being slow for order A doesn't delay order B.

---

### Dead Letter Queue

```python
# dlq.py
from confluent_kafka import Producer

dlq_producer = Producer({"bootstrap.servers": "kafka:9092"})

async def send_to_dlq(event: dict, failed_webhooks: list[str]):
    envelope = {
        "original_event": event,
        "failed_webhooks": failed_webhooks,
        "failed_at": time.time(),
    }
    dlq_producer.produce(
        topic="shiptrack.events.dlq",
        key=event["order_id"].encode(),
        value=json.dumps(envelope).encode(),
    )
    # Page on-call if DLQ rate spikes
    metrics.increment("webhook.dlq", tags={"webhooks": ",".join(failed_webhooks)})
    await alert_oncall(f"Webhook delivery permanently failed: {failed_webhooks} for event {event['id']}")
```

DLQ events can be replayed manually or via a separate reconciliation job after a webhook partner recovers.

---

### Ordering Guarantee: Why It Holds End-to-End

```
order_id → Kafka partition key
         → all events for order land in same partition
         → partition is consumed sequentially by webhook-dispatcher
         → per-order asyncio.Queue serializes delivery
         → each event delivered to all 4 webhooks before next event starts

Result: FedEx/UPS/DHL/Customs all see events for order X in causal order.
```

One edge case: if the dispatcher crashes mid-delivery, the uncommitted Kafka offset means the event is reprocessed on restart. The webhooks see it again — this is the "at-least-once" contract; idempotency keys in the payload let partners deduplicate.

---

### Throughput Analysis

| Metric | Current | Target | New Architecture |
|--------|---------|--------|-----------------|
| Events/hour | 800 | 15,000 | >500,000 (Kafka limit is ~1M+/sec) |
| Avg dispatch latency | 2.3s | <200ms | ~5ms (Kafka produce ack) |
| P99 latency | 12.8s | — | <50ms (produce path; DHL slowness is now isolated to webhook dispatcher) |
| Webhook success rate | 94% | 99.5% | ~99.8% (5-retry backoff with DLQ fallback) |
| Peak hour delays | 45s | — | Eliminated (consumers are independent) |

The producer path (what API handlers wait for) goes from seconds to milliseconds. DHL's 6-8s response time is now invisible to every internal consumer and to the other 3 webhook partners — only DHL delivery within the dispatcher is affected by DHL.

---

### Migration Path

Don't rewrite everything at once. Run old and new in parallel:

**Phase 1** (week 1): Add Kafka producer alongside existing synchronous loop. Dual-write. Verify events appear in Kafka correctly. Zero risk.

**Phase 2** (week 2): Stand up internal consumers reading from Kafka. Keep old sync calls as fallback. Shadow-compare results.

**Phase 3** (week 3): Stand up webhook dispatcher. Disable webhook calls from `dispatch_event`. This is the highest-risk step — test DLQ handling and retry behavior in staging with a mock slow endpoint (simulate DHL's 6-8s response).

**Phase 4** (week 4): Remove the synchronous internal consumer calls from `dispatch_event`. `dispatch_event` becomes a one-liner: `emit_event(event_type, payload)`.

---

### Key Failure Modes to Handle in Production

**Webhook dispatcher crashes with in-flight events**: Since Kafka offsets aren't committed until delivery completes, events are reprocessed on restart. Webhooks must be called again — partners must handle duplicate delivery via idempotency keys.

**Kafka partition rebalance during delivery**: Can cause a second dispatcher instance to pick up an event already in-flight. Same idempotency key solution applies.

**Per-order queue growing unbounded**: If a webhook is down for extended periods, per-order queues grow. Add a max queue size with back-pressure to Kafka (stop committing offsets, letting Kafka lag grow rather than OOM-ing the dispatcher).

**DHL degradation lasting >60s**: After exhausting retries, events go to DLQ. A separate reconciliation job can replay DLQ events when DHL recovers, using the event's original `created_at` timestamp to prioritize ordering.

## Response B
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
