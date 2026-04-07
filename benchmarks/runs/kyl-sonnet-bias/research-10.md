## Socratic Audit Before Answering

**Running the checklist explicitly — because this is a high-stakes foundational decision.**

---

### Step 1: What am I assuming?

Before I form a view, let me name my priors so I can challenge them:

1. That "testing pyramid" advice is universally applicable — **questionable**
2. That the tech lead is wrong — **too fast; steelman first**
3. That their codebase is mostly CRUD — **not verified, matters a lot**
4. That unit tests have low ROI for them — **depends on what's actually in the codebase**
5. That 80% coverage is a meaningful goal — **this one I'll challenge directly**

---

### Step 2: Steelman the tech lead's position

The strongest version of "testing pyramid + 80% coverage":

- Unit tests run in milliseconds; integration tests with a real DB can take minutes. A slow test suite doesn't get run.
- Fast tests give precise failure attribution — a failing unit test tells you *exactly* which function broke, not "something in the invoice flow."
- 80% coverage forces the team to reason about edge cases they'd otherwise skip.
- Integration tests have environmental failure modes: DB connections drop, test data collides, test order matters. Unit tests are deterministic.
- For a 3-person team, reliability of the test suite matters enormously — flaky tests destroy confidence faster than no tests.

This is a genuinely strong position. **Don't dismiss it.**

---

### Step 3: What does their specific evidence tell us?

Here's where I need to slow down. The invoice bug is not a minor anecdote — it's diagnostic information about *where their bugs actually live*:

> A "seemingly unrelated database migration" broke invoice generation. It took 4 hours to notice.

This is not a failure of logic inside a function. No unit test on `formatInvoice()`, `calculateTax()`, or any utility function would have caught this. This is a **schema/data-layer integration failure**. The bug lived at the boundary between the migration and the query that read invoice data.

That's one data point, but it's their most salient one, and it's telling. The class of bugs they're most worried about — the ones that already hurt paying customers — are integration-layer bugs.

---

### Step 4: Authority bias check — is the pyramid right for *this context*?

The testing pyramid comes from Mike Cohn, written in the context of enterprise software teams with rich domain models. It's been popularized and somewhat cargo-culted.

**Kent C. Dodds** ("Write tests, not too many, mostly integration"), **Justin Searls**, and **Martin Fowler** (who later wrote about "testing honeycomb" for service-oriented systems) all argue the pyramid doesn't translate well to API-centric web applications. Their core claim: in a web app, most bugs happen at the HTTP layer, the ORM/query layer, and the middleware stack — not inside pure functions.

**Who is right?** It depends on what's actually in the codebase. The question I'd ask:

- Does their Express code have **complex algorithmic business logic** — construction cost estimation algorithms, schedule dependency calculations, multi-step billing math? → Unit tests matter more.
- Or are their routes mostly **thin CRUD handlers** — validate input, call a DB query, return JSON? → Integration tests catch almost everything; unit testing the handlers adds little.

For a project management tool for construction companies, I'd estimate 80%+ of the value is in the data model and the API contracts, not in algorithmic logic. But I'd verify before betting on it.

---

### Step 5: The 80% coverage target — specific concern

This is where I'll disagree with the tech lead most directly.

Coverage is a **proxy metric**. It measures whether lines were executed, not whether behavior was asserted. A team chasing 80% coverage will:

1. Write tests that call functions without asserting meaningful behavior
2. Spend time covering low-risk utility functions instead of high-risk critical paths
3. Feel confident ("we have 80% coverage!") while the invoice bug still ships

Coverage without quality is worse than lower coverage with high-value tests — because it creates false confidence. **80% coverage of CRUD handlers is not 80% protection against the bugs that will hurt them.**

---

### Step 6: What would change my mind?

I'd revise this answer if:
- Their codebase has significant algorithmic complexity (scheduling engines, cost estimation math, dependency chains) — that's a genuine case for unit tests
- Their integration test setup is genuinely difficult (they're using a cloud DB they can't replicate locally, or their schema is too complex to reset between tests) — that changes the cost calculation
- Their frontend has complex client-side state logic — then E2E tests on a few flows might be higher value than I'm suggesting

---

## The Recommendation

Given the Socratic audit, here's my calibrated answer — not "integration tests are always better," but "here's what fits *your* situation":

---

### Do this, in this order:

**1. Integration tests for critical paths first (first 4-6 weeks)**

Use `supertest` against your Express app with a real PostgreSQL test database (use transactions that rollback after each test — fast and clean). Write tests that cover:

- Invoice generation (you already know this bites you)
- Payment recording and status changes
- Any flow that touches financial data
- Any flow that changed recently and caused a bug

Target: ~15-20 tests covering the 8-10 most business-critical endpoints. Not all 60. You're not trying to be comprehensive — you're trying to be protected.

These tests would have caught the migration bug. That's the bar.

**2. Unit tests only where logic is genuinely complex**

If you have functions that do real calculation work — cost estimation, schedule math, permission rules with multiple conditions — write focused unit tests for those. But don't unit test route handlers or DB queries in isolation; that's testing your mocks, not your code.

**3. Don't aim for 80% coverage — aim for 100% coverage of critical paths**

Reframe the goal: not "cover 80% of lines" but "every code path that processes money or changes billable project status has at least one integration test." That's a meaningful, achievable target.

**4. Skip E2E tests for now**

Playwright/Cypress tests are expensive to write and brittle to maintain. A 3-person team shouldn't be spending their 20% budget on them yet. One quarter from now, if you have solid API test coverage, revisit.

**5. Add a migration test check to CI**

The specific bug you shipped came from a migration. Consider a simple CI step: run migrations against a test DB, then run your integration test suite. This directly addresses the failure mode you experienced.

---

### On the tech lead disagreement

This is worth having explicitly. The tech lead's advice is not *wrong* — it's appropriate for a different context. The testing pyramid is well-suited for:
- Large teams where test speed matters at scale
- Systems with complex domain logic
- Codebases that already have some coverage and are maturing it

For a **3-person team starting from zero with integration-layer bugs and paying customers at risk**, the pyramid's advice to "write lots of unit tests first" optimizes for the wrong thing. You need tests that would have caught your actual bugs, fast.

The framing I'd bring to your tech lead: "The pyramid makes sense as a long-term steady-state. But given where we are and what just hurt us, let's start by protecting the critical paths with integration tests, then layer in unit tests for the complex logic as we go. We can revisit coverage targets once we have a baseline."

---

### Confidence levels

| Claim | Confidence |
|---|---|
| Integration tests would have caught the invoice bug | High — it's a DB-layer failure by description |
| CRUD-heavy Express apps get more ROI from integration tests | Medium-high — but depends on actual codebase |
| 80% coverage is the wrong target for this team right now | High |
| E2E tests should wait | Medium — could be wrong if frontend bugs are the real pain |
| The specific recommendations above are optimal | Medium — I haven't read their code; this is reasoned from context |

The part I'm least certain about: how much complex business logic they actually have. If a senior engineer walked their codebase and found rich domain objects with significant algorithmic complexity, that would shift the balance back toward unit tests. Worth asking your tech lead: "What specific functions are you imagining we'd unit test?"