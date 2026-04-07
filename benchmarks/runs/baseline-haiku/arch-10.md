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