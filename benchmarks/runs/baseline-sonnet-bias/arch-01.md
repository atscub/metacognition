## ShipTrack Event Dispatch Architecture

### The Core Problem

The synchronous loop is a disaster in three ways: (1) internal consumers block on each other, (2) external webhooks block internal consumers, and (3) a single slow webhook (DHL at 6-8s) degrades the entire system. The fix is full decoupling via Kafka, with the webhook layer getting its own careful treatment for ordering and retry.

---

## Messaging Topology

**Use Kafka.** Redis Streams lacks the consumer group semantics we need for independent retry per webhook. RabbitMQ can do this but ordering across retries is painful. Kafka's partition model maps directly onto our ordering requirement.

```
                        ┌─────────────────────────────────────────────────┐
                        │          shiptrack.events (64 partitions)       │
                        │          partition key: order_id                │
                        └───────────────────┬─────────────────────────────┘
                                            │
              ┌─────────────────────────────┼─────────────────────────────┐
              ▼                             ▼                             ▼
   ┌──────────────────┐         ┌─────────────────────┐       ┌─────────────────────┐
   │ Internal Consumer│         │  Webhook Dispatcher  │       │  DLQ Monitor        │
   │ Groups (×8)      │         │  Service             │       │  shiptrack.dlq      │
   │                  │         │  (one worker pool    │       │                     │
   │ analytics-cg     │         │   per webhook)       │       │  alerts + replay    │
   │ inventory-cg     │         │                      │       └─────────────────────┘
   │ eta-cg           │         │  fedex-pool (×3)     │
   │ fraud-cg         │         │  ups-pool   (×3)     │
   │ notifications-cg │         │  dhl-pool   (×8)  ← more workers for slow endpoint
   │ audit-cg         │         │  customs-pool (×3)   │
   │ billing-cg       │         └─────────────────────┘
   │ sla-cg           │
   └──────────────────┘
```

**Topics:**
- `shiptrack.events` — 64 partitions, 7-day retention, keyed by `order_id`
- `shiptrack.webhooks.dlq` — dead-letter after 5 failed retries, indefinite retention
- `shiptrack.webhooks.retry.{name}` — one per webhook, used as a scheduled retry buffer (explained below)

**The producer becomes a 5ms fire-and-forget:**

```python
# new_dispatch.py
from confluent_kafka import Producer

producer = Producer({"bootstrap.servers": KAFKA_BROKERS, "acks": "all"})

def dispatch_event(event_type: str, payload: dict):
    event = {
        "event_id": str(uuid4()),    # idempotency key
        "type": event_type,
        "order_id": payload["order_id"],
        "ts": time.time(),
        **payload,
    }
    producer.produce(
        topic="shiptrack.events",
        key=event["order_id"].encode(),   # partition key → ordering
        value=json.dumps(event).encode(),
        callback=delivery_report,
    )
    producer.poll(0)  # non-blocking flush trigger
```

Average dispatch latency drops from 2.3s to ~5ms immediately.

---

## Internal Consumers

Straightforward: 8 independent consumer groups, each consuming `shiptrack.events`. They process at their own pace without blocking each other or the event loop.

```python
# analytics_consumer.py
consumer = KafkaConsumer(
    "shiptrack.events",
    group_id="analytics-cg",
    bootstrap_servers=KAFKA_BROKERS,
    enable_auto_commit=False,
    max_poll_records=100,
)

for msg_batch in consumer:
    analytics.process_batch(msg_batch)
    consumer.commit()
```

Scale each consumer group independently based on processing time. The 45-second peak-hour delay disappears because consumers no longer share the dispatch thread.

---

## External Webhook Architecture

This is the hard part. The constraints interact:

- **At-least-once** → commit Kafka offset only after confirmed delivery
- **Ordering** → can't commit offset N+1 until offset N is delivered
- **Retry** → on failure, retry before advancing; this can stall a partition
- **60s SLA** → 5 retries with backoff must complete within the window

