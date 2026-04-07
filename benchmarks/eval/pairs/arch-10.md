# Task: arch-10 — Message queue selection for e-commerce order processing

## Prompt
You are the principal engineer at CartNova, an e-commerce platform processing 50,000
orders per day (~35 orders/minute average, ~120 orders/minute during flash sales).
You need to design the message queue architecture for order processing.

Order structure:
```json
{
  "order_id": "ord-88291",
  "customer_id": "cust-4421",
  "items": [
    {"sku": "SKU-001", "qty": 2, "warehouse": "us-east"},
    {"sku": "SKU-042", "qty": 1, "warehouse": "us-west"},
    {"sku": "SKU-107", "qty": 3, "warehouse": "us-east"}
  ],
  "payment": {"method": "card", "status": "authorized"},
  "shipping": {"method": "standard", "address": {...}}
}
```

Order processing pipeline:
```
Order Placed → Payment Capture → Inventory Reserve → Fulfillment → Shipping
     │               │                 │                 │            │
     │               │                 │                 │            │
     ▼               ▼                 ▼                 ▼            ▼
 Fraud Check    Update Ledger    Per-warehouse    Pack & Label    Carrier
                                 allocation                      Integration
```

Each order goes through 5 sequential stages. Within a stage, there may be parallel
sub-tasks (e.g., inventory reservation happens per-warehouse in parallel, then results
are aggregated before moving to fulfillment).

Hard requirements:
- **At-least-once delivery**: No order can be silently dropped. Lost orders = lost
  revenue and customer trust.
- **Per-order ordering**: Events for the same order must be processed in sequence.
  You cannot ship before payment is captured. You cannot reserve inventory before fraud
  check passes.
- **High throughput**: Must handle flash sale peaks of 120 orders/minute without
  backpressure causing the web tier to reject orders.
- **Visibility**: Operations team needs to see: orders in each stage, stuck orders,
  processing latency per stage, dead-letter queue depth.
- **Retry with backoff**: Failed stages should retry with exponential backoff, with
  a dead-letter queue after 5 attempts.

Current system (synchronous, failing under load):
```python
# order_processor.py — current synchronous implementation
def process_order(order: Order):
    try:
        fraud_result = fraud_service.check(order)         # 200ms avg
        if fraud_result.flagged:
            return handle_flagged_order(order)

        payment = payment_service.capture(order)           # 500ms avg
        ledger_service.record(order, payment)              # 100ms avg

        # Reserve inventory per warehouse
        reservations = []
        for item in order.items:
            r = inventory_service.reserve(item)            # 300ms avg
            reservations.append(r)

        fulfillment = fulfillment_service.create(          # 400ms avg
            order, reservations
        )
        shipping = shipping_service.book(order, fulfillment)  # 600ms avg

        return OrderResult(status="completed", tracking=shipping.tracking_id)
    except Exception as e:
        # Retry? Compensate? Currently just logs and hopes for the best
        logger.error(f"Order {order.id} failed at unknown stage: {e}")
        return OrderResult(status="failed", error=str(e))
```

Total synchronous processing time: ~2.1 seconds per order (sum of avg latencies).
During flash sales, the web tier thread pool (50 threads) is exhausted after 24
concurrent orders, causing HTTP 503 errors.

The team is evaluating three message queue options:

**A. Apache Kafka**
```
- Throughput: 100K+ messages/second
- Ordering: guaranteed within a partition
- Durability: replicated commit log
- Consumer groups for parallel processing
- Concern: "Complex to operate; we don't have a Kafka team"
- Current infra: no existing Kafka cluster
```

**B. RabbitMQ**
```
- Throughput: ~30K messages/second
- Ordering: guaranteed within a single queue
- Routing: flexible exchange/queue binding with routing keys
- Priority queues available
- Existing: already used for email notifications (small cluster)
- Concern: "Can it handle flash sale volumes?"
```

**C. Redis Streams**
```
- Throughput: ~100K messages/second
- Ordering: guaranteed within a stream
- Consumer groups with pending entry list (PEL) for at-least-once delivery
- Built-in: already have Redis for caching (6-node cluster)
- Concern: "Is Redis reliable enough for orders? What about persistence?"
```

Additional context:
- Infrastructure: AWS, running on ECS. RDS PostgreSQL for primary database.
- Team: 8 backend engineers, 2 DevOps. Nobody has deep Kafka experience.
- Budget: approved for managed services (Amazon MSK for Kafka, Amazon MQ for RabbitMQ,
  or ElastiCache for Redis Streams).
