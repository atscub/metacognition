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