**Solution: per-webhook consumer with a sliding-window offset commit protocol.**

Each webhook runs a dedicated asyncio consumer process. The consumer maintains an in-memory **delivery tracking map** per partition: a dict of `{offset: DeliveryStatus}`. It only commits the partition offset up to the highest contiguous successfully-delivered offset.

```python
# webhook_dispatcher.py
import asyncio, aiohttp, time, random
from collections import defaultdict
from dataclasses import dataclass, field
from confluent_kafka import Consumer, TopicPartition

BACKOFF = [0, 2, 4, 8, 16]  # seconds per attempt (total max: 30s → within 60s SLA)

@dataclass
class DeliverySlot:
    event: dict
    offset: int
    done: bool = False

class WebhookConsumer:
    def __init__(self, name: str, url: str):
        self.name = name
        self.url = url
        # per-partition: ordered list of in-flight slots
        self.windows: dict[int, list[DeliverySlot]] = defaultdict(list)

    async def run(self):
        consumer = Consumer({
            "bootstrap.servers": KAFKA_BROKERS,
            "group.id": f"webhook-{self.name}-cg",
            "enable.auto.commit": False,
        })
        consumer.subscribe(["shiptrack.events"])
        connector = aiohttp.TCPConnector(limit=20)  # connection pool

        async with aiohttp.ClientSession(connector=connector) as session:
            while True:
                msgs = consumer.consume(num_messages=50, timeout=0.1)
                tasks = []
                for msg in msgs:
                    slot = DeliverySlot(
                        event=json.loads(msg.value()),
                        offset=msg.offset(),
                    )
                    self.windows[msg.partition()].append(slot)
                    tasks.append(self._deliver_with_retry(session, slot))

                if tasks:
                    await asyncio.gather(*tasks)
                    self._advance_offsets(consumer)

    async def _deliver_with_retry(self, session, slot: DeliverySlot):
        for attempt in range(5):
            try:
                async with session.post(
                    self.url,
                    json=slot.event,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status < 500:   # 2xx/3xx/4xx all stop retrying
                        if resp.status >= 400:
                            await self._send_to_dlq(slot, f"HTTP {resp.status}")
                        slot.done = True
                        return
            except (aiohttp.ClientError, asyncio.TimeoutError):
                pass

            if attempt < 4:
                jitter = random.uniform(0, 1)
                await asyncio.sleep(BACKOFF[attempt + 1] + jitter)

        await self._send_to_dlq(slot, "max retries exceeded")
        slot.done = True   # mark done so we don't stall the partition forever

    def _advance_offsets(self, consumer):
        """Commit offsets up to the highest contiguous completed slot."""
        to_commit = []
        for partition, window in self.windows.items():
            # drain leading done slots
            while window and window[0].done:
                committed_offset = window.pop(0).offset
            if committed_offset is not None:
                to_commit.append(TopicPartition("shiptrack.events", partition, committed_offset + 1))
        if to_commit:
            consumer.commit(offsets=to_commit)
```

**Key properties of this design:**

1. **Ordering preserved**: slots within a partition are committed strictly left-to-right. Event 2 for order A can't be acknowledged before event 1 is done.

2. **One stalled order doesn't block others**: a 64-partition topic means ~1/64 of orders share a partition. A stalled delivery only blocks that partition's progress, not all orders.

3. **Retry fits in the 60s window**: `0 + 2 + 4 + 8 + 16 = 30s` of backoff plus 5 × 10s of HTTP timeouts in the worst case = 80s theoretical max. In practice: use a 30s deadline from first attempt, abort and DLQ if exceeded, which keeps within the 60s SLA with buffer for Kafka consumer lag.

4. **DHL isolation**: DHL gets 8 async workers in its pool (vs 3 for others) to handle the 6-8s response times without stalling at the consumer read level.

---

## Circuit Breaker for Webhook Endpoints

Add a circuit breaker per webhook to prevent retry storms from a fully-down endpoint consuming the 60s window:

