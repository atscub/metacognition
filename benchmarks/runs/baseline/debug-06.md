## Root Cause

The bug is in the PostCSS build pipeline, not the CSS source. Here's the chain of events:

**`postcss-preset-env` 9.0.0** changed autoprefixer's grid behavior: with `autoprefixer: { grid: true }`, it now prefixes *subgrid* properties in addition to legacy grid properties. So the compiled output for `.product-card` becomes:

```css
grid-template-columns: subgrid;
-webkit-grid-template-columns: subgrid;   /* ← new in v9 */
```

**Safari's cascade rule** is the trap: when both the standard and `-webkit-` prefixed form of a property are present, Safari applies the *last one in source order*. The `-webkit-` prefixed version wins.

**The webkit-prefixed grid API predates subgrid** — `subgrid` is not a valid value for `-webkit-grid-template-columns`. So Safari 17 ends up applying an invalid/unsupported property value, the declaration is effectively dropped or misinterpreted, and the layout collapses. Chrome ignores the webkit prefix entirely and applies the standard property, so it works fine.

The DevTools output confirms this exactly:
```
grid-template-columns: subgrid          [overridden]   ← valid, but loses cascade
-webkit-grid-template-columns: subgrid  [active]       ← wins, but invalid value
```

---

## The Fix

The `autoprefixer: { grid: true }` option exists specifically for **IE 11** (which used `-ms-grid`). IE 11 reached end-of-life in June 2022 and is irrelevant to any modern browser, including Safari. Disable it:

```javascript
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
      autoprefixer: { grid: false },  // ← was: true
    }),
  ],
};
```

This stops autoprefixer from emitting any `-webkit-`/`-ms-` grid prefixes, so the compiled output is simply:

```css
.product-card {
  display: grid;
  grid-template-rows: auto 1fr auto;
  grid-template-columns: subgrid;   /* clean — no spurious prefix */
  ...
}
```

---

## Why the other attempted fixes failed

| Attempt | Why it failed |
|---|---|
| Rolling back CSS source | CSS source was never the problem; the compiled output changed |
| `!important` on `grid-template-columns` | Doesn't help — cascade specificity doesn't override *property name* precedence; the `-webkit-` variant is a different property entirely |
| Dropping subgrid | Would fix the symptom by removing the prefixed variant, but sacrifices a valid, well-supported feature unnecessarily |

---

## If you need targeted protection (belt-and-suspenders)

If you want to keep `grid: true` for some other reason, you can suppress prefixing on a single declaration:

```css
.product-card {
  display: grid;
  grid-template-rows: auto 1fr auto;
  /* autoprefixer: ignore next */
  grid-template-columns: subgrid;
```

But `grid: false` is the right answer — the IE 11 grid translation feature has had no valid use case since 2022.