## Working the Socratic Protocol First

Before recommending anything, let me interrogate my assumptions and the framing.

---

### Step 1: Check the numbers the prompt gave me — don't just accept them

The team is anxious about throughput. Let me actually compute whether it matters:

```
Peak load:       120 orders/minute = 2 orders/second
Pipeline stages: 5 stages × ~2 messages each (in + out) = ~10 messages/order
Peak message rate: 2 × 10 = 20 messages/second

RabbitMQ ceiling: ~30,000 messages/second
Redis Streams:    ~100,000 messages/second
Kafka:            100,000+ messages/second
```

**The throughput concern is a red herring.** All three options have 1,500× to 5,000× headroom over the peak load. The decision to consider Kafka because "RabbitMQ can't handle flash sales" is based on a misread of the numbers. This is the most important thing to say clearly before anything else.

### Step 2: What is "per-order ordering" actually asking for?

This is easy to misread. The requirement is *intra-order* ordering — fraud check before payment, payment before inventory, etc. It is *not* requiring order A to complete before order B starts. That distinction matters architecturally: you don't need a global FIFO queue. You need the pipeline topology itself to enforce sequencing — each stage only becomes reachable after the previous stage publishes to it.

### Step 3: What's genuinely hard here?

The parallel inventory reservation is the only architecturally interesting problem. Orders average 3 items across 1.5 warehouses — meaning ~2 independent warehouse calls that must all complete before fulfillment proceeds. No queue handles scatter-gather natively; that needs explicit design regardless of technology choice.

### Step 4: Steelman each option before dismissing

**Kafka's strongest case**: Its immutable, replayable commit log is genuinely unique. If you ever need to audit "what happened to order X," replay a failed batch, or do event sourcing, Kafka's log is irreplaceable. MSK removes most ops burden. This is a real argument that has nothing to do with throughput.

**RabbitMQ's strongest case**: Already deployed. Native dead-letter exchange (DLQ) maps directly to the retry-after-5-attempts requirement. The routing model (exchange → binding → queue) lets you build the retry-with-backoff pattern declaratively rather than in application code.

**Redis Streams' strongest case**: Already have a 6-node cluster. XADD + XREADGROUP + PEL gives at-least-once delivery natively. Sub-millisecond latency. Zero new infrastructure. At 50K orders/day, memory pressure is negligible.

### Step 5: What would change my recommendation?

- If the team needed **message replay/audit** (regulatory, dispute resolution) → Kafka wins clearly.
- If orders were **50M/day, not 50K** → throughput becomes real, Kafka pulls ahead.
- If the team had **no existing Redis expertise** → Redis Streams loses its "free" advantage.
- If inventory reservation called **20+ warehouses** per order → queue fan-out patterns become more important.

None of those conditions apply here. Now I can give a grounded recommendation.

---

## Recommendation: RabbitMQ (Amazon MQ) with Stage-Per-Queue Topology

Not because RabbitMQ is the best queue in the abstract. Because it already runs here, its native constructs map directly to every stated requirement, and adding Kafka or leaning on Redis for durable financial messaging is unnecessary complexity at 2 orders/second.

---

### Queue Topology

```
┌─────────────────────────────────────────────────────────────┐
│  Exchange: orders.pipeline (topic exchange)                  │
│                                                             │
│  Queues:                                                    │
│  ├── orders.fraud-check          (stage 1)                  │
│  ├── orders.payment-capture      (stage 2)                  │
│  ├── orders.inventory-reserve    (stage 3 coordinator)      │
│  ├── orders.warehouse.us-east    (stage 3 sub-task)         │
│  ├── orders.warehouse.us-west    (stage 3 sub-task)         │
│  ├── orders.fulfillment          (stage 4)                  │
│  ├── orders.shipping             (stage 5)                  │
│  │                                                          │
│  └── orders.dlq                  (dead letters, all stages) │
│      └── orders.{stage}.retry.delay  (TTL retry holding)   │
└─────────────────────────────────────────────────────────────┘
```

Each stage's consumer, on success, publishes directly to the next stage's queue. The pipeline topology itself enforces ordering — an order cannot enter `orders.payment-capture` until the fraud-check consumer puts it there. No global ordering mechanism needed.

