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