## Recommendation: Extract Notifications First

### Why Not the Others

**Billing** is the trap option. The `pricing_rules` table is a shared read/write surface between Billing and Orders — you cannot extract Billing without resolving that first. Your options are all bad: move the table to Billing's DB (Orders now depends on Billing service), move it to Orders' DB (Billing now depends on Orders service), or create a third Pricing Service (exceeds your 2-service budget and the quarter timeline). The eager team and low coupling score are misleading; the table conflict makes this a multi-quarter effort in disguise.

**User Management** has a structural prerequisite you can't skip: the in-process Redis session store is shared with Orders (cart state) and Billing (payment flow state). You're not extracting one service — you're forced to also externalize the session store as a shared service simultaneously, which is scope creep hidden as a dependency. The team being mid-SSO integration adds execution risk.

**Notifications** is the right call.

### Why Notifications Wins on All Three Criteria

| Criterion | Notifications | Reason |
|-----------|--------------|--------|
| Low production risk | Best candidate | Not in the transaction critical path. A delayed email is recoverable; a failed payment is not. Owns its tables exclusively. No shared state. |
| Demonstrable value | Sufficient | Proves the extraction pattern, establishes async messaging infrastructure, frees platform team bandwidth, and sets the template for Billing (the real prize next quarter). |
| 2 engineers, one quarter | Achievable | The call interface is already clean: `notifications.send(user_id, template, context)`. Extraction is mostly infrastructure work, not API redesign. |

The team ownership gap (platform team, side responsibility) is the one legitimate concern — address it by formally seconding 2 engineers for the quarter. Don't let a staffing logistics issue block the technically cleanest extraction.

---

### Migration Plan

#### Phase 1: Harden the boundary in-place (Weeks 1–3)

Before moving anything, make the boundary explicit inside the monolith:

```python
# Before: callers call this directly
notifications.send(user_id, template, context)

# After: introduce an interface that can be swapped
class NotificationPort:
    def send(self, user_id: str, template: str, context: dict) -> None:
        raise NotImplementedError

class InProcessNotificationAdapter(NotificationPort):
    def send(self, user_id, template, context):
        # existing in-process call
        notifications.send(user_id, template, context)
```

Add a feature flag: `NOTIFICATIONS_TRANSPORT = "in_process" | "queue"`.

**Why**: If anything breaks during extraction, you flip one flag. No emergency deploys touching call sites.

Also close the test coverage gap now, not later. Bring 72% → 85%+ with integration tests against the real template and log tables. You want a safety net before you pull the wire.

#### Phase 2: Deploy the service, route via queue (Weeks 4–8)

Deploy Notifications as a standalone service. Use an async queue (Redis Streams fits since you already have Redis; RabbitMQ if you want durability guarantees) as the transport:

```python
class QueuedNotificationAdapter(NotificationPort):
    def send(self, user_id, template, context):
        self.queue.publish("notifications", {
            "user_id": user_id,
            "template": template,
            "context": context,
            "enqueued_at": utcnow().isoformat()
        })
```

The queue is the key risk mitigation here. Callers become fire-and-forget — if the Notifications service is down or slow, messages queue up and drain when it recovers. No caller sees an error.

Migration sequence for the tables:
1. Snapshot `notification_templates` and `notification_log` from the monolith DB into the new service's DB
2. Dual-write to both during transition
3. Switch reads to the new DB
4. Stop dual-write

Rollout by notification type, lowest-stakes first: push notifications → SMS → email.

#### Phase 3: Cut over and remove the in-process path (Weeks 9–12)

Once 100% of traffic routes through the queue and you've had two weeks of clean metrics:

- Delete `InProcessNotificationAdapter` and the in-process module code from the monolith
- Remove the feature flag and its branches
- Transfer DB ownership formally (access controls, monitoring, on-call rotation)
- Write the postmortem/extraction retrospective — this becomes the playbook for Billing

---

### Risk Register

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Queue backlog during traffic spikes | Medium | Set queue depth alert at 1k messages; autoscale the consumer |
| Template data drift during dual-write | Low | Checksums on template records; reconciliation job runs nightly |
| In-process tests break before extraction complete | Medium | Keep both adapters wired until Phase 3; CI runs both paths |
| Platform team capacity drops | High | Formalize the 2-engineer allocation in writing before kickoff |
| 72% coverage hides integration bugs | Medium | Block Phase 2 start on coverage gate, not just line count |

---

### What This Sets Up for Q3

After a clean Notifications extraction, you have:
- A proven async messaging pattern that Billing can use for invoice events
- Tooling and runbooks for table migration
- A quarter of operational experience with inter-service networking and observability

Billing becomes the Q3 target, by which point you can propose the `pricing_rules` resolution cleanly: extract it into a lightweight Pricing Rules service that both Billing and Orders call. That's a three-service architecture, properly sequenced, rather than a two-service architecture with a hidden shared-table time bomb.