**On per-consumer concurrency**: Run 1 consumer per queue for the initial rollout. At 2 orders/second peak, a single consumer per stage with 500ms–600ms processing time handles the load with room to spare. Scale to N consumers per stage only if latency monitoring reveals a queue backlog.

---

### Handling Per-Warehouse Parallel Inventory Reservation

This is a scatter-gather problem. Here's the design:

```python
# Stage 3 coordinator: inventory-reserve consumer
def handle_inventory_reserve(order: Order):
    expected = count_unique_warehouses(order.items)

    # Write expected count atomically
    db.execute("""
        INSERT INTO order_inventory_jobs (order_id, expected_count, completed_count)
        VALUES (%s, %s, 0)
    """, (order.order_id, expected))

    # Fan out — one message per warehouse needed
    for warehouse_id, items in group_by_warehouse(order.items):
        channel.basic_publish(
            exchange='orders.pipeline',
            routing_key=f'orders.warehouse.{warehouse_id}',
            body=json.dumps({
                "order_id": order.order_id,
                "warehouse_id": warehouse_id,
                "items": items,
                "correlation_id": order.order_id,  # for aggregation
            })
        )
```

```python
# Per-warehouse consumer (one per warehouse, or one consumer routing on warehouse_id)
def handle_warehouse_reserve(msg):
    result = inventory_service.reserve(msg.items)  # 300ms

    with db.transaction():
        db.execute("""
            INSERT INTO order_warehouse_reservations
                (order_id, warehouse_id, status, reservation_id)
            VALUES (%s, %s, %s, %s)
        """, (msg.order_id, msg.warehouse_id, result.status, result.reservation_id))

        row = db.fetchone("""
            UPDATE order_inventory_jobs
            SET completed_count = completed_count + 1
            WHERE order_id = %s
            RETURNING completed_count, expected_count, has_failure
        """, (msg.order_id,))

        if row.completed_count == row.expected_count:
            if row.has_failure:
                # Compensate: release any successful reservations
                compensate_reservations(msg.order_id)
                publish_to_dlq(msg.order_id, reason="inventory_reservation_failed")
            else:
                # All warehouses reserved — advance to fulfillment
                channel.basic_publish(
                    routing_key='orders.fulfillment',
                    body=build_fulfillment_payload(msg.order_id)
                )
```

The PostgreSQL row is the aggregation barrier. The counter increment + completion check is atomic within a transaction. No special queue feature needed. A partial failure triggers saga compensation on the already-reserved warehouses.

**Latency gain**: The three warehouse calls (avg 2 warehouses per order) now run in parallel. Worst case: max(300ms, 300ms) = 300ms instead of sequential 600ms.

---

### Retry with Exponential Backoff and DLQ

RabbitMQ's dead-letter exchange (DLX) enables this declaratively:

```python
# Queue declaration — done once at startup
channel.queue_declare(
    queue='orders.payment-capture',
    durable=True,
    arguments={
        'x-dead-letter-exchange': 'orders.retry',
        'x-dead-letter-routing-key': 'orders.payment-capture.retry',
    }
)

# Retry holding queue — messages sit here for TTL, then re-enter
channel.queue_declare(
    queue='orders.payment-capture.retry.delay',
    durable=True,
    arguments={
        'x-message-ttl': compute_backoff_ms(delivery_count),  # set per-message
        'x-dead-letter-exchange': 'orders.pipeline',
        'x-dead-letter-routing-key': 'orders.payment-capture',
    }
)
```

```python
# In every consumer's error handler:
def handle_failure(channel, method, properties, body, error):
    headers = properties.headers or {}
    death_count = len(headers.get('x-death', []))  # RabbitMQ tracks this

    if death_count >= 5:
        # Final DLQ — needs human intervention
        channel.basic_publish(
            exchange='orders.pipeline',
            routing_key='orders.dlq',
            properties=pika.BasicProperties(
                headers={**headers, 'failure_reason': str(error), 'stage': method.routing_key}
            ),
            body=body
        )
        channel.basic_ack(method.delivery_tag)
    else:
        # Exponential backoff: 1s, 2s, 4s, 8s, 16s
        backoff_ms = (2 ** death_count) * 1000
        channel.basic_publish(
            exchange='orders.retry',
            routing_key=f'{method.routing_key}.retry',
            properties=pika.BasicProperties(
                headers=headers,
                expiration=str(backoff_ms)  # per-message TTL
            ),
            body=body
        )
        channel.basic_ack(method.delivery_tag)
```

