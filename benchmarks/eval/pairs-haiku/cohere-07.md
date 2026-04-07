# Task: cohere-07 — Event schema — producer vs consumer vs schema registry

## Prompt
Review the following three artifacts for consistency. Identify any discrepancies between them.

## Artifact 1: Event Producer (services/order_service/events.py)

```python
import json
import time
from dataclasses import dataclass, asdict
from typing import Optional
from confluent_kafka import Producer

kafka_config = {
    "bootstrap.servers": "kafka:9092",
    "client.id": "order-service",
}
producer = Producer(kafka_config)

TOPIC = "order.events"


@dataclass
class EventMetadata:
    event_type: str
    timestamp: float
    source: str
    correlation_id: str
    version: str = "1.0"


@dataclass
class OrderEvent:
    order_id: str
    user_id: Optional[str]
    status: str
    total_amount: float
    currency: str
    items: list
    metadata: EventMetadata


def publish_order_created(order, correlation_id: str):
    metadata = EventMetadata(
        event_type="order.created",
        timestamp=time.time(),
        source="api",
        correlation_id=correlation_id,
    )

    event = OrderEvent(
        order_id=order.id,
        user_id=order.user.id if order.user else None,
        status="created",
        total_amount=float(order.total),
        currency=order.currency,
        items=[
            {
                "product_id": item.product_id,
                "quantity": item.quantity,
                "unit_price": float(item.price),
            }
            for item in order.items
        ],
        metadata=metadata,
    )

    payload = asdict(event)
    producer.produce(
        topic=TOPIC,
        key=order.id.encode("utf-8"),
        value=json.dumps(payload).encode("utf-8"),
    )
    producer.flush()


def publish_order_system_update(order_id: str, new_status: str, correlation_id: str):
    """Publish status updates from background jobs (no user context)."""
    metadata = EventMetadata(
        event_type="order.status_changed",
        timestamp=time.time(),
        source="system",
        correlation_id=correlation_id,
    )

    event = OrderEvent(
        order_id=order_id,
        user_id=None,  # system-generated, no user
        status=new_status,
        total_amount=0.0,
        currency="USD",
        items=[],
        metadata=metadata,
    )

    payload = asdict(event)
    producer.produce(
        topic=TOPIC,
        key=order_id.encode("utf-8"),
        value=json.dumps(payload).encode("utf-8"),
    )
    producer.flush()
```

## Artifact 2: Event Consumer (services/analytics/orderConsumer.js)

```javascript
const { Kafka } = require('kafkajs');

const kafka = new Kafka({
  clientId: 'analytics-service',
  brokers: ['kafka:9092'],
});

const consumer = kafka.consumer({ groupId: 'analytics-group' });

async function processOrderEvent(message) {
  const event = JSON.parse(message.value.toString());

  // Extract metadata
  const eventType = event.metadata.event_type;
  const processedAt = event.metadata.processed_at;
  const source = event.metadata.source;
  const correlationId = event.metadata.correlation_id;

  console.log(`Processing ${eventType} [${correlationId}] processed at ${processedAt}`);

  // Validate required fields
  if (!event.user_id) {
    console.warn(`Event ${correlationId} missing user_id, skipping analytics`);
    return;
  }

  if (!event.order_id || !event.status) {
    throw new Error(`Malformed event: missing order_id or status`);
  }

  // Store analytics data
  await storeAnalytics({
    orderId: event.order_id,
    userId: event.user_id,
    status: event.status,
    totalAmount: event.total_amount,
    currency: event.currency,
    itemCount: event.items.length,
    eventType,
    source,
    processedAt: new Date(processedAt),
    receivedAt: new Date(),
  });

  // Update real-time dashboard
  if (eventType === 'order.created') {
    await updateDashboard({
      metric: 'orders_created',
      userId: event.user_id,
      amount: event.total_amount,
      currency: event.currency,
    });
  }
}

async function storeAnalytics(data) {
  // Insert into analytics database
  const { pool } = require('../db');
  await pool.query(
    `INSERT INTO order_analytics
      (order_id, user_id, status, total_amount, currency, item_count,
       event_type, source, processed_at, received_at)
     VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)`,
    [
      data.orderId, data.userId, data.status, data.totalAmount,
      data.currency, data.itemCount, data.eventType, data.source,
      data.processedAt, data.receivedAt,
    ]
  );
}

async function updateDashboard(data) {
  const { redis } = require('../cache');
  await redis.hincrby(`dashboard:${data.currency}`, 'order_count', 1);
  await redis.hincrbyfloat(`dashboard:${data.currency}`, 'total_revenue', data.amount);
}

async function start() {
  await consumer.connect();
  await consumer.subscribe({ topic: 'order.events', fromBeginning: false });
  await consumer.run({
    eachMessage: async ({ message }) => {
      try {
        await processOrderEvent(message);
      } catch (err) {
        console.error('Failed to process order event:', err);
      }
    },
  });
}

module.exports = { start };
```

