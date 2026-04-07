## Premortem Results: Module Extraction Failure

**Scenario: End of Q2. The extraction is live but production is broken. What went wrong?**

---

### Top Failure Modes (High → Medium Risk)

| Risk | Likelihood | Impact | Reversibility |
|------|-----------|--------|---------------|
| **Billing: Shared `pricing_rules` table becomes a consistency bottleneck** | High | High | Hard |
| **Billing: Direct function calls can't become distributed RPCs without adding timeout/retry logic that causes new bugs** | High | Med | Hard |
| **User Mgmt: Session store remains in-process, not truly extracted; or replication causes auth failures** | High | High | Hard |
| **Any module: No data migration strategy; cutover causes data loss or duplication** | Med | High | Hard |
| **Notifications: Platform team can't operate a microservice alongside monolith work** | Med | High | Easy (can revert) |
| **Any module: Test coverage doesn't translate; old tests break on service boundaries** | Med | Med | Med |

---

### What We're Assuming (Should Verify Now)

1. **The static analysis coupling score (0.23 for Billing) captures *transactional* coupling** — it might measure code imports, but pricing_rules requires atomic reads/writes across both modules. ✋ **This is NOT just a code coupling problem; it's a data consistency problem.**

2. **The team has operating experience for microservices** — no mention of observability, alerting, on-call procedures, distributed tracing. Extracting Billing to a service means they now own a separate deployment, health checks, and failure scenarios they've never handled.

3. **The "very stable" modules (Notifications) will remain stable post-extraction** — stability measured within the monolith might be stability with synchronous, in-process error handling. As a service, async semantics change behavior.

4. **Session state in User Mgmt is truly the only thing blocking a clean extraction** — but it's used by *three* modules (User Mgmt, Orders, Billing). Any session state replication across services is a distributed consensus problem.

---

### Critical Realization

**The CTO's criteria are incomplete:**
- ✓ "Low risk of production incidents"
- ✓ "Demonstrable value"
- ✓ "2 engineers, one quarter"
- ✗ **Migration strategy (zero-downtime? dual-write? strangler pattern?)**
- ✗ **Service observability (who operates this? on-call model?)**
- ✗ **Data consistency guarantees during and after extraction**

Without these, even the "safest" module becomes risky.

---

## Recommendation: **Extract Notifications First**

### Why NOT Billing

- **Shared pricing_rules table is a hidden mine.** Both Billing and Orders read *and* write. During extraction, you need to:
  - Convert direct function calls to RPCs (adds latency, timeout handling, circuit breakers)
  - Handle pricing_rules consistency without distributed transactions
  - Dual-write during migration, then cut over (consistency window = risk window)
  
  This is 2 weeks of work minimum, not accounted for in "one quarter for 2 engineers."

- **Direct function calls are deceptively coupled.** The code shows `orders_module.get_order()` — this works now because they're in the same process. Converting to HTTP calls requires:
  - Defining a versioned API contract
  - Timeout and retry policies
  - Handling Orders service failures (billing can't proceed)
  
  The "0.23 low coupling score" doesn't reflect this.

### Why NOT User Management

- **Session state is a fundamental bottleneck.** Redis is accessed by User Mgmt, Orders (cart), and Billing (payment flow). You can't extract User Mgmt without solving session state across services. Options:
  - Keep shared Redis (not extraction, just code split)
  - Replicate session data (consistency problems)
  - Route all sessions through User Mgmt service (new dependency chain, latency)
  
  This makes the extraction 30% harder, minimum.

- **SSO integration is in flight.** The team context-switches between SSO and extraction = both slow down. If one fails, the other is blamed.

### Why Notifications

**Minimal coupling:**
- 0.08 coupling score (half of Billing, quarter of User Mgmt)
- No shared data; owns its own tables completely
- Receives events via function call: `notifications.send(user_id, template, context)`
- No transactional dependencies
- Simple → easier to test, operate, monitor

**Controlled risk:**
- If it fails, you revert (no shared state = clean rollback)
- If it succeeds, you prove the extraction model works
- No cascading failures to Orders or Billing

**BUT with one major caveat:** The platform team maintains it "as a side responsibility." Extracting it means the team owns a real microservice. **This is the real risk — operational readiness, not code complexity.**

---

## Migration Plan for Notifications

### Phase 1: Preparation (Weeks 1-2)

1. **Define the service contract:**
   - Input: `POST /notify` with `{user_id, template_id, context, channel}`
   - Output: `{notification_id, status, delivery_timestamp}`
   - Document template precedence, retry behavior

2. **Create the baseline:**
   - Copy `notification_templates` and `notification_log` to new service DB
   - Write data sync script to verify consistency

3. **Stub the monolith:**
   - Change `notifications.send()` to a thin wrapper that calls the service
   - Add fallback: if service is down, log to queue and retry later
   - Zero production traffic yet

### Phase 2: Extraction (Weeks 3-6)

4. **Build the service:**
   - Standard REST service: template lookup, logging, event publishing
   - Health check endpoint
   - Single database (PostgreSQL, same as monolith initially)

5. **Add observability:**
   - Structured logging (JSON, correlationId)
   - Prometheus metrics: `notifications_sent_total`, `notification_latency`, `delivery_failures`
   - Error alerting to Slack

6. **Test in shadow mode:**
   - Notifications service processes real requests
   - Monolith also processes (dual-write, for now)
   - Compare results; log mismatches
   - Run for 1 week with zero production impact

### Phase 3: Cutover (Weeks 7-8)

7. **Gradual traffic shift:**
   - Week 1: 10% of notifications → service; 90% → monolith
   - Monitor error rates, latency
   - Week 2: 100% to service

8. **Cleanup:**
   - Remove notification code from monolith
   - Archive shadow-mode logs
   - Document runbook (deployment, incidents, scaling)

### Phase 4: Validation (Weeks 9-12)

9. **Platform team training:**
   - Incident response (service is down, customer notifications delayed)
   - On-call rotation
   - Deployment process

10. **Demonstrate value:**
    - Faster iteration: service deploys independently from Orders/Billing
    - Scaling: can scale Notifications separately during email-heavy campaigns
    - Team ownership: platform team grows from "side of desk" to owning a real service

---

## Risk Mitigations

| Risk | Mitigation |
|------|-----------|
| **Service is down, notifications don't send** | Queue in monolith; retry later. Notifications can delay but shouldn't be lost. |
| **Database gets out of sync** | Checksums on template_log table, daily verification query. Alert if mismatch. |
| **Platform team can't operate it** | Budget weeks 11-12 for runbook, incident simulations, on-call training. Don't skip. |
| **"Low" test coverage (72%) means edge cases** | Before extracting, add tests for: invalid templates, SMS validation, retry logic, rate limiting. Get to 85%+ before cutover. |
| **Dependency on template lookup performance** | Service should cache templates (5-minute TTL); monolith invalidates cache on template change. Monitor cache hit rate. |

---

## Decision

**Proceed with Notifications extraction.** It's the lowest-risk pilot that proves the extraction model works without adding operational burden or hidden data consistency problems. Success here justifies extracting Billing later (which requires a data migration strategy) and User Management last (which requires solving session state).

**Explicit acceptance:** The team needs operational training. Don't skip weeks 11-12. This is a quarter of work to do it right.