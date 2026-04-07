## Root Cause: Stripe Batch Delivery, Not Clock Skew

**Clock skew is a red herring.** Your NTP data proves this — your server is 23 nanoseconds off. The Stripe `event.created` timestamps are also in the correct order. No clocks are wrong.

The actual cause is in the Stripe docs you included:

> *"Events within a delivery batch may arrive in any order."*

Look at the delivery latencies:
- `order.created` (happened at 10:15:18): delivered 16.0s later
- `order.paid` (happened at 10:15:21): delivered 12.2s later

Both events were batched together and dispatched in the same window. `order.paid` had lower delivery latency within that batch, so it arrived first. The events occurred during concentrated windows (10:15–10:16, 22:45–22:46) — high-volume periods where Stripe's docs specifically warn batch sizes increase.

## Why the Team's Proposals Are Wrong

**NTP sync checks**: Clock skew is not the problem. This adds monitoring overhead for a problem that doesn't exist.

**Investigating Stripe clock drift**: Stripe's clocks are fine — the `event.created` timestamps are correctly ordered. This is a dead end.

**5-second processing delay**: This does not fix ordering. Delivery latency differences can exceed 5 seconds, and this just adds 5 seconds of latency to every event in your system permanently. The 1.2s gap in your data would still fail with a 5s delay... until a worse batch hits.

## The Correct Fix

Your handler must tolerate out-of-order delivery. There are two layers to this:

**Layer 1: Never throw on missing order — return 200 and requeue.**

Right now, throwing in the handler causes an unhandled exception. You need to decouple Stripe acknowledgment from processing, then handle missing-order as a retryable condition:

```typescript
// src/webhooks/stripe.ts
webhookRouter.post('/stripe', express.raw({ type: 'application/json' }), async (req, res) => {
  const sig = req.headers['stripe-signature'];
  let event: Stripe.Event;

  try {
    event = stripe.webhooks.constructEvent(req.body, sig, process.env.STRIPE_WEBHOOK_SECRET);
  } catch (err) {
    return res.status(400).send(`Webhook signature verification failed`);
  }

  // Acknowledge immediately — never block Stripe waiting for processing
  res.status(200).json({ received: true });

  // Enqueue for async processing with order guarantee per order ID
  await eventQueue.enqueue({
    eventId: event.id,
    eventType: event.type,
    eventCreated: event.created,
    payload: event.data.object,
  });
});
```

**Layer 2: Process with retry on missing prerequisite.**

```typescript
// src/workers/stripe-event-worker.ts
async function processEvent(job: StripeEventJob, attempt: number = 1): Promise<void> {
  const MAX_ATTEMPTS = 5;
  const BACKOFF_MS = [1000, 2000, 5000, 10000, 30000];

  switch (job.eventType) {
    case 'order.paid':
    case 'order.shipped': {
      const existing = await orderRepository.findByStripeId(job.payload.id);

      if (!existing) {
        if (attempt >= MAX_ATTEMPTS) {
          // Alert — order.created may have been lost entirely
          await alerting.critical(`order.created never arrived for ${job.payload.id}`, job);
          return;
        }
        // Requeue with backoff — order.created is probably in-flight
        const delay = BACKOFF_MS[attempt - 1];
        console.warn(`Order ${job.payload.id} not found, retrying in ${delay}ms`, {
          eventId: job.eventId,
          attempt,
        });
        await eventQueue.enqueueDelayed(job, delay, attempt + 1);
        return;
      }

      if (job.eventType === 'order.paid') {
        await orderRepository.updateStatus(job.payload.id, 'paid');
      } else {
        await orderRepository.updateStatus(job.payload.id, 'shipped');
      }
      break;
    }

    case 'order.created':
      // Idempotent upsert — safe if order.created arrives late
      await orderRepository.upsert(job.payload.id, {
        status: 'created',
        stripeData: job.payload,
      });
      break;
  }
}
```

**Layer 3: Make `order.created` idempotent.**

If `order.created` arrives after `order.paid` has already been retried and succeeded, your upsert must not overwrite the 'paid' status:

```typescript
// In your repository
async upsert(stripeId: string, data: { status: string; stripeData: any }) {
  const STATUS_RANK = { created: 0, paid: 1, shipped: 2, delivered: 3 };

  await db.transaction(async (trx) => {
    const existing = await trx('orders').where({ stripe_id: stripeId }).first();
    if (!existing) {
      await trx('orders').insert({ stripe_id: stripeId, ...data });
    } else if (STATUS_RANK[data.status] > STATUS_RANK[existing.status]) {
      // Only move forward in the lifecycle, never backward
      await trx('orders').where({ stripe_id: stripeId }).update({ status: data.status });
    }
    // else: existing status is already ahead — do nothing
  });
}
```

## Summary

| Hypothesis | Evidence | Verdict |
|---|---|---|
| Clock skew | NTP: 23ns off; Stripe timestamps correct | Not the cause |
| Stripe clock drift | `event.created` order is correct | Not the cause |
| Batch delivery reordering | Stripe docs + latency data (12.2s vs 16.0s) | **Root cause** |

The fix is **idempotent handlers + async retry with backoff**, not timing adjustments. Your 0.17% failure rate will drop to ~0% once dependent events retry until their prerequisites exist.