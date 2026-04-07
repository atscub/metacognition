## First Principles Decomposition

### Step 1: State it without jargon

A developer writes CSS. A build tool transforms it. The browser receives the transformed version and renders it. After upgrading the build tool, one browser renders the layout incorrectly. The source CSS hasn't changed — so something in the transformation changed.

---

### Step 2: Identify the layers between source and render

```
[1] CSS source (authored)
      ↓
[2] PostCSS pipeline (transforms)
      ├── tailwindcss
      └── postcss-preset-env → autoprefixer
      ↓
[3] Compiled CSS (what the browser actually receives)
      ↓
[4] Browser CSS parser (reads declarations)
      ↓
[5] CSS cascade (resolves conflicts between declarations)
      ↓
[6] Layout engine (renders)
```

The CSS source (layer 1) is unchanged. Chrome renders correctly. Safari doesn't. That means the failure must be in layers 2–6 — and since Chrome and Safari receive the same compiled CSS, the divergence is in layers 4–6: **how Safari parses and applies the compiled output**.

---

### Step 3: Question each component

**What changed at layer 2?** `postcss-preset-env` 8.5.1 → 9.4.0. The changelog is explicit:

> Previously, only legacy grid properties were prefixed. Now includes subgrid-related properties.

So the compiled CSS (layer 3) changed, even though the source didn't. This is the silent transformation problem: a build tool upgrade changed the artifact without touching the source.

**What does the compiled CSS now contain?**

```css
.product-card {
  grid-template-columns: subgrid;         /* standard — written first */
  -webkit-grid-template-columns: subgrid; /* prefixed — written second */
}
```

**What does the CSS cascade do with two declarations for the same property?** Same specificity, same selector → **last declaration wins**. The prefixed `-webkit-grid-template-columns` comes after the standard one, so it overrides it.

**Does Safari 17 understand `-webkit-grid-template-columns: subgrid`?** This is the crux. Safari DevTools confirms it's "active." But `-webkit-grid-template-columns` is Safari's *legacy* WebKit grid implementation — a pre-standard implementation from 2012–2016 that used a completely different grid syntax. That legacy implementation **never received `subgrid` support** because `subgrid` wasn't standardized until CSS Grid Level 2 (2022). When Safari 17 processes `-webkit-grid-template-columns: subgrid`, it interprets `subgrid` through the old WebKit grid engine, which treats it as an unknown/invalid value and collapses the column structure — causing the overlap and collapse you see.

Chrome doesn't have this problem because Chrome dropped all `-webkit-grid-*` legacy properties years ago. There's nothing to conflict with.

---

### Root Cause (one sentence)

`postcss-preset-env` 9.x now vendor-prefixes `subgrid`, injecting `-webkit-grid-template-columns: subgrid` *after* the standard declaration in the compiled output; Safari 17 applies the webkit-prefixed version (last-wins in the cascade), but its legacy WebKit grid engine doesn't understand `subgrid`, breaking the layout.

---

### Step 4: Rebuild to find the correct fix

The team's attempted fixes failed because they all worked on **layer 1** (source CSS) when the bug lives in **layer 2** (build tool output):

| Attempt | Why it failed |
|---|---|
| Rolling back CSS | Source wasn't the problem |
| Adding `!important` | Forces layer 1 to win the cascade, but fights the symptom not the cause; breaks specificity elsewhere |
| Dropping `subgrid` | Abandons a valid, supported feature unnecessarily |

The correct fix is at **layer 2** — stop generating the harmful prefix:

**Option A — Disable grid prefixing entirely (recommended)**

Safari 16.4+ supports CSS Grid Level 2 natively. No modern browser needs `-webkit-grid-*` prefixes anymore. Turn it off:

```js
// postcss.config.js
require('postcss-preset-env')({
  stage: 2,
  features: {
    'nesting-rules': true,
    'custom-media-queries': true,
  },
  autoprefixer: { grid: false }, // ← was `true`, now `false`
})
```

**Option B — Update your browserslist to exclude pre-subgrid Safari**

```json
// package.json
"browserslist": [
  "> 0.5%",
  "last 2 versions",
  "not dead",
  "not Safari < 16.4"
]
```

Autoprefixer reads browserslist and won't emit a prefix if no targeted browser needs it. This is more principled because it lets autoprefixer make data-driven decisions about all future prefixes.

**Option C — Both (belt and suspenders)**

If you need to support older Safari for other CSS features but not for grid, you can scope grid specifically:

```js
autoprefixer: { grid: false }  // explicit, immune to browserslist changes
```

---

### Verdict

Go with **Option B** if you don't already have a `browserslist` config, since it correctly documents your target browser support and benefits all future autoprefixer decisions. Add **Option A** as well if you want the config to be self-documenting about the intentional exclusion. Do not use `!important`, do not drop `subgrid` — the feature works perfectly when the build pipeline stops generating conflicting vendor-prefixed overrides.