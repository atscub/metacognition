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