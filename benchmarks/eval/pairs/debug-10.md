# Task: debug-10 — Flaky integration test passes 9 out of 10 times

## Prompt
We have an integration test for our notification system that fails approximately 10% of
the time. The test has been marked as flaky for months. The team has added extensive
waits and retries assuming it's an async timing issue, but the flakiness persists at
exactly the same rate. Can you figure out why?

The failing test (tests/integration/notifications.test.tsx):

```typescript
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { App } from '../../src/App';
import { setupMockServer } from '../mocks/server';

const server = setupMockServer();

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('Notification system', () => {
  it('should show unread notification count after marking as read', async () => {
    // Setup: user has 5 unread notifications
    server.use(
      rest.get('/api/notifications', (req, res, ctx) => {
        return res(ctx.json({
          unread: 5,
          items: [
            { id: 'n1', message: 'New comment on PR #42', read: false },
            { id: 'n2', message: 'Build succeeded', read: false },
            { id: 'n3', message: 'Review requested', read: false },
            { id: 'n4', message: 'Deployment complete', read: false },
            { id: 'n5', message: 'Issue assigned', read: false },
          ],
        }));
      }),
      rest.post('/api/notifications/:id/read', (req, res, ctx) => {
        return res(ctx.json({ success: true }));
      }),
    );

    render(<App />);

    // Wait for notifications to load
    await waitFor(() => {
      expect(screen.getByTestId('notification-bell')).toBeInTheDocument();
    }, { timeout: 5000 });

    // Verify initial unread count
    const badge = document.querySelector('.notification-badge');
    expect(badge).not.toBeNull();
    expect(badge.textContent).toBe('5');

    // Click first notification to mark as read
    await userEvent.click(screen.getByText('New comment on PR #42'));

    // Verify count decreased
    await waitFor(() => {
      const updatedBadge = document.querySelector('.notification-badge');
      expect(updatedBadge.textContent).toBe('4');
    }, { timeout: 5000 });
  });
});
```

NotificationBell component (src/components/NotificationBell.tsx):

```tsx
import { useState, useEffect } from 'react';
import { fetchNotifications, markAsRead } from '../api/notifications';

export function NotificationBell() {
  const [notifications, setNotifications] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [isOpen, setIsOpen] = useState(false);

  useEffect(() => {
    fetchNotifications().then(data => {
      setNotifications(data.items);
      setUnreadCount(data.unread);
    });
  }, []);

  const handleMarkAsRead = async (id: string) => {
    await markAsRead(id);
    setUnreadCount(prev => prev - 1);
    setNotifications(prev =>
      prev.map(n => n.id === id ? { ...n, read: true } : n)
    );
  };

  return (
    <div data-testid="notification-bell">
      <button onClick={() => setIsOpen(!isOpen)}>
        <BellIcon />
        {unreadCount > 0 && (
          <span className="notification-badge">{unreadCount}</span>
        )}
      </button>
      {isOpen && (
        <NotificationList
          notifications={notifications}
          onMarkAsRead={handleMarkAsRead}
        />
      )}
    </div>
  );
}
```

SystemAlert component (src/components/SystemAlert.tsx):

```tsx
import { useState, useEffect } from 'react';
import { fetchSystemAlerts } from '../api/system';

export function SystemAlert() {
  const [alerts, setAlerts] = useState([]);

  useEffect(() => {
    fetchSystemAlerts().then(data => {
      setAlerts(data.active);
    });
  }, []);

  if (alerts.length === 0) return null;

  return (
    <div data-testid="system-alert" className="system-alert-bar">
      <WarningIcon />
      <span className="alert-message">{alerts[0].message}</span>
      <span className="notification-badge">{alerts.length}</span>
    </div>
  );
}
```

App component tree (src/App.tsx):

```tsx
export function App() {
  return (
    <AuthProvider>
      <div className="app-layout">
        <header className="app-header">
          <Logo />
          <Navigation />
          <div className="header-actions">
            <SystemAlert />
            <NotificationBell />
            <UserMenu />
          </div>
        </header>
        <main className="app-main">
          <Outlet />
        </main>
      </div>
    </AuthProvider>
  );
}
```

Mock server setup (tests/mocks/server.ts):

```typescript
import { rest } from 'msw';
import { setupServer } from 'msw/node';

export function setupMockServer() {
  return setupServer(
    // Default handlers
    rest.get('/api/user', (req, res, ctx) =>
      res(ctx.json({ id: 'u1', name: 'Test User' }))
    ),
    rest.get('/api/system/alerts', (req, res, ctx) =>
      res(ctx.json({
        active: [
          { id: 'a1', message: 'Scheduled maintenance tonight', severity: 'info' },
        ],
      }))
    ),
  );
}
```

CI test results (last 50 runs):

