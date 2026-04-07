I found it! Look at the alias names in the current state:

```
products-live  products-20260313030001  ← OLD index (from 2026-03-13)
product-live   products-20260327030001  ← NEW index (from 2026-03-27)
```

The application queries `products-live` (plural), but the script swapped the wrong alias: `product-live` (singular).

In the rebuild script, Step 4 is using:
```bash
"alias": "product-live"  # ← singular (wrong!)
```

But the application code uses:
```typescript
index: 'products-live',  # ← plural (correct!)
```

**The fix:** Change the script to use the correct alias name. In `scripts/rebuild-product-index.sh`, line in Step 4, change both references from `product-live` to `products-live`:

```bash
echo "[$(date)] Step 4: Swapping alias"
SWAP_RESPONSE=$(curl -s -X POST "${ES_HOST}/_aliases" \
  -H 'Content-Type: application/json' \
  -d "{
    \"actions\": [
      { \"remove\": { \"index\": \"*\", \"alias\": \"products-live\" } },
      { \"add\": { \"index\": \"${NEW_INDEX}\", \"alias\": \"products-live\" } }
    ]
  }")
```

Also update the ALIAS variable at the top for consistency:
```bash
ALIAS="products-live"  # was "products-live"
```

Once you fix this and run the script again, the `products-live` alias will point to the correct index and queries will return fresh data.