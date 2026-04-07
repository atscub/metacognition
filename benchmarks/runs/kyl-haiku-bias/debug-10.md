### Step 1: Restate Without Jargon

A test waits for the app to load, then checks what a badge displays. The badge *should* show "5" (unread notifications), but 10% of the time it shows "1" instead. Longer waits don't fix it.

### Step 2: Atomic Components

**Inputs:**
- App renders two things that both create `.notification-badge` elements:
  - `SystemAlert` displays `alerts.length` in a badge (1 alert in the mock)
  - `NotificationBell` displays `unreadCount` in a badge (5 notifications in the mock)
- Mock server configured to return both system alerts and notifications
- Test queries for `.notification-badge` without specifying which component

**Output:**
- Test needs to read the *NotificationBell's* badge and see "5"

**Core transformation:**
- Test does: `document.querySelector('.notification-badge')` → gets first matching element in DOM

### Step 3: Question

**Here's the issue:** Both components use the same CSS class name. When you call `querySelector('.notification-badge')`, you get the **first match in DOM tree order**.

In `App.tsx`:
```tsx
<SystemAlert />        {/* Declares first */}
<NotificationBell />   {/* Declares second */}
```

**SystemAlert is declared FIRST.** If both components render their badges, SystemAlert's badge (showing "1") will appear first in the DOM. `querySelector` returns that one—not the NotificationBell badge showing "5".

**Why only 10% flaky then?** Race condition. Both components fetch asynchronously:
- Sometimes one update batches before the other
- Sometimes DOM tree order momentarily differs based on timing
- Sometimes a render cycle processes differently

The test is **accidentally working 90% of the time** by luck, not by design.

---

## The Fix

Target the specific component's badge instead of the global class:

```typescript
// BEFORE (wrong — gets first .notification-badge in DOM)
const badge = document.querySelector('.notification-badge');

// AFTER (correct — scoped to NotificationBell)
const badge = document.querySelector('[data-testid="notification-bell"] .notification-badge');
```

Apply the same fix to the second check:
```typescript
await waitFor(() => {
  const updatedBadge = document.querySelector('[data-testid="notification-bell"] .notification-badge');
  expect(updatedBadge.textContent).toBe('4');
}, { timeout: 5000 });
```

**Why this fixes it:** You're no longer ambiguous about which badge you're checking. The selector now says "get the badge *inside* the notification-bell component," not "get any badge that happens to be first in the document."

This is a **DOM selector collision**, not a timing issue. The extensive waits didn't help because the test was reading the wrong element 10% of the time, not because the right element was slow to render.