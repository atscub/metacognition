## Socratic Protocol: Working Through the Decision

Before recommending anything, I need to interrogate my own assumptions. Let me do that visibly.

---

### Step 1: What am I assuming — and which assumptions are wrong?

**Assumption 1: "This is a throughput problem."**

Let me check the actual numbers.

```
Peak load: 120 orders/minute = 2 orders/second

Pipeline messages per order: ~5 stages + retries ≈ 8–10 messages
Peak message rate: ~20 messages/second

RabbitMQ capacity:  30,000 msg/s → we'd use 0.07% of capacity
Redis Streams:     100,000 msg/s → we'd use 0.02% of capacity
Kafka:             100,000 msg/s → we'd use 0.02% of capacity
```

**This is not a throughput problem.** None of these systems will break a sweat. The "can RabbitMQ handle flash sale volumes?" concern is almost certainly wrong. 120 orders/minute is hobby-project load for any modern message broker.

The actual problem is **web tier coupling**: 50 threads × 2.1s processing = ~24 concurrent orders before 503s. The fix is decoupling HTTP response from processing — accept fast, enqueue, return `202 Accepted`. That's architecture, not throughput.

**Assumption 2: "Kafka is the serious choice; the others are compromises."**

This is anchoring bias. Kafka is designed for hundreds of thousands of messages per second, replicated across data centers, with 30-day log retention. At 20 messages/second, Kafka is a freight train to carry a loaf of bread. Amazon MSK starts at ~$0.21/hour *before* data transfer. The operational surface area of Kafka (topic management, consumer group rebalancing, offset management, schema registry, lag monitoring) is non-trivial even managed. "We don't have a Kafka team" is not a minor concern — it is the correct concern.

**Assumption 3: "Redis is unreliable for order data."**

This needs scrutiny. Redis Streams with AOF persistence (`appendfsync always`) is durable. Consumer groups with the Pending Entry List (PEL) provide at-least-once delivery — unacknowledged messages survive consumer crashes. The real risk is using the *same* Redis cluster for caching and queuing: a cache memory pressure event causing evictions could touch queue data. A **separate** Redis instance for queuing is durable and reliable at this scale.

**Assumption 4: "The inventory parallelism problem requires complex fan-out queue topology."**

Let me think about this more carefully. The current code does warehouse reservations *sequentially* in a single thread. The simplest fix is `asyncio.gather()` *within a single stage consumer* — you don't need a separate queue layer for the parallelism. The queue manages stage transitions; concurrency within a stage is an application concern.

---

### Step 2: Steelman each option at its strongest

**Kafka's best case**: If CartNova grows 100x, and if they hire engineers who know Kafka, and if they need multi-datacenter replication, Kafka's design pays off. Every other concern is manageable. Amazon MSK genuinely does reduce ops burden. Kafka's consumer group model scales linearly.

**RabbitMQ's best case**: Dead-letter exchanges (DLX) are first-class and well-documented. Exchange routing handles stage transitions natively. They *already run it*. Amazon MQ removes the managed-service concern. The team knows it. Adding order processing to an existing, trusted system beats introducing new infrastructure.

**Redis Streams' best case**: Simplest API (`XADD`, `XREADGROUP`, `XACK`). Already have a cluster. No AMQP protocol overhead. PEL gives at-least-once for free. XPENDING shows stuck messages operationally. If you use a separate cluster with AOF, it's genuinely reliable.

---

### Step 3: What would change my mind?

- If the team had zero RabbitMQ experience, I'd weight Redis Streams higher.
- If the throughput target were 120,000 orders/minute (not 120), I'd weight Kafka heavily.
- If the team was already running Kafka for another service, the "no Kafka team" concern evaporates.
- If Redis memory eviction policies on the existing cluster were misconfigured and couldn't be changed, I'd be more skeptical of Redis Streams even on a separate cluster.

---

### Step 4: The crux

The decision is not about throughput — all three options are equivalent there. It's about:

