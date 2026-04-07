# Task: debug-08 — Elasticsearch returning stale results after index rebuild

## Prompt
We rebuilt our Elasticsearch product index last night to pick up schema changes, but
search results are still returning stale data. Products updated in the last two weeks
show old prices and descriptions. The engineering team thinks the reindex didn't complete
fully, but the logs show success. Can you figure out what went wrong?

Index rebuild script (scripts/rebuild-product-index.sh):

```bash
#!/bin/bash
set -euo pipefail

ES_HOST="http://es-prod-cluster:9200"
NEW_INDEX="products-$(date +%Y%m%d%H%M%S)"
ALIAS="products-live"

echo "[$(date)] Step 1: Creating new index ${NEW_INDEX}"
curl -s -X PUT "${ES_HOST}/${NEW_INDEX}" \
  -H 'Content-Type: application/json' \
  -d @/opt/config/product-index-mapping.json

echo "[$(date)] Step 2: Reindexing from database"
node /opt/scripts/db-to-es-sync.js --target="${NEW_INDEX}" --batch-size=5000

echo "[$(date)] Step 3: Verifying document count"
DB_COUNT=$(psql -t -c "SELECT count(*) FROM products WHERE active = true" | tr -d ' ')
ES_COUNT=$(curl -s "${ES_HOST}/${NEW_INDEX}/_count" | jq '.count')

echo "  DB count: ${DB_COUNT}"
echo "  ES count: ${ES_COUNT}"

if [ "${DB_COUNT}" != "${ES_COUNT}" ]; then
  echo "ERROR: Count mismatch! Aborting."
  exit 1
fi

echo "[$(date)] Step 4: Swapping alias"
SWAP_RESPONSE=$(curl -s -X POST "${ES_HOST}/_aliases" \
  -H 'Content-Type: application/json' \
  -d "{
    \"actions\": [
      { \"remove\": { \"index\": \"*\", \"alias\": \"product-live\" } },
      { \"add\": { \"index\": \"${NEW_INDEX}\", \"alias\": \"product-live\" } }
    ]
  }")

echo "  Alias swap response: ${SWAP_RESPONSE}"

echo "[$(date)] Step 5: Cleanup old indices"
OLD_INDICES=$(curl -s "${ES_HOST}/_cat/indices/products-*" \
  | awk '{print $3}' \
  | grep -v "${NEW_INDEX}" \
  | head -5)

for idx in ${OLD_INDICES}; do
  echo "  Deleting old index: ${idx}"
  curl -s -X DELETE "${ES_HOST}/${idx}"
done

echo "[$(date)] Rebuild complete!"
```

Rebuild log output (from last night):

```
[2026-03-27 03:00:01] Step 1: Creating new index products-20260327030001
[2026-03-27 03:00:02] Step 2: Reindexing from database
  Batch 1/47: 5000 docs indexed
  Batch 2/47: 5000 docs indexed
  ...
  Batch 47/47: 2341 docs indexed
  Total: 232,341 documents indexed
[2026-03-27 03:12:45] Step 3: Verifying document count
  DB count: 232341
  ES count: 232341
[2026-03-27 03:12:46] Step 4: Swapping alias
  Alias swap response: {"acknowledged":true}
[2026-03-27 03:12:47] Step 5: Cleanup old indices
  Deleting old index: products-20260313030001
  Deleting old index: products-20260120030002
[2026-03-27 03:12:48] Rebuild complete!
```

Elasticsearch cluster health:

```
$ curl -s es-prod-cluster:9200/_cluster/health | jq .
{
  "cluster_name": "prod-search",
  "status": "green",
  "number_of_nodes": 3,
  "active_primary_shards": 15,
  "active_shards": 30,
  "unassigned_shards": 0
}
```

Current alias state:

```
$ curl -s es-prod-cluster:9200/_cat/aliases/products*
products-live  products-20260313030001  - - -
product-live   products-20260327030001  - - -
```

Search query used by the application:

```typescript
// src/services/search.ts
const searchProducts = async (query: string) => {
  const result = await esClient.search({
    index: 'products-live',    // uses the alias
    body: {
      query: {
        multi_match: {
          query,
          fields: ['name^3', 'description', 'category'],
        },
      },
    },
  });
  return result.hits.hits;
};
```

The team verified:
- The new index `products-20260327030001` has all 232,341 documents with correct data
- Querying the new index directly returns fresh results
- The application is definitely using the `products-live` alias (confirmed in logs)
- Cluster health is green, no shard allocation issues

Spot-check on the new index (direct query):

```
GET products-20260327030001/_doc/prod_1234
{
  "name": "Wireless Headphones Pro",
  "price": 79.99,           // ← correct new price
  "description": "Updated 2026 model with noise cancellation"
}
```

Spot-check via the alias:

```
GET products-live/_doc/prod_1234
{
  "name": "Wireless Headphones Pro",
  "price": 99.99,           // ← old price!
  "description": "Premium wireless headphones"
}
```

What's going on?


## Response A
The bug is a typo in the alias name — one character difference that's easy to miss.

**Root cause: `product-live` vs `products-live`**

The script (Step 4) swaps the alias `product-live` (no 's'), but the application queries `products-live` (with 's').

