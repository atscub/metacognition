I'll cut to the answer: **The clock skew theory is a red herring. This is Stripe's documented behavior, and your NTP status proves your clocks are fine.**

## What's actually happening

Stripe explicitly states in their webhook docs that **events within a delivery batch may arrive in any order**. Your logs show this clearly:

- `order.created` was timestamped **first** (10:15:18Z) but arrived 16 seconds later
- `order.paid` was timestamped **after** (10:15:21Z) but arrived 12 seconds later
- Both were delivered in the same webhook batch (~1 second apart)

The 3.8-second difference in delivery latency caused the reversal. Your NTP status (0.000000023 seconds drift) is essentially perfect—not the problem.

The timing windows (10:15-10:16 UTC, 22:45-22:46 UTC) and low rate (4/2400 orders) suggest Stripe batched these during a brief high-volume spike.

## Why the proposed fixes are wrong

| Proposal | Problem |
|----------|---------|
| **NTP sync checks** | Your clocks are already synced. Monitoring perfect sync doesn't help. |
| **5-second delay** | Band-aid that adds latency to every webhook for a 0.17% issue. Won't reliably solve it—sometimes events will still be out of order. |

## The correct fix

Your webhook handler is **not idempotent**. It assumes events arrive in order and fails hard when they don't. Fix that:

```typescript
async function handleOrderPaid(order: any) {
  const existing = await orderRepository.findByStripeId(order.id);
  
  if (!existing) {
    // Option A: Queue for retry with exponential backoff
    await eventQueue.enqueue({
      type: 'order.paid',
      order,
      timestamp: new Date(),
      retries: 0,
    });
    return; // Don't fail; let the retry mechanism handle it
  }
  
  await orderRepository.updateStatus(order.id, 'paid');
}
```

**Better:** Process events in timestamp order, not receipt order:

```typescript
webhookRouter.post('/stripe', express.raw({ type: 'application/json' }), async (req, res) => {
  const sig = req.headers['stripe-signature'];
  let event: Stripe.Event;

  try {
    event = stripe.webhooks.constructEvent(req.body, sig, process.env.STRIPE_WEBHOOK_SECRET);
  } catch (err) {
    return res.status(400).send(`Webhook signature verification failed`);
  }

  // Parse batch and sort by event.created timestamp
  const events = Array.isArray(req.body) ? req.body : [event];
  const sortedEvents = events.sort((a, b) => a.created - b.created);

  for (const evt of sortedEvents) {
    await processEvent(evt);
  }

  res.status(200).json({ received: true });
});
```

**Best:** Use an **idempotent event queue** with `event.created` ordering:
- Store events with a deduplication key (Stripe's `event.id`)
- Process in `event.created` order, not receipt order
- Retry failed events (missing orders will exist after retries)
- Guarantee exactly-once processing per event

The root cause is that Stripe's batching behavior is documented and expected. Your handler's failure mode was never handling missing dependencies gracefully.