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