1. **Operational risk** of introducing new infrastructure vs. extending existing
2. **Fit of the routing model** to the stage pipeline
3. **First-class DLQ and retry support**
4. **Idempotency requirements** (real, regardless of choice)

---

## Recommendation: RabbitMQ via Amazon MQ

**Primary choice, with Redis Streams as a well-reasoned alternative.**

### Why not Kafka

At 2 orders/second peak, Kafka's throughput advantage is irrelevant. The operational complexity is real. Amazon MSK reduces it but doesn't eliminate it: topic/partition design, consumer group rebalancing, offset lag monitoring, and schema management still need owners. The team doesn't have them. This is not risk-aversion — it is correctly calibrated cost/benefit. Kafka earns its complexity at scale. You don't have that scale.

### Why RabbitMQ wins over Redis Streams

| Criterion | RabbitMQ | Redis Streams |
|---|---|---|
| DLQ support | First-class (DLX) | DIY (XPENDING + manual move) |
| Stage routing | Native (exchange bindings) | App-layer logic |
| Retry with backoff | TTL + DLX pattern, well-documented | DIY |
| Operations familiarity | Already running it | Need new patterns |
| Ordering | Single queue = ordered | Single stream = ordered |
| Monitoring | Management UI built in | XPENDING, XINFO (CLI-heavy) |

The clincher: RabbitMQ's dead-letter exchange pattern maps directly to the retry/DLQ requirement. Redis Streams requires you to implement DLQ logic yourself by inspecting XPENDING and moving messages — it works, but it's application code that can have bugs.

---

## Queue Topology

```
Web Tier (ECS)
    │
    │ HTTP POST /orders → 202 Accepted immediately
    ▼
[orders.intake queue]
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│ Stage Queues (each with its own DLX binding)            │
│                                                         │
│  orders.fraud-check ──→ orders.payment-capture          │
│                    ──→ orders.flagged (terminal)         │
│                                                         │
│  orders.payment-capture ──→ orders.inventory-reserve   │
│                                                         │
│  orders.inventory-reserve ──→ orders.fulfillment       │
│                                                         │
│  orders.fulfillment ──→ orders.shipping                │
│                                                         │
│  orders.shipping ──→ orders.completed (terminal)       │
└─────────────────────────────────────────────────────────┘
         │ (on any failure, after 5 retries)
         ▼
[orders.dead-letter] ←── all stage DLXes route here
```

**Exchange design:**

```
orders.direct (direct exchange)
  routing key "fraud-check"       → orders.fraud-check queue
  routing key "payment-capture"   → orders.payment-capture queue
  routing key "inventory-reserve" → orders.inventory-reserve queue
  routing key "fulfillment"       → orders.fulfillment queue
  routing key "shipping"          → orders.shipping queue

orders.dlx (fanout exchange)
  → orders.dead-letter queue (all failed messages land here)
```

Each stage queue is declared with:
```python
arguments={
    "x-dead-letter-exchange": "orders.dlx",
    "x-dead-letter-routing-key": "dead"
}
```

---

## Per-Order Ordering

**The key insight**: You don't need to partition by `order_id`. Ordering is enforced by the pipeline contract — a consumer only publishes stage N+1 after stage N succeeds and returns. There is no race condition between stage 2 and stage 3 for the same order because stage 3's message doesn't exist until stage 2's consumer emits it.

What this means:
- Multiple consumers per stage queue is safe
- No need for consistent hashing or sticky routing
- Scale each stage consumer pool independently

```python
# Stage consumer pattern — enforces ordering by construction
class FraudCheckConsumer:
    def process(self, message: Order) -> None:
        result = fraud_service.check(message)

        if result.flagged:
            channel.basic_publish(
                exchange="orders.direct",
                routing_key="flagged",
                body=serialize(message)
            )
        else:
            # Only emitted after fraud check succeeds — this IS the ordering guarantee
            channel.basic_publish(
                exchange="orders.direct",
                routing_key="payment-capture",
                body=serialize(message)
            )

        channel.basic_ack(delivery_tag=message.delivery_tag)
```

