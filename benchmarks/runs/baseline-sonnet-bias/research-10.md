Your bug is the most important data point here: a database migration silently broke invoice generation, and it took 4 hours to notice. That's not a unit-testing failure — unit tests mock the database and would have passed right through it. That bug would have been caught in the first minute by an integration test hitting a real database.

## The core disagreement

Your tech lead is drawing on advice that was more true 10 years ago. The testing pyramid was designed when integration tests required spinning up real servers and took minutes each — unit tests were the only practical fast feedback loop. With modern tooling (supertest for Express, a test Postgres database, Docker), API integration tests can run in milliseconds and are nearly as cheap to write.

The pyramid's guidance to "write mostly unit tests" made sense for systems where bugs live inside complex algorithmic logic. For a CRUD-heavy B2B SaaS, most of your bugs live at the boundaries: between your API and your database schema, between your ORM queries and your actual data model, between your business logic and your HTTP layer.

## My recommendation: integration tests first

**Start here — API integration tests with a real database:**

Use `supertest` to call your Express endpoints against a real test PostgreSQL database. The pattern is:
- Before each test (or suite): seed the required data
- Call the endpoint via supertest
- Assert on the HTTP response AND the resulting database state
- Use transactions that roll back after each test to keep things fast and isolated

The invoice bug would have looked like this as a test:
```js
it('generates invoice with correct line items after migration', async () => {
  await seedProject({ id: 'proj-1', ... })
  await seedLineItems([...])
  
  const res = await request(app)
    .post('/api/invoices/generate')
    .send({ projectId: 'proj-1' })
  
  expect(res.status).toBe(200)
  expect(res.body.lineItems).toHaveLength(3)
  expect(res.body.total).toBe(1250.00)
  
  // Also verify what landed in the DB
  const invoice = await db.invoices.findById(res.body.id)
  expect(invoice.status).toBe('draft')
})
```

That test would have caught the migration bug immediately.

**Where to focus first (not by coverage %, by business risk):**

1. Invoice generation and PDF export — you already know this hurts when broken
2. Payment processing flows — financial data, compliance risk, customer trust
3. Whatever your largest customers use most heavily
4. Any flow that runs on a schedule or background job (these fail silently)

**Add 3-4 E2E tests for your most critical user journeys:**

Playwright works well here. Not many — just the flows where a breakage would immediately cause a customer support crisis. Probably: create project → add team members → generate invoice → send. These are slow and occasionally flaky, but they catch the class of bug where your API works but your frontend doesn't wire it up correctly.

**Use unit tests selectively, not as the default:**

Unit tests genuinely help for:
- Complex pricing calculations, tax logic, date arithmetic
- Data transformation/normalization functions
- Any pure function with significant branching logic

They add little value for:
- Express route handlers (you're mostly testing supertest's mock)
- ORM queries (you're testing your mocks, not your database)
- React components that mostly render props

## Reject the 80% coverage goal

Coverage is a bad primary metric when starting from zero. It creates perverse incentives — you end up writing tests for simple getters and setters to hit the number while the risky invoice generation code has one happy-path test. 

A better heuristic: **no bug should occur twice without a test that would have caught it.** When you fix a bug, write the test that would have caught it before writing the fix. This builds coverage organically where it matters most.

## Practical sequencing for your 20% budget

**Weeks 1-2:** Set up the infrastructure. Test database, supertest wired up, CI running tests on every PR. This is the highest-leverage investment because it makes every future test cheap to write.

**Weeks 3-8:** Cover your 10 most critical API flows with integration tests. Invoice and payment flows first. Add 2-3 E2E tests.

**Ongoing rule:** New feature ships with integration tests for its endpoints. Bug fixed = test added. You don't need to go back and test everything — let the coverage grow forward from where you are.

After a quarter of this, you'll have much better coverage of what actually matters than you would from chasing 80% unit test coverage on a 60-endpoint backend.