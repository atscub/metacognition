# Task: debug-07 — Webhook events arriving out of order

## Prompt
Our e-commerce platform processes Stripe webhooks to track order lifecycle events. We're
seeing a critical bug where `order.paid` events are processed BEFORE `order.created`
events for the same order, causing our handler to fail because it tries to update an
order record that doesn't exist yet. The team suspects clock skew between Stripe's
servers and ours. Can you investigate?

Application error logs:

```
[2026-03-28T10:15:33.221Z] ERROR: Cannot process event order.paid — order ord_9x8w7v not found
  event_id: evt_1OqR2sLk4j
  order_id: ord_9x8w7v
  event_type: order.paid
  event_created: 1711616121    (2026-03-28T10:15:21Z)

[2026-03-28T10:15:34.008Z] INFO: Processing event order.created
  event_id: evt_1OqR2sLk4i
  order_id: ord_9x8w7v
  event_type: order.created
  event_created: 1711616118    (2026-03-28T10:15:18Z)

[2026-03-28T10:15:34.150Z] INFO: Order ord_9x8w7v created successfully
```

Note: the `event_created` timestamps are in the correct order (order.created at 10:15:18,
order.paid at 10:15:21), but the events were RECEIVED and PROCESSED in reverse order
(order.paid at 10:15:33, order.created at 10:15:34).

More examples from the last 24 hours:

```
=== Out-of-order events (last 24h) ===
Order ID       | Expected first  | Actually first | Gap
ord_9x8w7v     | order.created   | order.paid     | 0.8s
ord_3m4n5p     | order.created   | order.paid     | 0.3s
ord_7a8b9c     | order.created   | order.shipped  | 1.2s
ord_2d3e4f     | order.created   | order.paid     | 0.5s

Total affected: 4 out of ~2,400 orders (0.17%)
All occurred during 10:15-10:16 UTC and 22:45-22:46 UTC windows
```

Webhook handler (src/webhooks/stripe.ts):

```typescript
import express from 'express';
import Stripe from 'stripe';
import { orderRepository } from '../repositories/order';

const stripe = new Stripe(process.env.STRIPE_SECRET_KEY);

export const webhookRouter = express.Router();

webhookRouter.post('/stripe', express.raw({ type: 'application/json' }), async (req, res) => {
  const sig = req.headers['stripe-signature'];
  let event: Stripe.Event;

  try {
    event = stripe.webhooks.constructEvent(req.body, sig, process.env.STRIPE_WEBHOOK_SECRET);
  } catch (err) {
    return res.status(400).send(`Webhook signature verification failed`);
  }

  console.log(`Processing event ${event.type}`, {
    event_id: event.id,
    event_created: event.created,
  });

  switch (event.type) {
    case 'order.created':
      await handleOrderCreated(event.data.object);
      break;
    case 'order.paid':
      await handleOrderPaid(event.data.object);
      break;
    case 'order.shipped':
      await handleOrderShipped(event.data.object);
      break;
    default:
      console.log(`Unhandled event type: ${event.type}`);
  }

  res.status(200).json({ received: true });
});

async function handleOrderPaid(order: any) {
  const existing = await orderRepository.findByStripeId(order.id);
  if (!existing) {
    throw new Error(`Cannot process event order.paid — order ${order.id} not found`);
  }
  await orderRepository.updateStatus(order.id, 'paid');
}
```

NTP status on our servers:

```
$ chronyc tracking
Reference ID    : A9FEA9FE (time.aws.com)
Stratum         : 3
Ref time (UTC)  : Thu Mar 28 10:20:01 2026
System time     : 0.000000023 seconds slow of NTP time
Last offset     : +0.000000012 seconds
```

Stripe API docs (from their webhook documentation):

```
## Event Delivery

Events are delivered via HTTP POST to your configured endpoint. Stripe
batches events for efficiency — multiple events may be delivered in
rapid succession.

**Important**: Events within a delivery batch may arrive in any order.
Your webhook handler should be designed to handle out-of-order delivery.
Use the `event.created` timestamp or the object's state to determine
the correct processing sequence.

Batch delivery typically occurs at regular intervals. During high-volume
periods, batch sizes increase.
```

