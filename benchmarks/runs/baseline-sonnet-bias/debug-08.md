## Root Cause: Typo in the Alias Name

The alias swap succeeded — it just swapped the **wrong alias**.

Look at Step 4 of the script:

```bash
{ \"remove\": { \"index\": \"*\", \"alias\": \"product-live\" } },
{ \"add\": { \"index\": \"${NEW_INDEX}\", \"alias\": \"product-live\" } }
```

The script uses `product-live` (no **s**), but the application queries `products-live` (with **s**).

The current alias state confirms exactly this:

```
products-live  products-20260313030001   ← OLD index, NEVER touched
product-live   products-20260327030001   ← NEW index, wrong alias name
```

The remove action silently did nothing (or removed a nonexistent alias — ES won't error on that), then created a brand-new alias `product-live` pointing to the new index. The original `products-live` alias was left untouched, still pointing to the March 13 index.

The document count check passed because it verified the new index directly by name, not via the alias. Everything looked fine in the logs because `{"acknowledged":true}` just means ES accepted the request — it doesn't validate that the alias you removed existed.

## Fix

**Immediate:** Manually swap the correct alias:

```bash
curl -X POST "http://es-prod-cluster:9200/_aliases" \
  -H 'Content-Type: application/json' \
  -d '{
    "actions": [
      { "remove": { "index": "*", "alias": "products-live" } },
      { "add":    { "index": "products-20260327030001", "alias": "products-live" } }
    ]
  }'
```

Then optionally clean up the spurious `product-live` alias:

```bash
curl -X DELETE "http://es-prod-cluster:9200/products-20260327030001/_alias/product-live"
```

**In the script**, fix the typo on both alias references in Step 4 (`product-live` → `products-live`), and consider adding a guard that fails loudly if the alias doesn't exist before the swap:

```bash
# Verify the alias exists before attempting removal
EXISTING=$(curl -s "${ES_HOST}/_cat/aliases/${ALIAS}" | wc -l)
if [ "${EXISTING}" -lt 1 ]; then
  echo "ERROR: Alias ${ALIAS} not found. Aborting to prevent silent failure."
  exit 1
fi
```

Also define `ALIAS` once at the top and reference it throughout — having the alias name as a literal string in two places is what allowed this typo to survive.