## Artifact 3: Avro Schema (schemas/order-event.avsc)

```json
{
  "type": "record",
  "name": "OrderEvent",
  "namespace": "com.example.orders",
  "doc": "Event emitted when an order is created or updated",
  "fields": [
    {
      "name": "order_id",
      "type": "string",
      "doc": "Unique identifier for the order"
    },
    {
      "name": "user_id",
      "type": "string",
      "doc": "ID of the user who placed the order"
    },
    {
      "name": "status",
      "type": {
        "type": "enum",
        "name": "OrderStatus",
        "symbols": ["created", "confirmed", "shipped", "delivered", "cancelled"]
      }
    },
    {
      "name": "total_amount",
      "type": "double"
    },
    {
      "name": "currency",
      "type": "string"
    },
    {
      "name": "items",
      "type": {
        "type": "array",
        "items": {
          "type": "record",
          "name": "OrderItem",
          "fields": [
            { "name": "product_id", "type": "string" },
            { "name": "quantity", "type": "int" },
            { "name": "unit_price", "type": "double" }
          ]
        }
      }
    },
    {
      "name": "metadata",
      "type": {
        "type": "record",
        "name": "EventMetadata",
        "fields": [
          { "name": "event_type", "type": "string" },
          { "name": "timestamp", "type": "double" },
          { "name": "correlation_id", "type": "string" },
          { "name": "version", "type": "string", "default": "1.0" }
        ]
      }
    }
  ]
}
```


## Response A
Now I'll systematically audit these three artifacts for coherence. Let me work through the 10 categories:

## 1. **Factual Accuracy**

**Critical Issue Found**: Metadata field mismatch

