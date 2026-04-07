This is not a Node.js version problem. It's a **timezone bug**, and the Node version pinning was a red herring that cost your team two days.

## Root Cause

`toLocaleDateString()` converts the timestamp to a date using the **system's local timezone**. The timestamps in your tests land near midnight, so they fall on different calendar dates depending on where the process is running.

Let's verify with test 1. The comment says "March 5, 2026 at 00:30 UTC" — but work backwards from the failure:

- CI (UTC) returns **March 4** → the UTC time is March 4 at ~23:30
- Berlin dev (UTC+1) returns **March 5** → +1 hour pushes it to 00:30 on March 5 ✓

So the timestamp `1772791800000` is actually **March 4, 2026 at 23:30 UTC** — the comment in the test is wrong. It was written from Berlin's perspective (where 23:30 UTC = 00:30 local = "March 5 already").

The same applies to test 2. Test 3 passes everywhere because December 31 at ~22:30 UTC stays December 31 regardless of the timezone offsets in play.

The SF developer passing locally is suspicious — they likely have a non-default system timezone (VM, WSL, or a manually set `TZ` variable), not UTC-8 for their Node process.

## The Fix

**Option A — Make the implementation timezone-explicit** (recommended if you want consistent UTC dates):

```typescript
export function formatDate(timestampMs: number): string {
  const date = new Date(timestampMs);
  return date.toLocaleDateString('en-US', {
    timeZone: 'UTC',       // ← pin this
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });
}
```

**Option B — Fix the test timestamps** (if the intent is local-time display):

Use timestamps at noon UTC so no timezone offset can shift the date by a day:

```typescript
// March 5, 2026 at 12:00 UTC — safe from any UTC±14 offset
const timestamp = 1772834400000;
```

**Option C — Pin TZ in the test environment** (quick CI fix, but masks the underlying fragility):

```yaml
# .github/workflows/test.yml
- run: npm test
  env:
    TZ: Europe/Berlin
```

This makes CI match your Berlin developers, but now SF developers (or any future CI migration to a different timezone) will be surprised again.

## Recommendation

Go with **Option A** + fix the test comments. The `timeZone: 'UTC'` option makes the function's behavior explicit and deterministic regardless of where it runs. If the business requirement is actually to format in the user's local timezone, that needs to be a parameter — and tests should document what timezone they assume by setting `process.env.TZ` explicitly in a `beforeAll` block or by mocking `Date`.

The version difference between 20.9.0 and 20.11.1 was never the variable that mattered. The variable was `Europe/Berlin` vs `Etc/UTC`.