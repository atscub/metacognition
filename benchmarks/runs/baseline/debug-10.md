## Root Cause: Ambiguous DOM Query, Not a Timing Issue

The bug is in the test's selector, not the async behavior. The team has been solving the wrong problem.

### The Smoking Gun

```typescript
// This selects the FIRST .notification-badge in the entire document
const badge = document.querySelector('.notification-badge');
```

`document.querySelector` returns the **first match** in DOM order. Look at two things together:

**1. `SystemAlert` also renders `.notification-badge`:**
```tsx
<span className="notification-badge">{alerts.length}</span>
```

**2. `SystemAlert` appears *before* `NotificationBell` in the App:**
```tsx
<SystemAlert />       {/* renders .notification-badge with alerts.length = 1 */}
<NotificationBell />  {/* renders .notification-badge with unreadCount = 5 */}
```

**3. The mock server has a default handler for system alerts:**
```typescript
rest.get('/api/system/alerts', (req, res, ctx) =>
  res(ctx.json({ active: [{ id: 'a1', ... }] }))  // 1 active alert
)
```

### Why Exactly ~10%

Both `SystemAlert` and `NotificationBell` fire `useEffect` fetches on mount. The test waits for the bell element to appear (`notification-bell` testid), but that only guarantees `NotificationBell` mounted — not that `SystemAlert`'s fetch completed.

- **90% of runs**: SystemAlert's fetch hasn't resolved yet when `document.querySelector` runs → finds NotificationBell's badge → `'5'` ✓  
- **10% of runs**: SystemAlert's fetch resolves first, its badge renders above NotificationBell's in the DOM → `document.querySelector` returns `'1'` ✗

This is why **no timing fix works**: adding more `await`/sleep actually makes failure *more likely* by giving `SystemAlert` additional time to render. The issue isn't "waiting long enough" — it's "selecting the wrong element."

### Fix

Scope the query to the notification bell's subtree:

```typescript
// Before (broken):
const badge = document.querySelector('.notification-badge');

// After (correct):
const bell = screen.getByTestId('notification-bell');
const badge = bell.querySelector('.notification-badge');
```

And for the post-click assertion:

```typescript
await waitFor(() => {
  const bell = screen.getByTestId('notification-bell');
  const updatedBadge = bell.querySelector('.notification-badge');
  expect(updatedBadge?.textContent).toBe('4');
}, { timeout: 5000 });
```

### Deeper Fix: Remove the Shared Class Name

The real underlying issue is that two unrelated components share the same CSS class for semantically different things. `SystemAlert`'s badge is an alert count; `NotificationBell`'s is an unread count. They shouldn't share `.notification-badge`.

Rename `SystemAlert`'s span to `.alert-count-badge` and the accidental collision disappears entirely, making the test resilient even if someone writes a naïve `document.querySelector` in the future.

### Why the Team Was Misled

The error message `Expected '1' to be '5'` looks like a state/count bug. The duration similarity across pass/fail (~2.3s) rules out timeouts. The `--runInBand` non-result rules out test parallelism. Everything pointed toward async state — but the real culprit was element identity, not timing. The 10% rate is the giveaway: true timing flakiness rates vary based on machine load; a suspiciously stable percentage suggests a probabilistic collision with a fixed-rate external dependency (the system alerts fetch).