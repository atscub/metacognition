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
Now let me apply the decomposition process to your flaky test:

## Step 1: State Without Jargon

"A test verifies that clicking a notification updates a display counter from 5 to 4. The test fails ~10% of the time because the counter shows 1 instead of 5—even though the API definitely returns 5. Adding delays doesn't help. The failure rate stays at 10% no matter what changes we make."

## Step 2: Atomic Components

**Inputs:** 
- GET /api/notifications returns `{ unread: 5, items: [...] }`
- GET /api/system/alerts returns `{ active: [{ ... }] }` (length = 1)

**Outputs:** 
- A `<span className="notification-badge">` displaying "5"

**The Core**: A test queries for `.notification-badge` and expects text "5"

**The Problem**: There are **two elements** with `className="notification-badge"`:
- `NotificationBell` renders: `<span className="notification-badge">{unreadCount}</span>` → shows **5**
- `SystemAlert` renders: `<span className="notification-badge">{alerts.length}</span>` → shows **1**

## Step 3: Critical Question

```javascript
const badge = document.querySelector('.notification-badge');
```

`querySelector` returns the **first** matching element. Which badge is first depends on **DOM insertion order**, which is a race between two async effects completing.

## Step 4: Why ~10% Specifically?

The 10% rate is your clue: this isn't a simple async timing bug (those would be 0% or 100%). It's a **non-deterministic collision**. 

About 90% of the time, NotificationBell renders before SystemAlert in the DOM, making its badge first. About 10% of the time, they render in reverse order, and the test grabs SystemAlert's badge (which has count 1).

The rate is stable because it's based on the inherent variability of when two independent useEffects complete—a fundamentally probabilistic event in JavaScript.

---

## The Fix

The test's selector is **ambiguous**. Make it specific:

```typescript
// BEFORE (ambiguous):
const badge = document.querySelector('.notification-badge');

// AFTER (specific):
const notificationBellBadge = document.querySelector(
  '[data-testid="notification-bell"] .notification-badge'
);
expect(notificationBellBadge.textContent).toBe('5');
```

Alternatively, refactor the components to use unique selectors:

```typescript
// NotificationBell
<span className="notification-badge" data-testid="notification-badge">
  {unreadCount}
</span>

// SystemAlert
<span className="alert-badge">{alerts.length}</span>

// Test
const badge = screen.getByTestId('notification-badge');
expect(badge).toHaveTextContent('5');
```

The 10% flakiness **will stop immediately** once the selector is unambiguous, because the underlying race condition is harmless—the test was just picking the wrong element.

## Response B
Looking at the test and components, I see the problem immediately.

**The issue is an ambiguous selector with a DOM race condition.**

Both `NotificationBell` and `SystemAlert` render elements with the `.notification-badge` class:
- `NotificationBell` shows unread count (should be '5')
- `SystemAlert` shows alert count (always '1' from the default mock)

The test uses:
```javascript
const badge = document.querySelector('.notification-badge');
```

This returns the **first** matching element on the page. When the test runs:
1. Both components mount and fetch data in parallel (both useEffect hooks fire)
2. Whichever component finishes rendering first puts its badge in the DOM first
3. `querySelector` returns that badge
4. ~10% of the time, `SystemAlert` wins the race and renders first → badge shows '1' → test fails
5. ~90% of the time, `NotificationBell` renders first → badge shows '5' → test passes

The consistent 10% failure rate (not 50%) suggests the system alerts are slightly slower to fetch in your CI environment, but sometimes they race ahead.

**Why timing changes don't help:** You're adding waits *after* both components have already rendered. The race happens during the initial render, not during the user interaction.

**The fix:** Use a selector specific to the notification bell:

```typescript
// Instead of:
const badge = document.querySelector('.notification-badge');

// Use:
const badge = document.querySelector('[data-testid="notification-bell"] .notification-badge');
```

This ensures you're always checking the notification bell's badge, not whichever badge happens to exist first in the DOM.

Additionally, I'd recommend adding a data-testid to the badge itself in the component for clarity:
```tsx
<span className="notification-badge" data-testid="notification-count">
  {unreadCount}
</span>
```

Then in the test:
```typescript
expect(screen.getByTestId('notification-count')).toHaveTextContent('5');
```

This is a classic example of test flakiness caused by ambiguous selectors rather than timing issues—why all the waits and retries didn't help.

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
