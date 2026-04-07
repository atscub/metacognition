## Root Cause

The bug is a **cascade collision introduced by autoprefixer's new grid prefixing behavior in postcss-preset-env 9.x**.

Here's the exact sequence:

1. `postcss-preset-env` 9.0 expanded `autoprefixer: { grid: true }` to prefix *all* grid properties, including `subgrid`-related ones. Previously it only prefixed legacy IE-era grid properties.

2. The compiled output now contains both:
   ```css
   grid-template-columns: subgrid;           /* standard — comes first */
   -webkit-grid-template-columns: subgrid;   /* prefixed — comes AFTER */
   ```

3. Safari 17 supports `subgrid` natively via the standard property. But it also recognizes `-webkit-grid-template-columns` as a legacy property from the *old* pre-spec WebKit grid implementation — which **never supported `subgrid` as a valid value**.

4. Since the `-webkit-` rule appears last in source order, it wins the cascade. Safari applies it, finds `subgrid` invalid in that context, and either discards the declaration or falls back to `none`, collapsing the column definition.

5. Chrome/Firefox/Edge don't recognize `-webkit-grid-template-columns` at all on modern engines, so they only see the standard property — which works fine.

This is why `!important` on `grid-template-columns` didn't fully work: it wins in specificity for the standard property, but the `-webkit-` property is a *different* property name entirely — `!important` on one doesn't affect the other.

---

## The Fix

**Don't disable `subgrid` — disable grid autoprefixing.** You almost certainly don't need `-webkit-` grid prefixes in 2024+ unless you're targeting IE 11 (which is dead).

**Option A — Disable grid prefixing entirely (recommended):**

```js
// postcss.config.js
module.exports = {
  plugins: [
    require('tailwindcss'),
    require('postcss-preset-env')({
      stage: 2,
      features: {
        'nesting-rules': true,
        'custom-media-queries': true,
      },
      autoprefixer: { grid: false },  // was: true
    }),
  ],
};
```

**Option B — Surgical inline suppression (if you need grid prefixing elsewhere):**

```css
.product-card {
  display: grid;
  grid-template-rows: auto 1fr auto;
  /* autoprefixer: ignore next */
  grid-template-columns: subgrid;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  overflow: hidden;
}
```

---

## Why the other attempts failed

| Attempt | Why it didn't work |
|---|---|
| Rolling back CSS | The CSS source is fine — the bug lives in the *compiled* output from the new PostCSS version |
| `!important` on `grid-template-columns` | Raises specificity of the standard property, but `-webkit-grid-template-columns` is a separate property — still active, still overrides |
| Dropping `subgrid` | Would work but is unnecessary; the feature itself is fine in all target browsers |

---

Option A is the right long-term call. The `grid: true` autoprefixer option exists for IE 11's old `-ms-grid` syntax. Safari 17's native grid support is excellent — there's nothing to prefix.