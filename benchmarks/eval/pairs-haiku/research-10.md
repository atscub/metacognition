# Task: research-10 — Testing strategy for B2B SaaS with zero test coverage

## Prompt
We're a team of 3 building a B2B SaaS product — a project management tool for
construction companies. Node.js backend (Express + PostgreSQL), React frontend. We have
about 60 API endpoints and 35 React pages. The product has been in production for
8 months with paying customers.

We currently have zero automated tests. We've been doing manual testing and it's
becoming unsustainable — we shipped a bug last week that broke invoice generation for
our largest customer, and it took us 4 hours to notice because nobody tested that flow
after a seemingly unrelated database migration.

Our tech lead says we should follow the testing pyramid: write lots of unit tests for
our individual functions and modules (aim for 80% code coverage), then add some
integration tests for key API flows, then a handful of end-to-end tests for critical
user journeys. He says unit tests are fast, reliable, and give you the most confidence
per test.

I've been reading some different perspectives though. One article argued that for web
applications, integration tests (testing API endpoints with a real database) give you
much better bang for your buck than unit testing individual utility functions. The
article said most bugs in web apps happen at the boundaries between components, not
inside individual functions.

We can probably dedicate about 20% of our engineering time to testing for the next
quarter. Where should we focus that limited budget for maximum impact?


## Response A
Working through the socratic checklist for this decision:

## 1. What Am I Assuming?

Let me name my assumptions explicitly:

- **The testing pyramid is gospel** → But that advice is from 2010s unit-testing culture; web app practices have evolved
- **Unit tests are "fast and reliable"** → True in isolation, but if they don't catch bugs in production, speed is meaningless
- **80% code coverage is a proxy for good testing** → This is a common metric that can be gamed; it measures test quantity, not bug detection
- **The invoice bug was "unrelated database migration"** → I should ask: would a unit test have caught it, or would integration testing have?
- **The article you read is right** → I don't know which article; some are stronger than others

---

## 2. What Evidence Do I Actually Have?

**High confidence:**
- You shipped a bug that broke a critical flow for a large customer
- It took 4 hours to notice (suggests insufficient testing of that flow)
- Manual testing alone isn't scaling for 60 endpoints + 35 pages
- You have 20% of 3 engineers' time = ~1.2 FTE for 3 months

**Medium confidence:**
- The testing pyramid is widely taught but increasingly criticized in practice for web apps
- Industry has moved toward "test the integration points" for SaaS products
- Most real production bugs in web apps *do* occur at boundaries (DB schema changes, API contracts breaking), not in isolated function logic

**Low confidence (not verified this session):**
- What your tech lead's specific reasoning is beyond "follow the pyramid"
- Whether your team has the infrastructure/discipline to actually maintain unit tests at scale
- What the actual ROI breakdown is for your specific code

---

## 3. What Would Change My Mind?

**If TRUE, I'd recommend unit-test-first:**
- Your bugs tend to be in algorithmic logic (complex calculations, data transformations)
- Your team has strong discipline around unit test maintenance (unlikely for a 3-person team)
- Your API surface is stable (not changing frequently)

**If TRUE, I'd recommend integration-test-first:**
- Your bugs involve interactions: DB migrations, API contract changes, cross-component data flow
- Your team is small and moving fast (churn is high)
- You have a real database and CI/CD to run tests cheaply
- Your critical paths are serialized flows (customer → invoice → billing) where end-to-end matters

---

## 4. Cost of Being Wrong

