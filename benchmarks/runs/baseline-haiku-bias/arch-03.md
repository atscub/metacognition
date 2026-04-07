I recommend **extracting Billing first**, with a specific migration plan for the `pricing_rules` table. Here's the analysis:

## Recommendation Summary

| Criterion | Billing | Notifications | User Management |
|-----------|---------|---|---|
| **Risk of incidents** | Medium (shared table, but isolated logic) | Low | High (session store, multi-module impact) |
| **Demonstrable value** | ✓ High (team autonomy, clear ownership) | ✗ Low (stable side project, no strategic benefit) | ✓ Medium (SSO enablement blocked by this) |
| **1Q feasibility** | ✓ Yes (2 engineers, stable, 87% test coverage) | ✓ Yes (but unmotivated team) | ✗ Risky (session store migration affects all modules) |

**Why Billing wins:** It's the *lowest-risk* entry point that still delivers *demonstrable value*. The team is motivated, the code is stable, and extracting it proves engineers *want* to own microservices (not just that modules can be split). Notifications is too low-stakes; User Management's session store creates unacceptable risk for a pilot.

---

## Extraction Plan: Billing Microservice

### Phase 1: Prepare (Weeks 1–2)

1. **Decouple from Orders module**
   - Replace direct function call (`orders_module.get_order()`) with an API call
   - Add integration test to verify both code paths work
   - No production risk — it's a code change within the monolith

2. **Solve the `pricing_rules` table problem**
   
   **Option A (Recommended): Read-through cache**
   - Billing still queries the same `pricing_rules` table initially
   - But add an event bus: when Orders writes to `pricing_rules`, publish an event
   - Billing subscribes and caches rules locally
   - Gradual migration: once caching is stable, move `pricing_rules` to Billing's DB
   - **Timeline: 2–3 weeks**

   **Option B (Faster): Duplicate ownership**
   - Create `billing_pricing_rules` table in Billing's DB
   - Orders + Billing both write to their copy
   - Add async reconciliation job (hourly sync from monolith → service)
   - **Timeline: 1 week, but more operational burden**

   **Option C (Longer-term): Pricing Rules microservice**
   - Too heavyweight for a pilot; skip for now

   → **Go with Option A for this pilot.**

3. **Add monitoring and kill switch**
   - Deploy Billing in shadow mode: dual-write (monolith + service), dual-read (compare)
   - Monitor discrepancies on invoices, payment calculations
   - Establish instant rollback: if the service diverges, traffic goes back to monolith

### Phase 2: Extract (Weeks 3–6)

1. **Set up Billing service infrastructure**
   - Separate repo, separate database (reuse tables initially if needed, plan migration)
   - API gateway routing: `POST /billing/*` → service instead of monolith
   - CI/CD pipeline, secrets, monitoring

2. **Migrate existing functionality**
   - Move all 14 REST endpoints to the service
   - Keep same request/response contracts (no API changes yet)
   - Run tests in parallel: monolith tests still pass, service tests pass

3. **Run in shadow mode for 1 week**
   - Monolith still answers billing requests
   - Service processes them in parallel
   - Compare results; fix any divergences
   - Monitor latency, error rates

4. **Cut over traffic** (gradual)
   - 10% of billing traffic → service (Friday afternoon, watch logs)
   - Ramp to 50% by Monday, 100% by Wednesday
   - Instant rollback available

### Phase 3: Stabilize (Weeks 7–8)

1. **Decommission dual-write to monolith**
   - Stop syncing `pricing_rules` back to monolith
   - Remove code paths from Orders that reference old Billing tables

2. **Plan for Orders' next extraction**
   - With Billing extracted, Orders loses its direct dependency and `pricing_rules` becomes Billing's responsibility
   - Orders can follow in Q2/Q3

---

## Risk Mitigations

| Risk | Mitigation |
|------|-----------|
| **Shared `pricing_rules` table** | Event-driven sync (Phase 1, Option A); service queries its local cache after week 2 |
| **Billing queries Order data** | Already decoupled via API; this is now a service-to-service call (acceptable) |
| **Payment processing breaks** | Shadow mode + kill switch ensures rollback is < 30 seconds; 87% test coverage gives high confidence |
| **Database consistency** | Start with read-only replica of monolith tables; gradual data migration after go-live |
| **Team overload** | 2 engineers is right-sized; Notifications team doesn't want this; User Mgmt team is focused on SSO |

---

## Why Not the Others?

- **Notifications:** Lowest risk, but zero strategic value. It's a "nice cleanup" that doesn't unblock the real work. A successful extraction of it won't convince anyone else that services are worth the effort.
- **User Management:** Session Store is shared across Billing, Orders, *and* User Mgmt. Extracting it requires solving a 3-way coupling problem in a pilot quarter. Too risky for first extraction.

---

## Success Metrics

By end of Q2:
1. Billing service handles 100% of invoicing, payments, subscriptions traffic with <1% error rate
2. `pricing_rules` fully owned by Billing service (monolith no longer writes)
3. Billing team ships features independently of Orders/User Mgmt
4. Extraction playbook documented for next service (Orders, targeting Q3)

This approach extracts real value (team autonomy + cleaner architecture) while keeping incident risk acceptably low.