- The inventory service is the bottleneck — reservation calls take 300ms each, and
  orders average 3 items from 1.5 different warehouses.

Recommend a message queue architecture. Specify: the queue topology (topics/queues per
stage? single queue?), the partition/routing strategy for ordering, how you handle the
per-warehouse parallel inventory reservation, retry/DLQ strategy, and how you meet the
throughput target during flash sales.


## Response A
## Recommendation: Redis Streams

Before justifying, let's normalize the actual scale. 120 orders/minute is 2 orders/second. Any of the three options can handle this by orders of magnitude. The real problem isn't throughput — it's the synchronous coupling between the web tier and a 2.1-second pipeline. This reframing matters because it means **operational simplicity beats raw throughput headroom**.

Redis Streams wins because you already have a 6-node ElastiCache cluster and zero additional infrastructure risk. The Kafka operational concern ("we don't have a Kafka team") is a hard veto at your team size — Amazon MSK still requires deep expertise to partition correctly, tune consumers, and debug lag. RabbitMQ is viable, but your existing cluster is undersized and would require migration work before it carries order traffic.

---

## Queue Topology

Seven streams, each representing a stage transition. The stream is the handoff, not the processor.

```
orders:new
orders:fraud-cleared
orders:payment-captured
orders:inventory-reserved
orders:fulfillment-created
orders:shipped
orders:dlq

warehouse:{warehouse_id}          # fan-out for parallel inventory
reservations:completed            # fan-in aggregation
```

Each stream has one consumer group. Multiple ECS task replicas form the consumer pool within that group. A message moves from stream to stream when a stage completes — it doesn't "progress through" a single queue.

```
[Web Tier] ──XADD──► orders:new
                           │
                    [fraud-workers CG]
                           │ XADD on pass
                           ▼
                   orders:fraud-cleared
                           │
                    [payment-workers CG]
                           │ XADD on capture
                           ▼
                  orders:payment-captured
                           │
                  [inventory-coordinator CG]
                     │         │
              XADD   │         │  XADD
                     ▼         ▼
             warehouse:us-east  warehouse:us-west
                     │         │
              [wh-workers CG]  [wh-workers CG]
                     └────┬────┘
                  XADD aggregated result
                          ▼
                  orders:inventory-reserved
                           │
                    [fulfillment-workers CG]
                           │
                           ▼
                  orders:fulfillment-created
                           │
                     [shipping-workers CG]
                           │
                           ▼
                      orders:shipped
```

---

## Per-Order Ordering

Redis Streams don't need Kafka-style partitioning to enforce ordering, because ordering is provided by the **state machine**, not the queue.

An order in `orders:payment-captured` physically cannot be processed by fulfillment workers — they're reading a different stream. The sequence is enforced structurally. Each stage consumer only reads from its own input stream and only writes to the next stream on success.

Within a stream, Redis guarantees FIFO ordering (IDs are monotonically increasing). If you have 5 payment-worker replicas, they'll race on different orders — that's fine because order A's payment and order A's fraud check are in different streams by the time payment runs.

**The one constraint:** within a single order's lifecycle, never allow two workers to be processing the same order concurrently. This is naturally prevented by the pipeline topology, but make it explicit:

```python
# Idempotency key in PostgreSQL — set before XADD to next stream
UPDATE orders SET stage = 'payment_captured', stage_idempotency_token = :token
WHERE order_id = :order_id AND stage = 'fraud_cleared'  -- optimistic lock
```

If two workers somehow race (clock skew, retry storm), the DB UPDATE with the stage precondition acts as a fencing token. The second worker gets 0 rows updated and treats it as a duplicate.

---

## Parallel Inventory Reservation

This is the architecturally interesting part. The current code reserves sequentially (900ms for 3 items). You want parallel per-warehouse fan-out with a fan-in aggregation gate.

**Step 1 — Coordinator fans out:**

```python
# inventory-coordinator consumer reads from orders:payment-captured
def handle_payment_captured(order):
    warehouses = group_items_by_warehouse(order.items)
    
    # Write expected completion count to Redis hash BEFORE fanning out
    pipe = redis.pipeline()
    pipe.hset(f"inv:pending:{order.order_id}", "expected", len(warehouses))
    pipe.hset(f"inv:pending:{order.order_id}", "received", 0)
    pipe.expire(f"inv:pending:{order.order_id}", 300)  # 5 min TTL
    pipe.execute()
    
    # Fan out to per-warehouse streams
    for warehouse_id, items in warehouses.items():
        redis.xadd(f"warehouse:{warehouse_id}", {
            "order_id": order.order_id,
            "items": json.dumps(items),
            "correlation_key": f"inv:pending:{order.order_id}"
        })
    
    # Do NOT XACK yet — coordinator acks after fan-in completes
    # Actually: ack here, the pending hash is the continuation
    xack(order.message_id)
```

