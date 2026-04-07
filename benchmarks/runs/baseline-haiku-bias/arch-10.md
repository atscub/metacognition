# Message Queue Architecture for CartNova Order Processing

I'm recommending **RabbitMQ with a per-stage queue topology**, augmented by a saga-pattern orchestrator. Here's why and how.

---

## Recommendation: RabbitMQ

**The core argument:** Your actual message volume (10 msg/sec peak) is trivial for all three options. The bottleneck is not queue throughput—it's the inventory service (300ms per warehouse). The right choice is operational fit, not theoretical capacity.

| Criterion | Kafka | RabbitMQ | Redis Streams |
|-----------|-------|----------|---------------|
| Throughput | 100K+/sec | 30K/sec | 100K+/sec |
| Your actual need | 10–50/sec | 10–50/sec | 10–50/sec |
| **Operational lift** | **High** (new cluster, monitoring, tuning, staffing) | **Low** (you already run it) | **Medium** (risk of cache degradation) |
| Ordering guarantee | Per partition | Per queue | Per stream |
| At-least-once | Consumer offsets | Acks + DLQ | Consumer groups + PEL |
| Team fit | Requires Kafka expertise | Known, battle-tested in house | Single expert dependency |

**RabbitMQ wins because:**
1. Already deployed for email notifications → existing ops, monitoring, backups
2. 8 backend engineers + 2 DevOps with no Kafka experience → operational risk of Kafka is real
3. Message volume is small enough that RabbitMQ has massive headroom
4. Easier to debug failed orders (familiar tool)

---

## Architecture: Per-Stage Queue Topology

```
┌─────────────────────────────────────────────────────────────┐
│ Order Placed (REST API)                                     │
└──────────────────┬──────────────────────────────────────────┘
                   │ publish order.fraud_check_required (routing key: order_id % partition)
                   ▼
        ┌──────────────────────────┐
        │  QUEUE: fraud-check      │  (partition by order_id hash)
        │  - max retries: 5        │
        │  - backoff: exponential  │
        └──────────────────────────┘
                   │ consume
                   ▼
        ┌──────────────────────────┐
        │ Fraud Check Worker       │  (1–4 consumers, prefetch=10)
        │ (RabbitMQ ack on success)│
        └──────────────────────────┘
             fraud check service (200ms avg)
             
          If flagged → order.fraud_failed (DLQ)
          If pass ───► order.payment_capture_required

        ┌──────────────────────────┐
        │  QUEUE: payment-capture  │  (partition by order_id hash)
        │  - max retries: 5        │
        │  - backoff: exponential  │
        └──────────────────────────┘
                   │ consume
                   ▼
        ┌──────────────────────────┐
        │ Payment Worker           │
        └──────────────────────────┘
             capture + ledger (500ms + 100ms)
             
          If payment fails → order.payment_failed (DLQ)
          If pass ───► order.inventory_reserve_required

        ┌──────────────────────────┐
        │  QUEUE: inventory-reserve│  (partition by order_id hash)
        │  - max retries: 5        │
        │  - backoff: exponential  │
        └──────────────────────────┘
                   │ consume (1 message = 1 order, not 1 item)
                   ▼
        ┌──────────────────────────┐
        │ Inventory Worker         │
        │ (handles per-warehouse   │
        │  parallelism internally) │
        └──────────────────────────┘
             for each item: spawn async reserve
                ├─ warehouse us-east → inventory_service.reserve (300ms)
                ├─ warehouse us-west → inventory_service.reserve (300ms)
                └─ gather results concurrently
             
          If any fails → order.inventory_failed (DLQ)
          If all pass ───► order.fulfillment_required

        ┌──────────────────────────┐
        │  QUEUE: fulfillment      │  (partition by order_id hash)
        └──────────────────────────┘
                   │
                   ▼
        ┌──────────────────────────┐
        │ Fulfillment Worker       │
        │ (1–2 consumers)          │
        └──────────────────────────┘
             create fulfillment (400ms) + book shipping (600ms)
             
          If fails → order.fulfillment_failed (DLQ)
          If pass ───► order.completed

        ┌──────────────────────────┐
        │  QUEUE: completed        │  (metrics, notifications)
        │  (fire-and-forget)       │
        └──────────────────────────┘
                   │
                   ▼
             Emit to stream (webhook, emails,
             analytics) — acks optional
```

