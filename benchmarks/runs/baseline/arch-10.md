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