**Step 2 — Warehouse workers reserve and report:**

```python
def handle_warehouse_reservation(msg):
    result = inventory_service.reserve(msg.items)  # 300ms, but now parallel
    
    pipe = redis.pipeline()
    # Store this warehouse's result
    pipe.hset(f"inv:results:{msg.order_id}", msg.warehouse_id, json.dumps(result))
    # Increment completion counter, get new value atomically
    pipe.hincrby(f"inv:pending:{msg.order_id}", "received", 1)
    received, expected = pipe.execute()[-1], redis.hget(f"inv:pending:{msg.order_id}", "expected")
    
    if int(received) == int(expected):
        # All warehouses complete — aggregate and advance pipeline
        all_results = redis.hgetall(f"inv:results:{msg.order_id}")
        redis.xadd("orders:inventory-reserved", {
            "order_id": msg.order_id,
            "reservations": json.dumps(all_results)
        })
        redis.delete(f"inv:pending:{msg.order_id}", f"inv:results:{msg.order_id}")
```

This gives you ~300ms for inventory (parallel) instead of 900ms (sequential), and the aggregation is coordination-free except for the Redis atomic counter.

**Failure in fan-out:** If the coordinator crashes after writing 1 of 2 warehouse messages, the pending hash will have `expected=2, received=1` and sit there until TTL expires. The coordinator's DLQ retry will re-fan-out — warehouse workers must be idempotent (use `SET NX` on the reservation, not INSERT).

---

## Retry and Dead-Letter Strategy

Redis Streams have a built-in pending entry list (PEL): every `XREADGROUP` delivery that hasn't been `XACK`'d is tracked. You use `XPENDING` + `XCLAIM` for recovery.

```python
class StageWorker:
    MAX_RETRIES = 5
    BACKOFF_BASE = 2  # seconds

    def process_loop(self, stream: str, group: str):
        while True:
            # First: claim stale pending entries (worker crashed mid-processing)
            stale = redis.xautoclaim(stream, group, consumer_id,
                                     min_idle_time=60_000,  # 60s
                                     start="0-0", count=10)
            for msg in stale:
                self._handle_with_retry(msg, stream, group)
            
            # Then: read new messages
            msgs = redis.xreadgroup(group, consumer_id, {stream: ">"}, count=10, block=5000)
            for msg in msgs:
                self._handle_with_retry(msg, stream, group)
    
    def _handle_with_retry(self, msg, stream, group):
        order_id = msg["order_id"]
        attempt = int(msg.get("attempt", 0))
        
        try:
            self.process(msg)
            redis.xack(stream, group, msg.id)
        except RetryableError as e:
            if attempt >= self.MAX_RETRIES:
                redis.xadd("orders:dlq", {**msg, "failed_stage": stream, "error": str(e)})
                redis.xack(stream, group, msg.id)  # Remove from PEL
                logger.error(f"Order {order_id} sent to DLQ after {attempt} attempts")
            else:
                # Re-queue with backoff using a delay set
                delay = self.BACKOFF_BASE ** attempt  # 2, 4, 8, 16, 32 seconds
                redis.zadd("orders:delayed", {
                    json.dumps({**msg, "attempt": attempt + 1, "target_stream": stream}): 
                    time.time() + delay
                })
                redis.xack(stream, group, msg.id)  # Remove stale entry
        except NonRetryableError as e:
            # Fraud flagged, payment declined — not retryable
            redis.xadd("orders:dlq", {**msg, "failed_stage": stream, "dlq_reason": "non_retryable"})
            redis.xack(stream, group, msg.id)
```

A separate delay-pump process runs every second and moves due messages from the sorted set back to their target stream:

```python
def delay_pump():
    while True:
        due = redis.zrangebyscore("orders:delayed", 0, time.time(), start=0, num=100)
        for raw in due:
            msg = json.loads(raw)
            redis.xadd(msg["target_stream"], msg)
            redis.zrem("orders:delayed", raw)
        time.sleep(1)
```

---

## Throughput During Flash Sales

The current failure mode: web tier blocks for 2.1 seconds holding a thread, exhausting the 50-thread pool at 24 concurrent orders. The fix is to make order placement O(1) from the web tier's perspective.

