## Step 1 — State the Initial Framing

The team's framing: **"The reindex didn't complete."** Disproved by logs (232,341 docs match, direct index queries return fresh data, cluster is green).

My reflex framing: **"Something is wrong with how documents were synced."** But the spot-check on the new index returns correct data. So the data is *there* — the problem is in *routing*.

---

## Step 2 — Apply Reframing Lenses

**Zoom In Lens:** Forget the reindex. Focus only on the alias state and the script. Compare byte-by-byte:

```
# Alias state observed:
products-live  products-20260313030001   ← OLD index
product-live   products-20260327030001   ← NEW index
```

```bash
# Variable defined at top of script:
ALIAS="products-live"

# Hardcoded strings inside the curl body (Step 4):
{ "remove": { "index": "*", "alias": "product-live" } }
{ "add":    { "index": "${NEW_INDEX}", "alias": "product-live" } }
```

`products-live` vs `product-live`. The `$ALIAS` variable is **never used** in the curl body — it's hardcoded with a typo (missing the `s`).

**Inversion Lens:** What would guarantee the swap looks successful but does nothing to the real alias? Swap a *different* alias. Elasticsearch returns `{"acknowledged":true}` when it processes the request — not when it achieves your intent. Removing an alias that doesn't already exist on an index is silently accepted.

**Novice Lens:** "The script created a brand new alias called `product-live` on the new index, and left `products-live` — the one the app actually uses — pointing at the old index. Untouched."

---

## Step 3 — Convergence

All lenses point to the same place. This is not a reindex problem, a sync problem, or a data problem.

---

## Root Cause

**Typo in the alias swap curl command.** The script defines `ALIAS="products-live"` but never uses `$ALIAS` in Step 4. The hardcoded strings say `product-live` (no `s`). The swap operated on the wrong alias.

Result:
- `products-live` (what the app queries) → still points to `products-20260313030001` (old)
- `product-live` (typo alias) → correctly points to `products-20260327030001` (new, never queried)

---

## Fix

**Immediate:** Manually swap the correct alias:

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

**Fix the script** — use the variable instead of hardcoding:

```bash
# Step 4: Swapping alias
SWAP_RESPONSE=$(curl -s -X POST "${ES_HOST}/_aliases" \
  -H 'Content-Type: application/json' \
  -d "{
    \"actions\": [
      { \"remove\": { \"index\": \"*\", \"alias\": \"${ALIAS}\" } },
      { \"add\": { \"index\": \"${NEW_INDEX}\", \"alias\": \"${ALIAS}\" } }
    ]
  }")
```

**Add a verification step** after the swap — check that the alias now resolves to the new index before declaring success:

```bash
ACTIVE_INDEX=$(curl -s "${ES_HOST}/_alias/${ALIAS}" | jq -r 'keys[0]')
if [ "${ACTIVE_INDEX}" != "${NEW_INDEX}" ]; then
  echo "ERROR: Alias ${ALIAS} still points to ${ACTIVE_INDEX}, not ${NEW_INDEX}"
  exit 1
fi
```

The 14-day window of "stale data" matches exactly: `products-20260313030001` was the index from March 13, two weeks before the rebuild. The alias was never moved off it.