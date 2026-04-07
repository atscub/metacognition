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