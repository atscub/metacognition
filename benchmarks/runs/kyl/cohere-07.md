Running the coherence audit across all 10 categories now.

---

## Coherence Audit: Order Event Pipeline

**Parts under review:**
- **P** = Producer (`events.py`)
- **C** = Consumer (`orderConsumer.js`)
- **S** = Schema (`order-event.avsc`)

---

### Findings by Category

**1. Factual Accuracy** — 3 defects found

**Defect A — `processed_at` doesn't exist (HIGH)**

| Artifact | What it says |
|----------|-------------|
| Producer | Sets `metadata.timestamp` (Unix float) |
| Schema | Defines `metadata.timestamp` |
| Consumer | Reads `event.metadata.processed_at` — this field does not exist |

The consumer reads a field that neither the producer nor the schema ever populate. `processedAt` will always be `undefined`. It then calls `new Date(undefined)` — producing `Invalid Date` — and stores that in the analytics database. Every row in `order_analytics.processed_at` is invalid.

---

**Defect B — `user_id` nullability conflict (HIGH)**

| Artifact | What it says |
|----------|-------------|
| Producer | `user_id: Optional[str]` — explicitly `None` for system events |
| Schema | `"type": "string"` — non-nullable, required |
| Consumer | `if (!event.user_id) { return; }` — treats null as expected |

The producer sends `null` for `user_id` on every `order.status_changed` event. The Avro schema requires a non-null string. These three parts cannot all be correct simultaneously. The schema needs `["null", "string"]` with `"default": null`, or `publish_order_system_update` must be redesigned not to send a full `OrderEvent`.

---

**Defect C — `metadata.source` missing from schema (MEDIUM)**

| Artifact | What it says |
|----------|-------------|
| Producer | `EventMetadata` includes `source: str` (values: `"api"`, `"system"`) |
| Consumer | Reads and stores `event.metadata.source` |
| Schema | `EventMetadata` has 4 fields — `source` is not among them |

The schema's `EventMetadata` record defines: `event_type`, `timestamp`, `correlation_id`, `version`. The `source` field is used by both the producer and consumer but is invisible to the schema. Any schema validation layer would reject these events or strip the field.

---

**2. Representational Completeness** — Schema is systematically incomplete

The schema represents what the event *should* look like, but the actual events produced contain two fields the schema doesn't know about (`source`, and by runtime behavior, `null` user_ids). The schema cannot be used for validation without breaking the pipeline.

---

**4. Naming Coherence** — `timestamp` vs `processed_at`

The producer and schema both use the name `timestamp` for the event time field. The consumer calls the same concept `processedAt` and uses it as if it were a server-side stamp of when processing occurred. These are the same field but with different semantic interpretations layered on top — further obscuring the bug in Defect A.

---

**8. Category Accuracy** — `publish_order_system_update` sends a mistyped event

`publish_order_system_update` populates an `OrderEvent` with `total_amount=0.0`, `currency="USD"`, `items=[]` for what is a status-change event. This is categorically wrong: status updates are not order creation events, yet they're stuffed into the same record type. The consumer then stores `totalAmount: 0` for every status change, silently corrupting any revenue aggregation in `storeAnalytics`. The `updateDashboard` call is correctly gated on `order.created`, but the `storeAnalytics` call is not gated — every `order.status_changed` event writes a row with `total_amount = 0`.

---

### Consolidated Defect Table

| # | Severity | Location | Description |
|---|----------|----------|-------------|
| A | **High** | Consumer | Reads `metadata.processed_at` — field doesn't exist in producer or schema; actual field is `metadata.timestamp` |
| B | **High** | Producer ↔ Schema | `user_id` is `Optional` in producer (null for system events) but required non-null string in schema |
| C | **Medium** | Schema | `metadata.source` field present in producer and consumed by consumer, but absent from schema |
| D | **Medium** | Producer ↔ Consumer | `publish_order_system_update` emits `total_amount=0.0` for status events; consumer stores this unchecked, corrupting revenue data in analytics |

---

### Recommended Fixes (in priority order)

1. **Fix Defect A** — Consumer line `const processedAt = event.metadata.processed_at;` → `event.metadata.timestamp`. Update `storeAnalytics` call accordingly.

2. **Fix Defect B** — Schema `user_id` type: change `"type": "string"` → `"type": ["null", "string"], "default": null`. Alternatively, create a separate `OrderStatusChangedEvent` schema that doesn't include `user_id`, `total_amount`, or `items`.

3. **Fix Defect C** — Add `{ "name": "source", "type": "string" }` to the schema's `EventMetadata` record.

4. **Fix Defect D** — Guard `storeAnalytics` in the consumer: only call it when `event.total_amount > 0` or `eventType === 'order.created'`. Or redesign the producer to not use `OrderEvent` for status-only updates.