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