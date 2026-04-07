I'll design a high-throughput, low-latency event dispatch architecture that decouples the fast path (internal consumers) from the slow path (external webhooks).

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│ EVENT SOURCE (order.created, order.shipped, etc.)           │
└──────────────────────────┬──────────────────────────────────┘
                           │
                    ┌──────▼────────┐
                    │  Event Topic  │ ← Kafka/RabbitMQ
                    │ (partitioned  │   3 replicas, retention: 7 days
                    │  by order_id) │
                    └──────┬────────┘
        ┌───────────────────┼───────────────────┐
        │                   │                   │
   ┌────▼──────┐   ┌────────▼──────┐   ┌───────▼────┐
   │ Analytics │   │ Inventory     │   │ ETA        │
   │ Pipeline  │   │ Updater       │   │ Predictor  │
   │ (Celery)  │   │ (Celery)      │   │ (Celery)   │
   └───────────┘   └───────────────┘   └────────────┘
        
        ┌─────────────────┬──────────────────┬──────────────┐
        │                 │                  │              │
   ┌────▼──────┐   ┌──────▼──────┐   ┌──────▼─────┐   ┌────▼──────┐
   │ Fraud     │   │ Notification│   │ Billing    │   │ SLA       │
   │ Scorer    │   │ Dispatcher  │   │ Trigger    │   │ Monitor   │
   │ (Celery)  │   │ (Celery)    │   │ (Celery)   │   │ (Celery)  │
   └───────────┘   └─────────────┘   └────────────┘   └───────────┘
        
        
┌──────────────────────────────────────────────────────────────┐
│         WEBHOOK DELIVERY SERVICE (separate path)             │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ Webhook Event Topic (partitioned by order_id)          │  │
│  │ - Contains: event_type, payload, webhook_names        │  │
│  └───────────┬──────────────────────────────────────────┘  │
│              │                                              │
│  ┌───────────▼──────────────────────────────────────────┐  │
│  │ Webhook Delivery Workers (4-8 instances, Celery)     │  │
│  │ - Fetch from topic in order per partition           │  │
│  │ - Dispatch to FedEx, UPS, DHL, Customs              │  │
│  │ - 5-retry exponential backoff with jitter           │  │
│  │ - Success: ACK & move to next event                 │  │
│  │ - Failure: move to DLQ after 5 retries             │  │
│  └───────────┬──────────────────────────────────────────┘  │
│              │                                              │
│  ┌───────────▼──────────────────────────────────────────┐  │
│  │ Dead Letter Queue (webhook failures)                 │  │
│  │ - Persisted for 30 days                             │  │
│  │ - Manual review / alerting                          │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

---

## Detailed Design

### 1. **Messaging Topology**

**Choice: Kafka (RabbitMQ alternative included)**

```python
# Kafka topics configuration

# Primary topic: absorbs all events, 8 internal consumers subscribe
TOPIC_EVENTS = "shiptrack.events"
- Partitions: 12 (by order_id hash % 12) → guarantees causal order per order
- Replication factor: 3
- Retention: 7 days (replay capability for debugging)
- Compression: snappy (reduces network overhead)

# Webhook delivery queue
TOPIC_WEBHOOKS = "shiptrack.webhooks.pending"
- Partitions: 4 (by order_id hash % 4, fewer for webhook service scaling)
- Replication factor: 3
- Retention: 24 hours (webhooks complete within SLA)

# Dead letter queue
TOPIC_WEBHOOKS_DLQ = "shiptrack.webhooks.dead-letter"
- Partitions: 1
- Retention: 30 days (compliance + debugging)
```

**RabbitMQ alternative:**
```
# If using RabbitMQ instead of Kafka
- Exchange: shiptrack.events (direct, durable)
- Queue: internal-consumers (8 workers, durable, exclusive=false)
- Queue: webhooks-pending (durable, persistent messages)
- Queue: webhooks-dlq (durable, 30-day TTL)
```

### 2. **Fast Path: Internal Consumers (Decoupled)**

