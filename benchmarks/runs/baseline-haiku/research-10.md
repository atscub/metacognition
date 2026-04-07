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