**Idempotency is mandatory.** At-least-once delivery means retries will reprocess messages. Every stage consumer must be idempotent:

```python
class PaymentCaptureConsumer:
    def process(self, order: Order) -> None:
        # Check before acting — idempotency guard
        existing = db.query(
            "SELECT id FROM payments WHERE order_id = %s AND status = 'captured'",
            order.order_id
        )
        if existing:
            # Already captured — safe to ack and emit next stage
            self.emit_next_stage(order)
            return

        payment = payment_service.capture(order)
        db.insert("payments", {...})
        self.emit_next_stage(order)
```

This applies to every stage. Inventory reservation checks if already reserved. Shipping booking checks for existing tracking ID.

---

## Per-Warehouse Parallel Inventory Reservation

Handle this **within the inventory stage consumer**, not with separate queues. Fan-out queues for sub-tasks add complexity without benefit at this scale.

```python
class InventoryReserveConsumer:
    async def process(self, order: Order) -> None:
        # Group items by warehouse
        by_warehouse = defaultdict(list)
        for item in order.items:
            by_warehouse[item.warehouse].append(item)

        # Parallel reservation — each warehouse call is ~300ms
        # With 1.5 avg warehouses: total ≈ 300ms, not 900ms
        tasks = [
            self.reserve_warehouse(warehouse, items, order.order_id)
            for warehouse, items in by_warehouse.items()
        ]

        try:
            results = await asyncio.gather(*tasks, return_exceptions=False)
        except InventoryError as e:
            # Let the retry/DLQ mechanism handle it
            # Partial reservations must be compensated
            await self.compensate_partial_reservations(order.order_id)
            raise  # RabbitMQ will redeliver after nack

        # All warehouses succeeded — proceed
        self.emit_fulfillment(order, results)

    async def reserve_warehouse(self, warehouse: str, items: list, order_id: str):
        # Idempotency: check if already reserved
        existing = db.query(
            "SELECT * FROM reservations WHERE order_id = %s AND warehouse = %s",
            order_id, warehouse
        )
        if existing:
            return existing

        return await inventory_service.reserve(warehouse, items, order_id)
```

This drops inventory stage latency from 900ms (3 items × 300ms sequential) to ~300ms (all warehouses parallel). No queue complexity needed.

---

## Retry with Exponential Backoff + DLQ

Use RabbitMQ's TTL + DLX pattern. No plugins required:

```python
RETRY_DELAYS_MS = [30_000, 60_000, 120_000, 240_000, 480_000]  # 5 attempts

def handle_failure(channel, message: Order, stage: str, error: Exception):
    retry_count = message.headers.get("x-retry-count", 0)

    if retry_count >= 5:
        # Exhausted retries — send to dead-letter for human review
        channel.basic_publish(
            exchange="orders.dlx",
            routing_key="dead",
            body=serialize(message),
            properties=pika.BasicProperties(
                headers={
                    **message.headers,
                    "x-failed-stage": stage,
                    "x-final-error": str(error),
                    "x-exhausted-at": datetime.utcnow().isoformat(),
                }
            )
        )
        channel.basic_ack(delivery_tag=message.delivery_tag)
        return

    delay_ms = RETRY_DELAYS_MS[retry_count]

    # Publish to per-stage retry queue with TTL
    # TTL expiry routes back to original stage queue via DLX
    channel.basic_publish(
        exchange="",  # default exchange
        routing_key=f"{stage}.retry",
        body=serialize(message),
        properties=pika.BasicProperties(
            headers={**message.headers, "x-retry-count": retry_count + 1},
            expiration=str(delay_ms)  # TTL in ms, then DLX routes back
        )
    )
    channel.basic_nack(delivery_tag=message.delivery_tag, requeue=False)
```

