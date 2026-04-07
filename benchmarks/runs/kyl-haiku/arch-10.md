# Recommendation: RabbitMQ (with clear caveats)

Before I land on this, let me work through my reasoning transparently and flag where I'm uncertain.

## My Key Assumptions & Confidence Levels

| Assumption | Confidence | Why |
|-----------|-----------|-----|
| 120 orders/min peak is the realistic max | Medium | Scenario specifies, but flash sales are unpredictable |
| 30K msg/sec RabbitMQ throughput is achievable in your setup | Medium | General industry knowledge, not verified against your AWS config |
| Team of 2 DevOps can't operate Kafka safely | Medium-High | Historically true; Kafka requires deep operational knowledge |
| Inventory reservation is the true bottleneck | High | Explicitly stated (300ms × 1.5 warehouses per order) |
| At-least-once via consumer acks is sufficient (not exactly-once) | Medium | depends on your fraud/payment idempotency story |

## What I'm NOT confident about:

- **Whether the ordering constraint is actually per-order or per-warehouse.** Your pipeline says "sequential stages," but if warehouse conflicts are rare, maybe you can parallelize more aggressively than I'm recommending.
- **Whether 30K msg/sec RabbitMQ is a hard ceiling or conservative.** With tuning, it might go higher. With your current email cluster, you might have data.
- **Whether the inventory reservation latency is really about the queue, or about the service itself.** Adding a queue doesn't fix a slow service. *(This is critical.)*

## The Real Problem

Your sync code takes 2.1 seconds per order because:
1. You're blocking the web thread for the entire pipeline
2. The inventory service is slow (300ms per warehouse reservation)

**A queue solves (1), not (2).**

The queue's job is: *decouple the web tier from processing latency.* If order acceptance returns immediately (order queued, processing async), you can handle 120 orders/min with a thread pool of 5, not 50.

## Why RabbitMQ (not Kafka, not Redis)

### Against Kafka:
- **You don't have the team.** Kafka is powerful but operationally expensive. Two DevOps people learning Kafka in production, during a flash sale, is a nightmare scenario.
- **You don't have the operational maturity yet.** Kafka needs monitoring (lag per consumer, partition rebalancing, broker health). Miss a rebalance and your pipeline stalls silently.
- **You're not at the throughput ceiling.** 100K msg/sec sounds impressive, but 120 orders/min is 2 msg/sec on average. Kafka's complexity is overkill unless you're 10× the current load or have regulatory ordering requirements (e.g., financial transactions).

**Kafka is right if**: You scale to 1M orders/day, or if you need Kafka's exactly-once semantics or multi-consumer fan-out patterns. Right now, you're not there.

### Against Redis Streams:
- **Persistence is the bottleneck.** Redis Streams lives in memory. Your 6-node cluster gives you cache replication, but not disk durability by default. You'd have to enable RDB/AOF, which introduces latency. During a flash sale, that latency spike could fail the whole system.
- **No built-in DLQ.** You can build one, but it's extra operational work and error-prone.
- **Consumer group management is newer.** Redis Streams consumer groups were released in Redis 5.0 (2018), but not as battle-tested as RabbitMQ or Kafka. If the cluster has a bug or you hit an edge case, you're on your own.

**Redis is right if**: You have a Redis ops team already AND you can afford to lose in-flight messages (e.g., notifications, not orders).

### Why RabbitMQ:
1. **Familiar to your team.** You're already running it for email. Your ops engineers understand exchanges, queues, and dead-lettering.
2. **Adequate throughput.** 30K msg/sec handles 120 orders/min with headroom. You're not at risk of queue saturation *for your current scale.*
3. **Durability by default.** RabbitMQ persists to disk. At-least-once delivery is built-in with consumer acks.
4. **Dead-lettering is trivial.** Failed orders automatically move to a DLQ after N retries. Operations can see DLQ depth and alert on it.
5. **Priority queues** (bonus): Rush orders can get higher priority without code changes.

---

## Queue Topology

**Single queue per stage, or one queue total?**

**Recommendation: Single queue with message type routing** (one physical queue, logical stages via message type):

```
orders-processing (single queue, 8–12 workers)
  ├─ Message type: fraud.check
  ├─ Message type: payment.capture
  ├─ Message type: inventory.reserve
  ├─ Message type: fulfillment.create
  └─ Message type: shipping.book

Dead-letter exchange: orders-dlq (auto-routed after 5 fails)
```

