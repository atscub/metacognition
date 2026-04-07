Looking at this, I found it: **the test is querying the wrong element due to a CSS class name collision**.

Both `NotificationBell` and `SystemAlert` render a badge with the same class name `notification-badge`:
- SystemAlert badge: shows `1` (from the default mock returning 1 active alert)
- NotificationBell badge: shows `5` (from the test-specific override)

In the test, this line:
```typescript
const badge = document.querySelector('.notification-badge');
```

Returns the **first** matching element on the page, which is the SystemAlert badge (showing `1`), not the NotificationBell badge (showing `5`).

The flakiness is ~10% because of **non-deterministic render ordering**: depending on async timing and React's batching, sometimes the SystemAlert updates first (causing querySelector to find it), and sometimes the NotificationBell updates first. The rate stays constant because it's driven by the inherent timing behavior of the test runner.

**The fix**: Query more specifically:

```typescript
// Option 1: Query within the notification bell component
const bell = screen.getByTestId('notification-bell');
const badge = bell.querySelector('.notification-badge');
expect(badge.textContent).toBe('5');

// Option 2: Better - use testing-library utilities
const bell = screen.getByTestId('notification-bell');
expect(bell).toHaveTextContent('5');

// Option 3: Use data-testid on the badge itself
expect(screen.getByTestId('notification-bell-badge')).toHaveTextContent('5');
```

**Why this wasn't caught by the "async" fixes**: The issue isn't timing—it's element selection. More `waitFor` calls and timeouts can't help because the test is literally checking the wrong element.

This is a great example of why CSS class names should be specific to their components or why integration tests should use data-testid attributes for assertions rather than generic class selectors.