I think I found it—this is a **timezone issue**, not a Node version issue. The problem isn't with CI's timezone being different from your local timezone; it's that **the test timestamps were created in a non-UTC timezone, but the test expectations assume a specific timezone**.

Here's what's happening:

1. **The timestamps are UTC milliseconds since epoch**, but the comment says they represent specific dates "at ... UTC"
2. **The implementation uses `toLocaleDateString()`**, which formats according to the **system's local timezone**, not UTC
3. **The test expectations are hardcoded** to match what the developer who wrote the test saw locally

When CI runs in UTC timezone, `new Date(1772791800000).toLocaleDateString('en-US')` gives a different date than when the developer in Berlin runs it (because the same absolute moment appears as different local times in different timezones).

**Evidence:**
- Berlin dev (CET, UTC+1): tests pass
- SF dev (UTC-8): claims tests pass (but may not have run them, or something's off with their setup)
- CI (UTC): one day *earlier* than expected

The fix is to **make the test timezone-independent**. Change your implementation to explicitly use UTC:

```typescript
export function formatDate(timestampMs: number): string {
  const date = new Date(timestampMs);
  return new Intl.DateTimeFormat('en-US', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    timeZone: 'UTC',  // Add this
  }).format(date);
}
```

This ensures the date formatting is always in UTC, regardless of the system's timezone. Now all developers and CI will get the same output.

**Alternative (if you want to preserve local timezone behavior):** Set the CI environment to match your expected timezone by adding this to `.github/workflows/test.yml`:

```yaml
- run: npm test
  env:
    TZ: Europe/Berlin  # or whatever timezone you want
```

But the first approach is better—tests should be timezone-agnostic unless timezone handling is explicitly being tested.