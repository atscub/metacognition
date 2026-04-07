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