Server clock comparison (during incident):

```
Our server:  2026-03-28T10:15:33.221Z
Stripe event created: 2026-03-28T10:15:21Z (for order.paid)
Stripe event created: 2026-03-28T10:15:18Z (for order.created)

Delivery latency:
  order.paid:    12.2s from creation to delivery
  order.created: 16.0s from creation to delivery
```

The team is considering adding NTP sync checks to their health monitoring and
investigating whether Stripe's clock is drifting. They've also proposed adding
a 5-second delay to all webhook processing "to let events settle."

What's the actual cause and the correct fix?


## Response A
**Excellent question. You're right to push back on the team's hypothesis. Clock skew is a *plausible red herring*.**

Let me work through the evidence systematically:

## The Clock Skew Hypothesis Fails Here

**Assumption**: If clock skew were the root cause, the `event.created` timestamps would be backwards.

**Reality**: They're not. They're in the correct causal order:
- `order.created`: 1711616118 (10:15:18Z) 
- `order.paid`: 1711616121 (10:15:21Z)

If Stripe's clock was drifting or ahead of ours, these timestamps would be reversed. They're not. ✓

**Your NTP is also perfect** (microsecond precision), so even if there *were* clock drift, you'd catch it. That rules out our side too.

---

## What the Delivery Latencies Actually Tell Us

**The key insight**:

```
Event created        |  Delivered at     |  Latency
order.created  10:15:18Z  →  10:15:34Z    (16.0s)
order.paid     10:15:21Z  →  10:15:33Z    (12.2s)
```

Even though `order.created` came **first by 3 seconds**, it was **delivered last by 1 second**. 

This is not a clock problem. **This is a batch delivery problem.**

---

## The Actual Root Cause

Stripe's documentation is explicit:
> "Events within a delivery batch may arrive in any order."

What happened:
1. At 10:15:18Z, Stripe created the `order.created` event
2. At 10:15:21Z, Stripe created the `order.paid` event
3. **These went into different batches** (batching happens at regular intervals, and during high volume, batch boundaries move)
4. The batch containing `order.paid` (created 3s later) was delivered **faster** (12.2s vs 16.0s)
5. Your webhook received them out of causal order, and the handler crashed

**This is not a defect. This is documented, expected behavior.**

---

## Why the Team's Proposed Fixes Won't Work

| Proposed Fix | Why It Fails |
|-------------|------------|
| **NTP sync checks** | NTP isn't the problem; delivery order is. Checking it won't help. |
| **5-second delay** | Masks the symptom temporarily but breaks under load. With enough traffic, you'll see gaps > 5s. |
| **Investigating Stripe's clock** | Their clock is fine. Their *batching* is the issue, which is documented behavior. |

---

## The Correct Fix

Your handler **assumes events arrive in causal order, but they don't.** The fix is to make it **defensive**:

**Option 1: Use `event.created` timestamps to reorder**
```typescript
// Process out-of-order events by storing them temporarily
// and replaying them in created-timestamp order
```

**Option 2: Graceful degradation (better for most cases)**
```typescript
async function handleOrderPaid(order: any) {
  const existing = await orderRepository.findByStripeId(order.id);
  if (!existing) {
    // Don't error — queue for retry in 2-3 seconds
    // The order.created event will likely arrive by then
    await eventQueue.retryLater(event, 2000);
    return;
  }
  await orderRepository.updateStatus(order.id, 'paid');
}
```

**Option 3: Make handlers idempotent**
```typescript
// Ensure the handler can safely run multiple times
// and can handle partial state
```

---

## High Confidence Assessment

- **Root cause**: Stripe's batch delivery ordering (not clock skew) — **Very High Confidence** (documented, all evidence supports it)
- **Why the team's hypothesis is wrong**: Event timestamps are correct, NTP is perfect, documentation is explicit — **Very High Confidence**
- **Why simple fixes fail**: They don't address the actual mechanism — **Very High Confidence**

**Cost of getting this wrong**: High. Chasing NTP and adding delays wastes time and doesn't solve the recurrence.

Should I draft the actual code fix for the webhook handler?