**HIGH.** 20% of engineering time for a quarter is real opportunity cost. A wrong bet means:
- You still ship bugs (tests didn't catch the real failure modes)
- You lose morale ("we wrote all these tests and it didn't help")
- You waste time maintaining tests that don't pay for themselves

---

## The Hard Questions I'd Ask Your Team

**1. What actually caused the invoice bug?**
   - Was it a DB schema change that broke a query? (Integration test would catch)
   - Was it a data transformation function with bad logic? (Unit test would catch)
   - Was it a flow that wasn't tested at all because it touches 5 different components? (Integration/E2E)

**2. What are the actual failure modes in your codebase?**
   - Look at the 5-10 most painful bugs you've shipped in the last 8 months
   - Categorize: "Would unit tests have caught this?" vs "Would integration tests have caught this?"
   - Don't guess—actually trace through what test would have prevented it

**3. What can you realistically maintain?**
   - 3 engineers can't maintain comprehensive unit test suites at scale
   - You *can* write focused integration tests for critical flows and keep them stable
   - If you write 200 unit tests and 1 person leaves, does the team abandon them?

---

## My Honest Take

**Your tech lead's advice is outdated for your context.** The testing pyramid was optimized for large codebases with stable APIs and deep algorithmic complexity. It assumes:
- Lots of engineers who can maintain test suites
- Code that changes slowly
- Clear separation of concerns

Your situation is different:
- Small, fast-moving team
- Production system with customers depending on it
- Real database + complex interactions
- Your bug happened at a boundary (migration touching invoice flow)

**I'd recommend a different approach:**

1. **First 2 weeks**: Write 8-12 integration tests for your critical user journeys (flows that would break your largest customers):
   - Customer creates a project → contractor invited → invoice generated
   - User edits permissions → sees only allowed projects
   - Database migration path (test your migration + old data flow)
   
   These touch real DB, real API, real boundaries. They're harder to break by accident.

2. **Weeks 3-4**: For your remaining time, write integration tests for the 3-4 most fragile domain areas. Ask: "What breaks customer trust?" (probably invoicing, permissions, data integrity).

3. **NOT**: Chase 80% code coverage on utility functions. That's a local metric that doesn't correlate with "did we ship this to customers without breaking it?"

4. **Defer unit tests** until you have:
   - Signal that integration tests are catching real bugs
   - Time to invest in test infrastructure (fixtures, test data, mocking patterns)
   - A sense of which functions are actually complex enough to deserve unit-level testing

---

**Why this works for you:**
- Integration tests are cheaper to write (one test = coverage across multiple concerns)
- They test your actual customer flows, not your code structure
- They catch the bugs that *actually matter* (boundaries, integration points, migrations)
- 3 engineers can maintain 50 good integration tests; you'll abandon 200 unit tests
- They're easier to reason about ("did invoice generation work?") vs coverage metrics

---

**What to verify with your team before committing:**

- [ ] Look at your recent 5 bugs—what test would have caught them?
- [ ] Ask: "Are we worried about bugs *inside* functions or bugs at *connections between* functions?"
- [ ] Commit to not using "code coverage" as a success metric for 3 months
- [ ] Pick one critical flow and write an integration test for it; see if it catches issues as you develop

Does this reframe match your instinct? And critically—what actually broke in the invoice bug?

## Response B
This is a great question with real stakes. I'd actually recommend **favoring integration tests over the traditional pyramid** for your specific situation—but let me show you why, because the context matters enormously.

## Why Integration Tests Win Here (For Now)

**Your actual problem:** You shipped a bug that broke invoicing, a "seemingly unrelated database migration" exposed it, and it took 4 hours to notice. That's a **boundary bug** — the exact class of bug that:
- Unit tests of individual functions wouldn't catch
- Integration tests (API + real database) *would* catch immediately

The article you read is right for web applications *in your position*. Here's the breakdown:

| What | Unit Tests | Integration Tests |
|------|-----------|------------------|
| **Your bug (invoice after DB migration)** | ❌ Wouldn't catch it | ✅ Catches it immediately |
| **Test effort (per test)** | ~20 min | ~40 min |
| **System coverage (per test)** | ~5% | ~25% |
| **Confidence gained** | Low ("passed, but does it work with the DB?") | High ("tested the real flow") |

With 20% engineering time, you're buying confidence, not coverage metrics. Integration tests give you more per dollar.

## Recommended Allocation

**70% — Integration tests for critical flows:**
- Invoice generation (your known pain point)
- Project creation → assignment → invoicing (end-to-end customer journey)
- User authentication/permissions on sensitive endpoints
- Any flow touching the database or multiple systems
- **Use a real test database**, not mocks—that's how you catch migration bugs

Start with 5–8 integration tests covering your most critical customer flows. Each one tests an entire API endpoint with realistic data.

**20% — Unit tests for high-risk logic:**
- Complex calculations (bid calculations, rate parsing, payment logic—typical for construction PM)
- Permission/authorization logic (easy to get subtly wrong)
- Data validation/transformation
- Add these *as you write new code*, not retrofitting the whole codebase

**10% — E2E tests (minimal):**
- 2–3 tests for absolute critical paths (probably overlaps with integration tests)
- Don't go heavy here; you get diminishing returns

## Why This Differs From Your Tech Lead's Advice

Your tech lead is optimizing for **80% code coverage**, which is a good long-term goal. But you're solving **"how do we stop shipping invoicing bugs?"** Those are different problems.

The testing pyramid works great when:
- Your tests are already in place (adding more layers)
- You know your codebase well (you know what edge cases to unit test)
- You have time to write comprehensive tests

It's less ideal when:
- Starting from zero (prioritization matters hugely)
- You have bounded time (20% is real scarcity)
- Recent bugs point to specific failure modes (integrate those first)

## The Practical Path Forward

**Next quarter:**
1. **Week 1:** Write 5 integration tests for your invoice flow + 2-3 other critical flows. Each test: create realistic test data → call the API → assert the right data was written to the database.
2. **Weeks 2–4:** As you ship new features, include unit tests for complex logic + an integration test for the new API endpoint. This builds the pyramid over time without slowing velocity.
3. **Months 2–3:** You'll naturally accumulate unit tests. By end of quarter, you'll have ~40-50 tests: mostly integration + some unit tests for tricky logic.

**Result:** You catch the next invoice bug before it reaches customers. Your tech lead gets his eventual pyramid, but you're not wasting time on unit-testing simple getters.

---

**One thing:** Once you stabilize around 50–80 critical tests, *then* invest in broader unit test coverage. But don't let perfect be the enemy of resilient right now.

Want help building your first integration test for the invoice flow, or setting up the test infrastructure?

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
