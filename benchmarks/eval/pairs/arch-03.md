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
## Recommendation: Extract Notifications First, Billing Second

### Why Not User Management

Rule this out immediately. The in-process Redis session store is shared by all three modules — extracting User Management forces a concurrent infrastructure change (externalizing the session store) while Orders and Billing are still coupled to it. The active SSO integration compounds the risk. This violates criterion #1 decisively.

### Notifications vs. Billing: The Core Trade-off

| Factor | Notifications | Billing |
|--------|--------------|---------|
| Coupling score | 0.08 (textbook clean) | 0.23 (low, but has a blocker) |
| Shared data | None | `pricing_rules` (shared read+write with Orders) |
| Call interface | Event-style `send()` — easy to swap | Direct `orders_module.get_order()` call must become HTTP |
| Test coverage | 72% | 87% |
| Dedicated team | No | Yes (2 eager engineers) |
| Failure blast radius | Missed notification | Incorrect invoice / failed payment |

**Extract Notifications first.** The shared `pricing_rules` table in Billing is a genuine blocker — both modules read *and write* it, meaning you cannot cleanly assign ownership without either (a) splitting the service boundary mid-table or (b) adding an API hop into the Orders validation path before Billing is even extracted. That's two simultaneous changes in a revenue-critical path. Save Billing for Q2 once the pattern is proven.

---

## Why Notifications Satisfies All Three Criteria

**1. Low incident risk**
- Zero shared tables, zero shared in-process state
- Callers already use a single, narrow interface: `notifications.send(user_id, template, context)` — this is trivially swappable
- Failures are non-transactional: a missed email doesn't roll back a payment

**2. Demonstrable value**
The pilot's real deliverable isn't "we moved a module" — it's "we proved the org can operate a microservice safely." Notifications lets you validate the full operational stack: separate deploy pipeline, service mesh config, structured logging, alerting, on-call runbook. When you extract Billing next quarter, you're not learning all of that under revenue pressure.

**3. Completable by 2 engineers in one quarter**
Realistically 6–8 weeks of part-time work given the platform team's existing ownership.

---

## Migration Plan

### Phase 0: Pre-extraction (Weeks 1–2)
**Harden the boundary before touching infrastructure.**

```python
# Replace direct calls with an interface abstraction NOW, before any deployment change
# This lets you swap implementations without changing callers

# Before: scattered direct calls
from notifications import send_email, send_sms

# After: single facade (still in-process, just abstracted)
from shared.notifications_client import NotificationsClient
notifications = NotificationsClient()
notifications.send(user_id, "order_confirmed", {"order_id": order.id})
```

- Audit all 6 endpoints — identify any hidden callers beyond `send()` using static analysis
- Raise test coverage from 72% to ≥80% for the notification dispatch paths (the risk surface)
- Define the service contract: what does `send()` guarantee on failure? (async vs. sync, retry semantics)

**Risk mitigation:** If you find undocumented call sites, you've discovered your real coupling before changing a single deployment.

### Phase 1: Parallel Deployment (Weeks 3–5)
**Run new service alongside monolith with no traffic yet.**

```
┌─────────────────────┐      ┌────────────────────┐
│      MONOLITH       │      │  Notifications Svc  │
│                     │      │                     │
│  NotificationsClient│      │  POST /send         │
│  [feature flag OFF] │      │  GET /templates/:id │
│                     │      │  GET /log/:user_id  │
└─────────────────────┘      └────────────────────┘
```

- Deploy Notifications as an HTTP service with its own database (migrate `notification_templates` and `notification_log` tables — these are exclusively owned, so this is a clean copy-then-cutover)
- Implement `NotificationsClient` to support both modes: `use_service=False` calls in-process code, `use_service=True` calls the HTTP service
- No traffic goes to the new service yet

**Risk mitigation:** Production incidents are impossible at this phase — the flag is off.

### Phase 2: Shadow Mode (Week 6)
**Dual-write with monolith as source of truth.**

