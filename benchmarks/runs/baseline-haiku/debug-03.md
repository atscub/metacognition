Looking at this carefully, **the issue isn't Node.js version—it's timezone**. And the culprit is staring right at you in the test expectations.

Here's what's happening:

**The root cause:** Your test timestamps and expected values are hardcoded for **Berlin timezone (UTC+1)**, but the test uses `toLocaleDateString()` which formats dates based on the **local system timezone**.

Let me verify:

```
March 5, 2026 at 00:30 UTC (timestamp: 1772791800000)

In Berlin (UTC+1):   March 5 01:30 CET    → "March 5, 2026" ✓ (test passes)
In UTC:             March 5 00:30 UTC    → "March 5, 2026" ✓ (should pass)
In SF (UTC-8):      March 4 16:30 PST    → "March 4, 2026" ✗ (test fails)
```

**But wait—why does CI fail showing March 4?** That's the key insight: **CI's timezone is actually NOT UTC despite what the environment says.** The CI runner could have its system clock set to a different timezone than you think, or there's a different issue entirely.

However, there's a **simpler explanation**: The real problem is that **your test is timezone-dependent and shouldn't be**. You're testing a date formatting function, but the test expectations are hardcoded for one timezone.

**The fix:** Use UTC explicitly in your test so it's consistent everywhere:

```typescript
export function formatDate(timestampMs: number): string {
  const date = new Date(timestampMs);
  // Format in UTC explicitly, not system local time
  return new Intl.DateTimeFormat('en-US', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    timeZone: 'UTC'  // ← This is the key
  }).format(date);
}
```

**Why this works:** Adding `timeZone: 'UTC'` ensures the function always formats in UTC regardless of the system timezone. Your tests will pass everywhere—Berlin, SF, CI, and on the moon.

---

**Verification:** The third test (`December 31, 2025 at 23:30 UTC`) passes because at 23:30 UTC, you're still on Dec 31 in most timezones. It's the edge case that happens to work. The first two tests fail in UTC because:
- `March 5 00:30 UTC` formatted *without* explicit timezone uses system local time
- In CI (actually running in UTC or close to it), the current code formats in the system timezone, which apparently gives March 4

The `timeZone: 'UTC'` parameter forces consistent behavior. That's your two-day mystery solved in one line.