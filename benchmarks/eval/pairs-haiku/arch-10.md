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

## Response B
Looking at this architecture challenge, I'll structure my recommendation around the specific constraints: modest but bursty throughput, hard per-order sequencing, small operations team, and existing infrastructure.

## Recommendation: **Redis Streams**

This is the right choice for CartNova's constraints, not because of raw throughput (all three options handle 2 orders/sec easily), but because of **operational fit** and **leveraging existing infrastructure**.

---

## Why Redis Streams?

| Criterion | Kafka | RabbitMQ | Redis Streams |
|-----------|-------|----------|---------------|
| Peak throughput needed | 2 msgs/sec | 2 msgs/sec | 2 msgs/sec |
| Capacity | 100K+/sec | 30K/sec | 100K+/sec |
| Already deployed? | ❌ | ✅ email | ✅ caching |
| Operational complexity | **HIGH** | Medium | **LOW** |
| Team expertise | None | Minimal | Existing |
| At-least-once semantics | ✅ | ✅ | ✅ PEL-based |
| Per-order ordering | Partition by order_id | Routing logic needed | **Built-in per-stream** |
| New infra cost | Amazon MSK (~$2K/mo) | Amazon MQ (~$1.5K/mo) | $0 (reuse existing) |

**The kill-switch decision**: Your 8 backend engineers + 2 DevOps know Redis. Kafka requires a dedicated team. RabbitMQ is already in prod, but Redis is simpler for this use case.

---

## Proposed Architecture

### 1. Stream Topology (5 stages)

```
orders:fraud_check → orders:payment_capture → orders:inventory_reserve 
    → orders:fulfillment → orders:shipping
```

One stream per stage. Each stream contains **order messages** (not per-item; entire order moves as one unit).

### 2. Consumer Group Design

```
Stream: orders:fraud_check
├─ Consumer group: fraud_check_processors
│  ├─ Consumer-1 (processes orders [hash % 3 = 0])
│  ├─ Consumer-2 (processes orders [hash % 3 = 1])
│  └─ Consumer-3 (processes orders [hash % 3 = 2])
│
Stream: orders:payment_capture
├─ Consumer group: payment_processors (3 consumers)
├─ Stream: orders:inventory_reserve
├─ Consumer group: inventory_processors (5 consumers, inventory is bottleneck)
│
Stream: orders:fulfillment
├─ Consumer group: fulfillment_processors (2 consumers)
│
Stream: orders:shipping
├─ Consumer group: shipping_processors (2 consumers)
```

**Why 3-5 consumers per group?**
- **Fraud check, payment, fulfillment, shipping**: 2-3 consumers (latencies 200-600ms; one consumer handles 5-10 orders/sec)
- **Inventory reserve**: 5 consumers (300ms × 1.5 warehouses = 450ms per item × 3 items ≈ 400-500ms per order, but this is the **bottleneck**)

### 3. Per-Order Sequencing (The Key Pattern)

**Redis Streams guarantees ordering within a stream.** To ensure a single order doesn't get processed out-of-sequence while allowing parallel processing of different orders:

```python
# Pseudo-code for consumer
import hashlib

def consumer_loop(stream_key, consumer_group, consumer_id):
    my_shard = hash(consumer_id) % NUM_CONSUMERS  # e.g., 0, 1, or 2
    
    while True:
        # Read pending messages (at-least-once)
        pending = redis.xreadgroup(
            groupname=consumer_group,
            consumername=consumer_id,
            count=1,
            block=1000
        )
        
        if pending:
            stream, messages = pending[0]
            msg_id, data = messages[0]
            order = deserialize(data)
            
            # Only process if this order belongs to my shard
            order_hash = int(hashlib.md5(order['order_id'].encode()).hexdigest(), 16)
            if order_hash % NUM_CONSUMERS != my_shard:
                # Skip; another consumer will pick this up
                redis.xack(stream, consumer_group, msg_id)  # Still ack to clear PEL
                continue
            
            try:
                process_fraud_check(order)  # Call service
                redis.xack(stream, consumer_group, msg_id)
                
                # Emit to next stage
                redis.xadd('orders:payment_capture', {'*'}, serialize(order))
                
            except Exception as e:
                # Will be retried (PEL keeps track of retries)
                handle_retry(order_id, e)
```

**Why this works:**
- Consistent hashing by `order_id` → same order always goes to same consumer
- That consumer processes messages from its shard sequentially
- Different orders are processed in parallel (by other consumers)
- No complex routing logic; all messages stay in one stream

### 4. Retry & Dead-Letter Queue Strategy

**Retry mechanism:**

```python
# In your consumer exception handler
def handle_retry(order_id, error, attempt=1):
    if attempt < 5:
        # Exponential backoff: 2^n seconds
        delay_seconds = 2 ** attempt
        
        # Peek at PEL count; if high, log alert
        pending = redis.xpending('orders:fraud_check', 'fraud_check_processors')
        if pending[0] > 100:
            alert_ops(f"Fraud check queue backing up: {pending[0]} messages")
        
        # Message stays in PEL; consumer will retry after block timeout
        # OR: explicitly delay by publishing to delayed queue
        redis.zadd('orders:retry_queue', {
            f"{order_id}:{attempt}": time.time() + delay_seconds
        })
    else:
        # After 5 attempts, move to DLQ
        redis.xadd('orders:dead_letter_queue', {'*'}, {
            'order_id': order_id,
            'error': str(error),
            'stage': 'fraud_check',
            'attempts': 5,
            'timestamp': time.time()
        })
        alert_ops_critical(f"Order {order_id} moved to DLQ after 5 retries")
```