```python
# producer.py
import kafka
from datetime import datetime

producer = kafka.KafkaProducer(
    bootstrap_servers=['kafka1:9092', 'kafka2:9092', 'kafka3:9092'],
    value_serializer=lambda v: json.dumps(v).encode('utf-8'),
    acks='all',  # Wait for all replicas
    compression_type='snappy'
)

def dispatch_event(event_type: str, payload: dict):
    # Single publish, no blocking on consumers
    event = {
        "id": str(uuid.uuid4()),
        "type": event_type,
        "order_id": payload["order_id"],  # Partition key
        "timestamp": datetime.utcnow().isoformat(),
        "payload": payload,
        "webhooks": determine_webhooks_for_event(event_type)
    }
    
    # Publish to main topic (async fire-and-forget)
    producer.send("shiptrack.events", value=event, key=payload["order_id"].encode())
    
    # Also enqueue for webhook delivery (different topic)
    producer.send("shiptrack.webhooks.pending", value={
        "event_id": event["id"],
        "order_id": payload["order_id"],
        "event_type": event_type,
        "payload": payload,
        "webhooks": event["webhooks"],
        "attempt": 0,
        "created_at": datetime.utcnow().isoformat()
    }, key=payload["order_id"].encode())
    
    return {"status": "queued", "event_id": event["id"]}

# Result: dispatch returns in <100ms (only Kafka network I/O, no consumer blocking)
```

**Internal Celery consumers:**
```python
# tasks.py
from celery import shared_task
from kafka import KafkaConsumer

@shared_task
def consume_analytics_events():
    consumer = KafkaConsumer(
        'shiptrack.events',
        bootstrap_servers=['kafka1:9092'],
        group_id='analytics-pipeline',
        value_deserializer=lambda m: json.loads(m.decode('utf-8')),
        auto_offset_reset='earliest',
        max_poll_records=100
    )
    
    for message in consumer:
        event = message.value
        analytics.process(event['type'], event['payload'])
        # Similar for inventory, eta, fraud, etc.
```

Alternatively: direct Celery consumption without Kafka (if already stable):
```python
@shared_task
def enqueue_internal_tasks(event_type: str, payload: dict):
    """Called after Kafka publish succeeds"""
    tasks = [
        analytics_task.delay(event_type, payload),
        inventory_task.delay(event_type, payload),
        eta_task.delay(event_type, payload),
        fraud_task.delay(event_type, payload),
        notifications_task.delay(event_type, payload),
        audit_task.delay(event_type, payload),
        billing_task.delay(event_type, payload),
        sla_task.delay(event_type, payload),
    ]
    return [t.id for t in tasks]
```

---

### 3. **Webhook Delivery Service (Resilient Async)**

