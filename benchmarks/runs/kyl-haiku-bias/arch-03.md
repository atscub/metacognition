## Premortem Results: Service Extraction Decision

Let me work through what each extraction looks like when it fails.

---

### SCENARIO 1: Billing Service Extraction Failed

**What broke:**
- `pricing_rules` table is now a shared data layer between two independent services with no sync mechanism
- Orders and Billing both read AND write `pricing_rules` → inconsistencies emerge within days
  - Orders team updates a rule for "bulk discounts"
  - Billing service still has the old rule cached → invoices calculated incorrectly
  - Customers charged under two different pricing regimes depending on which service processed their order
- Circular dependency emerged: Billing needs Orders API to fetch order data; Orders needs Billing API for pricing validation
- Migration took 4 months instead of 3; pricing_rules data wasn't cleanly migrated (duplicates, orphans)
- Rollback impossible without data reconciliation work

**What we missed:**
- The coupling score (0.23) looked low, but it's LOW-LATENCY shared state. Extracting code is different from extracting shared data.
- The fact that BOTH modules write to `pricing_rules` makes this fundamentally harder than a read-only dependency
- No clear source of truth: which service owns the pricing data? Both?

**Key risk**: **Shared mutable state in a decomposed system is extremely hard to manage.** This is not a "low risk" extraction.

---

### SCENARIO 2: Notifications Service Extraction Failed

**What broke:**
- Switching from in-process calls to HTTP calls introduced latency and silent failures
  - `notifications.send()` now returns eventually; errors don't bubble up to Orders/Billing flows
  - Customer gets confirmation email 3 hours late (or never)
  - No one noticed for a week because there was no monitoring
- The service has no auth; someone reverse-engineered the endpoint and sent spam
- "72% coverage" was all unit tests — integration tests discovered the templates table has foreign key issues
- The platform team (side responsibility) had no on-call support — bugs sat in production for days
- Platform team burned out; service maintenance became a blocker for other work

**What we missed:**
- "Low coupling" in a monolith ≠ "ready to be a microservice"
- 72% coverage was insufficient; the tests didn't validate the contract (template lookup, error handling)
- No operational ownership plan

**Key risk**: **Extraction without operational readiness is riskier than high coupling.** A poorly-run service is worse than no service.

---

### SCENARIO 3: User Management Extraction Failed

**What broke:**
- Session state became distributed. User Mgmt, Orders, and Billing all write to the same Redis instance
- Extraction forced a choice: replicate the session store (eventual consistency nightmare) or make it a separate service (single point of failure)
- Race conditions: User Mgmt writes session; Orders writes cart state to same session → session gets corrupted
- User Mgmt service restarts → whole platform can't authenticate users
- SSO integration work (which the team was already doing) got blocked because session management is now split
- Extraction took 5 months instead of 3; the "medium coupling" was actually severe

**What we missed:**
- 0.31 coupling is actually HIGHER than Billing (0.23), and it's through infrastructure (session store), not business logic
- Sessions are the most critical shared state in an e-commerce system
- The team is already overcommitted (SSO work); they don't have capacity for extraction + operational ownership

**Key risk**: **Extracting a service that owns critical infrastructure creates a single point of failure.** This violates criterion 1 immediately.

---

## Risk Assessment Matrix

| Scenario | Likelihood | Impact | Reversibility | Blockers |
|----------|-----------|--------|---------------|----------|
| **Billing**: shared data write conflicts | High | Critical | Hard (data reconciliation) | ❌ Violates criterion 1 & 3 |
| **Notifications**: silent failures + poor ops | Med | High | Hard (now source of record) | ❌ Violates criterion 1 |
| **User Mgmt**: distributed session state | High | Critical | Impossible | ❌ Violates criterion 1, 2, & 3 |

---

## Unverified Assumptions to Check Now

Before I recommend, I need to verify three things:

1. **Billing's pricing_rules**: Are both modules actively WRITING to it, or is one mostly reading?
2. **Notifications' operational readiness**: Does the platform team actually have on-call capacity? Are there production incidents we could look up?
3. **User Mgmt's session architecture**: Is the session store truly shared with write access from all modules, or is it mostly User Mgmt-owned with reads from others?

**These answers change the recommendation significantly.** Billing might be safer if Orders only reads pricing_rules. Notifications might be viable if ops is stronger than described. User Mgmt is almost certainly unsafe regardless.

---

## My Recommendation

**Extract the Notifications Service first** — with mandatory mitigations.

**Why:** It's the only extraction that doesn't create a new distributed state problem or violate the "low production risk" criterion. BUT this only works if you solve the operational risk.

**Critical condition**: This recommendation requires the platform team to get **actual on-call coverage and monitoring** before go-live. Without that, you're trading code extraction for operational chaos.

### Phased Migration Plan for Notifications

#### Phase 1: Pre-extraction (Weeks 1-2)
```
[ ] Add Datadog monitoring/alerting for notification failures
[ ] Set up PagerDuty rotation for platform team (or assign to a team with on-call)
[ ] Run integration tests against all callers (Orders, User Mgmt, Billing)
[ ] Verify all notification templates are in the DB (no hardcoded paths)
[ ] Add request logging to catch the async-failure problem early
```

#### Phase 2: Extraction (Weeks 3-8)
```
[ ] Extract `notifications/` module to separate service
[ ] Convert in-process calls to HTTP (internal gRPC better than REST for latency)
[ ] Add circuit breaker in callers: if notifications is down, log but don't fail the order flow
[ ] Implement request signing (basic secret-key auth)
```

#### Phase 3: Cutover (Weeks 9-12)
```
[ ] Dark-launch notifications service (dual-write): both in-process and service get called
[ ] Monitor for divergence (they should produce identical results)
[ ] Flip traffic entirely; keep in-process as fallback for 1 week
[ ] Rollback plan: revert to in-process calls if error rate >1%
```

#### Monitoring gates
- Error rate < 0.1% (notification failures)
- P99 latency < 500ms (acceptable async delay)
- No silent failures (every error is logged and alerted)

---

## Why NOT the Others (Given Current Information)

**Billing**: Don't extract first.
- The `pricing_rules` shared write creates a data consistency problem you'll spend 3 months solving
- You'd be out of budget for the pilot
- Better as the **second** extraction, after you've built experience + tools for shared state migration

**User Management**: Don't extract.
- Session state coupling is too severe
- This requires a multi-quarter effort (extract User Mgmt + rebuild session infrastructure)
- The team is already context-switching (SSO work)
- Violates all three CTO criteria

---

## What Could Still Go Wrong With Notifications (And How to Mitigate)

| Risk | Mitigation |
|------|-----------|
| Silent notification failures break UX | Circuit breaker in callers; fallback to async queue if service down |
| Platform team has no capacity | Get explicit commitment from engineering leadership or assign to another team with on-call |
| Template data becomes inconsistent | Schema validation + integration tests; templates are immutable after deploy |
| HTTP latency breaks the UX flow | Use gRPC or event queue instead; don't block the order flow on notification delivery |

---

**Next step**: Verify the assumptions about Billing and User Mgmt coupling. If you can confirm that Billing's writes to `pricing_rules` are rare or read-heavy in practice, Billing might actually be the safer first extraction instead.