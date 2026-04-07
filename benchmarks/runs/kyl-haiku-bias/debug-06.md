## Root Cause: Vendor Prefix Cascade Override

Here's what's happening:

**Layer 1 — CSS Source** (unchanged): Contains `grid-template-columns: subgrid;`

**Layer 2 — PostCSS Pipeline** (changed): 
- postcss-preset-env 8.5.1: Did NOT prefix subgrid properties
- postcss-preset-env 9.0.0+: NOW prefixes subgrid properties when `autoprefixer: { grid: true }` is set in your config

**Layer 3 — Compiled Output** (the problem):
```css
grid-template-columns: subgrid;           /* standard property */
-webkit-grid-template-columns: subgrid;   /* vendor prefix added by v9.x */
```

**Layer 4 — Safari Rendering** (the symptom):
In CSS cascade, when two properties have equal specificity, the **last one wins**. Safari 17 understands both properties, so it applies `-webkit-grid-template-columns` (the last one). The `-webkit-` prefixed version of subgrid either has different semantics or a bug in Safari 17's older implementation, causing the layout to break.

Chrome/Firefox/Edge don't have this problem because they either:
- Only recognize the standard property (ignore the `-webkit-` version), OR
- Don't add the vendor prefix in the first place

---

## The Correct Fix

Remove the explicit `grid: true` option from your PostCSS config. In postcss-preset-env 9.x, this option changed behavior—it now aggressively prefixes *all* grid properties, including subgrid, which is unnecessary for your target browsers.

**Change postcss.config.js:**

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
      // Remove this line entirely:
      // autoprefixer: { grid: true },
    }),
  ],
};
```

**Why this works:**
- Without `grid: true`, autoprefixer will still add prefixes for truly legacy grid syntax (the IE grid spec), but will NOT prefix modern grid features like subgrid that are natively supported
- This prevents the `-webkit-` version from being added to your compiled CSS
- Safari will use only `grid-template-columns: subgrid` (the standard property)

**If you need legacy IE grid support**, you can be more granular:

```javascript
autoprefixer: { 
  grid: 'autoplace',  // Only prefixes legacy IE grid, not modern subgrid
},
```

Or check your `.browserslistrc` / `package.json` browserslist—if you're not supporting IE11, you don't need `grid: true` at all.

---

## Why The Previous Attempts Failed

- **Reverting CSS**: Wouldn't help, since the CSS source hasn't changed—the issue is in PostCSS output
- **Adding `!important`**: Only a band-aid; it masks the cascade problem but doesn't fix the root cause
- **Dropping subgrid**: Would work but loses modern layout capabilities unnecessarily

The real fix addresses the *pipeline*, not the CSS itself.