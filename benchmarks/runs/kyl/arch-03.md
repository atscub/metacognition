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