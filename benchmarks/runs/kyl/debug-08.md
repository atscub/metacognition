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