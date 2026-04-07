# CartNova Message Queue Architecture

## Recommendation: Redis Streams

Before justifying the choice, let's establish the actual scale: 120 orders/minute = **2 orders/second**. Every candidate technology can handle this — the decision is therefore not about raw throughput but about operational fit, correctness, and how well each maps to your pipeline's structural requirements.

---

## Why Redis Streams Wins

| Criterion | Kafka (MSK) | RabbitMQ (Amazon MQ) | Redis Streams (ElastiCache) |
|-----------|-------------|----------------------|----------------------------|
| Throughput | ✅ 100K+/sec | ✅ 30K/sec (>>your need) | ✅ 100K+/sec |
| Per-entity ordering | ✅ per-partition | ⚠️ per-queue, single consumer | ✅ application-enforced via streams |
| At-least-once delivery | ✅ consumer groups | ✅ acks + dead-lettering | ✅ PEL (Pending Entry List) |
| Fan-out/fan-in pattern | ✅ native | ✅ exchange routing | ✅ with coordination table |
| Operational cost | ❌ high, no team experience | ⚠️ medium | ✅ already running, team knows it |
| Infrastructure delta | ❌ new cluster | ⚠️ expand existing | ✅ extend existing 6-node cluster |
| Durability concern | ✅ replicated log | ✅ mirrored queues | ⚠️ needs explicit AOF config |

**Kafka is over-engineered for 2 orders/second and your team has no Kafka expertise.** MSK reduces operational burden but not learning burden. A system your team can't debug at 3am during a flash sale is not a reliable system.

**RabbitMQ's ordering guarantee is a trap:** it guarantees ordering within a single queue, but a single queue with one consumer bottlenecks your throughput. Horizontal scaling (multiple consumers) breaks per-order ordering unless you add consistent-hashing exchange plugins — complexity that rivals Kafka without the benefits.

**Redis Streams' durability concern is real but solvable** with a one-time ElastiCache configuration change. See the durability section below.

---

## Architecture: Queue Topology

```
Web Tier                    Streams                      Workers
─────────              ──────────────────────────────    ──────────────────────────

POST /orders  ───────► orders:incoming                  [fraud-worker × 2]
                              │
              ◄── 202 ────────┘ (async, return order_id)
                              │
                              ▼
                        orders:payment                   [payment-worker × 3]
                              │
                              ▼
                        orders:inventory                 [inventory-fanout × 2]
                         /           \
                        ▼             ▼
               inventory:us-east  inventory:us-west      [warehouse-worker × 2 each]
                        \             /
                         ▼           ▼
                    (coordination: PostgreSQL)
                              │
                              ▼ (when all warehouses done)
                        orders:fulfillment               [fulfillment-worker × 2]
                              │
                              ▼
                        orders:shipping                  [shipping-worker × 2]
                              │
                              ▼
                        orders:completed                 [audit/webhook emitter]

                        orders:dlq                       [ops dashboard alert]
```

Each box is a Redis Stream. Each `[worker × N]` is an ECS task in a consumer group on that stream.

---

## Web Tier Fix (Prerequisite)

The synchronous design is the root cause of the 503 errors. Fix this first, independent of queue choice:

```python
# order_service.py — new async entry point
async def place_order(order: Order) -> OrderAcceptance:
    order.id = generate_order_id()
    order.status = "accepted"
    
    # Write to DB for durability, then enqueue
    await db.orders.insert(order)  # PostgreSQL, ~20ms
    
    await redis.xadd(
        "orders:incoming",
        {
            "order_id": order.id,
            "payload": order.json(),
            "enqueued_at": time.time(),
            "attempt": 0
        },
        maxlen=100_000  # cap stream length
    )
    
    return OrderAcceptance(
        order_id=order.id,
        status_url=f"/orders/{order.id}/status"
    )
    # Returns HTTP 202 in ~25ms — thread released immediately
```

With 202 responses, your 50-thread pool can now handle 50 × (1000ms / 25ms) = **2,000 concurrent order placements per second**. Flash sale backpressure problem eliminated.

