## Architecture: ShipTrack Event Dispatch

The fundamental problem is that 12 consumers share one execution context, and the slowest one (DHL at 6-8s) gates everything else. The fix is **topology separation by consumer contract**: internal consumers need low latency; external webhooks need durability and retries. These are different requirements and should use different infrastructure.

---

### Topology

```
dispatch_event()
      │
      ▼
Kafka (dual publish, < 5ms)
      │                         │
      ▼                         ▼
shiptrack.events         shiptrack.webhooks
(partitioned by order_id)  (partitioned by order_id)
      │                         │
      ▼                         ▼
8 Consumer groups          Kafka→Celery bridge
(each service independent)       │
                           ┌─────┴──────────┐
                           ▼                ▼
                    webhooks.fast     webhooks.dhl
                    (fedex,ups,         (isolated
                     customs)         worker pool)
                           │                │
                           └────────┬───────┘
                                    ▼
                               webhook.dlq → DB + page
```

---

### Producer: Remove sync from critical path

```python
_producer = Producer({"bootstrap.servers": KAFKA_BROKERS, "acks": "all"})

def dispatch_event(event_type: str, payload: dict):
    envelope = {
        "type": event_type,
        "event_id": str(uuid4()),
        "created_at": time.time(),
        **payload,
    }
    order_id = str(payload.get("order_id", "")).encode()

    _producer.produce("shiptrack.events",   key=order_id, value=json.dumps(envelope).encode())
    _producer.produce("shiptrack.webhooks", key=order_id, value=json.dumps(envelope).encode())
    _producer.flush()  # ~2-5ms with linger.ms=5
```

`acks=all` + replication factor 3 means the event is durable before returning. Target: **< 5ms** vs. current 2.3s average.

---

### Internal Consumers: Independent offset tracking

Each of the 8 services runs a standard Kafka consumer in its own process. No logic changes — just replace direct calls with a poll loop:

```python
_consumer = Consumer({"group.id": "analytics", ...})
_consumer.subscribe(["shiptrack.events"])
while True:
    msg = _consumer.poll(1.0)
    if msg and not msg.error():
        analytics.process(msg["type"], msg)
        _consumer.commit(asynchronous=False)
```

Each group has independent offsets. If billing falls behind during a deploy, analytics is unaffected.

---

### Webhook Delivery: Celery with per-destination queue isolation

```python
@app.task(
    bind=True,
    max_retries=5,
    acks_late=True,       # at-least-once: re-enqueue on worker crash
)
def deliver_webhook(self, name: str, payload: dict):
    try:
        resp = requests.post(WEBHOOK_URLS[name], json=payload, timeout=15)
        resp.raise_for_status()
    except (requests.Timeout, requests.ConnectionError, requests.HTTPError) as exc:
        if time.time() - payload["created_at"] > 55:
            deliver_webhook_dlq.apply_async(args=[name, payload, str(exc)])
            return
        # Exponential backoff: 30s → 60s → 120s → 240s → 480s
        raise self.retry(exc=exc, countdown=30 * (2 ** self.request.retries))
```

DHL gets a **dedicated queue and worker pool** (`webhooks.dhl`). This is the critical isolation decision: DHL's 6-8s response time cannot be allowed to queue-starve FedEx/UPS/customs, which respond in < 500ms. Separate queues = separate concurrency budgets.

```python
WEBHOOK_QUEUES = {
    "dhl":     "webhooks.dhl",   # 2 workers, isolated
    "fedex":   "webhooks.fast",
    "ups":     "webhooks.fast",
    "customs": "webhooks.fast",
}
```

---

### Ordering Guarantee

The causal ordering contract is met by a chain of three properties:

1. **Kafka partitioning by `order_id`**: all events for one order land on one partition, consumed in offset order
2. **Bridge publishes tasks sequentially**: one event at a time, commits only after all 4 `apply_async` calls succeed
3. **Celery FIFO queue**: tasks arrive in submission order; workers pull in FIFO order

The one edge case is retry interleaving — if event N fails and retries after event N+1 delivered. Include `sequence_num` (Kafka offset) in the payload; webhook partners can use idempotency keys and reject out-of-order delivery. Document this in the webhook contract.

---

### Technology Choice: Kafka over alternatives

| | Kafka | RabbitMQ | Redis Streams |
|---|---|---|---|
| Native partition ordering | Yes | No (need exclusive consumers) | Yes |
| Independent consumer groups | Yes, built-in | Requires separate queues | Yes |
| Log replay on consumer lag | Yes | No | Limited |
| Throughput at 15k events/hour | Massive headroom | Adequate | Adequate |

Redis Streams would work at this scale, but Kafka's consumer group model maps cleanly to 8 independent services and the ordering guarantee is simpler to reason about. The existing Celery+Redis stack handles webhook retry state, which is where Redis earns its place.

---

### Throughput Math

15,000 events/hour = **4.2 events/second**. This is trivially within capacity:

- Kafka: ~1M msgs/sec capacity
- 4 webhooks × 4.2 events/sec = 16.7 webhook calls/sec
- Celery at `--concurrency=20` × 2 workers = 40 concurrent outbound HTTP requests — 2x headroom even if every call takes 500ms

---

### Expected Metrics After Migration

| Metric | Current | After |
|---|---|---|
| Avg dispatch latency | 2.3s | < 5ms |
| P99 latency | 12.8s | < 10ms |
| Webhook success rate | 94% | > 99.5% |
| Peak internal consumer delay | 45s | < 1s |
| Webhook SLA compliance (60s) | Breached on DHL timeout | Met; DLQ + page on breach |

---

### Migration Path (5 weeks, zero downtime)

1. **Week 1** — Deploy Kafka, dual-write alongside old `dispatch_event`. Validate events appear in both paths.
2. **Week 2** — Migrate internal consumers to Kafka. Remove 8 direct function calls from the loop.
3. **Week 3** — Deploy webhook bridge + Celery workers. Shadow mode: fire webhooks from both paths, compare delivery receipts with partners.
4. **Week 4** — Cut over webhooks to Kafka/Celery path. Remove synchronous webhook loop.
5. **Week 5** — Remove dual-write. Retire old `dispatch_event`.

Each step is independently rollbackable. Partners see no change in payload shape, only improved reliability.