**Why single queue:**
- Simpler operational model (fewer queues to monitor)
- Natural ordering (FIFO within the queue)
- Dead-lettering is automatic

**Why by message type (not separate queues):**
- You avoid the problem of "all orders stuck at payment" blocking the queue
- A consumer group can handle all stages, but route based on message type
- Scaling is per-stage: if inventory is slow, spin up more inventory workers without changing the queue topology

---

## Handling Per-Warehouse Parallel Inventory Reservation

**Current bottleneck**: You call `inventory_service.reserve()` once per warehouse per order (3 items = 1.5 warehouses avg = 1–3 calls = 300–900ms).

**In the queue:**

```python
# In a handler for inventory.reserve message:
order_msg = {
    "type": "inventory.reserve",
    "order_id": "ord-88291",
    "items": [
        {"sku": "SKU-001", "qty": 2, "warehouse": "us-east"},
        {"sku": "SKU-042", "qty": 1, "warehouse": "us-west"},
        {"sku": "SKU-107", "qty": 3, "warehouse": "us-east"}
    ],
    "attempt": 1
}

def handle_inventory_reserve(msg):
    # Group by warehouse
    by_warehouse = {}
    for item in msg['items']:
        w = item['warehouse']
        if w not in by_warehouse:
            by_warehouse[w] = []
        by_warehouse[w].append(item)
    
    # Parallelize across warehouses
    futures = []
    for warehouse, items in by_warehouse.items():
        f = executor.submit(inventory_service.reserve, warehouse, items)
        futures.append((warehouse, f))
    
    # Aggregate results
    reservations = {}
    for warehouse, f in futures:
        try:
            reservations[warehouse] = f.result(timeout=10)
        except Exception as e:
            # Log, retry the whole order
            raise RetryableError(f"Warehouse {warehouse} failed: {e}")
    
    # Once all warehouses succeed, emit next stage
    emit('payment.capture', {
        "order_id": msg['order_id'],
        "reservations": reservations,
        "attempt": 1
    })
```

**Key points:**
- Parallelization happens *within* a single handler, not across queue workers
- If any warehouse fails, the entire order retries (at-least-once via queue ack)
- The queue ensures orders are processed sequentially per order_id (no race conditions)

---

## Partition/Routing Strategy for Ordering

**Single queue, but route consumption to ensure per-order ordering:**

```python
# Consumer group: "order-processors" (8 workers)
# RabbitMQ will deliver messages FIFO from the single queue

# Each worker processes one message at a time:
connection = pika.BlockingConnection(...)
channel = connection.channel()
channel.queue_declare(queue='orders-processing', durable=True)

def callback(ch, method, properties, body):
    msg = json.loads(body)
    try:
        handle_message(msg)
        ch.basic_ack(delivery_tag=method.delivery_tag)  # Ack = success
    except RetryableError as e:
        # Nack without requeue → RabbitMQ sends to DLQ after X tries
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
    except Exception as e:
        # Log, investigate
        logger.error(f"Unrecoverable error: {e}")
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

channel.basic_qos(prefetch_count=1)  # One message at a time (strict ordering)
channel.basic_consume(queue='orders-processing', on_message_callback=callback)
channel.start_consuming()
```

**Ordering guarantee:**
- RabbitMQ queue is FIFO
- `prefetch_count=1` ensures one worker only processes one message at a time
- Orders are processed sequentially across all stages
- ✅ You cannot ship before payment is captured