```python
class NotificationsClient:
    def send(self, user_id, template, context):
        # Always execute via monolith path
        result = self._send_in_process(user_id, template, context)
        
        # Also fire to new service — errors are swallowed, logged only
        try:
            self._send_http(user_id, template, context)
        except Exception as e:
            metrics.increment("notifications_service.shadow_error")
            logger.warning("shadow_mode_divergence", error=e)
        
        return result
```

- Compare delivery rates, latency, and error rates between paths
- Alert on any divergence in `notification_log` between the two systems
- Target: zero divergence for 72 hours before proceeding

**Risk mitigation:** Users never see the new service's failures. You get production validation for free.

### Phase 3: Cutover (Week 7)
**Flip the flag; monolith path becomes the fallback.**

- Enable `use_service=True` via feature flag, 10% → 50% → 100% over 48 hours
- Keep in-process path alive as circuit-breaker fallback for 2 weeks
- Define rollback trigger: if error rate on new service exceeds 0.5% over a 5-minute window, auto-revert flag

### Phase 4: Decommission (Week 8)
- Remove in-process notification code from monolith after 2 weeks of clean operation
- Archive the feature flag

---

## Setting Up Billing for Q2

Use the time Notifications buys you to resolve the `pricing_rules` blocker cleanly:

**Decision to make now:** Assign `pricing_rules` ownership to Billing. Orders should be a consumer, not a co-owner.

```python
# Q2 prep: Orders stops writing to pricing_rules directly
# Instead calls Billing's API:

# orders/service.py — replace the direct DB query
def validate_order(order: Order) -> ValidationResult:
    # Before: db.query("SELECT * FROM pricing_rules ...")
    # After:
    rules = billing_client.get_pricing_rules(category=order.category)
    max_quantity = next(r["value"] for r in rules if r["type"] == "max_qty")
```

This API-first change can ship in the monolith during Q1 — no service extraction required — so when you extract Billing in Q2, the cross-module call pattern is already battle-tested.

---

## Summary

```
Q1: Notifications
  ✓ Zero shared state → near-zero incident risk
  ✓ Proves operational pattern (CI/CD, monitoring, on-call)
  ✓ Comfortable for part-time platform team ownership

Q1 (parallel prep): Pricing rules ownership clarified, Orders → Billing API call added in-monolith

Q2: Billing
  ✓ pricing_rules blocker already resolved
  ✓ Dedicated eager team
  ✓ High test coverage + stable codebase
  ✓ Revenue-critical = highest business impact
```

The sequencing principle: extract the cleanest module first to learn, then extract the most valuable module second with confidence.

## Response B
## Premortem: OrderlyCommerce Module Extraction Decision

---

### Step 1: State the Plan

**What we're deciding:** Extract one of three modules (Billing, Notifications, User Management) as a pilot microservice.

**Success looks like:** Module running independently in production, no regressions, no production incidents, completed by 2 engineers in one quarter, and demonstrates enough value to justify the second extraction.

**Key assumptions being made:**
- Coupling scores capture the real coupling (not just code-level)
- Module boundaries are as clean as described
- Infrastructure for running services exists (container runtime, service discovery, observability)
- One quarter = ~13 weeks of actual engineering time

---

### Step 2: Imagine Each Option Failed — Work Backwards

#### If we extracted **Billing** and it failed:

**The `pricing_rules` table is a distributed data timebomb.**

Both Billing and Orders read *and* write `pricing_rules`. The moment Billing becomes a separate service, you face an inescapable trilemma:

- **Option A:** Billing owns `pricing_rules` → Orders must call Billing for validation during `validate_order()`. You've created a runtime dependency where none existed architecturally. A Billing outage now blocks order validation.
- **Option B:** Orders owns `pricing_rules` → Billing must call Orders for every invoice calculation. Circular dependency risk, and you've made Billing slower and less reliable.
- **Option C:** Extract `pricing_rules` into a third shared service → You've exceeded your 2-service budget before the pilot is done.

