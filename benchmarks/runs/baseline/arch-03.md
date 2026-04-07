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