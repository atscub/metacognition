Here are the discrepancies across the three artifacts:

---

## Discrepancy 1: `metadata.processed_at` vs `metadata.timestamp`

**Most critical — causes a silent runtime bug.**

| Artifact | Field |
|---|---|
| Producer (events.py) | `metadata.timestamp` (Unix float) |
| Schema (order-event.avsc) | `metadata.timestamp` |
| Consumer (orderConsumer.js) | `event.metadata.processed_at` ← **wrong name** |

The consumer reads a field that doesn't exist. `processedAt` will be `undefined`, so `new Date(undefined)` produces an `Invalid Date` that gets written to the database silently.

---

## Discrepancy 2: `metadata.source` missing from schema

| Artifact | Has `source`? |
|---|---|
| Producer `EventMetadata` | Yes — values `"api"` or `"system"` |
| Consumer | Yes — reads `event.metadata.source`, stores it |
| Schema `EventMetadata` | **No** |

The schema omits `source` entirely. Any schema-based validation or deserialization (e.g., Confluent Schema Registry) would reject or strip the field.

---

## Discrepancy 3: `user_id` nullability

| Artifact | Nullable? |
|---|---|
| Producer | `Optional[str]` — explicitly `None` for system events |
| Schema | `"type": "string"` — **required, non-nullable** |
| Consumer | Skips record if falsy — implicitly allows null |

The producer sends `user_id: null` for `publish_order_system_update`. The Avro schema defines it as a plain `string` with no null union, so those messages are schema-invalid. The fix would be `"type": ["null", "string"], "default": null`.

---

## Discrepancy 4: Consumer silently drops system events

This is behavioral, not structural. The producer has an explicit `publish_order_system_update` path that sets `user_id=None`, `items=[]`, `total_amount=0.0` to represent system-generated status transitions. The consumer treats a missing `user_id` as a reason to skip analytics entirely:

```javascript
if (!event.user_id) {
  console.warn(`Event ${correlationId} missing user_id, skipping analytics`);
  return;
}
```

`order.status_changed` events (e.g., shipped, delivered, cancelled) will never reach the analytics store or dashboard. Whether intentional or not, this is undocumented and inconsistent with the producer's design intent.

---

## Summary table

| Issue | Producer | Schema | Consumer |
|---|---|---|---|
| Timestamp field name | `timestamp` | `timestamp` | `processed_at` ❌ |
| `source` in metadata | present | **absent** ❌ | present |
| `user_id` nullable | `Optional[str]` | non-nullable ❌ | skips if null |
| System events tracked | emitted | — | silently dropped ❌ |