---

## Per-Order Ordering Strategy

Redis Streams don't provide per-key ordering natively (unlike Kafka partitions). You enforce ordering through **pipeline topology**: an order advances to stream N+1 only after a worker successfully completes stage N and explicitly publishes forward.

```
orders:incoming  →  (fraud worker processes order A) → publishes to orders:payment
                                                     → never skips to orders:inventory
```

This is actually **stronger** than Kafka's partition-level ordering: Kafka guarantees messages within a partition arrive in order at the consumer, but it doesn't prevent a consumer from publishing out-of-stage. Your topology makes out-of-stage transitions structurally impossible.

**Idempotency is required** for at-least-once delivery correctness:

```python
# base_worker.py
async def process(self, message: StreamMessage) -> None:
    order_id = message["order_id"]
    
    # Idempotency check — has this stage already completed for this order?
    stage_key = f"stage:{self.stage_name}:{order_id}"
    if await redis.exists(stage_key):
        await self.ack(message)  # already done, safe to ack
        return
    
    result = await self.handle(message)
    
    # Mark stage complete (TTL 7 days — longer than max order lifetime)
    await redis.set(stage_key, result.json(), ex=604800)
    await self.publish_next(order_id, result)
    await self.ack(message)
```

---

## Inventory Fan-Out / Fan-In

This is the hardest structural problem. An order with items in 2 warehouses needs parallel reservation, then a gate before fulfillment.

### Step 1: Fan-Out Worker

```python
# inventory_fanout_worker.py
class InventoryFanoutWorker(BaseWorker):
    stage_name = "inventory_fanout"
    
    async def handle(self, message):
        order = Order.parse(message["payload"])
        
        # Group items by warehouse
        by_warehouse = defaultdict(list)
        for item in order.items:
            by_warehouse[item.warehouse].append(item)
        
        # Write coordination record to PostgreSQL
        await db.execute("""
            INSERT INTO inventory_coordination 
              (order_id, expected_count, completed_count, reservations, created_at)
            VALUES ($1, $2, 0, $3, NOW())
            ON CONFLICT (order_id) DO NOTHING
        """, order.id, len(by_warehouse), json.dumps({}))
        
        # Publish one message per warehouse (parallel reservation)
        for warehouse, items in by_warehouse.items():
            await redis.xadd(f"inventory:{warehouse}", {
                "order_id": order.id,
                "items": json.dumps([i.dict() for i in items]),
                "attempt": 0
            })
```

### Step 2: Warehouse Workers (per-stream, parallel)

```python
# warehouse_worker.py — one consumer group per inventory:{warehouse} stream
class WarehouseWorker(BaseWorker):
    
    async def handle(self, message):
        order_id = message["order_id"]
        items = json.loads(message["items"])
        
        # Call inventory service (300ms avg)
        reservation = await inventory_service.reserve(
            warehouse=self.warehouse,
            items=items
        )
        
        # Atomic update: increment completed_count, store reservation result
        async with db.transaction():
            result = await db.fetchrow("""
                UPDATE inventory_coordination
                SET 
                    completed_count = completed_count + 1,
                    reservations = reservations || $2::jsonb
                WHERE order_id = $1
                RETURNING expected_count, completed_count
            """, order_id, json.dumps({self.warehouse: reservation.dict()}))
            
            # Last warehouse to complete triggers fulfillment
            if result["completed_count"] == result["expected_count"]:
                all_reservations = await db.fetchval(
                    "SELECT reservations FROM inventory_coordination WHERE order_id = $1",
                    order_id
                )
                await redis.xadd("orders:fulfillment", {
                    "order_id": order_id,
                    "reservations": json.dumps(all_reservations),
                    "attempt": 0
                })
```

The PostgreSQL coordination record is the fan-in gate. The `completed_count == expected_count` check within a transaction ensures exactly one worker publishes to fulfillment, even if warehouse workers race.

---

