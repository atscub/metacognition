## First Principles Decomposition

### Step 1: State the problem without jargon

"A test checks that a number on screen says '5'. Sometimes it says '1' instead. No amount of waiting changes this. The '1' comes from somewhere."

### Step 2: Strip the assumptions

The team's assumption: *this is a timing/async problem.*

Evidence against that assumption:
- The error is `Expected '1' to be '5'` — not a timeout, not a null element
- The badge already has content (`'1'`), so something rendered successfully
- Timing fixes (waits, retries, act wrappers) have zero effect on the 10% rate
- The rate is *suspiciously stable* — real timing races exhibit variance

**If async mitigations don't change the rate, async timing is not the cause.**

### Step 3: What actually produces the value `'1'`?

Two components use `className="notification-badge"`:

```tsx
// NotificationBell.tsx
<span className="notification-badge">{unreadCount}</span>  // → "5"

// SystemAlert.tsx
<span className="notification-badge">{alerts.length}</span>  // → "1"
```

The default mock server **always** returns 1 active alert:
```typescript
rest.get('/api/system/alerts', (req, res, ctx) =>
  res(ctx.json({ active: [{ id: 'a1', ... }] }))  // length = 1
)
```

The test selector:
```typescript
const badge = document.querySelector('.notification-badge');
```

`querySelector` returns the **first match in DOM order**. The App renders `SystemAlert` before `NotificationBell`:

```tsx
<SystemAlert />        {/* .notification-badge = "1" — first in DOM */}
<NotificationBell />   {/* .notification-badge = "5" — second in DOM */}
```

### Step 4: Why exactly 10%?

The test only passes when `SystemAlert`'s badge **hasn't rendered yet** at assertion time. Both components fetch in `useEffect`. The race is:

| State at assertion time | querySelector returns | Result |
|---|---|---|
| Only `NotificationBell` badge rendered | `"5"` | PASS (90%) |
| Both badges rendered | `"1"` (first in DOM) | FAIL (10%) |
| Only `SystemAlert` badge rendered | `"1"` | (would also fail) |

The 10% is the rate at which `SystemAlert`'s fetch resolves *before* the test's synchronous assertion — a microtask ordering race driven by response delivery, not human-perceptible timing. No `await`, `act()`, or `setTimeout` can fix this, because the bug isn't about waiting long enough — it's about **which element is found when both are present**.

### The Root Cause

**Class name collision.** `notification-badge` is a shared CSS class used as a test selector in two different components. `document.querySelector` is global and returns the first DOM match, which is `SystemAlert`'s element — not the one the test intends.

### The Fix

Scope the selector to the component under test:

```typescript
import { within } from '@testing-library/react';

// Instead of:
const badge = document.querySelector('.notification-badge');

// Use:
const bell = screen.getByTestId('notification-bell');
const badge = within(bell).getByText('5');
// or
const badge = bell.querySelector('.notification-badge');
```

And the same for the second assertion:
```typescript
await waitFor(() => {
  expect(within(screen.getByTestId('notification-bell'))
    .getByText('4')).toBeInTheDocument();
});
```

### Why All Their Fixes Failed

| Fix attempted | Why it didn't work |
|---|---|
| Longer `waitFor` timeout | Gives *more* time for `SystemAlert` to render, potentially making it *worse* |
| `await act(...)` | Flushes effects — including `SystemAlert`'s, making its badge more likely to render |
| `setTimeout(1000)` | Same: more time = more likely both badges are present |
| `--runInBand` | Serial test execution — no cross-test parallelism involved here |

Every timing "fix" either did nothing or slightly increased the probability of the second badge being present.

### Secondary bug

The second assertion also uses `document.querySelector('.notification-badge')` with no scoping. After clicking, if `SystemAlert` is rendered, it will still show `"1"` — causing the test to fail with `Expected '1' to be '4'` for a different reason.