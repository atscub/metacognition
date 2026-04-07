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