The coupling score of **0.23 is misleading.** Static analysis counts code coupling, not data coupling. Two services writing to the same table is *more dangerous* than a function call because you lose transactional guarantees without realizing it. The code sample makes it explicit:

```python
# billing/service.py
rules = db.query("SELECT * FROM pricing_rules WHERE category = %s", ...)

# orders/service.py — same table, same rows
rules = db.query("SELECT * FROM pricing_rules WHERE category = %s", ...)
```

This isn't low coupling — it's hidden coupling. The static analysis tool didn't see it because it lives in SQL strings.

**Additionally:** `orders_module.get_order(order_id)` is a direct in-process call. Converting it to an HTTP call introduces latency, failure modes, and potentially distributed transaction requirements for the billing flow. Payment flows are not the place to learn these lessons.

**Verdict on Billing failure modes:**
- Shared table → impossible to extract cleanly without resolving ownership first
- Direct function call to Orders → payment flow now has network failure modes
- 2 engineers cannot solve the data ownership problem AND do the extraction in one quarter

---

#### If we extracted **User Management** and it failed:

**Session Store externalization is a hidden prerequisite that touches every module.**

The failure mode here is subtle but severe. The problem isn't extracting User Management — it's what has to happen first:

```python
# user_mgmt/auth.py
from shared.session import session_store  # in-process Redis wrapper
```

This isn't User Management's session store. It's *the entire monolith's* session store. Orders uses it for cart state. Billing uses it for payment flow state. The moment User Management becomes a separate process, `shared.session` can no longer be in-process for the remaining monolith. You must:

1. Externalize the Redis client to a network service
2. Refactor Orders to use the network session store (not User Mgmt)
3. Refactor Billing to use the network session store (not User Mgmt)
4. Coordinate all of this across teams simultaneously

That's not extracting one module. That's a platform-level infrastructure migration that touches every module. You've turned a pilot into a company-wide initiative.

**Additionally:** Authentication is on the critical path for *every user request*. A degraded User Management microservice is not a partial outage — it's a full site outage. This is the highest-risk place to learn microservice operational patterns.

**Additionally:** SSO integration is actively in-flight. The interface contract is unstable during development. You'd be extracting a moving target.

**Verdict on User Management failure modes:**
- Session store is a shared monolith resource, not a User Mgmt resource — extraction requires refactoring all modules
- Auth on critical path = blast radius is entire site
- Active SSO work = unstable contract during extraction

---

#### If we extracted **Notifications** and it failed:

**The failure modes are real but bounded.**

- **72% test coverage:** The weakest coverage of the three. Missing 28% could mean undiscovered edge cases in email/SMS delivery paths.
- **No dedicated team:** Platform team owns it as a side responsibility. Post-extraction, on-call ownership is ambiguous.
- **Async delivery semantics change:** The current call is synchronous in-process (`notifications.send(...)`). Moving to async (event queue) means callers no longer get delivery confirmation — failures become silent if not designed carefully.
- **Demonstrable value is unclear:** Does extracting Notifications move a business metric? On its face, it solves no product problem — it just moves bytes across a network boundary.

**But notice what's *absent* from this failure list:**
- No shared tables
- No shared in-process infrastructure
- No bidirectional dependencies
- No critical path for user-facing requests (a notification failure is recoverable; a payment or auth failure is not)
- No active development making the interface unstable

---

### Step 3: Risk Assessment

| Risk | Module | Likelihood | Impact | Reversibility |
|------|--------|-----------|--------|---------------|
| `pricing_rules` shared write creates distributed data corruption | Billing | **High** | **High** | Hard — data is already split |
| In-process Orders call becomes network call with payment transaction risk | Billing | Certain | Medium | Medium |
| Session store externalization requires refactoring every module | User Mgmt | **High** | **High** | Hard — multi-team coordination |
| Auth degradation = sitewide outage | User Mgmt | Medium | **High** | Impossible mid-incident |
| SSO in-flight makes contract unstable | User Mgmt | High | Medium | Hard |
| Silent notification delivery failures (async transition) | Notifications | Medium | Medium | Easy — add dead-letter queue + alerting |
| Ambiguous on-call ownership post-extraction | Notifications | Low | Medium | Easy — assign owner |
| Low demonstrable business value | Notifications | **High** | Low | N/A — reframe the value proposition |