```python
# New synchronous web handler — total latency: ~10ms
def place_order(order_data: dict) -> OrderResponse:
    order = Order(**order_data)
    
    # Write canonical record to PostgreSQL
    db.execute("INSERT INTO orders (id, data, stage, created_at) VALUES (%s, %s, 'new', NOW())",
               [order.id, json.dumps(order_data)])
    
    # Enqueue — this is the only "queue" operation in the hot path
    redis.xadd("orders:new", {"order_id": order.id, "attempt": 0})
    
    # Return immediately — processing is async
    return OrderResponse(order_id=order.id, status="processing",
                         status_url=f"/orders/{order.id}/status")
```

At 120 orders/minute (2/sec), with 10ms response time and 50 threads, you can handle 5,000 concurrent requests before exhaustion. You have 40× headroom against the current limit.

**Capacity math for the processing side:**

| Stage | Latency | Workers needed at 2 RPS |
|-------|---------|------------------------|
| Fraud check | 200ms | 1 (0.4 concurrent) |
| Payment capture | 500ms | 1 (1.0 concurrent) |
| Inventory (parallel) | 300ms | 1 coordinator + 2 wh workers |
| Fulfillment | 400ms | 1 (0.8 concurrent) |
| Shipping | 600ms | 2 (1.2 concurrent) |

You need roughly 8-10 ECS tasks total to process 2 orders/second through the pipeline. Scale to 20 during flash sales and you have 4× safety margin. Set ECS auto-scaling on stream depth (`XLEN`) — if `orders:fraud-cleared` depth exceeds 50, scale up fraud workers.

---

## Visibility

The operations team needs four things:

**1. Orders per stage** — `XLEN` on each stream, polled every 30 seconds to CloudWatch:
```python
stages = ["orders:new", "orders:fraud-cleared", "orders:payment-captured", 
          "orders:inventory-reserved", "orders:fulfillment-created", "orders:shipped", "orders:dlq"]
for stage in stages:
    cloudwatch.put_metric_data(MetricName="OrderQueueDepth", 
                               Dimensions=[{"Name": "Stage", "Value": stage}],
                               Value=redis.xlen(stage))
```

**2. Stuck orders** — `XPENDING` returns messages in PEL with idle time. Alert if any message has been pending > 5 minutes:
```python
pending = redis.xpending_range(stream, group, min="-", max="+", count=100)
stuck = [p for p in pending if p["idle"] > 300_000]  # 300s in ms
```

**3. Per-stage latency** — Embed `enqueued_at` timestamp in every message. Consumer records `dequeued_at` in PostgreSQL when it starts processing, and `completed_at` when done:
```sql
SELECT stage, 
       AVG(EXTRACT(EPOCH FROM (completed_at - enqueued_at))) as avg_latency_s,
       PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (completed_at - enqueued_at))) as p95_s
FROM order_stage_events
WHERE completed_at > NOW() - INTERVAL '1 hour'
GROUP BY stage;
```

**4. DLQ depth** — `XLEN orders:dlq` as a primary alert. DLQ growth > 5 in 5 minutes = PagerDuty. The DLQ entries contain `failed_stage` and `error`, so ops can see exactly where things broke and replay with `XADD` back to the appropriate stage stream.

---

## Durability Caveat and Mitigation

The legitimate concern about Redis: ElastiCache with AOF (`appendfsync everysec`) can lose up to 1 second of data on a node failure. This would drop messages already `XADD`'d but not yet processed.

Mitigation: **write to PostgreSQL first, then enqueue.** The web tier already does this above. For inter-stage advancement, the consumer writes the stage transition to PostgreSQL before `XADD`-ing to the next stream:

```python
def advance_to_payment(order_id, fraud_result):
    # Write to DB first
    db.execute("UPDATE orders SET stage='fraud_cleared', fraud_result=%s WHERE order_id=%s AND stage='new'",
               [json.dumps(fraud_result), order_id])
    
    # Then enqueue — if this Redis write fails, a reconciliation job recovers it
    redis.xadd("orders:fraud-cleared", {"order_id": order_id})
```

A reconciliation job runs every 5 minutes and scans for orders whose PostgreSQL `stage` doesn't match any Redis stream presence. It re-enqueues them. This is the recovery path for Redis failures, and because your volumes are low (50K orders/day), a 5-minute scan is trivially fast.

This makes Redis Streams the transport and PostgreSQL the source of truth — the architecture that best matches your team's existing operational footprint.

## Response B
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
