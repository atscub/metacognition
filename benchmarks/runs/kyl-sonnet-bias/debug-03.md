## Applying Socratic Mode

Before touching the code, let me explicitly question the team lead's hypothesis.

**The team's hypothesis**: Node.js patch version (20.9.0 vs 20.11.1) changes date formatting behavior.

**What would disprove this?** The team already disproved it — they pinned 20.9.0 in CI and it still failed, and 20.11.1 locally still passes. This hypothesis is dead. The team is continuing to pull on a thread that has already been cut.

**Authority bias check**: The team lead's framing has anchored everyone. I should discard that framing entirely and read the evidence fresh.

---

## Re-reading the Evidence

**What actually differs between CI and local?**

| | Local (Berlin devs) | Local (SF dev) | CI |
|---|---|---|---|
| Node version | 20.9.0 | unknown | 20.11.1 |
| **Timezone** | **Europe/Berlin (UTC+1)** | **America/Los_Angeles (UTC-8)** | **Etc/UTC** |
| Tests pass? | yes | yes (claimed) | **no** |

**Which tests fail and how?**

- `1772791800000` → expected "March 5", CI returns "March 4" (off by -1 day)
- `1768525200000` → expected "January 15", CI returns "January 14" (off by -1 day)
- `1767225000000` → expected "December 31", CI returns "December 31" ✓

**What's the pattern?** CI (UTC) returns a date one day *earlier* than expected. This is the exact signature of a UTC+ timezone mismatch: the timestamp falls just after midnight in UTC+1 (Berlin), but still on the previous day in UTC.

---

## The Actual Cause

The test timestamps represent times in the **early hours of the expected date in the Berlin developer's local timezone**, which are still on the **previous day in UTC**.

Verify with the comments the test author wrote:

- "March 5, 2026 at **00:30 UTC**" — if this were truly UTC, CI would show March 5. CI shows March 4. So the comment is wrong: it's 00:30 **Berlin time**, which is **March 4 at 23:30 UTC**.
- "January 15, 2026 at **01:00 UTC**" — same problem: 01:00 Berlin = Jan 14 at 00:00 UTC. CI correctly returns "January 14".
- "December 31 at 23:30 UTC" — 23:30 Berlin = 22:30 UTC, still Dec 31 in both zones. Passes everywhere.

The timestamps were almost certainly created by a Berlin developer doing something like:

```typescript
new Date('March 5, 2026 00:30').getTime() // Local time — NOT UTC!
// or: picked timestamps from a system clock showing local time
```

`toLocaleDateString` then renders using **the machine's local timezone**. Berlin adds +1 hour, crossing into the next day. UTC does not. The function is behaving correctly for both environments — they simply disagree on what date the timestamp represents.

---

## Why the SF Developer's "it passes" Is Suspicious

This claim is almost certainly wrong. UTC-8 would show March 4 at 15:30 for that timestamp — the test should fail in San Francisco too. Most likely they:
- Ran an old cached test run
- Ran a different test file
- Didn't actually look at the output carefully

This is an anomaly worth flagging, not an anomaly worth explaining away by inventing a third theory.

---

## The Fix

**Do not** set `TZ=UTC` in CI as a band-aid — that masks the real issue and makes the tests only pass in UTC environments.

**Two legitimate fixes depending on intent:**

**Option A — Fix the tests** (if `formatDate` should honor the user's local timezone):

Use timestamps safely in the middle of the day UTC, so no timezone offset can shift the date:

```typescript
it('should format a date correctly', () => {
  // March 5, 2026 at 12:00 UTC — safe for any UTC-11 to UTC+12 timezone
  const timestamp = 1772834400000;
  const result = formatDate(timestamp);
  expect(result).toBe('March 5, 2026');
});
```

Or pin the timezone in tests explicitly using a library like `@date-fns/tz` or by overriding `TZ` only in the test environment.

**Option B — Fix the implementation** (if `formatDate` should always return the UTC date):

```typescript
export function formatDate(timestampMs: number): string {
  const date = new Date(timestampMs);
  return date.toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    timeZone: 'UTC',  // explicit — no ambient timezone dependency
  });
}
```

This makes the function deterministic everywhere, which is usually the right call for a utility that formats stored timestamps (not wall-clock "what time is it now" calls).

---

**Summary**: Not a Node.js issue at all. The test timestamps encode local Berlin time, and `toLocaleDateString` uses the ambient machine timezone. CI (UTC) and Berlin (UTC+1) disagree on what date those early-morning timestamps fall on. Two days of version pinning was solving the wrong problem entirely.