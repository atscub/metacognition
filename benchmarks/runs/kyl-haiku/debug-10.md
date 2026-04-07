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