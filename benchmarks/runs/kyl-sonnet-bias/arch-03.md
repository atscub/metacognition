## Premortem: Monolith First Extraction Decision

---

### Step 1: The Plan

**Decision**: Choose one of three modules to extract as a microservice pilot.

**Success looks like**: A running, independently deployable service by end of quarter, with zero production incidents during extraction, that makes a compelling case to the CTO for continued decomposition.

**Key assumptions baked in**:
- Coupling scores are accurate proxies for extraction difficulty
- "Low coupling" means "easy extraction"
- Shared infrastructure (DB tables, session store) can be addressed during extraction
- A team's enthusiasm is a sufficient proxy for execution capacity

---

### Step 2: Imagine Each Option Has Failed

#### If we chose Billing — it's Q+1 and we're in a war room

**What broke**: The `pricing_rules` table. Both `billing/service.py` and `orders/service.py` write to it. When we extracted Billing, we had to make a call: leave the table in the monolith DB (so Billing reaches back in via API — we just moved the coupling, not eliminated it), or split it (now we have two services maintaining pricing rule consistency across a network boundary). We picked split. During a flash sale, Orders applied a stale discount rule while Billing used the updated one. Invoices were issued at the wrong price. Finance is doing manual reconciliation.

**What we ignored**: The coupling score of 0.23 measured *code* coupling, but the critical coupling was *data* coupling — a shared table with dual write access. These are different things. The code was clean; the data boundary was a landmine.

**Other failure modes**:

| Risk | Likelihood | Impact | Reversibility |
|------|-----------|--------|---------------|
| `pricing_rules` dual-write inconsistency causes wrong invoices | **High** | **Critical** | Hard |
| `orders_module.get_order()` in-process call becomes network call, introduces timeouts/failures | High | High | Medium |
| pricing_rules ownership debate consumes the quarter | High | High | Easy |
| Financial incident during DB cutover | Medium | **Catastrophic** | Impossible |

Billing is **disqualified**. The `pricing_rules` problem is not a risk to mitigate — it's a pre-existing architectural entanglement that makes this a two-module problem disguised as one. You can't cleanly extract Billing without first resolving data ownership, which is itself a quarter of work.

---

#### If we chose User Management — it's Q+1 and nothing shipped

**What broke**: Scope explosion. The session store is an in-process Redis wrapper shared by three modules:

```python
from shared.session import session_store  # used by User Mgmt, Orders (cart), Billing (payment flow)
```

Extracting User Management means auth becomes a network call. But Orders still needs cart session state, and Billing still needs payment flow state. The session store can't stay in-process when User Management is remote. So now we're refactoring three modules, not one. The "2 engineers, one quarter" budget is gone by week 4.

**What we ignored**: The 3 engineers were mid-SSO integration when we started. We were refactoring the auth layer while they were building on top of it. Merge conflicts, unclear ownership, two sprints of rework.

| Risk | Likelihood | Impact | Reversibility |
|------|-----------|--------|---------------|
| Session store forces 3-module refactor | **High** | High | Hard |
| SSO work + extraction = merge collision, doubled rework | **High** | High | Medium |
| Auth becomes a synchronous network call; every request now has auth latency budget | Medium | High | Medium |
| Cascading session logic errors = logged-out users, lost carts | Medium | High | Hard |

User Management is **disqualified**. The session store is a hidden dependency that expands the blast radius well beyond what two engineers can contain in a quarter.

---

#### If we chose Notifications — it's Q+1 and we partially shipped

**What broke**: Two things.

*First*: The platform team said yes to ownership at the kickoff, then got pulled into a production incident in week 3 and never recovered the momentum. The extraction is 70% done — the service exists, but the monolith still calls both paths. We're running dual-write with no cutover date.

*Second*: The internal call `notifications.send(user_id, template, context)` became an async event publish. We didn't implement dead-letter queues or monitoring. A queue backup during a Black Friday sale silently dropped 4,000 order confirmation emails. Customer support was flooded.

| Risk | Likelihood | Impact | Reversibility |
|------|-----------|--------|---------------|
| No dedicated owner; platform team deprioritizes it mid-quarter | **High** | Medium | Easy |
| Event delivery gaps (queue failure = silent dropped emails) | Medium | High | Hard |
| Low demonstrable value; CTO underwhelmed | **High** | Medium | Easy |
| 72% test coverage: production edge cases undiscovered | Low | Medium | Medium |

These risks are **manageable**. None of them are financial incidents. None of them require expanding scope to three modules. None are irreversible.

---

### Step 3: Prioritized Risk Summary

