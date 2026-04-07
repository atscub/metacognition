I'll work through this carefully, because both perspectives have merit and the right answer depends on your specific context.

## Let me first check my assumptions and the crux of disagreement

**What I need to verify:** When does the testing pyramid work well vs. when do integration tests give better ROI?

**The steelman of your tech lead's position:**
- Unit tests are *fast* (feedback in milliseconds vs. integration tests taking seconds/minutes)
- Unit tests are *isolated* (easier to debug why one fails)
- Coverage metrics are concrete and measurable
- For codebases with complex business logic in utility functions, they catch real bugs
- The pyramid scales well as a team grows (more unit tests = more parallelizable)

That's not wrong reasoning — it's a valid strategy for certain codebases.

**Now, the critical question:** Is your codebase one where that applies?

You buried the key evidence in your description:
> "we shipped a bug last week that broke invoice generation... it took us 4 hours to notice because nobody tested that flow after a seemingly unrelated database migration"

**This is the opposite of a unit test failure.** A unit test would have caught "the invoice function doesn't work." You would have noticed immediately. The fact that it took 4 hours suggests:
- The invoicing code path runs, it just produces wrong output or fails silently
- The failure wasn't in a single utility function; it was at a *boundary* — query changed → data shape changed → downstream code broke
- Your risk isn't "are individual functions correct" — it's "do the moving parts fit together correctly"

## Here's what I'd actually recommend (with caveats):

**Start with integration tests. Not instead of unit tests, but as your priority.** Here's why:

1. **You have the data.** One bug you caught took 4 hours to detect. Integration tests would have caught that *immediately* (before merge, in CI). That's worth maybe 15-20 hours of lost time prevented per quarter.

2. **You have a small surface area.** With 60 API endpoints and 35 pages, you can test the critical ones. You don't need to test every possible path.

3. **ROI is asymmetric.** One integration test covering "user creates project → updates task → invoice generates correctly" catches bugs at 5+ boundaries simultaneously. A unit test of "parseInvoiceData()" function catches... one thing, in isolation.

4. **Your risk is integration, not functions.** Most of your bugs are probably "schema changed and query broke" or "service returned unexpected format" — not "this 15-line utility has a logic error."

**Realistic quarterly plan with 20% capacity:**

- **First 4-5 weeks:** Write integration tests for your critical user journeys (invoice generation, project creation, reporting — whatever breaks your customers):
  - Set up test database that mirrors production schema
  - Write 8-12 integration tests that hit your real DB and APIs
  - Goal: catch 80% of production bugs that take hours to notice
  
- **Remaining 2-3 weeks:** Start unit tests *where it matters*:
  - Complex calculation logic (invoice math, report aggregation)
  - Business rule validation
  - NOT: trivial getters, formatters, or wrapper functions

- **Long term:** Once you have integration test coverage, unit tests become much more valuable (you'll know the boundaries work; now test the logic inside).

## One caveat I want to flag:

The testing pyramid *is* better if you have:
- Deep, algorithmic business logic (financial calculations, optimization, etc.)
- Multiple teams working on independent modules
- A codebase where most bugs are in single functions, not across boundaries

But from what you've described, that doesn't sound like you yet. You're at the stage where "the integration points fail silently" is your biggest risk.

**What would change my mind:** If you showed me the actual codebase and I found that most of your logic is in complex utility functions rather than orchestration/queries. Then the pyramid makes more sense.

Does this resonate with how you experience bugs in your system?