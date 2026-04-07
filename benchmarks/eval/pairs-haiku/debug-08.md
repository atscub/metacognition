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
**Found it.** Look at your alias state:

```
products-live  products-20260313030001  - - -    ← OLD index, still here
product-live   products-20260327030001  - - -    ← NEW index here
```

There are **two different aliases** with nearly identical names:
- `products-live` (plural, with 's') — still points to the old index
- `product-live` (singular, no 's') — correctly points to the new index

Your application searches `products-live`, so it's hitting the stale data.

**The bug is in your script, line 34:**

```bash
{ "remove": { "index": "*", "alias": "product-live" } },      # ← missing 's'
{ "add": { "index": "${NEW_INDEX}", "alias": "product-live" } }  # ← missing 's'
```

You defined `ALIAS="products-live"` at the top but hardcoded `"product-live"` (singular) in the swap action. The script swapped the wrong alias, leaving the old index still bound to `products-live`.

**Quick fix:**

```bash
# Line 34-39, use the variable:
curl -s -X POST "${ES_HOST}/_aliases" \
  -H 'Content-Type: application/json' \
  -d "{
    \"actions\": [
      { \"remove\": { \"index\": \"*\", \"alias\": \"${ALIAS}\" } },
      { \"add\": { \"index\": \"${NEW_INDEX}\", \"alias\": \"${ALIAS}\" } }
    ]
  }"
```

**Immediate recovery:** Manually fix the alias:

```bash
curl -X POST "http://es-prod-cluster:9200/_aliases" \
  -H 'Content-Type: application/json' \
  -d '{
    "actions": [
      { "remove": { "index": "products-20260313030001", "alias": "products-live" } },
      { "add": { "index": "products-20260327030001", "alias": "products-live" } }
    ]
  }'
```

Then verify:
```bash
curl -s http://es-prod-cluster:9200/_cat/aliases/products* 
# Should show only one alias entry now
```

Search results should immediately reflect fresh data.

## Response B
## Reframe Analysis

**My initial framing:** "The reindex process failed to complete or transfer data, but the logs are misleading about success."

But that doesn't fit the evidence. The new index *has* the correct data. Let me challenge this.

### Applying the Zoom In & Simplicity Lenses

What if the reindex worked perfectly and the problem is much simpler? Look at what's actually happening:

The **alias swap step** in your script has this code:

```bash
{ \"remove\": { \"index\": \"*\", \"alias\": \"product-live\" } },
{ \"add\": { \"index\": \"${NEW_INDEX}\", \"alias\": \"product-live\" } }
```

But your application searches for:
```typescript
index: 'products-live',    // note: PRODUCTS (plural)
```

And your current alias state shows:
```
products-live  → products-20260313030001  (old index, Mar 13)
product-live   → products-20260327030001  (new index, Mar 27)
```

**There's a typo in the script.** It's swapping the alias `product-live` (singular) but your application expects `products-live` (plural).

---

## What Actually Happened

1. ✅ New index was created and populated correctly
2. ✅ Document counts matched (verification passed)
3. ✅ Alias swap technically succeeded
4. ❌ But it swapped the *wrong* alias name (`product-live` instead of `products-live`)
5. The old `products-live` → old index mapping was never touched
6. A *new* alias `product-live` was created pointing to the new index
7. Your app queries `products-live` (correct name) → still gets old index

---

## Fix

Change line in your script from:

```bash
{ \"remove\": { \"index\": \"*\", \"alias\": \"product-live\" } },
{ \"add\": { \"index\": \"${NEW_INDEX}\", \"alias\": \"product-live\" } }
```

To:

```bash
{ \"remove\": { \"index\": \"*\", \"alias\": \"products-live\" } },
{ \"add\": { \"index\": \"${NEW_INDEX}\", \"alias\": \"products-live\" } }
```

Then either:
- Manually fix the alias now: `curl -X POST es-prod-cluster:9200/_aliases -d '{"actions": [{"remove": {"index": "*", "alias": "products-live"}}, {"add": {"index": "products-20260327030001", "alias": "products-live"}}]}'`
- Or re-run the script with the corrected code

The moment you point `products-live` to the new index, fresh data will show up.

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