| Risk | Module it kills | Mitigation |
|---|---|---|
| `pricing_rules` dual-write → wrong invoices | Billing | Don't start here |
| Financial data incident during cutover | Billing | Don't start here |
| Session store forces 3-module refactor | User Mgmt | Don't start here |
| SSO collision mid-extraction | User Mgmt | Don't start here |
| No dedicated Notifications owner → stalls | **Notifications** | Explicit time allocation before day 1 |
| Silent event delivery failures | **Notifications** | DLQ + alerting before cutover |
| Low demonstrable value | **Notifications** | Frame value correctly (see below) |

---

### Decision: Extract Notifications First

The premortem does not make Notifications look safe because it scored 0.08 on coupling. It makes Notifications the answer by elimination: Billing has a data ownership bomb, User Management has a scope expansion trap. Notifications' failure modes are organizational and operational — the kind you can fix with a meeting and a monitoring dashboard.

---

## Migration Plan

### Pre-conditions (before writing code)

**Resolve the team problem first.** This is the #1 kill risk the premortem surfaced. Before the first sprint, get explicit written commitment from the platform team's manager: one named engineer owns Notifications extraction for the quarter at ≥50% time. A platform team "side responsibility" will not survive the first production incident elsewhere on their plate.

**Audit the 72% coverage gap.** Spend one week mapping what the missing 28% covers. If it's happy-path duplication, fine. If it's error-handling and retry logic for email/SMS providers, write tests before touching anything.

---

### Phase 1 — Strangle the interface (Weeks 1–4)

The `notifications.send(user_id, template, context)` call is the only coupling point. That's a gift. Use the strangler fig pattern:

1. Stand up the Notifications service as a separate process, same database initially (shared `notification_templates` and `notification_log`).
2. Introduce a thin **adapter** in the monolith that routes calls to the new service via HTTP while keeping the old in-process path as a fallback:

```python
# monolith/notifications_adapter.py
def send(user_id, template, context):
    if feature_flags.is_enabled("notifications_service", user_id):
        return _send_via_service(user_id, template, context)
    return _send_inline(user_id, template, context)  # original path
```

3. Roll out via feature flag: 1% → 10% → 50% → 100%.
4. Both paths log to the same `notification_log` table; compare delivery rates between cohorts.

**Risk mitigated**: No event bus yet. Synchronous HTTP call means you can see failures immediately, not silently. The fallback path means any service failure rolls back to the monolith automatically.

---

### Phase 2 — Own the data (Weeks 5–8)

1. Transfer DB ownership: the Notifications service gets its own DB instance (or schema). Run dual-writes to both — monolith DB and new DB — for two weeks, with a reconciliation job that diffs them nightly.
2. Cutover reads to the new DB once drift is zero for 5 consecutive days.
3. Drain writes to the monolith DB. Remove monolith's direct table access.

**Key guardrail**: The reconciliation job is not optional. It is the go/no-go gate for cutover.

---

### Phase 3 — Async event model (Weeks 9–12, only if Phase 2 is stable)

The current synchronous HTTP call works but creates a latency dependency. Only introduce async eventing after the service is proven stable:

1. Add a message queue (SQS or RabbitMQ). Notifications service subscribes to `notification.requested` events.
2. **Before any traffic shifts**: implement dead-letter queue + PagerDuty alert on DLQ depth > 0. This is non-negotiable — the premortem showed silent email drops as a realistic failure mode.
3. Implement idempotent handlers (deduplication on `event_id`) so at-least-once delivery doesn't mean duplicate emails.
4. Shift traffic to async only after DLQ alerting is live and tested in staging.

**If Phase 2 runs long**: skip Phase 3 this quarter. A stable synchronous HTTP service is a complete success. Async is an optimization, not a requirement.

---

### Demonstrable Value (addressing CTO criterion #2)

The premortem flagged "low demonstrable value" as a real risk. Here's how to frame the outcome:

- **Independent deployability**: Template changes (new email design, SMS copy) now ship without a monolith deploy and without a code change. This is measurable: track time-to-ship a template change before vs. after.
- **Scaling isolation**: During peak load, the monolith was one process — Notifications competing for CPU with order processing. Now it scales independently. Show the resource utilization graph.
- **Proof of pattern**: The strangler fig adapter, feature flag rollout, and dual-write reconciliation job are now reusable templates for every future extraction. The real value is the playbook, not just the service.

Frame the Q+1 demo as: "We extracted Notifications and built the extraction playbook for the next four services."

---

### What Not to Extract After This

The premortem work above also implies an ordering for the second extraction:

- **User Management** becomes viable only after the session store is externalized — which can happen as a standalone infrastructure project separate from extraction.
- **Billing** becomes viable only after `pricing_rules` ownership is resolved — either by making it a Pricing service (owned by one team, APIs for both), or by duplicating the table with clear read/write boundaries.

Neither of those is a Q2 first extraction. Both are Q2 *pre-conditions* for Q3 extractions. Recommend flagging this to the CTO now so the roadmap is honest.