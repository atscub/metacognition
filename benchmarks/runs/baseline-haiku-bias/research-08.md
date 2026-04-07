Given your context, **stay with styled-components** — but with intentional performance practices. Here's why:

## The Performance Concern Is Overstated (for your use case)

The "runtime performance problems" blogs usually refer to:
- **SSR overhead** (injecting styles on server) — you're client-side only
- **Large component trees with dynamic styles** — styled-components only re-computes styles for *changed props*, not the entire tree
- **Babel plugin overhead** — negligible with modern bundlers like Vite

For a Vite-bundled SPA with 50 screens used by 5 concurrent users, styled-components won't be your bottleneck. Your bottleneck will be:
- Bundle size (both styled-components and Tailwind add overhead)
- Render inefficiency (component-level, not styling method)
- Data fetching patterns

**Tailwind doesn't solve these.** It just moves cost to CSS parsing instead of JS.

## The Real Trade-offs

| | styled-components | Tailwind |
|---|---|---|
| **Team ramp-up** | ✅ Everyone knows it | ❌ New mental model |
| **Component encapsulation** | ✅ Scoped by default | ⚠️ Global utility namespace |
| **Dynamic styling** | ✅ Props-driven, clean | ⚠️ Computed classes get messy |
| **Bundle size** | ~13KB | ~15KB (both negligible) |
| **CSS parsing** | ✅ Only used styles | ⚠️ Entire utility sheet, then purged |
| **IDE/DX** | ✅ TypeScript, IntelliSense | ❌ classNames become strings |
| **40-component library** | ✅ Sealed, reusable | ⚠️ Consumers need Tailwind config |

## The Decision Rule: When Team Velocity Matters

For an **internal tool with 5 experienced developers and a tight deadline**, team velocity beats micro-optimizations. Your team can:
- Ship features 20% faster using known patterns
- Debug styling issues in 2 minutes (not 30)
- Hire new devs who already know styled-components

The performance difference between styled-components and Tailwind in a Vite SPA is **not detectable** by end users. Your actual performance problems will be:
- Inefficient queries or API calls
- Large table renders (fix with virtualization, not CSS method)
- Bundle bloat from libraries

## If You Do Switch to Tailwind, It's Not Risk-Free

The developer who "found it hard to read" was right. After ~40 components, utility-heavy class strings become:

```jsx
<div className="flex items-center justify-between gap-4 px-4 py-3 bg-white rounded-lg border border-gray-200 shadow-sm hover:shadow-md transition-shadow">
```

That's harder to scan than:

```jsx
<Box css={`
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.75rem 1rem;
  background: white;
  border-radius: 0.5rem;
  box-shadow: 0 1px 2px rgba(0,0,0,0.05);
  
  &:hover {
    box-shadow: 0 4px 6px rgba(0,0,0,0.1);
  }
`} />
```

(You'd build component abstractions to hide this anyway.)

## My Recommendation

**Stick with styled-components AND add these performance practices:**

1. **Use `React.memo` on form inputs** — prevents re-renders when sibling state changes
2. **Lazy-load modals/heavy components** — 50 screens don't need to be in one bundle
3. **Profile with DevTools** — if you see styling as a bottleneck, optimize *then*
4. **Consider `linaria`** if you hit real performance issues — it's styled-components API with zero-runtime (but requires build step)

The 20% velocity gain from using familiar tooling outweighs the 1% runtime cost (which you'll never hit).

---

**Would you find it helpful to think through potential failure modes with a premortem, or do you want to move forward with this decision?**