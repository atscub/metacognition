# Task: arch-03 — Monolith decomposition — choosing the first service to extract

## Prompt
You are leading the monolith decomposition effort at OrderlyCommerce, an e-commerce
platform. The CTO has approved extracting up to 2 services this quarter as a pilot.
You need to recommend which module to extract first.

Here is the simplified module dependency diagram:

```
┌─────────────────────────────────────────────────────┐
│                    MONOLITH                          │
│                                                     │
│  ┌──────────┐    ┌──────────┐    ┌──────────────┐  │
│  │ Billing  │───>│  Orders  │<───│   User Mgmt  │  │
│  │          │    │          │    │              │  │
│  └────┬─────┘    └────┬─────┘    └──────┬───────┘  │
│       │               │                 │          │
│       │  ┌────────────┴──────┐          │          │
│       └─>│  pricing_rules   │          │          │
│          │  (shared table)   │          │          │
│          └───────────────────┘          │          │
│                                         │          │
│  ┌───────────────┐              ┌──────┴───────┐  │
│  │ Notifications │              │ Session Store │  │
│  │ (email, SMS,  │              │ (Redis-backed │  │
│  │  push)        │              │  in-process)  │  │
│  └───────────────┘              └──────────────┘  │
│                                                     │
└─────────────────────────────────────────────────────┘
```

Module analysis:

**Billing Module**
- 14 internal API endpoints, all RESTful and well-documented
- Depends on: `pricing_rules` table (shared with Orders module — both read and write)
- Database tables: `invoices`, `payments`, `subscriptions`, `pricing_rules` (shared)
- Code coupling score (measured by static analysis): 0.23 (low)
- Test coverage: 87%
- Team: 2 dedicated engineers who are eager to own a microservice
- Recent changes: stable, ~3 PRs/month
```python
# billing/service.py — example of pricing_rules dependency
def calculate_invoice(order_id: str) -> Invoice:
    order = orders_module.get_order(order_id)  # direct function call
    rules = db.query("SELECT * FROM pricing_rules WHERE category = %s",
                      [order.category])
    discounts = [r for r in rules if r.type == 'discount' and r.active]
    # ... applies rules, calculates totals
```
```python
# orders/service.py — also uses pricing_rules
def validate_order(order: Order) -> ValidationResult:
    rules = db.query("SELECT * FROM pricing_rules WHERE category = %s",
                      [order.category])
    max_quantity = next(r.value for r in rules if r.type == 'max_qty')
    # ... validates order against pricing rules
```

**Notifications Module**
- 6 internal API endpoints
- Depends on: nothing (receives events, looks up templates in its own table)
- Database tables: `notification_templates`, `notification_log` (both owned exclusively)
- Code coupling score: 0.08 (very low)
- Test coverage: 72%
- Team: maintained by the platform team as a side responsibility
- Recent changes: very stable, ~1 PR/month
- Other modules call it via: `notifications.send(user_id, template, context)`

**User Management Module**
- 11 internal API endpoints, clean REST interface
- Depends on: Session Store (Redis, accessed via in-process client library)
- Database tables: `users`, `roles`, `permissions`, `user_preferences`
- Code coupling score: 0.31 (medium) — but mostly through session state
- Test coverage: 91%
- Team: 3 engineers, currently working on SSO integration
- Session coupling detail: the session store is an in-process Redis client shared across
  all modules. User Management reads/writes session data, but so do Orders (for cart
  state) and Billing (for payment flow state). Extracting User Management means the
  session store must become a shared service or be replicated.
```python
# user_mgmt/auth.py
from shared.session import session_store  # in-process Redis wrapper
def authenticate(request) -> User:
    session = session_store.get(request.cookies['session_id'])
    if not session:
        raise Unauthorized()
    return User.from_session(session)
```

The CTO's criteria (in priority order):
1. Low risk of production incidents during extraction
2. Demonstrable value to justify continued decomposition
3. Can be completed by 2 engineers in one quarter

Which module should be extracted first, and why? Provide a migration plan with specific
risk mitigations.


## Response A
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

## Response B
# Recommendation: Extract **Notifications Module** First

