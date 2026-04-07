## Root Cause

**The `-webkit-` prefix for `subgrid` is appearing *after* the standard property in the compiled CSS**, and Safari 17 is applying the last property in source order. The `-webkit-grid-template-columns: subgrid` override is either buggy or incomplete in Safari 17, breaking the layout.

This happened because:
- **postcss-preset-env 9.x changed its behavior**: it now prefixes `grid-template-columns: subgrid` with `-webkit-` when `autoprefixer: { grid: true }` is set
- **postcss-preset-env 8.5.1 did not** (no changes to grid prefixing)
- **Safari 17 supports subgrid natively** (shipped in 16.4), so the prefix is unnecessary and harmful
- Safari applies the last matching property, so the `-webkit-` version wins and breaks things

---

## Correct Fix

**Remove grid prefixing entirely.** Update `postcss.config.js`:

```javascript
module.exports = {
  plugins: [
    require('tailwindcss'),
    require('postcss-preset-env')({
      stage: 2,
      features: {
        'nesting-rules': true,
        'custom-media-queries': true,
      },
      // Remove or set to false: Safari 17 supports subgrid natively
      autoprefixer: false,
    }),
  ],
};
```

Or if you need autoprefixer for *other* prefixes, disable only grid:

```javascript
autoprefixer: { grid: false },
```

---

## Why This Works

- Safari 17 (and modern Firefox, Chrome, Edge) all support `subgrid` natively
- Removing the `-webkit-` prefix eliminates the override that breaks Safari's layout
- If you need to support older Safari versions (pre-16.4), check your actual `browserslist` config and scope prefixes to only those targets

---

## Verification

After the fix, rebuild and check Safari DevTools. You should see:

```css
.product-card {
  display: grid;
  grid-template-rows: auto 1fr auto;
  grid-template-columns: subgrid;  /* ← no -webkit- version */
  /* ... */
}
```

Grid should render correctly again.