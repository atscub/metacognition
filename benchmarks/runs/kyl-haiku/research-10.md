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