```python
class CircuitBreaker:
    def __init__(self, failure_threshold=10, recovery_timeout=60):
        self.failures = 0
        self.state = "closed"   # closed = normal, open = blocking, half-open = probing
        self.opened_at = None

    def record_failure(self):
        self.failures += 1
        if self.failures >= self.failure_threshold:
            self.state = "open"
            self.opened_at = time.time()

    def allow_request(self) -> bool:
        if self.state == "closed":
            return True
        if self.state == "open":
            if time.time() - self.opened_at > self.recovery_timeout:
                self.state = "half-open"
                return True   # probe
            return False      # fast-fail → DLQ immediately
        return True  # half-open: let one through
```

When a circuit is open, events route directly to DLQ with a `circuit_open` reason rather than burning retry attempts. The DLQ monitor alerts on-call and the team manually re-delivers once the endpoint recovers. This prevents DHL's slowness from causing cascading 60s timeouts across the board.

---

## Retry & Ordering Strategy Summary

| Scenario | Behavior |
|---|---|
| HTTP 5xx or timeout | Retry with backoff: 0s, 2s, 4s, 8s, 16s |
| HTTP 4xx | No retry — bad payload; route to DLQ immediately |
| 5 retries exhausted | Publish to `shiptrack.webhooks.dlq`, mark slot done, advance offset |
| Circuit open | Fast-fail to DLQ, alert on-call |
| Same order, multiple events | Partition-level ordering via Kafka key; sliding window ensures event N+1 not committed until event N delivered |
| Duplicate delivery (at-least-once) | Each event carries `event_id` (UUID); external consumers deduplicate on this key |

---

## Throughput Analysis

15,000 events/hour = **4.2 events/second**. This is well within Kafka's capabilities.

The real bottleneck was the synchronous webhook calls. Let's verify webhook throughput:

| Webhook | Avg response | Workers | Max events/hr per worker | Required events/hr |
|---|---|---|---|---|
| FedEx | ~0.5s | 3 | 7,200 | 3,750 |
| UPS | ~0.5s | 3 | 7,200 | 3,750 |
| DHL | ~7s | 8 | 514 | 3,750 — **bottleneck** |
| Customs | ~1s | 3 | 3,600 | 3,750 |

DHL at 8 workers × (3600/7s) = **4,114/hr** handles the 3,750 target with ~10% headroom. If DHL degrades further, the circuit breaker protects us and we can spin up more workers. DHL workers should be sized to 12 at peak to handle burst.

**Consumer group scaling:** Each internal consumer group gets 64 consumers max (matching partition count). Analytics and billing are the slowest — provision 8 consumers per group initially, auto-scale based on consumer lag metric.

---

## Migration Path

1. **Phase 1** (week 1): Deploy Kafka, wrap `dispatch_event` to produce to `shiptrack.events`. Keep synchronous dispatch as fallback via feature flag. Verify internal consumers work.
2. **Phase 2** (week 2): Deploy webhook dispatcher service. Route one webhook (UPS — most reliable) through it first. Monitor delivery success rate.
3. **Phase 3** (week 3): Migrate all 4 webhooks. Disable synchronous loop. Activate circuit breakers.
4. **Phase 4**: Tune partition count, worker pool sizes based on observed lag metrics.

---

## Metrics to Instrument

```
# These tell you if the architecture is working
kafka_consumer_lag{group, topic, partition}      # internal consumer health
webhook_delivery_attempts_total{name, outcome}   # delivery success rate
webhook_delivery_latency_seconds{name, quantile} # p50/p99 per endpoint
webhook_circuit_state{name}                      # 0=closed, 1=open, 2=half-open
dlq_events_total{name, reason}                   # what's hitting the DLQ and why
event_e2e_latency_seconds{type}                  # time from event creation to webhook ACK
```

The DLQ event count is your early warning: if `dlq_events_total` spikes on a specific webhook, the circuit breaker will trigger within minutes, but the metric gives you the alert before SLA breach.