## Response B
The actual cause is **not clock skew** — it's **Stripe's documented out-of-order batch delivery behavior**, and your team's proposed fixes miss the real problem.

## Root Cause

Stripe's API docs explicitly state: *"Events within a delivery batch may arrive in any order."* This is a normal, expected behavior, not a bug.

**What actually happened:**
1. Event A (order.created) was generated at 10:15:18
2. Event B (order.paid) was generated at 10:15:21 (3 seconds later)
3. Stripe batched these separately and delivered B first (12.2s latency) at 10:15:33
4. A arrived later (16.0s latency) at 10:15:34

The delivery order reversal is a **network/queuing effect**, not a time synchronization issue. Your NTP status proves your clocks are fine.

**Why this happens occasionally:**
- Stripe may batch by event type, priority, or delivery service
- Network packet reordering or congestion
- Internal retry logic retrying older events
- Load spikes causing batch queuing delays

The 0.17% incident rate and clustering in specific 1-minute windows suggest these are edge cases during high-volume periods.

## Why the proposed fixes are wrong

| Proposal | Why it fails |
|----------|-------------|
| **NTP monitoring** | Your clock is already synced to microsecond precision. This won't prevent network-level delivery reordering. |
| **5-second delay** | Masks the symptom for this case but fails silently if gaps exceed 5 seconds. Not a real fix, just slower masking. |

## The correct fix: Event ordering by timestamp

Your handler should **process events in chronological order** using `event.created`, not arrival order. Here's the pattern:

```typescript
// Option 1: Queue out-of-order events and retry
const eventQueue = new Map<string, Stripe.Event[]>();

webhookRouter.post('/stripe', express.raw({ type: 'application/json' }), async (req, res) => {
  const sig = req.headers['stripe-signature'];
  let event: Stripe.Event;

  try {
    event = stripe.webhooks.constructEvent(req.body, sig, process.env.STRIPE_WEBHOOK_SECRET);
  } catch (err) {
    return res.status(400).send('Webhook signature verification failed');
  }

  const orderId = event.data.object.id;
  
  // Track events for this order
  if (!eventQueue.has(orderId)) {
    eventQueue.set(orderId, []);
  }
  eventQueue.get(orderId)!.push(event);

  // Sort by event.created and process in order
  const orderedEvents = eventQueue
    .get(orderId)!
    .sort((a, b) => a.created - b.created);

  // Process only contiguous events from the start
  let processedCount = 0;
  for (const evt of orderedEvents) {
    try {
      await processEvent(evt);
      processedCount++;
    } catch (err) {
      // Stop if we hit a dependency error, others will retry on next webhook
      if (err.message.includes('not found')) {
        console.log(`Deferring event ${evt.id}, dependency not ready yet`);
        break;
      }
      throw err;
    }
  }

  // Remove processed events
  if (processedCount > 0) {
    eventQueue.set(orderId, orderedEvents.slice(processedCount));
  }

  res.status(200).json({ received: true });
});
```

**Or simpler: Make handlers idempotent**

```typescript
async function handleOrderPaid(order: any) {
  const existing = await orderRepository.findByStripeId(order.id);
  
  if (!existing) {
    // Instead of throwing, defer retry
    throw new Error(`Order not yet created, will retry on next webhook`);
  }
  
  // Idempotent: only update if not already paid
  if (existing.status !== 'paid') {
    await orderRepository.updateStatus(order.id, 'paid');
  }
  
  return; // Success even if already paid
}
```

Stripe will retry failed webhooks automatically. If `order.created` hasn't arrived yet, the `order.paid` handler defers gracefully and re-processes on the retry.

## What to do now

1. **Stop investigating NTP/clock skew** — your clocks are fine
2. **Implement event ordering by `event.created` timestamp** or idempotent handlers that defer on missing dependencies
3. **Remove the 5-second delay proposal** — it won't reliably fix the issue
4. **Add monitoring** for webhook processing latency and out-of-order incidents (which are expected)
5. **Test** by deliberately sending events out of order in your staging environment

The bug isn't that events arrived out-of-order; the bug is that your handler assumes they won't.

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
