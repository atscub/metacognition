## Decomposition: CSS Source → Rendered Output

**Step 1 — Restate without jargon**

A text file hasn't changed. A build tool transforms it into a different text file. One browser reads the built file differently than other browsers. The bug is in the *built* file, not the source.

---

## The Layers

```
CSS source  →  PostCSS pipeline  →  Compiled CSS  →  Browser CSS parser  →  Cascade winner
   (unchanged)    (CHANGED: v9)       (changed!)        (Safari 17)           (WRONG rule wins)
```

The team diagnosed at the wrong layer. They kept looking at the source file. The bug is in **layer 3** (compiled output), caused by a change in **layer 2** (build tool).

---

## Root Cause

**The vendor-prefix cascade problem.**

PostCSS-preset-env v9.0 changed autoprefixer behavior: it now prefixes *all* grid properties — including `subgrid` — when `autoprefixer: { grid: true }` is set. (v8 only prefixed legacy grid properties.)

So v9 now emits this compiled output:

```css
.product-card {
  grid-template-columns: subgrid;           /* standard — declared first */
  -webkit-grid-template-columns: subgrid;   /* prefixed — declared LAST  */
}
```

**Why this breaks only Safari 17:**

| Browser | Behavior |
|---------|----------|
| Chrome, Firefox, Edge | Ignore `-webkit-grid-template-columns` entirely (not their prefix) |
| Safari 17 | Recognizes *both*. Applies **the last declaration wins** cascade rule |

Safari 17 natively supports `grid-template-columns: subgrid` (shipped in Safari 16.4). But it also still parses legacy `-webkit-grid-template-columns` for backwards compatibility. When both are present, CSS cascade rules say the **last declaration for the same property wins**.

The `-webkit-` version appears last → it becomes active → its handling of `subgrid` differs from the modern spec implementation → layout collapses.

Your DevTools output confirms this exactly:

```
grid-template-columns: subgrid          [overridden]   ← written first, lost
-webkit-grid-template-columns: subgrid  [active]       ← written last, won — broken behavior
```

---

## Why the Team's Fixes Failed

| Attempt | Why it didn't work |
|---------|-------------------|
| Rolling back CSS changes | Source was never the problem — compiled output was |
| `!important` on `grid-template-columns` | Raises specificity of the standard rule, but `-webkit-grid-template-columns` is a *separate property*, so `!important` on the unprefixed one doesn't suppress the prefixed one |
| Dropping `subgrid` | Would work, but destroys the design intentionally |

---

## The Correct Fix

The unnecessary prefix is the problem. `subgrid` is fully supported without prefixes in every browser you're targeting (Safari 16.4+, Chrome 117+, Firefox 71+). The `-webkit-` prefix adds nothing and breaks Safari.

**Fix 1 — Disable grid prefixing (recommended):**

In `postcss.config.js`:

```javascript
require('postcss-preset-env')({
  stage: 2,
  features: {
    'nesting-rules': true,
    'custom-media-queries': true,
  },
  autoprefixer: { grid: false },  // ← change true → false
})
```

Grid is now a baseline feature. The `-webkit-` prefixed grid implementation predates the modern spec and its handling of `subgrid` is unreliable. There's no browser in the modern support matrix that needs it.

**Fix 2 — Targeted suppression (surgical, if you need grid prefixes for other reasons):**

In your CSS source, opt out per-declaration:

```css
.product-card {
  display: grid;
  grid-template-rows: auto 1fr auto;
  /* autoprefixer: ignore next */
  grid-template-columns: subgrid;
}
```

**Fix 3 — Browserslist (root-cause approach):**

Update your `.browserslistrc` or `package.json` `browserslist` to exclude ancient Safari versions that needed prefixed grid. If you're already targeting `> 0.5%, last 2 versions`, the prefix should never have been added — which suggests the browserslist may be too broad. Tightening it (e.g. `Safari >= 16`) prevents autoprefixer from emitting these vestigial prefixes at the source.

---

## The Principle Extracted

**Vendor prefixes are a cascade position problem, not just a compatibility problem.** Adding a prefixed variant of a property that the browser already supports natively will override the standard property if the prefixed version appears later in source order. This class of bug is invisible in Chrome/Firefox (which simply ignore foreign prefixes) and only surfaces in the browser whose prefix matches — which by v9's expanded prefixing, is now Safari on modern grid properties.