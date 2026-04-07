## Socratic Analysis: Questioning the Clock Skew Hypothesis

Let me work through this with the epistemic discipline the situation warrants, because the team's hypothesis is almost certainly wrong — and acting on it will waste time while leaving the real bug unfixed.

---

### Step 1: Steelman the Clock Skew Hypothesis

Before dismissing it: clock skew *is* a real category of webhook delivery bug. If our server clock were ahead of Stripe's, we'd process events "before" they were created, and could misorder them. This has burned teams before. It's a reasonable first guess.

**But does the evidence support it?**

---

### Step 2: Actively Falsify the Hypothesis

| Evidence | What it says about clock skew |
|---|---|
| NTP: 0.000000023s slow | Our clock is accurate to **23 nanoseconds**. Eliminates our server as the source. |
| Stripe's `event.created` timestamps are **correctly ordered** | `order.created` = 10:15:18, `order.paid` = 10:15:21. If Stripe's clock were wrong, these timestamps would themselves be inverted or inconsistent. They're not. |
| Delivery latency differs: paid = 12.2s, created = 16.0s | The events arrived with **different latencies from Stripe's delivery system**, not at inverted times. |
| All incidents cluster in 10:15–10:16 UTC and 22:45–22:46 UTC | Narrow burst windows — not random scatter you'd see from drift. |

**Clock skew explains none of this.** The timestamps are right. Our clock is right. Clock skew is ruled out.

---

### Step 3: What Else Could Explain These Symptoms?

Now I list alternatives before committing:

1. **Stripe batch delivery with differential latency** — Stripe batches events; within a batch, delivery order is not guaranteed. The `order.paid` event simply traveled a faster path through Stripe's delivery infrastructure than `order.created`.

2. **Retry divergence** — `order.created` may have failed its first delivery attempt and been retried, while `order.paid` succeeded on the first try.

3. **Parallel delivery workers** — Stripe may use multiple workers per endpoint; the `paid` worker was faster than the `created` worker for that batch.

4. **Our own concurrency** — Our Express server processes requests concurrently. Even if events arrived 0.8s apart, async processing could invert completion order.

Which of these does the evidence support?

**The Stripe docs answer it directly** (their own documentation, not speculation):

> *"Events within a delivery batch may arrive in any order. Your webhook handler should be designed to handle out-of-order delivery."*

And the timing pattern confirms it: 0.3–1.2s gaps, clustered in short burst windows consistent with batch delivery. This is **exactly** what Stripe documents as expected behavior.

**Actual cause: Stripe delivers events in batches with no guaranteed ordering within a batch. Differential delivery latency causes the "later" event to arrive before the "earlier" one.**

---

### Step 4: Why the Proposed Fixes Are Wrong

**NTP monitoring:**
Our NTP offset is 23ns. Adding NTP health checks will show nothing actionable because our clock is not the problem. This is a solution to a problem that doesn't exist here.

**Investigating Stripe's clock:**
Stripe's `event.created` timestamps are correctly ordered. There's no clock drift to find.

**5-second processing delay:**
This is the most dangerous proposal. It would:
- Add 5s latency to 99.83% of events that currently work fine
- Still fail for any gap larger than 5s (a retry cycle could produce a 30s+ gap)
- Mask the underlying problem rather than fix it

It's a band-aid sized for the observed gap, not for the actual failure mode.

---

### The Correct Fix

The webhook handler assumes **delivery order = event order**. That assumption is wrong, and Stripe's docs say so. The handler needs to be **resilient to out-of-order delivery**.

**Option A — Retry with back-off (simplest, most robust):**

```typescript
async function handleOrderPaid(order: any) {
  const existing = await orderRepository.findByStripeId(order.id);
  if (!existing) {
    // Re-enqueue for retry — order.created may not have been processed yet
    throw new RetryableError(`order ${order.id} not found — will retry`, { 
      retryAfterMs: 2000 
    });
  }
  await orderRepository.updateStatus(order.id, 'paid');
}
```

Pair this with a dead-letter queue and exponential back-off (2s → 4s → 8s → alert). This handles the case correctly without assuming anything about delivery order.

**Option B — Idempotent upsert (more resilient):**

When `order.paid` arrives and the order doesn't exist yet, create a stub record with status `paid`, then let `order.created` fill in the rest:

```typescript
async function handleOrderPaid(order: any) {
  await orderRepository.upsert(order.id, { status: 'paid' });
}

async function handleOrderCreated(order: any) {
  await orderRepository.upsert(order.id, { ...orderData, status: existing?.status ?? 'created' });
}
```

This requires idempotent upserts but eliminates the ordering dependency entirely.

**Option C — Event sequencing queue:**

Buffer incoming events per `order_id` and process them ordered by `event.created`. Most complex, warranted if you see this pattern across many event types.

---

### Summary

| | Team's Hypothesis | Actual Cause |
|---|---|---|
| **Root cause** | Clock skew | Stripe batch delivery with no ordering guarantee |
| **Evidence for** | Common pattern in webhook bugs | Stripe docs, delivery latency data, burst timing |
| **Evidence against** | NTP: 23ns offset; timestamps are correctly ordered | Nothing contradicts this |
| **Correct fix** | NTP monitoring, delay | Retry queue or idempotent upsert |

The fix is in the handler logic, not the infrastructure. The handler must never assume that receiving `order.paid` means `order.created` was already processed.