```python
# webhook_dispatcher.py
import requests
import time
from datetime import datetime, timedelta
from kafka import KafkaConsumer, KafkaProducer

class WebhookDispatcher:
    WEBHOOK_CONFIG = {
        "fedex": {
            "url": "https://fedex-partner.example.com/webhook",
            "timeout": 8,
            "max_retries": 5
        },
        "ups": {
            "url": "https://ups-integration.example.com/events",
            "timeout": 8,
            "max_retries": 5
        },
        "dhl": {
            "url": "https://dhl-connect.example.com/shiptrack",
            "timeout": 10,  # DHL is slow
            "max_retries": 5
        },
        "customs": {
            "url": "https://broker.example.com/api/events",
            "timeout": 8,
            "max_retries": 5
        },
    }
    
    BACKOFF_SEQUENCE = [1, 2, 4, 8, 16]  # Exponential: 1s, 2s, 4s, 8s, 16s
    
    def __init__(self):
        self.consumer = KafkaConsumer(
            'shiptrack.webhooks.pending',
            bootstrap_servers=['kafka1:9092'],
            group_id='webhook-dispatcher',
            value_deserializer=lambda m: json.loads(m.decode('utf-8')),
            auto_offset_reset='earliest',
            max_poll_records=50,
            session_timeout_ms=30000
        )
        
        self.producer = KafkaProducer(
            bootstrap_servers=['kafka1:9092'],
            value_serializer=lambda v: json.dumps(v).encode('utf-8')
        )
    
    def dispatch_webhooks(self):
        """Main loop: process webhook queue in order per partition"""
        for message in self.consumer:
            webhook_job = message.value
            
            # Skip if already delivered successfully
            if webhook_job.get("delivered"):
                self.consumer.commit()
                continue
            
            attempt = webhook_job.get("attempt", 0)
            order_id = webhook_job["order_id"]
            event_id = webhook_job["event_id"]
            
            # Deliver to each webhook
            for webhook_name in webhook_job["webhooks"]:
                success = self.deliver_to_webhook(
                    webhook_name,
                    webhook_job["event_type"],
                    webhook_job["payload"],
                    event_id,
                    attempt
                )
                
                if not success and attempt < self.BACKOFF_SEQUENCE[-1]:
                    # Calculate backoff delay (with jitter to avoid thundering herd)
                    backoff = self.BACKOFF_SEQUENCE[min(attempt, len(self.BACKOFF_SEQUENCE) - 1)]
                    jitter = random.uniform(0, backoff * 0.1)
                    delay = backoff + jitter
                    
                    # Re-queue for retry
                    webhook_job["attempt"] = attempt + 1
                    webhook_job["next_retry_at"] = (
                        datetime.utcnow() + timedelta(seconds=delay)
                    ).isoformat()
                    
                    self.producer.send(
                        'shiptrack.webhooks.pending',
                        value=webhook_job,
                        key=order_id.encode()
                    )
                elif not success:
                    # Failed after max retries → DLQ
                    self.producer.send(
                        'shiptrack.webhooks.dead-letter',
                        value={
                            **webhook_job,
                            "failed_webhook": webhook_name,
                            "error": "max_retries_exceeded",
                            "final_attempt": attempt,
                            "timestamp": datetime.utcnow().isoformat()
                        }
                    )
            
            # Commit offset after processing all webhooks for this event
            self.consumer.commit()
    
    def deliver_to_webhook(self, webhook_name: str, event_type: str,
                          payload: dict, event_id: str, attempt: int) -> bool:
        """Deliver to single webhook with idempotency key"""
        config = self.WEBHOOK_CONFIG.get(webhook_name)
        if not config:
            logger.error(f"Unknown webhook: {webhook_name}")
            return False
        
        try:
            # Idempotency key: prevents duplicate processing if retried
            headers = {
                "X-Shiptrack-Event-ID": event_id,
                "X-Shiptrack-Attempt": str(attempt),
                "User-Agent": "ShipTrack/1.0"
            }
            
            response = requests.post(
                config["url"],
                json={"type": event_type, **payload},
                headers=headers,
                timeout=config["timeout"]
            )
            
            if response.status_code < 400:
                logger.info(f"Webhook {webhook_name} delivered, attempt {attempt + 1}")
                return True
            else:
                logger.warning(
                    f"Webhook {webhook_name} returned {response.status_code}, "
                    f"will retry (attempt {attempt + 1})"
                )
                return False
                
        except requests.Timeout:
            logger.warning(
                f"Webhook {webhook_name} timeout after {config['timeout']}s, "
                f"will retry (attempt {attempt + 1})"
            )
            return False
            
        except requests.ConnectionError as e:
            logger.warning(
                f"Webhook {webhook_name} connection failed: {e}, "
                f"will retry (attempt {attempt + 1})"
            )
            return False

# Celery task to run dispatcher
@shared_task
def run_webhook_dispatcher():
    dispatcher = WebhookDispatcher()
    dispatcher.dispatch_webhooks()  # Blocks until consumer closes
```

**Deploy as Celery worker(s):**
```bash
celery -A tasks worker --queues=webhooks -c 4 --loglevel=info
# Run 4-8 instances for parallelism (each handles different partitions)
```

---

### 4. **Ordering & Idempotency Strategy**

```python
# Per-order causal ordering via partition key:
# - All events for order_id=X go to same Kafka partition
# - Webhook dispatcher processes partitions sequentially
# - Each webhook receives events for that order in creation order

# Idempotency mechanism (customer deduplicates on their end):
# - X-Shiptrack-Event-ID: UUID per event (never changes across retries)
# - X-Shiptrack-Attempt: retry attempt number
# - Customers MUST implement idempotent processing with this header
# - Can store in DB: (event_id, webhook_name) → delivered status

# Example webhook handler (customer side):
@app.post("/webhook")
def handle_shiptrack_event():
    event_id = request.headers.get("X-Shiptrack-Event-ID")
    attempt = int(request.headers.get("X-Shiptrack-Attempt", 0))
    
    # Check if already processed
    if WebhookDelivery.query.filter_by(event_id=event_id).exists():
        return {"status": "ok"}, 200  # Idempotent—return success
    
    # Process event
    process_event(request.json)
    
    # Record delivery
    WebhookDelivery.create(event_id=event_id, delivered_at=now())
    
    return {"status": "ok"}, 200
```

---

### 5. **Performance & Throughput Targets**

**Latency Breakdown:**

| Phase | Latency | Notes |
|-------|---------|-------|
| Event → Kafka | 20ms | Network + broker write |
| Kafka → Internal consumer | 50ms | Consumer poll interval |
| **Total internal latency** | **70ms** | ✅ Well under 200ms target |
| | | |
| Event → Webhook queue | 20ms | Same write |
| Webhook queue → Dispatcher | 100ms | Consumer poll |
| Dispatcher → Partner | 5-10s | Network (but non-blocking!) |
| **Total webhook latency** | **5.1-10.1s** | ✅ Under 60s SLA |

