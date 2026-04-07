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