**Primary Recommendation: Notifications** (followed by Billing in Q2)

---

## Why Notifications Wins Against the CTO's Criteria

| Criterion | Notifications | Billing | User Mgmt |
|-----------|----------------|---------|-----------|
| **Risk of incidents** | Minimal (0.08 coupling, zero dependencies) | High (shared mutable `pricing_rules` table) | High (session store shared with 2+ modules) |
| **Can complete in 1Q** | ✓ (minimal coordination) | ✗ (requires table migration strategy) | ✗ (SSO in progress, session refactor needed) |
| **Demonstrable value** | ✓ (proven extraction process → enables Billing) | ✓✓ (higher business impact, but riskier) | ✗ (session store extraction blocks other teams) |

---

## Why NOT the Others (First)

**Billing Module:**
- The `pricing_rules` shared table is a **hard blocker**. Both Billing and Orders write to it. Extracting creates three choices—all risky:
  1. Duplication: Each service caches rules (inconsistency risk)
  2. API boundary: Create pricing service (adds latency, coordination overhead)  
  3. Leave table in monolith (defeats extraction benefit)
- You'd spend Q1 on architecture, not extraction.

**User Management Module:**
- Session store coupling is worse than pricing_rules—it's **runtime state** used by multiple modules simultaneously
- Your team is mid-SSO integration (moving target)
- Extracting forces premature session refactoring while they're building

---

## Notifications Migration Plan (Low Risk)

### Phase 1: Strangler (Weeks 1–2)
1. Create `notifications-service` repo (microservice scaffold)
2. Copy tables: `notification_templates`, `notification_log` (PostgreSQL migration)
3. Deploy service to staging, no traffic yet

### Phase 2: Canary (Weeks 3–4)
```python
# In monolith, add feature flag:
if flags.use_notifications_service:
    notifications_client.send(user_id, template, context)
else:
    notifications_module.send(user_id, template, context)  # old code

# Route 10% of sends to service, compare results (should be identical)
```

### Phase 3: Cutover (Week 5)
- Flip flag to 100%, monitor logs for failures (should be zero—stateless logic)
- Keep old code in monolith for 1 sprint (quick rollback if needed)
- Remove old code in Week 6

### Risk Mitigations
| Risk | Mitigation |
|------|-----------|
| Service unavailable | Dead-letter failed sends to queue, retry async. Old code stays as fallback. |
| Data inconsistency | Tables are read-only after copy; no sync issues. |
| Slow to launch | Service is tiny—single Docker image, no dependencies |
| Team ownership unclear | Platform team keeps it (it's a utility) but ops-friendly design means others can patch |

---

## Post-Notifications: Billing Extraction Plan (Q2)

Once Notifications proves extraction is safe, tackle Billing with this refactor:

**Step 1: Decouple pricing_rules via API**
```python
# In monolith: create new internal API
POST /internal/pricing-rules/query
{
  "category": "electronics",
  "type": "discount"  # optional filter
}
# Returns rules + hash for client-side caching

# Both Billing and Orders call this API instead of direct DB queries
```

**Step 2: Move pricing service boundaries**
- `pricing_rules` table stays in monolith (shared)
- Billing queries it via API boundary (clear contract)
- Extract Billing logic; it calls pricing API
- Orders stays in monolith but also uses pricing API (future-proofs)

**Step 3: Run Billing on extracted schema**
- Copy `invoices`, `payments`, `subscriptions` to new DB
- Pricing reads hit monolith API (low latency, same datacenter)
- Once stable, consider promoting pricing rules to shared service

---

## Expected Outcomes

| By End of Q1 | By End of Q2 |
|--------------|-------------|
| Notifications running as service | Billing extracted and autonomous |
| Proven: infra, CI/CD, observability work | 2 services running; API boundaries established |
| Team confidence up | Can extract 3rd service with confidence (User Mgmt in Q3 after SSO work) |

---

**Bottom line:** Notifications is your proof-of-concept. It's fast, safe, and buys you architectural credibility to tackle Billing's shared-state problem head-on. The CTO gets low-risk success in Q1 and a roadmap for continued decomposition.

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