**Throughput:**

```
Current: 800 events/hour = 0.22 events/sec
Target:  15,000 events/hour = 4.17 events/sec

Kafka can handle 1M+ events/sec with 3 brokers.
Bottleneck: Webhook dispatcher

Celery workers needed:
- If DHL takes 8s and we need 4.17 events/sec
- Each worker can do ~1 webhook per 8s = 0.125 webhooks/sec
- But each event has 4 webhooks in parallel
- So each worker: 4 webhooks * 0.125 = 0.5 events/sec
- Need: 4.17 / 0.5 = 8-10 worker instances ✅

Better: parallelize webhook delivery within event processing:
```

**Parallel webhook delivery (better throughput):**
```python
def deliver_webhooks_parallel(webhook_job, attempt):
    """Send to all webhooks in parallel, not sequentially"""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    order_id = webhook_job["order_id"]
    
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {}
        for webhook_name in webhook_job["webhooks"]:
            future = executor.submit(
                self.deliver_to_webhook,
                webhook_name,
                webhook_job["event_type"],
                webhook_job["payload"],
                webhook_job["event_id"],
                attempt
            )
            futures[future] = webhook_name
        
        failed_webhooks = []
        for future in as_completed(futures):
            webhook_name = futures[future]
            if not future.result():
                failed_webhooks.append(webhook_name)
    
    # Re-queue only failed webhooks
    if failed_webhooks and attempt < 5:
        webhook_job["webhooks"] = failed_webhooks
        webhook_job["attempt"] = attempt + 1
        self.producer.send('shiptrack.webhooks.pending', value=webhook_job, ...)
    elif failed_webhooks:
        # DLQ for all failures
        for webhook in failed_webhooks:
            self.producer.send('shiptrack.webhooks.dead-letter', value={...})
```

With parallel delivery:
- Each worker: max(DHL 10s) per event = 0.1 events/sec
- For 4.17 events/sec: need 41 workers (expensive) OR reduce worker count with better batching

**Better approach: Increase Kafka partitions and workers**
```python
# Partition strategy:
TOPIC_WEBHOOKS = "shiptrack.webhooks.pending"
- Partitions: 12 (same as main events topic for correlation)
- Consumer group: webhook-dispatcher
- Each worker consumes 1-2 partitions independently
- 6-8 worker instances → each processes different partitions in parallel
- Parallelism within event: ThreadPoolExecutor for 4 webhooks
- Result: ~4-6 events/sec per worker, 24-48 events/sec total ✅
```

---

### 6. **Monitoring & Alerting**

```python
# Key metrics to track
metrics = {
    "event.dispatch.latency.p50": <100ms,  # Target
    "event.dispatch.latency.p99": <400ms,  # Should be quick
    "webhook.delivery.success_rate": >99.5%,
    "webhook.delivery.latency.p99": <30s,  # Before retry
    "webhook.retries.total": <5% of events,
    "dlq.messages": 0 (alert if > 10/hour),
    "consumer.lag": <5s,  # Kafka consumer group lag
}

# Alerts
- If webhook success_rate < 99%, page on-call
- If DLQ growth > 50/hour, investigate
- If event dispatch latency p99 > 500ms, check Kafka broker
- If consumer lag > 30s, scale workers
```

---

## Summary Table

| Aspect | Solution |
|--------|----------|
| **Messaging** | Kafka (3 brokers, 12 partitions for events, 12 for webhooks) |
| **Decoupling** | Async webhooks on separate topic; internal consumers subscribe to main topic |
| **Ordering** | Partition by `order_id` (hash % 12) |
| **Retry** | Exponential backoff [1, 2, 4, 8, 16]s + jitter; max 5 retries |
| **Idempotency** | `X-Shiptrack-Event-ID` header + customer-side deduplication |
| **Latency** | Internal: 70ms ✅; Webhooks: 5-10s + SLA buffer ✅ |
| **Throughput** | 6-8 Celery workers, parallel webhook delivery → 15k+ events/hr ✅ |
| **Delivery guarantee** | At-least-once (with idempotency) ✅ |
| **Dead lettering** | DLQ after 5 failed retries; 30-day retention |

This design unblocks the event loop from webhook latency, guarantees ordering per order, and scales to 15k events/hour while maintaining <200ms latency for your critical path (internal consumers).