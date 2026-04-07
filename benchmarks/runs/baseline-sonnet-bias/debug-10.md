## Root Cause: Ambiguous DOM Query Matches the Wrong Component

This is not a timing issue at all. The flakiness has nothing to do with async delays.

**The bug:** The test uses `document.querySelector('.notification-badge')`, which returns the **first** matching element in DOM order. The `SystemAlert` component also renders a `.notification-badge` element — and it appears **before** `NotificationBell` in the component tree.

Walk through the App layout:

```tsx
<div className="header-actions">
  <SystemAlert />        {/* renders: <span class="notification-badge">1</span> */}
  <NotificationBell />   {/* renders: <span class="notification-badge">5</span> */}
  <UserMenu />
</div>
```

And the default mock server handler (always active, never overridden by the test):

```typescript
rest.get('/api/system/alerts', (req, res, ctx) =>
  res(ctx.json({
    active: [{ id: 'a1', message: 'Scheduled maintenance tonight', severity: 'info' }],
  }))
),
```

So `SystemAlert` asynchronously loads 1 alert and renders a `.notification-badge` with text `"1"`.

**The race:**

- The test `waitFor` only waits for `notification-bell` to be **in the DOM** — but that div renders immediately, before the notifications fetch completes. So the `waitFor` resolves almost instantly.
- Then `document.querySelector('.notification-badge')` runs. At this moment, two independent fetches are in flight: `/api/notifications` and `/api/system/alerts`.
- **90% of the time:** `/api/system/alerts` hasn't resolved yet, so `SystemAlert` returns `null`. The only badge is the notification bell's `5`. Test passes.
- **10% of the time:** `/api/system/alerts` has already resolved and `SystemAlert` has rendered. Now there are two badges in DOM. `querySelector` returns the **first** one (SystemAlert's `1`). Test fails with `Expected '1' to be '5'`.

This explains everything:
- Duration is identical (~2.3s) regardless of pass/fail — no timeout is being hit
- Adding more `await`s or longer timeouts doesn't help — you'd just be giving the system alerts fetch *more* time to finish
- `--runInBand` doesn't help — both fetches are within the same test, not across test files

---

## The Fix

Scope the query to the notification bell, and wait for the badge content specifically:

```typescript
// Instead of the ambiguous:
const badge = document.querySelector('.notification-badge');
expect(badge.textContent).toBe('5');

// Scope to the correct component:
import { within } from '@testing-library/react';

const bell = screen.getByTestId('notification-bell');

// Also: actually wait for the badge to appear (don't assume it's there
// just because the bell wrapper rendered)
await waitFor(() => {
  expect(within(bell).getByText('5')).toBeInTheDocument();
}, { timeout: 5000 });
```

And for the "after click" assertion:

```typescript
await waitFor(() => {
  expect(within(bell).getByText('4')).toBeInTheDocument();
}, { timeout: 5000 });
```

**Or**, add a more specific test ID to the notification badge itself:

```tsx
// NotificationBell.tsx
{unreadCount > 0 && (
  <span className="notification-badge" data-testid="unread-count">
    {unreadCount}
  </span>
)}
```

```typescript
// test
await waitFor(() => {
  expect(screen.getByTestId('unread-count').textContent).toBe('5');
});
```

The deeper lesson: `document.querySelector` has no concept of component boundaries. Whenever two components share a CSS class name, an unscoped query will non-deterministically return whichever one happens to appear first in the DOM — and if both are asynchronously rendered, that ordering depends on fetch timing.