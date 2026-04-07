Your tech lead is describing the standard testing pyramid, which is *useful advice for test design*. But your article is pointing at something more important: **where your bugs are actually coming from.**

Given your situation, I'd recommend **inverting your priorities** for the next quarter. Here's why:

## The Evidence You Already Have

You shipped a bug in invoice generation after a "seemingly unrelated database migration." That's a classic integration boundary failure—exactly the kind of bug that:
- ✗ Won't be caught by unit tests of individual functions
- ✓ *Will* be caught by an integration test that runs the full flow
- ✓ *Will* be caught by an integration test that validates the database schema after migrations

Unit tests assume "if all the pieces work in isolation, the system works." But in web apps, bugs cluster at the boundaries: API contracts, database schemas, request/response transformations, concurrent state, external API calls.

## How to Spend Your 20% Budget

**1. Integration tests for critical API flows (50% of effort)**
- The 5–10 endpoints that make money or prevent data loss: invoicing, payments, project/task creation, permission checks
- Run these against a real test database and real Express app
- Test *what the endpoint actually returns*, not just "the function ran"
- Test database migrations: run the migration on test data, then verify the old queries still work or are updated

Example:
```javascript
// This catches the invoice bug
test('POST /invoices generates correct totals after DB schema change', async () => {
  // Set up: create a project, tasks, costs in the test DB
  // Run the actual POST /invoices endpoint
  // Verify the response structure AND the values are correct
  // Run a migration, do the same thing again
})
```

**2. Critical end-to-end flows (20% of effort)**
- Just the 2–3 journeys that directly impact revenue or customer retention
- Invoice generation end-to-end (since you just had a bug)
- User signup → add to team → assign task → invoice
- These validate that your integration tests actually cover what matters

**3. Unit tests for complex business logic only (20% of effort)**
- Invoice calculation (if it's complex)
- Permission/role logic (if you have it)
- Validation rules
- *Skip* unit tests for simple utilities, API handlers, and data fetching

**4. Tests around migrations (10% of effort)**
- Write a small test harness: run migrations, verify queries still work
- This prevents repeating the invoice bug

## The Real Insight

"80% code coverage" sounds good in a metrics dashboard. But if you have 80% coverage of functions that don't fail, and 0% coverage of the invoice endpoint that broke production, the coverage number is useless.

Your invoice bug tells you that bugs live at **boundaries**: where the database schema changed, where the endpoint queries changed, where the frontend calls the API. Integration tests find those bugs. Unit tests find bugs inside functions.

**For a 3-person team with limited time:** Write enough unit tests to cover genuinely complex logic, then frontload integration tests for anything that touches the database or crosses a service boundary. Add a few E2E tests for your critical journeys.

The traditional pyramid is optimal for *large codebases with stable architecture*. You need something tighter—test what's actually fragile in your system.