**Dead-letter handling:**
- Separate stream: `orders:dead_letter_queue`
- Ops team manually reviews (maybe order is genuinely fraudulent, payment declined, inventory unavailable, etc.)
- Ops can manually retry or refund customer after investigation

### 5. Per-Warehouse Parallel Inventory Reservation

The inventory service already handles parallelism. Your consumer just calls it:

```python
def process_inventory_reserve(order):
    # Inventory service internally parallelizes by warehouse
    reservations = inventory_service.reserve_multi(
        [(item['sku'], item['qty'], item['warehouse']) for item in order['items']]
    )
    
    # Returns aggregated result (list of per-warehouse reservations)
    if not all(r.success for r in reservations):
        # One warehouse failed; retry from queue
        raise InventoryReservationFailed(reservations)
    
    # Emit to fulfillment
    order['reservations'] = [r.to_dict() for r in reservations]
    redis.xadd('orders:fulfillment', {'*'}, serialize(order))
```

The queue doesn't need to know about warehouses—that's an internal detail of the inventory service.

---

## Throughput Analysis Under Load

**Peak: 120 orders/minute = 2 orders/sec**

Message flow per second at steady state:
- 2 orders enter → `fraud_check` stream
- ~2 orders exit `fraud_check` → enter `payment_capture`
- ~2 orders exit `payment_capture` → enter `inventory_reserve`
- ~2 orders exit `inventory_reserve` → enter `fulfillment`
- ~2 orders exit `fulfillment` → enter `shipping`

Total concurrent messages in flight: ~10 messages (2 per stage).

With 3 consumers per stage:
- **Fraud check** (200ms): 1 consumer handles 5 orders/sec; 2-3 consumers handle 10-15 orders/sec ✅
- **Payment capture** (500ms): 1 consumer handles 2 orders/sec; 3 consumers handle 6 orders/sec ✅
- **Inventory reserve** (400-500ms bottleneck): 1 consumer handles 2-2.5 orders/sec; **5 consumers handle 10-12 orders/sec** ✅
- **Fulfillment** (400ms): 2 consumers handle 5 orders/sec ✅
- **Shipping** (600ms): 2 consumers handle 3 orders/sec ✅

**Headroom**: All stages can handle 3x the peak load with current consumer counts.

---

## Monitoring & Visibility (for ops team)

```python
# Expose these metrics
def emit_metrics():
    for stream in ['fraud_check', 'payment_capture', 'inventory_reserve', 'fulfillment', 'shipping']:
        # Queue depth
        length = redis.xlen(f'orders:{stream}')
        emit_metric(f'orders.queue_depth.{stream}', length)
        
        # Consumer lag (max pending entry age)
        pending = redis.xpending(f'orders:{stream}', f'{stream}_processors')
        if pending[0] > 0:  # Has pending messages
            oldest_pending_ms = pending[1]  # Min ID (milliseconds since epoch)
            lag_ms = time.time() * 1000 - int(oldest_pending_ms)
            emit_metric(f'orders.consumer_lag.{stream}', lag_ms)
        
        # Dead-letter queue depth
        dlq_length = redis.xlen('orders:dead_letter_queue')
        emit_metric('orders.dlq_depth', dlq_length)
```

**Dashboards the ops team sees:**
1. Queue depth per stage (alerts if > 50)
2. Consumer lag (alerts if > 30 seconds)
3. DLQ depth (alerts if > 10)
4. Processing latency per stage (SLA tracking)
5. Retry rate per stage

---

## Implementation Checklist

- [ ] Upgrade Redis cluster AOF fsync to `always` for durability (trades latency for crash safety)
- [ ] Set Redis max-memory policy to `noeviction` (never drop messages)
- [ ] Create consumer startup script that registers consumers with the group
- [ ] Add Datadog/Prometheus exporter for metrics above
- [ ] Dead-letter queue review process (daily, ops-scheduled task)
- [ ] Load test with 150 orders/min (25% overhead) to validate consumer counts
- [ ] Implement graceful consumer shutdown (SIGTERM → finish current message before exit)

---

## Why Not RabbitMQ?

RabbitMQ is good, but requires custom routing logic to implement "process by order_id shard." You'd need either:
- One queue per order_id (unscalable with 50K orders/day)
- Complex routing key logic + manual sharding
- Or accept that all messages for an order go to one queue, then add application-level locking

Redis Streams' per-stream ordering is a better fit here.

---

## Why Not Kafka?

Kafka is overkill operationally. Your MSK cluster would cost ~$2K/month, require a dedicated engineer to manage schema registry, broker upgrades, and partition rebalancing. For 2 orders/sec, this is a heavy lift.

Redis Streams gives you Kafka's ordering guarantees at Redis's operational simplicity.

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
