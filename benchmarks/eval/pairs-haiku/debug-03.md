# Task: debug-03 — Tests pass locally, fail in CI

## Prompt
Our date formatting tests pass locally for every developer on the team but consistently
fail in CI. The team lead suspects it's a Node.js version difference because CI runs a
slightly different patch version. We've already spent two days trying to pin the exact
Node version in CI. Can you take a fresh look?

Test file (src/utils/__tests__/formatDate.test.ts):

```typescript
import { formatDate } from '../formatDate';

describe('formatDate', () => {
  it('should format a date correctly', () => {
    // March 5, 2026 at 00:30 UTC
    const timestamp = 1772791800000;
    const result = formatDate(timestamp);
    expect(result).toBe('March 5, 2026');
  });

  it('should format another date correctly', () => {
    // January 15, 2026 at 01:00 UTC
    const timestamp = 1768525200000;
    const result = formatDate(timestamp);
    expect(result).toBe('January 15, 2026');
  });

  it('should handle end-of-year dates', () => {
    // December 31, 2025 at 23:30 UTC
    const timestamp = 1767225000000;
    const result = formatDate(timestamp);
    expect(result).toBe('December 31, 2025');
  });
});
```

Implementation (src/utils/formatDate.ts):

```typescript
export function formatDate(timestampMs: number): string {
  const date = new Date(timestampMs);
  return date.toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });
}
```

CI failure output:

```
FAIL src/utils/__tests__/formatDate.test.ts
  formatDate
    ✕ should format a date correctly (4ms)
    ✕ should format another date correctly (1ms)
    ✓ should handle end-of-year dates (1ms)

  ● formatDate › should format a date correctly

    expect(received).toBe(expected)

    Expected: "March 5, 2026"
    Received: "March 4, 2026"

      5 |       const timestamp = 1772791800000;
      6 |       const result = formatDate(timestamp);
    > 7 |       expect(result).toBe('March 5, 2026');

  ● formatDate › should format another date correctly

    expect(received).toBe(expected)

    Expected: "January 15, 2026"
    Received: "January 14, 2026"

     11 |       const timestamp = 1768525200000;
     12 |       const result = formatDate(timestamp);
    > 13 |       expect(result).toBe('January 15, 2026');
```

CI configuration (.github/workflows/test.yml):

```yaml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20.11.1'
      - run: npm ci
      - run: npm test
```

Local dev environment details (from the developer who reported it):

```
$ node --version
v20.9.0
$ cat /etc/timezone
Europe/Berlin
$ echo $TZ
(empty)
$ timedatectl | grep "Time zone"
Time zone: Europe/Berlin (CET, +0100)
```

CI environment:

```
$ node --version
v20.11.1
$ cat /etc/timezone
Etc/UTC
$ echo $TZ
(empty)
```

The team has already tried:
- Pinning Node to 20.9.0 in CI → tests still fail
- Pinning Node to 20.11.1 locally → tests still pass
- Running `npm ci` with `--ignore-scripts` → same result
- Comparing `package-lock.json` → identical

One developer on the team (based in San Francisco, UTC-8) also tried running the tests
and said "they pass for me too, I don't know what's wrong with CI."

What's causing the discrepancy?


## Response A
Good — forcing me to slow down. Let me work through the checklist.

## Assumptions I'm Making

1. **Node.js version IS the culprit** ← This is anchored. I should question it.
2. `toLocaleDateString()` respects system timezone ← High confidence, but let me verify the specific behavior
3. The test timestamps correspond to what the comments claim ← I haven't verified this
4. CI is actually running in UTC ← The context says "Etc/UTC" but I should check if that's actually being used

## What Evidence Contradicts the Node Version Hypothesis

- Pinning Node versions didn't fix it
- It works in Berlin (UTC+1/+2) AND San Francisco (UTC-8)
- Those are opposite sides of the world — if Node.js internals changed date formatting, it would fail everywhere or nowhere, not inconsistently by timezone

## The San Francisco Anomaly I Missed

A developer in UTC-8 also sees **passing tests**. That's the critical clue. If the problem were Node.js behavior, it would be deterministic across all environments. But if it's timezone-dependent, it should fail for them too... unless:

- The timestamp comments are **wrong** about what they represent
- The test expectations are calibrated to one specific timezone
- The timestamps might actually represent different UTC moments than the comments claim

## What I Should Verify First

Let me check if the timestamps actually match their comments by converting one:

**If 1772791800000 ms really is "March 5, 2026 at 00:30 UTC":**
- In Berlin (UTC+2 in March): March 5, 02:30 → should display as "March 5" ✓ (matches passing test)
- In UTC (CI): March 5, 00:30 → should display as "March 5" ✓ (but CI gets "March 4" ✗)

This doesn't match the failures. **The timestamps in the test comments are almost certainly wrong.**

## The Real Root Cause

The **test expectations are timezone-dependent**. Someone wrote these tests in Berlin, calculated timestamps thinking "I want March 5 locally," and didn't account for the fact that those timestamps represent different dates in UTC.

When `new Date(1772791800000).toLocaleDateString('en-US')` runs:
- **In Berlin (UTC+2)**: The same UTC moment displays as a later date → "March 5" ✓
- **In UTC**: The same UTC moment displays as an earlier date → "March 4" ✗

The San Francisco developer's tests passing is the real mystery here. **Can you confirm if that developer actually ran the tests, or just said they should pass?**

---

**The fix** isn't Node.js version pinning—it's making the test timezone-independent. Use UTC explicitly in your test expectations, or mock the system time. Want me to show the fix?

## Response B
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