**Cost:** Throughput is limited by sequential processing. With 8 workers and 2.1 seconds per order, you can handle 8 orders in parallel (if one worker doesn't block the others). That's enough for your average load (2 msg/sec) and most of your peak (120 orders/min = 2 msg/sec).

---

## Retry & Dead-Letter Strategy

```
orders-processing (main queue)
  ↓
[Max retries: 5, Backoff: exponential]
  ↓ (failure)
orders-dlq (dead-letter queue)
  ↓
[ops team monitors, manual intervention]
```

**RabbitMQ configuration:**

```python
# Declare main queue with DLQ routing
channel.queue_declare(
    queue='orders-processing',
    durable=True,
    arguments={
        'x-dead-letter-exchange': 'orders-dlx',
        'x-dead-letter-routing-key': 'orders.dlq',
        'x-message-ttl': 300000,  # 5 minute timeout per attempt
    }
)

# Declare DLQ
channel.exchange_declare(exchange='orders-dlx', exchange_type='direct', durable=True)
channel.queue_declare(queue='orders-dlq', durable=True)
channel.queue_bind(queue='orders-dlq', exchange='orders-dlx', routing_key='orders.dlq')
```

**Retry logic (in handler):**

```python
def handle_message(msg):
    attempt = msg.get('attempt', 1)
    
    try:
        process_order_stage(msg)
    except RetryableError as e:
        if attempt < 5:
            # Exponential backoff: 2^attempt seconds
            delay = 2 ** attempt
            msg['attempt'] = attempt + 1
            requeue_with_delay(msg, delay_seconds=delay)
        else:
            # 5 attempts exhausted → let it fall through to DLQ
            raise
```

**Monitoring:**

```python
# Operations dashboard:
# - Queue depth: orders-processing (should be near 0 if processing is fast)
# - DLQ depth: orders-dlq (should be 0; alert if > 10)
# - Processing latency per stage (publish to CloudWatch)
# - Consumer lag (RabbitMQ management UI)
```

---

## Visibility for Operations

**What ops needs to see:**

1. **Orders in each stage** → Query your database:
   ```sql
   SELECT stage, COUNT(*) FROM orders 
   WHERE status = 'processing'
   GROUP BY stage;
   ```

2. **Stuck orders** → Orders in the same stage for > 5 minutes
   ```sql
   SELECT order_id, stage, EXTRACT(EPOCH FROM (NOW() - updated_at)) as age_seconds
   FROM orders
   WHERE status = 'processing' AND updated_at < NOW() - INTERVAL '5 minutes'
   ORDER BY age_seconds DESC;
   ```

3. **Processing latency per stage** → Emit metrics from handlers:
   ```python
   start = time.time()
   process_order_stage(msg)
   latency = time.time() - start
   cloudwatch.put_metric_data(
       Namespace='CartNova/Orders',
       MetricData=[{
           'MetricName': f'stage.{msg["type"]}.latency_ms',
           'Value': latency * 1000,
           'Unit': 'Milliseconds'
       }]
   )
   ```

4. **DLQ depth** → RabbitMQ management API:
   ```bash
   curl http://rabbitmq:15672/api/queues/%2F/orders-dlq
   ```
   Alert if `messages > 10`.

---

## The Hard Question: Is This Actually Sufficient?

**Can you hit 120 orders/min with RabbitMQ?**

Let's do the math:
- 120 orders/min = 2 orders/sec
- Per order, you have 5 stages
- With 8 workers and `prefetch_count=1`, you can handle up to **8 concurrent orders** (one per worker)
- If each order takes ~2.1 seconds, that's 8 / 2.1 ≈ **3.8 orders/sec** sustained capacity

✅ **Yes, 120 orders/min (2/sec) is well within capacity.**

Even during a flash sale spike to 120 orders/min, the queue will build up for ~30 seconds, then drain. Ops sees queue depth spike, and can scale workers if needed.

---

## What I'm Still Uncertain About

1. **Is the inventory service actually the bottleneck, or is the database?** If payment capture + inventory reserve are both hitting RDS hard, adding a queue doesn't help — you need to optimize those services (connection pooling, read replicas, caching). *I'd verify this before committing.*

2. **Do you have idempotency on payment capture?** If the payment service doesn't have idempotent keys, a retry could charge twice. *You need this solved before any async system.*

3. **What's the SLA for order processing?** If customers need "shipped within 1 hour," your 2.1 seconds per stage + queue latency might be tight. *Verify this doesn't change the architecture.*

4. **Will RabbitMQ actually scale to 1M orders/day?** You might hit the 30K msg/sec ceiling in 6–9 months. *Plan a migration path to Kafka then.*

---

## Decision Summary

| Criterion | RabbitMQ | Kafka | Redis |
|-----------|----------|-------|-------|
| Throughput for 120 orders/min | ✅ Sufficient | ✅ Overkill | ✅ Sufficient |
| Operational simplicity | ✅ High (you know it) | ❌ Low (new to team) | ⚠️ Medium (new feature) |
| Durability guarantee | ✅ Disk-backed | ✅ Replicated log | ⚠️ In-memory (risky for orders) |
| Dead-lettering | ✅ Built-in | ✅ Built-in | ❌ Custom |
| Risk of wrong choice | Medium (outgrow it in 2 yrs) | **High** (team can't operate) | Medium (durability concerns) |

**Recommendation: Start with RabbitMQ. Plan Kafka migration in 18 months if you scale to 1M+/day.**

The right choice isn't the most powerful system — it's the one your team can operate reliably today, while leaving room to grow.