## Retry and Dead-Letter Strategy

Redis Streams' Pending Entry List (PEL) is your retry mechanism. Messages stay in PEL after being read but before being ACKed. A separate retry daemon reclaims them:

```python
# retry_daemon.py — runs on a cron, once per minute
BACKOFF_SCHEDULE = [30, 120, 300, 900, 1800]  # seconds: 30s, 2m, 5m, 15m, 30m
MAX_ATTEMPTS = 5

class RetryDaemon:
    async def run(self, stream: str, group: str):
        # Find messages idle longer than our shortest backoff
        pending = await redis.xpending_range(
            stream, group, 
            min="-", max="+", 
            count=100,
            idle=30_000  # 30 seconds minimum idle
        )
        
        for entry in pending:
            message_id = entry["message_id"]
            idle_ms = entry["time_since_delivered"]
            delivery_count = entry["times_delivered"]
            
            if delivery_count > MAX_ATTEMPTS:
                # Claim, read payload, send to DLQ
                messages = await redis.xclaim(stream, group, "retry-daemon", 0, [message_id])
                await redis.xadd("orders:dlq", {
                    **messages[0],
                    "failed_stream": stream,
                    "final_attempt": delivery_count,
                    "dlq_at": time.time()
                })
                await redis.xack(stream, group, message_id)
                await metrics.increment("orders.dlq.added", tags={"stream": stream})
                continue
            
            # Check if enough time has passed for this attempt number
            required_idle = BACKOFF_SCHEDULE[delivery_count - 1] * 1000  # ms
            if idle_ms >= required_idle:
                # Reassign to an active consumer for retry
                await redis.xclaim(stream, group, "retry-daemon", 0, [message_id])
                # The message is now in PEL again; consumers will pick it up
```

**DLQ is a stream too** (`orders:dlq`). Operations team can replay messages by reading from it and re-publishing to the appropriate stage stream.

---

## Throughput Analysis

```
Flash sale: 120 orders/minute = 2 orders/second sustained

Stage       Avg Latency    Parallelism Needed    Workers Required
──────────  ───────────    ──────────────────    ────────────────
Fraud       200ms          2/sec × 0.2s = 0.4    2 (headroom)
Payment     500ms          2/sec × 0.5s = 1.0    3 (headroom)
Ledger      100ms          (same worker as payment, sequential)
Inv Fanout  ~10ms          near-instant          2
Warehouse   300ms per wh   2/sec × 0.3s = 0.6    2 per warehouse stream
Fulfillment 400ms          2/sec × 0.4s = 0.8    2
Shipping    600ms          2/sec × 0.6s = 1.2    3

Total ECS tasks: ~17 workers + 2 retry daemons
```

At 120 orders/minute with 17 workers, your utilization is **under 50% on every stage**. You have 2× headroom before any stage becomes a bottleneck. For unexpected spikes (2×–3× flash sale traffic), ECS auto-scaling on queue depth adds workers within 60–90 seconds.

**Inventory is your bottleneck, not the queue.** At 1.5 warehouses average × 300ms = 450ms per order through inventory, and 2 orders/second, you need ~0.9 concurrent inventory calls per warehouse stream. Two warehouse workers per region keeps you safe. If the inventory service itself degrades (e.g., 600ms latency), ECS scaling compensates — the queue absorbs the backlog rather than the web tier.

---

## Durability Configuration

This is the legitimate Redis concern. Configure ElastiCache before go-live:

```
# ElastiCache Redis parameter group settings
appendonly: yes           # Enable AOF persistence
appendfsync: everysec    # Sync to disk every 1 second (max 1s data loss on crash)
                          # Don't use "always" — 10× write amplification not worth it

# ElastiCache cluster settings
automatic-failover: enabled   # Multi-AZ, automatic failover on primary failure
multi-az: enabled
```

With AOF + Multi-AZ, your exposure window is ≤1 second of messages in the event of a primary node crash. Given orders are also written to PostgreSQL on placement, you can recover that 1-second window by comparing DB records against stream contents. This risk is acceptable; Kafka on MSK with 3-node replication is more durable in theory but not meaningfully so for your scale.

