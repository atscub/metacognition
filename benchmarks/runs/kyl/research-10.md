## Working Through the Socratic Protocol

### Step 1: Surface my assumptions and known biases

Before giving advice, I need to flag what could distort my answer:

- **Sycophancy risk**: The user read an article and is implicitly looking for validation to push back on their tech lead. I should not agree with that article just because they're presenting it favorably.
- **Authority bias risk**: The tech lead is "the tech lead." I shouldn't defer to that title, but I also shouldn't dismiss it.
- **Pattern matching risk**: "Testing pyramid" is a well-known pattern. Am I applying it because it's familiar, or because it fits?
- **Recency bias**: The invoice bug is vivid and recent. Am I over-weighting one incident?

### Step 2: What evidence do I actually have?

| Claim | My Confidence | Basis |
|-------|--------------|-------|
| The testing pyramid is broadly valid | High | Widely studied, used at scale |
| 80% coverage = good test suite | **Low** | Coverage metrics are gameable and context-dependent |
| Unit tests catch integration bugs | **Low** | By definition they don't — that's the point |
| Their invoice bug was an integration failure | **High** | "Seemingly unrelated DB migration broke invoice generation" — this is exactly what integration boundaries look like |
| Integration tests have better ROI for *this codebase* | Medium | Depends on how much pure business logic they have |

### Step 3: Steelman both positions before committing

**Steelman the tech lead (testing pyramid, lots of unit tests):**
Unit tests are fast (milliseconds), isolated, easy to debug when they fail, and force modular code design. 80% coverage is an objective measurable target. The pyramid is backed by decades of industry practice. Google, Microsoft, and major software organizations have converged on it for good reasons. Unit tests also improve code quality as a side effect — testable code tends to be better-structured code.

**Steelman the article (integration-heavy for web apps):**
Most web app bugs happen at boundaries: database queries, API contracts, middleware interactions. Mocking the database in unit tests gives you false confidence — your mock behaves the way you *think* the DB behaves, not the way it actually does. Testing an API endpoint against a real test database catches the class of failure they just experienced. Kent Dodds' "Testing Trophy" model explicitly argues this for JavaScript web apps.

### Step 4: The crux — what specific claim settles this?

**The key question is: what class of bugs are they actually experiencing?**

They told us. The bug was: *a DB migration broke invoice generation, and nobody caught it for 4 hours because it was tested manually*.

Let's reason about what test would have caught that:

- **Unit test of the invoice function**: Would NOT catch it. Unit tests typically mock the DB, so they'd test your function against a fake database that still "works." The migration wouldn't affect the mock.
- **Integration test of `POST /invoices` against a real test DB**: **Would catch it.** Run migrations against the test DB, run the test suite, invoice endpoint fails, alert goes off.
- **E2E test of the invoice user journey**: Would also catch it, but slower and more brittle.

This is direct evidence from their own production history, not theory.

### Step 5: Where I disagree with the tech lead — and why it's not sycophancy

The testing pyramid is a sound *shape*, but the tech lead is applying it prescriptively in the wrong context. Here's the specific disagreement:

**"Write lots of unit tests first, aim for 80% coverage"** is advice optimized for:
- Teams building greenfield software with TDD from day one
- Codebases with significant pure business logic (algorithms, financial calculations, complex domain rules)
- Large teams where fast test suites matter at scale

**It's poorly optimized for:**
- Teams retrofitting tests onto 8 months of production code (your situation)
- CRUD-heavy B2B web apps where most logic is "get this from DB, transform it, return it"
- Teams where bugs are happening at the DB/API boundary, not inside isolated functions
- 3-person teams where engineering time is the binding constraint

An 80% coverage target, pursued via unit tests, will likely give you a lot of tests for simple getter functions and small utilities — and zero coverage for "what happens when we run a migration and then try to generate an invoice."

### Step 6: What I'm uncertain about (I don't want to hide this)

- **How much complex business logic do you have?** If you have substantial invoice calculation logic, tax rules, project cost estimation algorithms — that's worth unit testing. Pure business logic in isolation is the best use case for unit tests.
- **How testable is your existing code?** If your Express route handlers are 200-line functions with DB calls embedded, you'll need to refactor before you can integration-test them easily.
- **Your team's testing experience.** Setting up a real test database with proper test isolation (transactions that roll back, fixtures) requires some upfront investment. The learning curve matters at 20% budget.

---

## My Recommendation

**Given your specific situation — 3 engineers, production app, bugs happening at integration boundaries, limited budget — here's how I'd allocate the 20%:**

### Priority 1: API integration tests (~50-60% of your testing budget)

Write tests that call your Express endpoints against a real PostgreSQL test database. Not mocks. Use a library like [supertest](https://github.com/ladjs/supertest) + a test DB that runs migrations before the suite.

**Why:** This is exactly what would have caught your invoice bug. It tests the full stack: route handler → business logic → SQL query → DB schema. When you run migrations, run the test suite. If something breaks, you know before it hits production.

**Where to start:** The flows that are most expensive to break. Invoice generation, payment processing, anything touching billing. Not the `GET /projects` list endpoint.

**Coverage target:** Not 80% of lines. Cover the 10-15 most business-critical API flows end-to-end.

### Priority 2: Unit tests for pure business logic (~20-25%)

Look specifically for functions that:
- Take inputs and return outputs with no side effects
- Implement calculation logic (invoice totals, tax rates, estimates)
- Have complex conditional behavior

These are genuinely worth unit testing. But if most of your functions are "query DB, format response, return JSON" — that's not where unit tests shine.

### Priority 3: 3-5 E2E tests for your highest-stakes journeys (~15-20%)

The invoice generation flow should be one of them. Use Playwright or Cypress. These are your smoke detectors — they'll catch things integration tests miss (broken frontend, auth flows, multi-step workflows), but they're slow and brittle, so keep them small.

### What to skip (for now)

- **Don't chase 80% code coverage.** It's the wrong metric. It can be satisfied by testing things that don't matter while missing the things that do. A test that covers the invoice generation boundary is worth more than 20 tests that cover utility functions.
- **Don't write unit tests for controller/route handler logic** unless you've already refactored it to be testable. Testing mocked Express responses tells you very little.

### Concrete first step

Before anything else: write a regression test for the exact bug that just burned you. Set up the test DB, run your migrations, call `POST /invoices` with a realistic payload, assert the response is correct. Get that green. That test now lives in your CI pipeline and will never silently break again.

That one test is worth more than 200 unit tests for utility functions — not because integration tests are always better, but because it directly addresses your actual failure mode.

---

**One honest caveat:** The tech lead isn't wrong about the long-term value of a well-structured unit test suite. If you build the product for another 2-3 years, you'll want unit tests for your business logic layer. The disagreement is about *where to start* given your specific constraints and bug history. Integration tests first is the right call for your first quarter of testing investment.