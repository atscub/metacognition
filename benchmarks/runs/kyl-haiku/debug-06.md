## Root Cause: The Build Tool Layer Changed

**The problem in simple terms**: You didn't change your CSS, but the build tool did. It's now adding browser vendor prefixes (`-webkit-`) for a CSS feature (`subgrid`) that Safari 17 actually supports natively — and when both the standard and prefixed versions exist in the same file, Safari's CSS cascade picks the prefixed version, which doesn't work correctly.

### Layer Breakdown

| Layer | Before (8.5.1) | After (9.4.0) | Status |
|-------|---|---|---|
| CSS source file | `grid-template-columns: subgrid;` | `grid-template-columns: subgrid;` | ✓ unchanged |
| **PostCSS processing** | Does NOT add `-webkit-` prefix for subgrid | **NOW ADDS** `-webkit-grid-template-columns: subgrid;` | ❌ **CHANGED** |
| Compiled CSS | Standard syntax only | Standard + prefixed both present | ❌ **OUTPUT CHANGED** |
| Browser parsing | Supports standard syntax since 16.4 | Still supports it in 17 | ✓ unchanged |
| CSS cascade | Uses standard version (only one) | Applies last rule: `-webkit-` version | ❌ **Selects broken version** |

The changelog confirms this: **9.0.0** added "Vendor prefixing now applies to all grid properties by default ... Now includes subgrid-related properties." This is the breaking change.

### Why Safari Breaks But Chrome Doesn't

- **Safari 17**: Both properties present → applies last rule → uses `-webkit-` version → breaks (not properly implemented)
- **Chrome**: Modern browser doesn't even load the `-webkit-` rule → uses standard syntax → works fine

---

## The Correct Fix

You have three options (best to worst):

### Option 1: Fix the Root Cause (Best) — Update Your Browserslist

The real issue is that your `browserslist` configuration is still targeting old browsers that need prefixes. Safari 16.4+ doesn't need them for subgrid.

**Check if you have a `.browserslistrc` or `browserslist` in `package.json`. If not, autoprefixer uses defaults that include old Safari versions.**

Update it to exclude Safari < 16.4:

```json
{
  "browserslist": [
    "defaults",
    "not Safari < 16.4"
  ]
}
```

This tells autoprefixer: "These browsers support subgrid natively, don't add prefixes." PostCSS processes this correctly in 9.4.0.

**Why this works**: Autoprefixer respects your browserslist and only adds prefixes for browsers that actually need them. Once you tell it "we don't support Safari < 16.4," it stops adding the `-webkit-` prefix.

### Option 2: Disable Grid Prefixing (Quick) — Update postcss.config.js

If you can't or don't want to set up a browserslist:

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
      autoprefixer: { grid: false },  // ← Disable grid prefixing entirely
    }),
  ],
};
```

This tells postcss-preset-env not to prefix any grid properties. **Trade-off**: If you do support older browsers, they won't get grid prefixes. But if you don't (and you probably don't anymore), this is fine.

### Option 3: Disable Autoprefixer Entirely (Nuclear) — Not Recommended

```javascript
autoprefixer: false,
```

This turns off all vendor prefixing from postcss-preset-env. **Don't do this** unless you have a separate autoprefixer plugin configured and you understand the implications.

---

## Why `!important` Partially Worked

When you added `!important` to `grid-template-columns`, you forced the browser to use the standard property over the prefixed one, overriding the cascade. This is a band-aid, not a fix — it breaks other layouts because `!important` cascades unexpectedly.

---

## Recommended Action

1. **Check if you have a `browserslist` configuration** (`cat .browserslistrc` or check `package.json`).
2. **If you have one**: Add `not Safari < 16.4` to ensure old Safari doesn't get prefixes.
3. **If you don't have one**: Create `.browserslistrc` with the above config.
4. **Run a clean rebuild** (`rm -rf node_modules/.cache` or `npm run build --clean`) and test in Safari.

This is the proper fix because it addresses the root cause: autoprefixer is being told to target browsers that don't need these prefixes anymore.