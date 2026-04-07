Okay, applying the checklist. I'm noticing several concerning gaps in the evidence, and one of them breaks the team's entire working theory.

## What I'm Assuming vs. What I Actually Know

**High confidence (read it):**
- The test code uses `toLocaleDateString()` which formats dates in system local time
- CI environment is Etc/UTC
- The timestamps are correct (1772791800000 = March 5, 2026 00:30 UTC)

**Low confidence (hearsay):**
- That the SF developer actually ran the same test and got a pass
- That the Berlin developer is actually using Europe/Berlin timezone
- That all "passing locally" claims are accurate

## The Crack in the Theory

Here's what doesn't add up: **If tests use `toLocaleDateString()` and an SF developer (UTC-8) ran the code, they should see a failure:**

- Timestamp 1772791800000 = March 5, 2026 00:30 UTC
- In SF (UTC-8): That's March 4, 2026 16:30 PST
- `toLocaleDateString()` in SF would format as "March 4, 2026"
- Test expects "March 5, 2026" ❌

Yet the SF dev said tests pass. This is either:
1. They didn't actually run the tests
2. Their `TZ` environment variable is set to UTC (or similar)
3. They're lying/misremembering

**This is the real problem, not Node.js versions.**

## The Actual Root Cause

The test is **fundamentally timezone-dependent** but written as if it's timezone-independent. The bug isn't "why does it fail in CI"—it's "**why does it pass locally for anyone, and under what hidden conditions?**"

**Questions to verify before we fix:**

1. **On your local machine, run this:**
   ```bash
   echo $TZ
   date +%Z
   ```
   What does your timezone show? (If `$TZ` is empty but your system timezone is Europe/Berlin, Node will use your system timezone.)

2. **Did the SF developer actually run the tests, or did they just assume?** Have them run:
   ```bash
   TZ=America/Los_Angeles npm test
   ```
   and report the actual result.

3. **Can you check CI's actual timezone?** The `cat /etc/timezone` shows `Etc/UTC`, but does CI have `$TZ` set?

## The Real Fix

Once we confirm the timezone issue, the solution is **not** to keep chasing Node versions. Instead:

- **Option A**: Make the test timezone-independent by using UTC-only formatting
- **Option B**: Mock/freeze the system timezone in tests
- **Option C**: Use a date library that doesn't depend on system timezone (date-fns, day.js with explicit UTC)

Don't fix it with environment variables in CI—that masks the bug, it doesn't solve it.

What does your `$TZ` show locally, and can you have the SF dev actually run the test in their timezone?