---

## Critical Design Decisions

### 1. **Partitioning for Per-Order Ordering**

Use RabbitMQ's **routing key** strategy, hashing `order_id` to a logical partition:

```python
order_partition = hash(order.order_id) % num_partitions  # e.g., 16 partitions

channel.basic_publish(
    exchange='order-events',
    routing_key=f"fraud_check.{order_partition}",  # e.g., "fraud_check.3"
    body=order_json,
    properties=pika.BasicProperties(
        delivery_mode=2,  # Persistent
        expiration='3600000',  # 1 hour TTL for stuck messages
    )
)
```

**Per-partition consumer** ensures orders are processed serially within the same partition, preserving order:

```python
queue_name = f"fraud-check.partition.3"  # One queue per logical partition
channel.queue_declare(queue=queue_name, durable=True)
channel.queue_bind(
    exchange='order-events',
    queue=queue_name,
    routing_key='fraud_check.3'
)
channel.basic_qos(prefetch_count=10)  # Batch processing
for method, properties, body in channel.consume(queue_name):
    order = json.loads(body)
    try:
        fraud_result = fraud_service.check(order)
        if fraud_result.flagged:
            publish_event(f"fraud_failed.{order_partition}", order)
        else:
            publish_event(f"payment_capture_required.{order_partition}", order)
        channel.basic_ack(delivery_tag=method.delivery_tag)
    except Exception as e:
        # Nack to retry — RabbitMQ will re-queue or send to retry exchange
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
```

**Why per-partition queues?**
- Single global queue would force sequential processing of all orders (bottleneck)
- Per-partition queues allow parallelism across orders while preserving order within each order
- RabbitMQ natively supports this via routing keys + separate queue declarations

---

### 2. **Handling Parallel Warehouse Inventory Reservation**

The inventory stage is the bottleneck. **Do NOT make the message queue handle parallelism here.** Instead:

```python
async def reserve_inventory(order: Order, order_partition: int):
    """
    Single message per order. Parallelism happens internally.
    """
    tasks = []
    for item in order.items:
        # Spawn concurrent reserve calls per warehouse
        task = inventory_service.reserve_async(item)
        tasks.append(task)
    
    # Gather all results concurrently
    reservations = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Check for failures
    failures = [r for r in reservations if isinstance(r, Exception)]
    if failures:
        # Publish to DLQ after 5 retries
        raise InventoryReservationFailed(failures)
    
    # All passed
    publish_event(f"fulfillment_required.{order_partition}", order, reservations)
```

The worker process uses `asyncio` (or threads if you prefer) to parallelize warehouse calls within a single order's processing. The message queue sees one message per order.

---

### 3. **Retry Strategy & Dead-Letter Queue**

```python
# RabbitMQ Exchange & Queue Setup
channel.exchange_declare(exchange='dlq', exchange_type='direct', durable=True)
channel.queue_declare(queue='fraud-check-dlq', durable=True)
channel.queue_bind(exchange='dlq', queue='fraud-check-dlq', routing_key='fraud_check.dlq')

# Retry exchange with TTL
channel.exchange_declare(exchange='fraud-check-retry', exchange_type='direct', durable=True)
channel.queue_declare(
    queue='fraud-check-retry',
    durable=True,
    arguments={
        'x-dead-letter-exchange': 'fraud-check',  # Back to main queue after TTL
        'x-message-ttl': 5000,  # Retry delay: 5 seconds for attempt 1
    }
)

# Worker logic
def process_fraud_check(order, attempt=0):
    try:
        result = fraud_service.check(order)
        # ... success path
    except Exception as e:
        attempt += 1
        if attempt >= 5:
            # Final retry exhausted
            publish_to_dlq(order, attempt, e)
        else:
            # Exponential backoff: 1s, 2s, 4s, 8s, 16s
            backoff_ms = 1000 * (2 ** (attempt - 1))
            publish_to_retry_queue(order, attempt, backoff_ms)
```

