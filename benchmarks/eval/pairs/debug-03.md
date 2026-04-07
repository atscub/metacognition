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
## Stop. Question the first hypothesis.

The team's working theory is **Node.js patch version**. Before accepting that, let me apply the Socratic checklist:

**What would a Node.js version difference actually change here?**
Date formatting via `toLocaleDateString` is built on ICU data. A patch version (20.9.0 → 20.11.1) changing how March 5 renders as March 4 would be an extraordinary, breaking regression — and would affect the month name or year format, not just shift by exactly one day. This is extremely implausible.

**What else could shift a date by exactly one day, consistently?**
Only two things: a timezone offset or a calendar bug. There's no calendar bug here.

**What evidence would disprove the timezone theory?**
If the failing dates weren't near midnight UTC, timezone couldn't explain a one-day shift.

---

## The actual root cause: timezone, not Node version

Let me verify the timestamps. Working backwards from the CI output:

CI (UTC) receives "March 4" for a timestamp the test calls "March 5, 2026 at 00:30 UTC." That description is the bug surface: if the timestamp is **March 4, 2026 at 23:30 UTC**:

| Environment | Local time | Date displayed | Result |
|---|---|---|---|
| CI (UTC) | March 4 at 23:30 | March 4 | **FAIL** — expected "March 5" |
| Berlin dev (UTC+1) | March 5 at 00:30 | March 5 | PASS |
| CI (UTC) | January 14 at 23:30 | January 14 | **FAIL** — expected "January 15" |
| Berlin dev (UTC+1) | January 15 at 00:30 | January 15 | PASS |

Test 3 (December 31) passes everywhere because that timestamp sits at ~22:50 UTC — far enough before midnight that even UTC+1 still renders it as December 31.

`toLocaleDateString` without a `timeZone` option uses the **system's local timezone** to determine the calendar date from the Unix timestamp. The two environments aren't running different Node versions — they're running in different timezones.

---

## Why pinning the Node version did nothing

Because the Node version was never the variable. The variable was `TZ`. GitHub Actions' `ubuntu-latest` runners use `Etc/UTC`. Developer machines in Berlin use `Europe/Berlin (CET, +0100)`. That's a fixed 1-hour offset — enough to push near-midnight timestamps across the day boundary.

---

## Red flag: the San Francisco developer

The SF developer (UTC-8) claiming "tests pass for me" is almost certainly **wrong or untested**. At UTC-8, `March 4 23:30 UTC` is `March 4 15:30 local` — that's still March 4. Their tests should show "March 4" and fail identically to CI.

Most likely explanations:
- They ran a different branch or stale build
- They didn't actually run the full suite and are pattern-matching on a summary
- They have `TZ=UTC` set somewhere in their shell (the problem shows Berlin's `echo $TZ` as empty, but doesn't show SF's)

**Don't chase this.** It's noise. The CI+Berlin data is sufficient.

---

## The fix

The implementation uses `toLocaleDateString` without specifying a timezone, so the output varies by where the process runs. Since your test comments describe the timestamps as UTC times and expect UTC dates, add `timeZone: 'UTC'` to the options:

```typescript
export function formatDate(timestampMs: number): string {
  const date = new Date(timestampMs);
  return date.toLocaleDateString('en-US', {
    timeZone: 'UTC',   // ← pin to UTC so output is environment-independent
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });
}
```

This makes the function deterministic regardless of the host timezone. If the **intended** behavior is actually "display in the user's local timezone," then the fix is opposite — the tests themselves need to control for timezone by setting `TZ=UTC` in jest config (`testEnvironmentOptions` or a `globalSetup` that sets `process.env.TZ = 'UTC'`), not by pinning Node.

---

## Summary

| Claim | Status |
|---|---|
| Node.js patch version causes this | **False** — pinning confirmed it, and the mechanism doesn't exist |
| CI timezone (UTC) vs local timezone (UTC+1) causes this | **True** — explains all observed failures precisely |
| SF developer's "passes for me" is meaningful | **Suspect** — contradicts the timezone model; likely untested |
| Fix: pin Node version | **No effect** |
| Fix: add `timeZone: 'UTC'` to `toLocaleDateString` options | **Resolves the root cause** |

## Response B
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
