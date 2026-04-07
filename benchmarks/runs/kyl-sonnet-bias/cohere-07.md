## Coherence Audit: Event Producer / Consumer / Schema

Working through the 10 categories, comparing each artifact against the others.

---

### Step 1: Parts Inventory

| Artifact | Defines |
|---|---|
| **Producer** (Python) | `EventMetadata` (5 fields), `OrderEvent` (7 fields), two publish functions |
| **Consumer** (JS) | Field reads from deserialized JSON, analytics storage, dashboard update |
| **Schema** (Avro) | Canonical contract: `OrderEvent` + `EventMetadata` + `OrderItem` |

---

### Step 2: Checklist Results

#### 1. Factual Accuracy — **3 failures**

**F1: `processed_at` doesn't exist (Consumer reads a phantom field)**

| Artifact | Field name |
|---|---|
| Producer `EventMetadata` | `timestamp` (Unix float, `time.time()`) |
| Avro Schema `EventMetadata` | `timestamp` (double) |
| Consumer reads | `event.metadata.processed_at` |

The consumer logs `processed_at`, stores `processedAt: new Date(processedAt)`, and passes it to the DB insert. Since the field doesn't exist, `processedAt` is always `undefined`. `new Date(undefined)` is an invalid Date. Every `processed_at` column written to `order_analytics` contains garbage.

**F2: `source` field produced and consumed but absent from schema**

| Artifact | `source` |
|---|---|
| Producer `EventMetadata` | Field present, set to `"api"` or `"system"` |
| Consumer | Reads `event.metadata.source`, stores in analytics DB |
| Avro Schema `EventMetadata` fields | `event_type`, `timestamp`, `correlation_id`, `version` — **no `source`** |

If the schema is used for validation or serialization (Schema Registry), this field is either stripped or causes a serialization error.

**F3: `version` field produced and schema-defined but never consumed**

Producer emits `version: "1.0"`. Schema declares it with `default: "1.0"`. Consumer never reads or stores it. Minor omission — not a runtime failure — but a factual mismatch between what the contract declares and what the consumer uses.

---

#### 2. Representational Completeness — **1 failure**

**F4: `user_id` nullability is unrepresented in the schema**

| Artifact | `user_id` |
|---|---|
| Producer `OrderEvent` | `Optional[str]` — can be `None` |
| `publish_order_system_update` | Explicitly sets `user_id=None` |
| Avro Schema | `"type": "string"` — **non-nullable, required** |

The schema has no union type (`["null", "string"]`). The producer will produce events with `null` `user_id` that violate the schema contract. In a Schema Registry setup this fails at produce time; without one, it produces malformed data.

The consumer acknowledges the nullability reality (`if (!event.user_id) ... return`) but the schema does not.

---

#### 4. Naming Coherence — **1 failure (same as F1, different framing)**

The concept "when this event occurred" is called three different things:
- `timestamp` in the producer
- `timestamp` in the schema
- `processed_at` in the consumer

Two artifacts agree; the consumer uses a different name for the same concept. This is a naming break, not just a runtime bug.

---

#### 5. Framing Precision — **1 failure**

**F5: System events silently dropped by consumer**

The producer has two publish paths:
- `publish_order_created` → `source: "api"`, `user_id` set
- `publish_order_system_update` → `source: "system"`, `user_id=None`, `total_amount=0.0`, `currency="USD"` (hardcoded placeholder)

The consumer's guard:
```javascript
if (!event.user_id) {
  console.warn(`Event ${correlationId} missing user_id, skipping analytics`);
  return;
}
```

Every system-sourced `order.status_changed` event is silently dropped. The schema's doc says it covers "an order is created **or updated**" — implying status changes should be captured — but the consumer never captures them. The framing of the schema (covers updates) doesn't match the consumer's behavior (ignores updates from system).

Additionally: when a system event is dropped, `storeAnalytics` is never called, so `total_amount: 0.0` / `currency: "USD"` placeholders never corrupt the DB — but that's only because they're dropped, not because the design is sound.

---

#### 8. Category Accuracy — **1 failure (same as F4, type dimension)**

The Avro schema classifies `user_id` as `"type": "string"` (non-nullable). The Python type system classifies it as `Optional[str]`. These are incompatible type categories. One says the field is required; the other says it's optional. Both can't be correct.

---

#### 9. Cross-Reference Redundancy — **No failures**

Each artifact serves a distinct role. No duplication of concern.

---

#### 3, 6, 7, 10 — No findings

Voice, origin fidelity, tone, and scope discipline are not applicable or show no issues.

---

### Step 3: Findings Summary

| # | Finding | Severity | Location |
|---|---|---|---|
| F1 | Consumer reads `processed_at`; producer/schema emit `timestamp` — field doesn't exist | **Critical** | Consumer ↔ Producer + Schema |
| F2 | `source` field in producer and consumer is absent from Avro schema | **High** | Producer + Consumer ↔ Schema |
| F3 | `user_id` is non-nullable in schema but `Optional` in producer; system events send `null` | **High** | Producer ↔ Schema |
| F4 | Consumer silently drops all system events (`user_id=None`), contradicting schema's stated coverage of updates | **Medium** | Consumer ↔ Schema doc + Producer intent |
| F5 | `version` field declared in producer and schema, absent from consumer | **Low** | Consumer ↔ Producer + Schema |

---

### Required Fixes

**F1 (Critical):** Either rename `processed_at` → `timestamp` in the consumer, or add a `processed_at` field to the producer and schema. Rename is almost certainly correct.

**F2 (High):** Add `source` to the Avro schema's `EventMetadata`:
```json
{ "name": "source", "type": "string" }
```

**F3 (High):** Change `user_id` in the Avro schema to a nullable union:
```json
{ "name": "user_id", "type": ["null", "string"], "default": null }
```

**F4 (Medium):** Make a deliberate choice — either:
- Filter system events intentionally and document it, or
- Redesign `publish_order_system_update` to include a real `user_id` and store status changes in analytics

The current `total_amount: 0.0` / `currency: "USD"` hardcoding in the system publisher reinforces that this path was never fully designed.