Looking at the evidence through multiple lenses:

**Zoom In Lens** — comparing the alias state to the script:
```
products-live  → products-20260313030001  (OLD)
product-live   → products-20260327030001  (NEW)
```

vs. the script variable:
```bash
ALIAS="products-live"
```

but the curl command:
```bash
{ "remove": { "index": "*", "alias": "product-live" } },
{ "add": { "index": "${NEW_INDEX}", "alias": "product-live" } }
```

**There's a typo.** The script swaps `product-live` (no 's'), but the application queries `products-live` (with 's'). The alias was never actually updated—it's still pointing to the old index.

**Simplicity Lens** — this explains all symptoms with zero mysteries:
- ✓ New index has fresh data (reindex worked fine)
- ✓ Direct queries to new index succeed (data is there)
- ✓ Alias queries show stale data (alias points to old index)
- ✓ Logs show success (the Elasticsearch operations succeeded—just on the wrong alias)

**The Fix:**

Update the script to use the variable:
```bash
{ "remove": { "index": "*", "alias": "${ALIAS}" } },
{ "add": { "index": "${NEW_INDEX}", "alias": "${ALIAS}" } }
```

Or hardcode consistently. Run the reindex again, and `products-live` will point to the new index. The fresh data will suddenly appear.