This gives you: 1s → 2s → 4s → 8s → 16s → DLQ. The x-death header is maintained by RabbitMQ across the retry cycle — no application state needed.

---

### Throughput During Flash Sales

The web tier's problem isn't the queue — it's synchronous processing holding threads. The fix is immediate decoupling:

```python
# New HTTP handler — returns in ~5ms
@app.post("/orders")
def place_order(order: Order):
    # Persist order with status=PENDING to Postgres (idempotency key: order_id)
    db.execute("INSERT INTO orders ... ON CONFLICT DO NOTHING")

    # Publish to queue — fire and return
    channel.basic_publish(
        exchange='orders.pipeline',
        routing_key='orders.fraud-check',
        properties=pika.BasicProperties(
            delivery_mode=2,  # persistent — survives broker restart
            message_id=order.order_id,  # deduplication
        ),
        body=order.json()
    )

    return {"status": "accepted", "order_id": order.order_id}
```

The thread pool is no longer blocked on 2.1 seconds of I/O. Each HTTP request completes in ~5ms. At 120 orders/minute (2/sec), 50 threads handle this trivially. The queue absorbs the burst and consumers work at their own pace.

**Backpressure protection**: If the queue depth exceeds a threshold (e.g., 5,000 messages), set up a CloudWatch alarm. Do not implement application-layer backpressure until the queue depth actually spikes — it hasn't been a problem yet and the fix is adding consumers, not rejecting orders.

---

### Visibility / Observability

Amazon MQ exposes RabbitMQ Management UI and CloudWatch metrics:

| Metric | Source | Alert Threshold |
|---|---|---|
| Queue depth per stage | CloudWatch `MessageCount` | > 500 messages |
| Consumer count | CloudWatch `ConsumerCount` | = 0 (stage down) |
| DLQ depth | CloudWatch on `orders.dlq` | > 0 (page on-call) |
| Message age (stuck orders) | Custom: timestamp in message headers, compared at consume time | > 5 minutes in any stage |

For per-stage latency, write to Postgres at each stage boundary:

```sql
CREATE TABLE order_stage_events (
    order_id TEXT,
    stage TEXT,
    event TEXT,  -- 'started', 'completed', 'failed'
    ts TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (order_id, stage, event)
);
```

A simple query surfaces P50/P95 latency per stage without any additional tooling. The ops team can query this directly, or you wire it into Grafana against RDS.

---

### Why Not the Alternatives

**Kafka**: Justified if you need message replay, audit logs, or event sourcing. At 50K orders/day, none of those are stated requirements. MSK costs ~$500/month for a minimal cluster, plus the team spending weeks learning Kafka's partition/consumer group model. The operational investment buys nothing at this volume that RabbitMQ doesn't already provide. If the audit/replay argument ever becomes real, revisit.

**Redis Streams**: Viable, but you'd be building the DLQ/retry mechanism yourself (Redis has no x-dead-letter equivalent). You'd also be betting order integrity on AOF persistence, which is configurable but less battle-tested for financial data than RabbitMQ's durable queues. The "already have Redis" argument is real but the incremental benefit over RabbitMQ (also already running) doesn't justify the missing primitives.

---

### What I'm Not Confident About

- **RabbitMQ cluster sizing on Amazon MQ**: I'm reasoning from general knowledge that a 3-node Amazon MQ cluster handles this load. Verify with AWS's sizing docs for your specific instance type before committing.
- **Inventory service behavior under parallel calls**: If the inventory service isn't idempotent (i.e., two parallel requests for the same SKU could double-reserve), the scatter-gather pattern needs idempotency keys at the inventory service level — that's outside the queue design.
- **Exactly-once vs. at-least-once for payment capture**: At-least-once delivery means your payment capture consumer could receive the same order twice (e.g., after a consumer crash between processing and ACK). The payment service must be idempotent on `order_id`. This is a consumer-side requirement, not a queue requirement — but it's the place where getting this wrong costs real money.