## The performance concern is real, but the choice isn't binary

### What's actually happening with styled-components

The runtime cost comes from two things:
1. **Style generation on render** — interpolations like `${props => props.primary ? ...}` are evaluated in JS, then injected into `<style>` tags via a CSS-in-JS runtime
2. **Style recalculation cascade** — when a parent re-renders, styled-components re-evaluates all its children's interpolations

For your use case (forms, tables, dashboards with 8+ hour daily usage), this matters more than a typical marketing site. A data table with 100 rows, each with styled cells, re-renders frequently. The runtime cost compounds.

However: the severity depends on *how* you use dynamic props. Static variants (`primary`, `size='large'`) are less costly than true runtime values (`color={user.brandColor}`).

---

### The actual options

**1. Stay on styled-components** — viable if you discipline your usage

The real culprit is runtime interpolations that change on every render. Static variants are fine. If you audit your patterns and avoid:
```jsx
// Bad: evaluated on every render
color: ${props => someCalculation(props.data)};

// Fine: only two possible outcomes, rarely changes
background: ${props => props.primary ? '#007bff' : '#6c757d'};
```

...the performance is acceptable for most apps. But you're leaving performance on the table for no good reason.

**2. Tailwind + Class Variance Authority** — solves both problems

The readability complaint is about *usage at callsites*, not the library itself. The pattern is to hide utility classes inside component definitions:

```tsx
// button.tsx — ugly lives here, hidden from callers
import { cva } from 'class-variance-authority';

const button = cva('rounded font-medium transition-colors', {
  variants: {
    intent: {
      primary: 'bg-blue-600 text-white hover:bg-blue-700',
      secondary: 'bg-gray-500 text-white hover:bg-gray-600',
    },
    size: {
      default: 'px-4 py-2 text-sm',
      large: 'px-6 py-3 text-base',
    },
  },
  defaultVariants: { intent: 'primary', size: 'default' },
});

export function Button({ intent, size, ...props }) {
  return <button className={button({ intent, size })} {...props} />;
}

// Usage at callsite — clean
<Button intent="primary" size="large">Submit</Button>
```

Zero runtime. Zero style injection. The JSX at callsites looks identical to styled-components from the consumer's perspective.

**3. vanilla-extract** — CSS-in-JS with zero runtime

Same authoring feel as styled-components, but styles are extracted at build time by Vite:

```ts
// button.css.ts
import { styleVariants } from '@vanilla-extract/css';

export const button = styleVariants({
  primary: { background: '#007bff', padding: '8px 16px' },
  secondary: { background: '#6c757d', padding: '8px 16px' },
});
```

TypeScript-native, Vite has first-class support, zero runtime. The tradeoff: separate `.css.ts` files, slightly more verbose than styled-components.

---

### My actual recommendation for your situation

**Go with Tailwind + CVA.** Here's why it fits your specific context:

| Factor | Weight |
|--------|--------|
| 8+ hours/day use → performance matters | High |
| ~40 shared components → component abstractions hide utility classes | Mitigates readability concern |
| Internal tool → no SSR constraints | Neutral |
| Vite build → Tailwind's JIT has excellent Vite support | Positive |
| React 19 → no styled-components SSR issues to worry about | Neutral |

The team familiarity with styled-components is a real switching cost, but CVA's variant API is close enough that the mental model transfers quickly. After building 5-10 components the pattern clicks.

**If the team won't switch:** Use vanilla-extract instead of styled-components. Same developer experience, zero runtime. Vite plugin: `@vanilla-extract/vite-plugin`. This is the easiest migration path since the API is similar.

**What I'd avoid:** Staying on styled-components unchanged. The performance issues you've read about are real for exactly the type of app you're building — dense UIs with frequent re-renders. You'd be building technical debt into your foundation.

---

### Migration risk if you choose Tailwind

The main risk is inconsistency during transition if you migrate incrementally. For a greenfield project (which this sounds like), start clean. Set up:
- Tailwind with your design tokens in `tailwind.config.ts`
- CVA for variant-based components
- `clsx` or `cn` (shadcn's utility) for conditional classes
- Consider shadcn/ui for the 40 shared components — it gives you unstyled, accessible components with Tailwind already wired up, which is a significant head start