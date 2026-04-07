Here are the discrepancies I found:

---

## Discrepancy 1: `metadata.processed_at` does not exist (Consumer vs. Producer + Schema)

The consumer reads `event.metadata.processed_at` in two places:
```javascript
const processedAt = event.metadata.processed_at;
// ...
processedAt: new Date(processedAt),
```

Neither the producer's `EventMetadata` dataclass nor the Avro schema define a `processed_at` field. The producer emits **`timestamp`** instead. This means `processedAt` is always `undefined`, `new Date(undefined)` produces an invalid date, and the `processed_at` column in `order_analytics` will always be garbage.

**Fix**: Change the consumer to read `event.metadata.timestamp`.

---

## Discrepancy 2: `user_id` is nullable in the producer but non-nullable in the schema

The producer defines `user_id: Optional[str]` and explicitly sends `null` in `publish_order_system_update`. The Avro schema declares:
```json
{ "name": "user_id", "type": "string" }
```
A bare `"string"` type in Avro does not accept `null`. System-generated events would fail schema validation.

**Fix**: Change the schema type to `["null", "string"]` with a `"default": null`.

---

## Discrepancy 3: `metadata.source` is missing from the schema (Producer + Consumer vs. Schema)

The producer's `EventMetadata` includes a `source` field (`"api"` or `"system"`), and the consumer reads and stores it:
```javascript
const source = event.metadata.source;
// ...
await storeAnalytics({ ..., source, ... });
```
The Avro schema's `EventMetadata` record has no `source` field — it only defines `event_type`, `timestamp`, `correlation_id`, and `version`. The field would be silently dropped or cause schema validation errors depending on the registry configuration.

**Fix**: Add `{ "name": "source", "type": "string" }` to the schema's `EventMetadata` fields.

---

## Discrepancy 4: Consumer silently drops all system events (Producer vs. Consumer)

The producer intentionally publishes events with `user_id=None` via `publish_order_system_update`. The consumer treats a missing `user_id` as a skip condition:
```javascript
if (!event.user_id) {
  console.warn(`Event ${correlationId} missing user_id, skipping analytics`);
  return;
}
```
This means every system-generated status-change event (`order.status_changed` with `source="system"`) is silently discarded by analytics. Combined with Discrepancy 2, these events are structurally expected by the producer but completely invisible to the consumer.

This may be intentional, but it is undocumented and inconsistent — the schema implies `user_id` is always present, the producer sends it as `null`, and the consumer skips on `null` without any corresponding contract.

---

## Summary table

| # | Field | Producer | Consumer | Schema |
|---|-------|----------|----------|--------|
| 1 | metadata timestamp key | `timestamp` | `processed_at` ❌ | `timestamp` |
| 2 | `user_id` nullability | `Optional[str]` | warns + skips | non-nullable `string` ❌ |
| 3 | `metadata.source` | present | reads it | missing ❌ |
| 4 | system events | sent with `user_id=null` | silently dropped | not modeled |