```
Run #  Result   Duration
450    PASS     2.3s
451    PASS     2.1s
452    FAIL     2.4s     "Expected '1' to be '5'"
453    PASS     2.2s
454    PASS     2.3s
455    PASS     2.1s
456    PASS     2.2s
457    PASS     2.3s
458    PASS     2.1s
459    FAIL     2.3s     "Expected '1' to be '5'"
460    PASS     2.2s
...
(5 failures in 50 runs = 10%)
```

Note the failure message: Expected '1' to be '5'. The badge text is '1' instead of '5'.

The team has tried:
- Adding `await act(...)` wrappers — no change
- Increasing waitFor timeout to 10 seconds — no change
- Adding `await new Promise(r => setTimeout(r, 1000))` before assertion — no change
- Running with `--runInBand` to prevent test parallelism — no change
- The failure rate stays at almost exactly 10% regardless of changes

What's causing the flakiness?


## Response A
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

## Response B
## Decomposition

### Step 1: State the problem without jargon

> "A test checks how many unread items appear in a badge. The badge sometimes shows '1' instead of '5'. Adding delays does not fix it."

The most important data point the team hasn't focused on: **the failure message is `Expected '1' to be '5'`** — the badge shows `'1'`, not some random number. `1` is a very specific value. Where does `1` come from in this system?

---

### Step 2: Break into atomic components

**What produces a `.notification-badge` in the DOM?**

Looking at the component tree rendered by `<App />`:

```
App
  header
    SystemAlert      → <span className="notification-badge">{alerts.length}</span>
    NotificationBell → <span className="notification-badge">{unreadCount}</span>
```

**Two separate components share the same CSS class name.** The default mock server (not overridden by the test) returns exactly **1 system alert**:

```typescript
rest.get('/api/system/alerts', (req, res, ctx) =>
  res(ctx.json({ active: [{ id: 'a1', ... }] }))  // ← 1 alert
),
```

`SystemAlert` renders its badge only after its API call resolves. `NotificationBell` renders its badge only after its API call resolves. Both start as empty (`[]` / `0`).

**What does the test query?**

```typescript
const badge = document.querySelector('.notification-badge');
```

`querySelector` returns the **first** matching element in DOM order. `SystemAlert` appears before `NotificationBell` in the header.

---

### Step 3: Question every assumption

| Assumption | Reality |
|---|---|
| "It's a timing/async issue" | Adding waits can't fix a selector collision |
| "The badge being queried is the notification badge" | There are **two** `.notification-badge` elements |
| "Retries help async problems" | Retrying a wrong selector returns the wrong element consistently |
| "10% is random variance" | 10% is how often the system-alerts API resolves **before** the notification API in the mock environment |

---

### The actual bug

The race condition is this:

**90% of runs** — notification API resolves first, `NotificationBell` renders its badge (`5`), test queries `.notification-badge`, `SystemAlert` hasn't rendered yet → gets `'5'` ✓

**10% of runs** — system-alerts API resolves first, `SystemAlert` renders its badge (`1`), test queries `.notification-badge` → gets `'1'` ✗

When **both** badges are present, `querySelector` always returns the `SystemAlert` badge (`'1'`) because it's first in the DOM — so longer waits actually make failure *more* likely if anything.

This is why:
- `await act(...)` doesn't help — the element being found is wrong, not missing
- 10s timeouts don't help — waiting longer means both badges are more likely to be present, with SystemAlert's `'1'` winning
- `--runInBand` doesn't help — it's not test parallelism, it's two `useEffect` calls racing inside a single render

The failure value `'1'` is not arbitrary — it is exactly `alerts.length` from the default mock handler.

---

### The fix

The test selects by shared class name across component boundaries. Use scoped queries instead:

```typescript
// Instead of:
const badge = document.querySelector('.notification-badge');

// Use scoped query within the notification bell:
const bell = screen.getByTestId('notification-bell');
const badge = within(bell).getByText('5');

// Or after adding a testid to the badge span:
screen.getByTestId('unread-count');
```

And the underlying design issue: `notification-badge` is used as a visual class for two semantically distinct UI elements. Either rename one, or add `data-testid` attributes that make them unambiguous.

---

### Why the decomposition caught this

The team pattern-matched to "flaky async test" because that's what flaky tests usually are. The decompose forced the question: *what exactly is `'1'` and where does it come from?* That question has a precise, non-probabilistic answer — and it reveals that the problem is structural (selector scope), not temporal.

---
Score each response on the following metrics (0-3):

| Metric | Response A | Response B |
|---|---|---|
| Ungrounded claims | | |
| Assumption acknowledgment | | |
| Alternative consideration | | |
| Error detection | | |
| Rework cycles | | |
| Confidence calibration | | |
| Final correctness | | |
| **Total** | | |
