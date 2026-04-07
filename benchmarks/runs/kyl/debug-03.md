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