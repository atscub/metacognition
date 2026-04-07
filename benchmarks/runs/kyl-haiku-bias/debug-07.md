## Socratic Analysis

**1. What am I assuming?**
- That `event.created` timestamps reflect Stripe's actual server time when events were generated
- That "events out of order" is fundamentally different from "clock skew"
- That Stripe's API docs are authoritative on how their system actually works
- That your NTP sync measurements are accurate

**2. What evidence do I have?**

| Claim | Confidence | Grounding |
|-------|-----------|-----------|
| `event_created` timestamps are in correct order | **High** | I read the logs directly: 1711616118 < 1711616121 |
| Your server clock is synced | **High** | NTP output shows 0.000000023s drift (nearly zero) |
| Stripe says events can arrive out of order | **High** | Their own documentation states this explicitly |
| Out-of-order delivery happened | **High** | Logs show order.paid error at 10:15:33, then order.created success at 10:15:34 |
| This is clock skew | **Very Low** | The event timestamps disprove it — if it were clock skew, those would be in reverse order |

**3. What would change my mind?**
- If the `event_created` timestamps were in **reverse** order (that would suggest Stripe's clock is wrong)
- If your server clock was actually drifting significantly (NTP says it's not)
- If this affected **every** webhook, not just 0.17% during two specific minute-long windows

**4. The critical test: Who's actually wrong?**

Clock skew hypothesis requires: *Stripe's clock is drifting, causing it to timestamp the paid event as if it arrived before the created event.*

But the logs show the opposite: Stripe's timestamps are **correct** (created→paid in time order). Stripe is telling you truthfully when it created each event. The problem is that Stripe batched them and delivered them in a different order than they were created.

---

## The Actual Cause

This is **not** a clock skew issue. This is **Stripe's documented behavior that your code is violating**.

Stripe explicitly says:
> "Events within a delivery batch may arrive in any order. Your webhook handler should be designed to handle out-of-order delivery."

The incident is in two 1-minute windows because Stripe likely batched multiple orders' events together during those periods (high-volume times, perhaps). Those events got delivered as one batch, and your handler processes them synchronously — whichever request arrives first gets processed first.

**Timeline reconstruction:**
1. Order 9x8w7v is created at 10:15:18 on Stripe's side
2. Order 9x8w7v is paid at 10:15:21 on Stripe's side
3. Stripe batches both events (along with others)
4. Stripe's batch delivery happens to send `order.paid` first, then `order.created` 
5. Your code processes them in that order
6. `order.paid` fails because the order doesn't exist yet ← **This is the bug**

**Why the team's clock skew hypothesis is wrong:**
- If it were clock skew on Stripe's side, the `event_created` timestamps would be backwards ✗
- If it were clock skew on your side, you'd see it affecting **all** your operations, not just this webhook ✗
- Your NTP is nearly perfect, ruling out your clock as the culprit ✗

---

## The Correct Fix

**NOT**: "Add NTP monitoring" or "Add a 5-second delay" (both are cargo-cult solutions for a problem that isn't actually there)

**Instead**: Make your handlers resilient to out-of-order delivery:

```typescript
async function handleOrderPaid(order: any) {
  const existing = await orderRepository.findByStripeId(order.id);
  
  if (!existing) {
    // Option 1: Retry later — let Stripe retry, or queue this for retry
    throw new RetryableError(
      `Order ${order.id} not found yet — will retry`
    );
    
    // Option 2: Defer processing until order is created
    // This is what you should actually do
  }
  
  await orderRepository.updateStatus(order.id, 'paid');
}
```

Or better: **Use `event.created` timestamps to ensure correct ordering yourself:**

```typescript
async function handleWebhook(event: Stripe.Event) {
  const key = `event:${event.data.object.id}`;
  const pendingEvents = await getPendingEvents(key);
  pendingEvents.push(event);
  pendingEvents.sort((a, b) => a.created - b.created);
  
  for (const ev of pendingEvents) {
    try {
      await processEvent(ev);
      await removePendingEvent(key, ev.id);
    } catch (err) {
      if (err.code === 'ORDER_NOT_FOUND') {
        // Stop here, retry this batch later
        break;
      }
      throw err;
    }
  }
}
```

**Cost of this bug continuing:**
- 0.17% of orders experience processing failures
- Each failure requires manual intervention or eventual retry
- Adding "delay" masks the problem without fixing it — you'll still have race conditions, just slightly less often

---

## Bottom Line

**The root cause is not clock skew — it's your code's unjustified assumption that webhooks arrive in chronological order.** Stripe's own documentation says this assumption is invalid. Fix the handler to be resilient to reordering, and the problem disappears.