Your tech lead's advice is theoretically sound but practically wrong for your specific situation. Here's why, and what to do instead.

## Why the pyramid is the wrong frame here

The testing pyramid made sense when popularized: it assumed unit-testable business logic isolated in pure functions, cheap tests at scale, and teams with time to build comprehensive suites. You have none of those conditions right now.

More importantly, **the bug you just shipped is diagnostic**. Invoice generation broke after a database migration — that's a failure at the boundary between your schema and your application layer. A unit test on the invoice calculation function would have passed. A test that hits a real endpoint against a real database would have caught it immediately.

That's not a coincidence. Most bugs in CRUD-heavy web apps like yours live at those boundaries: wrong SQL after a schema change, a missing JOIN, a serialization mismatch, an ORM behavior you didn't expect.

## What 80% unit coverage would actually get you

60 API endpoints, largely CRUD over PostgreSQL, means a lot of your code looks like:

```js
async function getInvoice(id) {
  return db.query('SELECT * FROM invoices WHERE id = $1', [id]);
}
```

You can unit test this with a mock database and get 80% coverage. Your tests will be green. Your database migration will still break invoice generation. Coverage is not the same as confidence.

## Where to put your 20% budget

**~60% of your testing budget: API integration tests**

Test your endpoints against a real PostgreSQL instance (use a test database, reset between test runs with `pg` transactions or a tool like `node-postgres` + `jest`). This directly addresses your failure mode. Start with your 10-12 most business-critical flows:

- Invoice creation, editing, sending, payment recording
- Any flow that touches money or customer-visible state
- Any endpoint that changed recently or breaks most visibly

A test like this catches your migration bug:

```js
it('returns invoice with correct total after line item changes', async () => {
  const invoice = await createTestInvoice({ lineItems: [...] });
  const res = await request(app).get(`/api/invoices/${invoice.id}`);
  expect(res.body.total).toBe(expectedTotal);
});
```

**~25% of your testing budget: 4-6 end-to-end tests**

Pick the flows where breakage causes the most customer pain and revenue risk. Invoice generation is your obvious first one. Use Playwright. You don't need many — you need the ones that would have paged you at 2am.

**~15% of your testing budget: unit tests for genuinely complex logic**

If you have pricing calculations, report generation, or date arithmetic that involves real business rules with edge cases — test those in isolation. They're worth it. Thin CRUD wrappers are not.

## Practical starting point for this week

Don't try to cover everything. Do this:

1. Set up a test database and a basic integration test harness (one day)
2. Write tests for invoice generation end-to-end through the API (one day)
3. Write tests for your 4-5 other highest-risk flows (rest of week)

You'll have more confidence than 80% unit coverage would give you, and you'll have it in a week instead of a quarter.

## One more thing your tech lead is missing

Tests aren't your only defense. Add Sentry or equivalent error monitoring to production **this week** — it's an afternoon of work. That's what cuts your "4 hours to notice" to "4 minutes to notice" regardless of your test coverage. Tests prevent regressions; monitoring detects incidents. You need both.

The article you read is right for your context. Your tech lead's advice is better suited to a team building a complex domain model with lots of pure business logic, not a 3-person team with a construction PM tool, 60 CRUD endpoints, and a recent integration-layer bug.