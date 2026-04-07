**Root cause**: postcss-preset-env 9.x changed its autoprefixer behavior to prefix **all** grid properties when `grid: true` is set—including `subgrid`. This adds `-webkit-grid-template-columns: subgrid` to your compiled CSS.

Since both the standard and webkit versions exist, and the webkit version comes last in source order, Safari 17 applies `-webkit-grid-template-columns: subgrid`. Despite Safari 17 supporting the standard syntax natively, the webkit-prefixed version has a broken or incomplete implementation of subgrid that causes the layout collapse.

**The correct fix**: Disable grid property prefixing entirely. All your target browsers (Chrome, Firefox, Edge, Safari 17+) support modern grid natively:

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
      autoprefixer: { grid: false }, // ← Disable grid prefixing
    }),
  ],
};
```

This prevents the webkit prefix from being added. Your CSS will compile with only the standard `grid-template-columns: subgrid`, and Safari 17 will use its native (and correct) implementation.

**Why this works**: 
- The webkit prefix was meant for legacy Safari versions (pre-16.4), but Safari 17 has full native support
- The webkit version doesn't handle subgrid correctly, so applying it breaks the layout
- Modern browsers don't need prefixes for grid anyway

**Alternative** (if you need to support older Safari <16.4): Add a `.browserslistrc` specifying minimum browser versions, and postcss-preset-env will intelligently skip unnecessary prefixes.