**Why this approach?**
- Avoids thundering herd on retry (exponential backoff)
- Failed orders end up in a single DLQ per stage for ops visibility
- `x-dead-letter-exchange` routing automatically moves retried messages back after TTL expires

---

### 4. **Consumer Scaling**

**Consumer count per queue:**

| Queue | Load | Consumers | Rationale |
|-------|------|-----------|-----------|
| fraud-check (partitioned) | Medium | 4 (1 per partition) | Fraud checks are CPU-bound, quick (200ms) |
| payment-capture | Medium | 2–3 | Payment calls are I/O-bound, slower (500ms) |
| inventory-reserve | **High** | 2–3 | Bottleneck! But internal parallelism handles warehouse calls |
| fulfillment | Low | 1–2 | Final stage, can be slower |

**Prefetch strategy:**
```python
channel.basic_qos(prefetch_count=10)  # Pull 10 messages at a time, process in batch
```

At 2 orders/sec peak, each consumer pulls ~5–10 messages before running out, then waits for more. This avoids overloading the consumer while maintaining throughput.

---

### 5. **Observability & Alerting**

Wire up Prometheus metrics for each queue:

```python
# Pseudo-code
class OrderProcessingMetrics:
    messages_processed = Counter('order_queue_processed_total', ['stage', 'status'])
    processing_latency = Histogram('order_queue_latency_seconds', ['stage'])
    dlq_depth = Gauge('order_queue_dlq_depth', ['stage'])
    retry_count = Counter('order_queue_retries_total', ['stage', 'attempt'])

# Usage
with metrics.processing_latency['fraud_check'].time():
    result = fraud_service.check(order)
    metrics.messages_processed['fraud_check', 'success'].inc()

# Monitor DLQ depth
dlq_depth = channel.queue_declare(queue='fraud-check-dlq', passive=True)
metrics.dlq_depth['fraud_check'].set(dlq_depth.method.message_count)
```

**Alerting thresholds:**
- DLQ depth > 10 → page oncall (orders silently failing)
- P99 latency per stage > 5 seconds → alert ops (bottleneck)
- Retry rate > 10% → alert ops (service degradation)

---

## Why NOT the Alternatives

### **Kafka**
- ✗ Operational overhead for 10 msg/sec is unjustifiable
- ✗ Requires Kafka expertise your team lacks
- ✗ Managed MSK is expensive (~$3–5K/month for production cluster)
- ✓ Would scale infinitely, but you don't need that yet

### **Redis Streams**
- ✗ Risk of cache performance degradation (order processing competes with session cache)
- ✗ Single-node failure kills both cache and queue (even with replication, failover is complex)
- ✗ Persistence (AOF) overhead can stall the cache under high load
- ✓ Simpler if you're willing to bet on ops maturity

---

## Implementation Checklist

```
[ ] Set up per-stage RabbitMQ exchanges (order-events, dlq, retries)
[ ] Implement order partitioning by hash(order_id) → 16 partitions
[ ] Build async inventory reservation (internal parallelism per order)
[ ] Wire up exponential backoff retry with DLQ
[ ] Add Prometheus metrics for latency, DLQ depth, retry rate
[ ] Set up dashboard in Grafana for ops visibility
[ ] Load test: simulate 120 orders/min, verify no 503s from API
[ ] Chaos test: kill workers, verify no order drops, check DLQ recovery
[ ] Document runbook: "Order stuck in DLQ? Check worker logs, requeue from DLQ"
```

---

## What This Achieves

- **At-least-once delivery**: RabbitMQ acks only on success; nack triggers retries + DLQ
- **Per-order ordering**: Partitioning by order_id ensures events for same order stay ordered
- **High throughput**: 10–50 msg/sec with headroom; flash sale peaks absorbed easily
- **Visibility**: Prometheus metrics, DLQ dashboard, worker logs per stage
- **Retry with backoff**: Exponential backoff (1s → 16s), 5 attempts, then DLQ
- **Inventory parallelism**: Async/threaded warehouse calls within a single worker process

**Result:** API no longer blocks on payment/inventory calls. Web tier can accept orders at full 120/min without 503 errors. Orders flow through pipeline asynchronously with built-in resilience.