| Artifact | Field Present? |
|----------|---|
| Producer (Python) | `timestamp`, `source`, `correlation_id`, `version` |
| Consumer (JS) | References `processed_at` (doesn't exist in producer) |
| Schema | `timestamp`, `correlation_id`, `version` — **NO `source`** |

**Discrepancy**: The consumer expects `metadata.processed_at`, but the producer never sets this field. The producer sets `source`, but the schema omits it entirely.

---

## 2. **Representational Completeness**

**Issue**: The schema is incomplete. It defines:
- `order_id` (required)
- `user_id` (required in schema)
- `status`, `total_amount`, `currency`, `items`, `metadata`

But it's **missing the `source` field** that the producer includes in metadata. The Avro schema is the contract — if `source` exists in produced messages, it must be in the schema.

---

## 3. **Voice Consistency**

**Moderate Issue**: The consumer refers to "processed at" (JS naming convention) while the producer uses `timestamp` (generic). This suggests different mental models of the same concept.

---

## 4. **Naming Coherence**

**High-Impact Issue**: Same concept, different names:
- Producer calls it: `timestamp` (in EventMetadata)
- Consumer reads it as: `processed_at` (doesn't exist)
- Schema calls it: `timestamp`

The consumer is looking for the wrong field name.

---

## 5. **Framing Precision**

**Issue**: The Avro schema doc says "Event emitted when an order is created or updated" but the producer has two functions:
- `publish_order_created()` — creates `order.created` event
- `publish_order_system_update()` — creates `order.status_changed` event

The schema framing is too narrow — it only mentions creation, not status changes.

---

## 6. **Origin Fidelity**

**Issue**: The producer has a `source` field (set to "api" or "system") which indicates intentional differentiation between user-initiated vs. system-generated events. The schema completely omits this field, suggesting the schema was created without understanding the producer's intent.

---

## 7. **Tone Calibration**

The artifacts vary wildly in formality:
- **Producer**: Minimal documentation (one docstring)
- **Consumer**: Extensive comments and error handling
- **Schema**: Formal Avro style with namespace and documentation

This isn't necessarily wrong, but it suggests they were created independently.

---

## 8. **Category Accuracy**

**Critical Issue**: The Avro schema marks `user_id` as required (no `null` type), but the producer explicitly allows:
```python
user_id=order.user.id if order.user else None  # Can be None!
user_id=None,  # System events have no user
```

The schema should have: `"type": ["null", "string"]` to match producer behavior.

---

## 9. **Cross-Reference Redundancy**

The three artifacts define overlapping structures:
- Producer defines `OrderEvent` dataclass
- Schema defines `OrderEvent` Avro record
- Consumer infers structure from messages

There's no explicit reference between them. The schema appears to be a standalone definition rather than the source-of-truth that both producer and consumer should follow.

---

## 10. **Scope Discipline**

**Minor Issue**: The consumer includes implementation details (Redis caching, database storage) that are outside the scope of the event contract. These don't affect coherence with the other artifacts, but they blur the line between "event consumer interface" and "analytics service internals."

---

## Summary: Critical Discrepancies

| Issue | Severity | Impact |
|-------|----------|--------|
| `processed_at` field doesn't exist in producer | **CRITICAL** | Consumer crashes on `event.metadata.processed_at` |
| `user_id` nullable in code but required in schema | **CRITICAL** | Schema validation will reject valid system events |
| `source` field in producer but missing from schema | **HIGH** | Schema incomplete; producer validation will fail |
| Metadata structure mismatch (multiple fields) | **HIGH** | Serialization/deserialization will fail |

**Root cause**: The Avro schema was not derived from the producer code — it's a separate definition with gaps.

## Response B
# Consistency Review: Event Artifacts

I found **3 significant discrepancies** between the artifacts:

## 1. **Missing `source` field in Avro Schema** ❌
- **Producer** (Artifact 1): Creates `source` in EventMetadata ("api" or "system")
- **Schema** (Artifact 3): Does NOT define `source` field
- **Impact**: Events will fail schema validation when published to Kafka

**Fix**: Add to Avro schema metadata fields:
```json
{ "name": "source", "type": "string" }
```

---

## 2. **Consumer reads non-existent `processed_at` field** ❌
- **Consumer** (Artifact 2): Reads `event.metadata.processed_at`
- **Producer** (Artifact 1): Creates `timestamp`, NOT `processed_at`
- **Schema** (Artifact 3): Defines `timestamp`, NOT `processed_at`
- **Impact**: `processedAt` will always be undefined in the consumer

**Likely fix**: Consumer should read `event.metadata.timestamp` instead:
```javascript
const processedAt = event.metadata.timestamp;  // not processed_at
```

---

## 3. **Avro schema doesn't allow nullable `user_id`** ❌
- **Producer** (Artifact 1): Sets `user_id=None` for system updates
- **Schema** (Artifact 3): Defines `user_id` as non-nullable `"string"`
- **Impact**: System-generated events (`publish_order_system_update`) violate the schema

**Fix**: Make `user_id` nullable in schema:
```json
{
  "name": "user_id",
  "type": ["null", "string"],
  "default": null
}
```

---

## Summary Table

| Field | Producer | Consumer | Schema | Status |
|-------|----------|----------|--------|--------|
| `source` | ✓ Created | ✗ Used | ✗ Missing | **CONFLICT** |
| `timestamp` | ✓ Created | ✗ Reads `processed_at` | ✓ Defined | **MISMATCH** |
| `user_id` | ✓ Can be null | ✓ Expects nullable | ✗ Non-nullable | **CONFLICT** |

All three need to be fixed before events will validate and process correctly.

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
