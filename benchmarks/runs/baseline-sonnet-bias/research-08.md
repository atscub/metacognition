## Recommendation: Don't use styled-components for this project

The performance concern is real, but the choice isn't binary between styled-components and Tailwind. Here's the honest breakdown:

### The styled-components problem is real for your use case

styled-components generates CSS at runtime via CSSOM injection. Every render of a component with dynamic props recalculates and injects styles. For 8hr/day users on dashboards with dense data tables that re-render frequently, this is measurable:

- Each styled component adds ~1-3ms overhead per unique prop combination at render time
- Large component trees compound this (your 40 shared components × usage density)
- **React 19 specifically**: styled-components v5 uses the legacy context API, which React 19 still supports but with deprecation warnings. v6 is better but still has open issues with concurrent rendering and `<Suspense>`

The blog post you read was not wrong.

### The real alternative to consider: vanilla-extract or Panda CSS

These give you **zero-runtime CSS-in-JS** — styles are extracted at build time by Vite, so there's no runtime cost. The mental model is close enough to styled-components that your team's existing intuition transfers:

```ts
// vanilla-extract
import { style } from '@vanilla-extract/css';
import { recipe } from '@vanilla-extract/recipes';

export const button = recipe({
  base: { borderRadius: 4, fontWeight: 600 },
  variants: {
    intent: {
      primary: { background: '#007bff' },
      secondary: { background: '#6c757d' },
    },
    size: {
      large: { padding: '12px 24px' },
      default: { padding: '8px 16px' },
    },
  },
});
```

This compiles to static CSS at build time. Zero runtime. Full TypeScript. Props-as-variants still work. The Vite plugin (`@vanilla-extract/vite-plugin`) is mature.

### Tailwind is also a strong choice, but not for the reason you think

The readability problem your teammate mentioned is real **if you write Tailwind inline in feature components**. But for an internal app with 40 shared components, most developers never touch raw Tailwind — they use `<Button variant="primary" size="large" />`. The utility classes live in one place, inside the component library. That's a solved problem.

Tailwind's advantage: zero build configuration risk, massive ecosystem (shadcn/ui, Headless UI, etc.), and the fastest possible runtime (pure static CSS, nothing injected).

### The actual decision matrix

| | styled-components | vanilla-extract | Tailwind |
|---|---|---|---|
| Runtime overhead | High | None | None |
| React 19 compatibility | Shaky | Good | Perfect |
| Team learning curve | Zero | Low (2-3 days) | Medium (1-2 weeks) |
| Dynamic styles via props | Natural | Variants API | Component abstraction |
| 40-component library | Works | Works well | Works well |
| Vite integration | Okay | First-class plugin | First-class |

### What I'd actually do

**vanilla-extract** is the lowest-risk path forward. The migration from styled-components is smaller than it looks — you're still writing CSS properties in JS objects, you still have variants/props, you just define them as a recipe instead of a template literal. Your team will be productive in a day or two.

If your team is willing to invest ~1 week and you want access to pre-built component ecosystems (shadcn/ui is outstanding), **Tailwind + shadcn/ui** for an internal app like this is genuinely excellent and will make your 40-component library much faster to build.

**Don't stick with styled-components** — not because it's wrong in general, but because React 19's concurrent features and your performance requirements make the timing bad. The runtime cost will show up in your heaviest screens.