**Must-mitigate before proceeding (High likelihood + High impact):**
- Billing's `pricing_rules` data coupling
- User Management's session store prerequisite

**Accept with detection:**
- Notifications' async delivery semantics → mitigate with dead-letter queues and delivery metrics

---

### Step 4: Mitigations for the Chosen Path

**Recommendation: Extract Notifications first.**

The "demonstrable value" concern is real but resolvable with a reframe. The value is not product features — it is *organizational capability*. The pilot teaches:

- How to run a service in production (deployment pipeline, rollbacks, health checks)
- How to instrument a service (distributed tracing, alerting, SLOs)
- How to handle async messaging reliability (at-least-once delivery, idempotency, dead-letter queues)
- How incident response works across a service boundary

That organizational learning is what the CTO actually needs before authorizing 10 more service extractions. Notifications is the right place to learn those lessons because the blast radius when something goes wrong is a delayed email — not a failed payment or a locked-out user.

---

### Migration Plan

**Phase 1: Prerequisite (Weeks 1–2)**

- Assign explicit on-call ownership to one engineer (from platform team or borrow from another team)
- Write integration tests that exercise the full `send()` path end-to-end (bring coverage to ≥85%)
- Instrument the existing in-process calls with metrics: call volume, latency, failure rate — this becomes your baseline for the new service

**Phase 2: Extract and Run in Parallel (Weeks 3–7)**

- Stand up Notifications as a separate process behind its own deployment pipeline
- Keep the in-process call path active; add a feature flag to route a small percentage of calls to the new service
- Introduce an async event queue (e.g., RabbitMQ or Redis Streams) with:
  - At-least-once delivery semantics
  - Dead-letter queue for failed deliveries
  - Alerting on DLQ depth and delivery latency
- The monolith retains its `notifications.send()` interface — callers don't change. The implementation behind it either calls in-process or publishes an event, controlled by the flag.

**Phase 3: Cutover (Weeks 8–10)**

- Route 100% of traffic through the new service
- Monitor against baseline metrics for one full week
- Disable the in-process code path (keep it dead-coded for one sprint as a rollback option, then delete)

**Phase 4: Validate and Document (Weeks 11–13)**

- Write a postmortem-style document of what was learned: what was harder than expected, what the runbook looks like, what monitoring is in place
- This document drives the pitch for the second extraction

---

### On the Second Extraction

**Do not attempt Billing next without first resolving `pricing_rules` ownership.**

The prerequisite work before extracting Billing is:
1. Decide ownership: Billing owns `pricing_rules`, Orders reads via Billing's API (preferred — Billing is the domain that understands pricing semantics)
2. Migrate Orders to read pricing rules via an API call to Billing (this can happen *before* Billing is extracted — it's just refactoring the monolith's internal call to go through a defined interface)
3. Once Orders has no direct table access to `pricing_rules`, the data coupling is resolved and Billing can be extracted cleanly

This prerequisite can be done in parallel during the Notifications extraction quarter, so Q2 starts from a clean position.

---

### Decision

**Extract Notifications first.** It is the only candidate where:

1. No shared data — both tables are exclusively owned
2. No bidirectional dependencies — all communication is one-directional (modules call it, it calls nothing)
3. Failures are recoverable — a slow or unavailable notification service is degraded UX, not a production incident
4. Scope is bounded — 2 engineers can finish it in one quarter without surprises lurking in the data layer
5. The pilot proves the process — which is what the CTO actually approved, not just a line item moved to a new server

The strongest counterargument is "demonstrable value is low." The correct response to the CTO is: *"The value of the pilot is proving we can extract and operate a service safely. Notifications is the right place to prove that because the cost of being wrong is a delayed email, not a payment failure. We'll use this quarter to build the operational foundation that makes the Billing extraction in Q2 safe."*

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
