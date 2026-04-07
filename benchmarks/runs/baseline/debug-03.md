This is a **timezone bug**, not a Node.js version issue. The Node version chase was a red herring.

## Root cause

`toLocaleDateString()` renders dates in the **system's local timezone**. When you pass a timestamp, it converts it to local time first, then formats it.

The test timestamps were authored on a machine in Berlin (CET = UTC+1). Each "failing" timestamp is in the late evening UTC — which falls on the *next* calendar day in Berlin:

| Timestamp | Actual UTC time | Berlin (UTC+1) | CI / UTC |
|---|---|---|---|
| `1772791800000` | March 4, 23:30 UTC | March 5, 00:30 → **"March 5"** ✓ | **"March 4"** ✗ |
| `1768525200000` | Jan 14, 23:00 UTC | Jan 15, 00:00 → **"January 15"** ✓ | **"January 14"** ✗ |
| `1767225000000` | Dec 31 ~evening UTC | still Dec 31 in both → **passes everywhere** ✓ | ✓ |

The test comments say "00:30 UTC" and "01:00 UTC" — but those are the Berlin local times, not UTC. The comments are copy-pasted from `new Date(ts).toString()` on the author's machine.

## Why the San Francisco dev's results are suspicious

A UTC-8 machine would also show the previous day for these timestamps (March 4, January 14). The SF dev's tests should *fail*, not pass. They likely:
- Have their system TZ set to UTC (common in Docker/WSL environments)
- Looked at a cached test run
- Didn't actually run the tests

## The fix

The implementation is fine for displaying dates in user-local time. The tests are broken because they hardcode timezone-dependent expectations without controlling the timezone.

**Option 1 — Use noon-UTC timestamps in tests (safest, no code changes needed):**

Timestamps at 12:00 UTC are safe for any timezone from UTC-11 to UTC+11.

```typescript
it('should format a date correctly', () => {
  // March 5, 2026 at 12:00 UTC — safe for all timezones
  const timestamp = new Date('2026-03-05T12:00:00Z').getTime();
  const result = formatDate(timestamp);
  expect(result).toBe('March 5, 2026');
});
```

**Option 2 — Pin `TZ=UTC` in Jest config** (makes tests timezone-hermetic):

```json
// jest.config.js or package.json "jest" section
{
  "testEnvironmentOptions": {
    "env": { "TZ": "UTC" }
  }
}
```

Or in `package.json`:
```json
"scripts": {
  "test": "TZ=UTC jest"
}
```

**Option 3 — Fix the implementation to use UTC explicitly** (only if the intent is always-UTC display):

```typescript
export function formatDate(timestampMs: number): string {
  const date = new Date(timestampMs);
  return date.toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    timeZone: 'UTC',  // explicit — no more system TZ dependency
  });
}
```

## Recommendation

Option 3 is usually the right call for backend/utility date formatting — it makes the function **pure and deterministic** regardless of where it runs. Option 2 is a good backstop for any existing tests in the suite that may have the same latent bug.