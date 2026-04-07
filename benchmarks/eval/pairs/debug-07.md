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

## Response B
## Diagnosis: Not Clock Skew — Stripe Batch Delivery with Variable Latency

The evidence rules out clock skew immediately. Your NTP offset is 23 nanoseconds — irrelevant. Stripe's `event.created` timestamps are also correct and in the right order. The problem is **differential delivery latency within a Stripe event batch**.

### What actually happened

```
Timeline:
  10:15:18Z  order.created event created on Stripe (evt_1OqR2sLk4i)
  10:15:21Z  order.paid    event created on Stripe (evt_1OqR2sLk4j)
                ↓ Stripe batches both events for delivery ↓
  10:15:33Z  order.paid    arrives at your server   (12.2s latency)
  10:15:34Z  order.created arrives at your server   (16.0s latency)
```

Stripe's own docs confirm this: *"Events within a delivery batch may arrive in any order."* The two events were created 3 seconds apart, batched together, and delivered in the same ~1-second window — but `order.paid` won the race by 0.8 seconds because of internal routing variance, not clock drift.

The clustering at `10:15-10:16` and `22:45-22:46` UTC is consistent with Stripe's batch delivery intervals during high-volume periods, exactly as their docs describe.

### Why the proposed fixes are wrong

| Proposal | Why it fails |
|---|---|
| NTP monitoring | Your clock is fine (23ns offset). This investigates the wrong system. |
| Investigate Stripe clock drift | Stripe's timestamps are correct. Not a clock issue. |
| 5-second processing delay | The gap in `ord_7a8b9c` is already 1.2s. Nothing prevents a 6s or 30s gap. Brittle. |

### The correct fix: idempotent handlers with retry on missing prerequisite

Stripe webhooks must be designed for out-of-order delivery. The handler should never hard-fail on a missing prerequisite — it should requeue with a short delay:

```typescript
// src/webhooks/queue.ts — simple in-process retry (replace with SQS/BullMQ in prod)
const RETRY_DELAY_MS = 2000;
const MAX_RETRIES = 5;

export async function withRetryOnNotFound<T>(
  fn: () => Promise<T>,
  context: { eventId: string; orderId: string; attempt?: number }
): Promise<T> {
  const attempt = context.attempt ?? 1;
  try {
    return await fn();
  } catch (err) {
    if (err instanceof OrderNotFoundError && attempt < MAX_RETRIES) {
      const delay = RETRY_DELAY_MS * attempt; // 2s, 4s, 6s, 8s
      console.warn(`Order ${context.orderId} not found, retrying in ${delay}ms`, {
        event_id: context.eventId,
        attempt,
      });
      await sleep(delay);
      return withRetryOnNotFound(fn, { ...context, attempt: attempt + 1 });
    }
    throw err;
  }
}
```

```typescript
// src/webhooks/stripe.ts
class OrderNotFoundError extends Error {
  constructor(orderId: string) {
    super(`Order ${orderId} not found`);
    this.name = 'OrderNotFoundError';
  }
}

async function handleOrderPaid(order: any, eventId: string) {
  await withRetryOnNotFound(
    async () => {
      const existing = await orderRepository.findByStripeId(order.id);
      if (!existing) throw new OrderNotFoundError(order.id);
      await orderRepository.updateStatus(order.id, 'paid');
    },
    { eventId, orderId: order.id }
  );
}

// Update the router to pass event.id through:
case 'order.paid':
  await handleOrderPaid(event.data.object, event.id);
  break;
```

**Important**: Return `200` to Stripe immediately after the `constructEvent` call and process asynchronously. If you let Stripe time out waiting for your handler, it will retry — which compounds the ordering problem. In production, push to SQS/BullMQ/Redis and acknowledge Stripe synchronously.

### Additional hardening: use `event.created` as a sequence guard

For state transitions, reject events that are older than the current recorded state:

```typescript
async function handleOrderPaid(order: any, eventCreated: number, eventId: string) {
  const existing = await orderRepository.findByStripeId(order.id);
  if (!existing) throw new OrderNotFoundError(order.id);

  // Idempotency: skip if we already processed a newer event
  if (existing.lastEventTimestamp >= eventCreated) {
    console.info(`Skipping stale event ${eventId} for order ${order.id}`);
    return;
  }

  await orderRepository.updateStatus(order.id, 'paid', { lastEventTimestamp: eventCreated });
}
```

This also handles Stripe's guaranteed-retry behavior (it retries failed webhooks for up to 3 days, so you'll see duplicate deliveries).

### Root cause summary

The bug is architectural: the handler assumes Stripe delivers events in creation order. Stripe explicitly does not guarantee this. The fix is making each handler resilient to missing prerequisites via retry, not by trying to control or predict delivery timing.

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