```bash
# Step 4 in the script — WRONG alias name:
{ "remove": { "index": "*", "alias": "product-live" } },
{ "add":    { "index": "${NEW_INDEX}", "alias": "product-live" } }
```

The current alias state confirms this exactly:

```
products-live  products-20260313030001  ← OLD index, correct alias — untouched
product-live   products-20260327030001  ← NEW index, wrong alias — nobody reads this
```

The reindex completed perfectly. All 232,341 docs are correct in the new index. But the alias swap operated on `product-live`, leaving `products-live` still pointing at the two-week-old index. The `{"acknowledged":true}` response wasn't a lie — ES successfully swapped an alias nobody uses.

**Fix the script:**

```bash
# Step 4: Swapping alias
SWAP_RESPONSE=$(curl -s -X POST "${ES_HOST}/_aliases" \
  -H 'Content-Type: application/json' \
  -d "{
    \"actions\": [
      { \"remove\": { \"index\": \"*\", \"alias\": \"products-live\" } },
      { \"add\":    { \"index\": \"${NEW_INDEX}\", \"alias\": \"products-live\" } }
    ]
  }")
```

**Immediate remediation** (no reindex needed — data is already correct):

```bash
curl -X POST "es-prod-cluster:9200/_aliases" -H 'Content-Type: application/json' -d '{
  "actions": [
    { "remove": { "index": "*",                    "alias": "products-live" } },
    { "add":    { "index": "products-20260327030001", "alias": "products-live" } }
  ]
}'
```

This is a zero-downtime fix. Once run, `products-live` points at the new index and fresh data is live instantly.

**To prevent recurrence**, add a validation step to the script after the swap:

```bash
# After Step 4, verify the RIGHT alias points to the new index
LIVE_INDEX=$(curl -s "${ES_HOST}/_alias/products-live" | jq -r 'keys[0]')
if [ "${LIVE_INDEX}" != "${NEW_INDEX}" ]; then
  echo "ERROR: products-live alias did not update! Points to: ${LIVE_INDEX}"
  exit 1
fi
```

## Response B
## Applying Reframe Before Diagnosing

**Initial framing (what the team thinks):** "Reindex didn't complete" — but the evidence directly contradicts this. Let me question that assumption.

---

### Zoom In Lens: Read the exact evidence byte by byte

The alias state output is the key artifact. Look at it very carefully:

```
products-live  products-20260313030001  - - -   ← OLD index (March 13)
product-live   products-20260327030001  - - -   ← NEW index (March 27)
```

There are **two different alias names** here:
- `products-live` (with **s**) — what the application queries
- `product-live` (without **s**) — what the script actually swapped

---

### The Bug: Typo in the Alias Swap

Now look at the script's Step 4:

```bash
ALIAS="products-live"   # ← defined correctly at the top, never used below

# Step 4 hardcodes a different name:
{ \"remove\": { \"index\": \"*\", \"alias\": \"product-live\" } },
{ \"add\": { \"index\": \"${NEW_INDEX}\", \"alias\": \"product-live\" } }
```

The `$ALIAS` variable is set but **never referenced** in the curl body. The literal string `"product-live"` is hardcoded instead — missing the **s**.

**What actually happened:**
1. Reindex completed perfectly — 232,341 docs, counts match ✓
2. Step 4 successfully created/updated the `product-live` alias → ES returned `{"acknowledged":true}` ✓ (but on the *wrong* alias)
3. `products-live` was never touched — still points to the March 13 old index
4. The application queries `products-live` → gets stale data

---

### Secondary Issue: Silent Deletion Attempt

The cleanup step tried to delete `products-20260313030001`, but:

```bash
curl -s -X DELETE "${ES_HOST}/${idx}"
# no response check, no exit code validation
```

If that deletion failed (e.g., a permission issue), it would fail silently. The alias state showing the old index still alive and serving data suggests the deletion either failed or the alias became dangling but ES somehow preserved the data. Worth checking ES logs for that DELETE request's actual response.

---

### Fix

**Immediate:** Point `products-live` to the new index:

```bash
curl -X POST "http://es-prod-cluster:9200/_aliases" \
  -H 'Content-Type: application/json' \
  -d '{
    "actions": [
      { "remove": { "index": "*", "alias": "products-live" } },
      { "add": { "index": "products-20260327030001", "alias": "products-live" } }
    ]
  }'
```

**Script fix:** Use the `$ALIAS` variable in Step 4 instead of the hardcoded literal:

```bash
SWAP_RESPONSE=$(curl -s -X POST "${ES_HOST}/_aliases" \
  -H 'Content-Type: application/json' \
  -d "{
    \"actions\": [
      { \"remove\": { \"index\": \"*\", \"alias\": \"${ALIAS}\" } },
      { \"add\": { \"index\": \"${NEW_INDEX}\", \"alias\": \"${ALIAS}\" } }
    ]
  }")
```

Also add response validation after the swap — `{"acknowledged":true}` alone doesn't confirm the *right* alias was updated. Check that `$ALIAS` is actually listed in the response or follow up with a `_cat/aliases` verification step.

---

### Why the Reframe Mattered

The team's hypothesis ("incomplete reindex") sent them looking at document counts, shard health, and sync logs — all of which were fine. The real failure was in **Step 4**, which succeeded at doing the wrong thing. The logs showed success *because the operation did succeed* — just against a phantom alias nobody queries.

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