Retry queue declaration (one per stage):
```python
channel.queue_declare(
    queue="orders.fraud-check.retry",
    arguments={
        "x-dead-letter-exchange": "orders.direct",
        "x-dead-letter-routing-key": "fraud-check",  # routes back to main queue
        "x-message-ttl": 480_000  # max TTL — actual TTL set per-message
    }
)
```

---

## Meeting the Throughput Target During Flash Sales

The 503s come from the web tier holding threads open for 2.1 seconds. Fix:

```python
# BEFORE: synchronous, thread-expensive
@app.post("/orders")
def place_order(order: Order):
    result = process_order(order)  # blocks for 2.1 seconds
    return result

# AFTER: async intake, instant response
@app.post("/orders")
def place_order(order: Order):
    order_id = generate_order_id()
    order.order_id = order_id

    db.insert("orders", {
        "id": order_id,
        "status": "processing",
        "created_at": datetime.utcnow()
    })

    channel.basic_publish(
        exchange="orders.direct",
        routing_key="fraud-check",
        body=serialize(order),
        properties=pika.BasicProperties(
            delivery_mode=2,  # persistent — survives broker restart
            message_id=order_id,
        )
    )

    return {"order_id": order_id, "status": "processing"}, 202
```

Now each HTTP handler takes ~5ms (DB insert + enqueue). 50 threads × 200 requests/second = handles 10,000 orders/second — well beyond your 2/second peak.

At 120 orders/minute, you need approximately 2 consumer instances per stage to keep latency low. Each stage consumer auto-scales on ECS based on queue depth CloudWatch metric.

---

## Visibility (Operations Requirements)

RabbitMQ Management UI (included with Amazon MQ) provides:
- Queue depth per stage → orders in each stage
- Message rates → processing throughput
- Consumer count → active workers per stage

For latency per stage and stuck order detection, add message metadata:

```python
# Add to message headers on publish
headers={
    "x-stage-entered-at": datetime.utcnow().isoformat(),
    "x-order-created-at": order.created_at.isoformat(),
}

# On consume, before acking:
stage_latency_ms = (datetime.utcnow() - parse(headers["x-stage-entered-at"])).total_seconds() * 1000
cloudwatch.put_metric_data(
    Namespace="CartNova/OrderPipeline",
    MetricData=[{
        "MetricName": "StageDurationMs",
        "Dimensions": [{"Name": "Stage", "Value": current_stage}],
        "Value": stage_latency_ms,
        "Unit": "Milliseconds"
    }]
)
```

Dead-letter queue depth → CloudWatch alarm at depth > 10 → PagerDuty.

---

## Summary

| Decision | Choice | Rationale |
|---|---|---|
| Queue system | RabbitMQ (Amazon MQ) | Already deployed; DLX first-class; correct scale |
| Topology | One queue per stage + DLX retry queues | Clean separation; independent scaling |
| Ordering | Pipeline contract (emit N+1 only after N succeeds) | No partitioning needed |
| Inventory parallelism | asyncio.gather() within consumer | No queue complexity needed |
| Retry | TTL + DLX, 5 attempts, exponential backoff | Native RabbitMQ pattern |
| DLQ | Single orders.dead-letter, all stages | Centralized human review |
| Idempotency | DB check before every external call | Mandatory with at-least-once |
| Web tier fix | 202 Accepted + enqueue | Releases threads immediately |

**Kafka**: Reject. Operational cost not justified at 2 orders/second.

**Redis Streams**: Viable alternative if team prefers simpler API. Requires separate cluster from cache. DLQ logic is DIY. Not wrong — just more application code where RabbitMQ gives you primitives.

**The honest uncertainty**: I haven't operated Amazon MQ in production. I'm reasoning from RabbitMQ documentation and patterns. Before committing, verify that Amazon MQ's managed version supports dead-letter exchange configuration — Amazon MQ has occasionally restricted certain RabbitMQ features. If DLX support is limited, Redis Streams with a custom retry processor becomes more attractive.