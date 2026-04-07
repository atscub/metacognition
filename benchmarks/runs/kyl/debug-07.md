## Socratic Analysis: Questioning the Clock Skew Hypothesis

Before accepting the team's framing, let me work through the actual evidence.

---

### Step 1: Steelman the team's hypothesis

Clock skew *would* explain out-of-order processing: if our server clock is ahead of Stripe's, events created at time T on Stripe could arrive "before" our wall clock catches up. It's a reasonable first guess for ordering issues across distributed systems.

---

### Step 2: Look for disconfirming evidence

**The hypothesis requires the `event_created` timestamps to be wrong or inverted.** Are they?

```
order.created: event_created = 1711616118  (10:15:18Z)  ✓
order.paid:    event_created = 1711616121  (10:15:21Z)  ✓
```

They are **correct and in sequence**. Stripe's clocks agree: `created` happened first, `paid` happened second. Clock skew would corrupt these timestamps — it didn't.

**The NTP data confirms this directly:**

```
System time: 0.000000023 seconds slow
Last offset: +0.000000012 seconds
```

Our clock is 23 nanoseconds off. This is not the problem.

**Anchoring bias check**: The team anchored on "clock skew" because it's a common distributed systems gotcha. But no evidence supports it here.

---

### Step 3: What actually explains the symptoms?

Look at the delivery latencies:

| Event | Created | Received | Delivery latency |
|---|---|---|---|
| `order.created` | 10:15:18Z | 10:15:34Z | **16.0 seconds** |
| `order.paid` | 10:15:21Z | 10:15:33Z | **12.2 seconds** |

`order.paid` was created 3 seconds *later* but arrived 0.8 seconds *earlier* — because it had 3.8 seconds less delivery latency. The timestamps are fine. **The delivery latency differed between two events in the same batch.**

Stripe's own documentation, which is in your provided context, says this explicitly:

> **Events within a delivery batch may arrive in any order.** Your webhook handler should be designed to handle out-of-order delivery.

**This is documented, expected behavior.** Not a bug on Stripe's end, not clock skew.

The time-clustering (10:15–10:16 and 22:45–22:46) is consistent with Stripe's batch delivery interval — during high-volume windows, events accumulate and flush together. Within a flush, delivery order is not guaranteed.

---

### Step 4: Evaluate the proposed fixes

| Proposal | Verdict |
|---|---|
| Add NTP sync checks to health monitoring | Irrelevant — the clock is fine |
| Investigate Stripe clock drift | Irrelevant — event timestamps are correct |
| Add 5-second delay to all webhook processing | Wrong — doesn't fix the problem, just shifts the window. A gap of >5s would still fail, and you'd add 5s latency to every webhook unnecessarily |

---

### The actual root cause

**The webhook handler assumes sequential delivery but Stripe does not guarantee it.** `handleOrderPaid` throws immediately when the order doesn't exist, with no mechanism to handle legitimate ordering races.

---

### The correct fix

The handler needs to tolerate out-of-order events. Two solid options:

**Option A — Retry queue (simplest, correct for your scale):**

```typescript
async function handleOrderPaid(order: any, event: Stripe.Event) {
  const existing = await orderRepository.findByStripeId(order.id);
  if (!existing) {
    // Don't throw — requeue for later processing
    await eventQueue.enqueue({
      event,
      retryAfter: Date.now() + 5000,
      maxAttempts: 5,
    });
    return;
  }
  await orderRepository.updateStatus(order.id, 'paid');
}
```

This handles the race without adding latency to the happy path and without a fixed delay.

**Option B — Idempotent upsert (if you control the order schema):**

When `order.paid` arrives and no record exists, create a partial order record in a `pending` state, then let `order.created` fill it in. Requires your data model to handle incomplete records gracefully.

Option A is lower risk and directly matches the failure mode — a transient ordering gap of under 2 seconds, solved by a short retry.

---

### What I'd actually verify before shipping the fix

1. Is there already a retry mechanism in the event queue? The fix above assumes one exists or can be added.
2. Are there other handlers (`handleOrderShipped`, etc.) with the same `if (!existing) throw` pattern? They have the same bug.
3. Does the retry queue deduplicate on `event.id`? It should, to stay idempotent.

The root cause is **missing tolerance for out-of-order delivery in a system where out-of-order delivery is explicitly documented as possible** — not clock skew.