---

## Visibility and Observability

```python
# metrics_collector.py — runs every 30 seconds, publishes to CloudWatch

async def collect_metrics():
    streams = [
        "orders:incoming", "orders:payment", "orders:inventory",
        "orders:fulfillment", "orders:shipping", "orders:dlq"
    ]
    
    for stream in streams:
        # Queue depth (pending messages not yet consumed)
        length = await redis.xlen(stream)
        await cloudwatch.put_metric(
            "OrderQueueDepth", length, 
            dimensions={"Stream": stream}
        )
        
        # Stuck orders (PEL entries idle > 5 minutes)
        for group in await redis.xinfo_groups(stream):
            pending = await redis.xpending_range(
                stream, group["name"], 
                min="-", max="+", 
                count=1000,
                idle=300_000  # 5 min
            )
            await cloudwatch.put_metric(
                "StuckOrders", len(pending),
                dimensions={"Stream": stream, "Group": group["name"]}
            )
    
    # DLQ alert (pagerduty threshold: DLQ depth > 0)
    dlq_depth = await redis.xlen("orders:dlq")
    if dlq_depth > 0:
        await pagerduty.trigger(f"CartNova DLQ has {dlq_depth} orders requiring manual review")
```

**CloudWatch Dashboard panels:**
- Orders per stage (queue depth sparklines)  
- Processing latency per stage (P50/P95/P99 emitted by each worker)
- DLQ depth (always-visible, alert on non-zero)
- Retry count distribution (is stage N consistently failing?)
- Stuck order count (PEL entries idle > 5min per stream)

This gives operations everything they need without a separate observability stack.

---

## Migration Path

Don't rewrite everything at once. Three phases:

**Phase 1 (Week 1–2): Decouple web tier.** Implement the 202-response pattern. Orders go to `orders:incoming`. A single monolithic worker reads from the stream and runs the current synchronous `process_order()` logic. Web tier pressure disappears immediately. This alone fixes the 503 errors.

**Phase 2 (Week 3–5): Stage decomposition.** Split the monolithic worker into per-stage workers. Add retry/DLQ. Add idempotency. Run both paths in parallel (feature flag per customer_id), compare results.

**Phase 3 (Week 6–7): Inventory fan-out.** This is the most complex piece — implement the coordination table pattern. Worth doing last because it requires coordinating two new stream types and a DB schema change.

---

## What You're Not Getting (Deliberately)

**Kafka-style replay of the full event log**: Redis Streams retain history up to `MAXLEN`, configured to ~100K entries. You don't get arbitrarily replayable history — if you need that, write audit events to PostgreSQL (you already have it). Don't put that requirement on your order queue.

**Sub-millisecond ordering across consumers**: If two workers grab two messages for the same order simultaneously (only possible on retry), idempotency guards handle it. Don't over-architect ordering — the pipeline topology does 95% of the work.

**Zero ops overhead**: You will add ~20 ECS tasks and a retry daemon. This is manageable for 2 DevOps engineers who already run Redis. It is not Kafka.

---

## Summary

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Queue technology | Redis Streams | Existing infra, operational fit, sufficient durability with AOF |
| Topology | One stream per stage | Maps cleanly to pipeline, enforces ordering structurally |
| Per-order ordering | Pipeline topology + idempotency | Structurally prevents out-of-stage advancement |
| Inventory fan-out | Per-warehouse streams + PostgreSQL coordination table | Correct fan-in gate without distributed locking |
| Retry | PEL + retry daemon with exponential backoff | Native to Redis Streams |
| DLQ | `orders:dlq` stream with ops alert | Inspectable, replayable |
| Web tier | 202 Accepted + async processing | Eliminates thread pool exhaustion |
| Durability | AOF everysec + Multi-AZ ElastiCache | ≤1s exposure window, acceptable for your SLA |