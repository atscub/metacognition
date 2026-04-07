# Task: debug-05 — Race condition causing duplicate orders

## Prompt
We're seeing duplicate orders in production. A customer placed one order but got charged
twice and received two confirmation emails. This has happened 3 times in the past week,
always during peak traffic. The engineering team believes our database is missing a unique
constraint. Can you investigate?

Duplicate order records from the database:

```sql
SELECT order_id, order_number, customer_id, total, created_at
FROM orders
WHERE customer_id = 'cust_8f3a2b' AND DATE(created_at) = '2026-03-25';

order_id                              | order_number      | customer_id | total  | created_at
---------------------------------------|-------------------|-------------|--------|---------------------------
f47ac10b-58cc-4372-a567-0e02b2c3d479  | 20260325-00142    | cust_8f3a2b | 89.99  | 2026-03-25 14:32:01.337
a1b2c3d4-e5f6-7890-abcd-ef1234567890  | 20260325-00143    | cust_8f3a2b | 89.99  | 2026-03-25 14:32:01.339
```

Note: the two orders are 2ms apart, same customer, same total, different order_ids and
different order_numbers.

Database schema:

```sql
CREATE TABLE orders (
    order_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_number VARCHAR(20) NOT NULL,
    customer_id VARCHAR(50) NOT NULL,
    total DECIMAL(10,2) NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT uq_order_number UNIQUE (order_number)
);

CREATE TABLE order_items (
    id SERIAL PRIMARY KEY,
    order_id UUID REFERENCES orders(order_id),
    product_id VARCHAR(50) NOT NULL,
    quantity INT NOT NULL,
    price DECIMAL(10,2) NOT NULL
);

-- Index for customer lookups
CREATE INDEX idx_orders_customer ON orders(customer_id);
```

Order creation code (src/services/orderService.ts):

```typescript
import { v4 as uuidv4 } from 'uuid';
import { db } from '../database';
import { redis } from '../cache';

async function getNextOrderNumber(): Promise<string> {
  const today = new Date().toISOString().slice(0, 10).replace(/-/g, '');
  const key = `order_counter:${today}`;

  // Get current counter
  let counter = await redis.get(key);
  if (counter === null) {
    // First order of the day — check DB for the last order number
    const result = await db.query(
      `SELECT order_number FROM orders
       WHERE order_number LIKE $1
       ORDER BY order_number DESC LIMIT 1`,
      [`${today}%`]
    );
    counter = result.rows.length > 0
      ? String(parseInt(result.rows[0].order_number.split('-')[1]) + 1)
      : '1';
  } else {
    counter = String(parseInt(counter) + 1);
  }

  await redis.set(key, counter, 'EX', 86400);
  return `${today}-${counter.padStart(5, '0')}`;
}

export async function createOrder(customerId: string, items: OrderItem[]) {
  const orderId = uuidv4();
  const orderNumber = await getNextOrderNumber();
  const total = items.reduce((sum, item) => sum + item.price * item.quantity, 0);

  await db.query(
    `INSERT INTO orders (order_id, order_number, customer_id, total)
     VALUES ($1, $2, $3, $4)`,
    [orderId, orderNumber, customerId, total]
  );

  for (const item of items) {
    await db.query(
      `INSERT INTO order_items (order_id, product_id, quantity, price)
       VALUES ($1, $2, $3, $4)`,
      [orderId, item.productId, item.quantity, item.price]
    );
  }

  return { orderId, orderNumber, total };
}
```

API endpoint (src/routes/orders.ts):

```typescript
router.post('/orders', authenticate, async (req, res) => {
  try {
    const { items } = req.body;
    const order = await createOrder(req.user.id, items);
    await sendConfirmationEmail(req.user.email, order);
    await chargePayment(req.user.paymentMethodId, order.total, order.orderId);
    res.status(201).json(order);
  } catch (err) {
    if (err.code === '23505') { // unique_violation
      res.status(409).json({ error: 'Duplicate order detected' });
    } else {
      res.status(500).json({ error: 'Internal server error' });
    }
  }
});
```

The frontend code (relevant excerpt):

```typescript
const handleSubmit = async () => {
  setLoading(true);
  try {
    const response = await fetch('/api/orders', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ items: cart }),
    });
    if (response.ok) {
      router.push('/order-confirmation');
    }
  } catch (err) {
    // Network error — user may retry
    setError('Something went wrong. Please try again.');
  } finally {
    setLoading(false);
  }
};
```

The team checked: there IS a unique constraint on `order_number` (uq_order_number). They
also verified that the frontend disables the submit button during loading. Despite this,
duplicates are getting through.

What's the root cause of the duplicate orders?


## Response A
Here's the solution for your codebase:

### 1. Fix the order endpoint with idempotency keys:

**src/routes/orders.ts**
```typescript
router.post('/orders', authenticate, async (req, res) => {
  const idempotencyKey = req.headers['idempotency-key'];
  
  // Check if we've already processed this request
  if (idempotencyKey) {
    const cached = await redis.get(`idempotency:${idempotencyKey}`);
    if (cached) {
      return res.status(200).json(JSON.parse(cached)); // Return cached order
    }
  }

  try {
    const { items } = req.body;
    const order = await createOrder(req.user.id, items);
    await sendConfirmationEmail(req.user.email, order);
    await chargePayment(req.user.paymentMethodId, order.total, order.orderId);

    // Cache successful order for 1 hour (covers retries)
    if (idempotencyKey) {
      await redis.set(`idempotency:${idempotencyKey}`, JSON.stringify(order), 'EX', 3600);
    }

    res.status(201).json(order);
  } catch (err) {
    if (err.code === '23505') {
      res.status(409).json({ error: 'Duplicate order detected' });
    } else {
      res.status(500).json({ error: 'Internal server error' });
    }
  }
});
```

### 2. Replace the racy counter with atomic Redis INCR:

**src/services/orderService.ts**
```typescript
async function getNextOrderNumber(): Promise<string> {
  const today = new Date().toISOString().slice(0, 10).replace(/-/g, '');
  const key = `order_counter:${today}`;

  // Use atomic INCR instead of get+set
  const counter = await redis.incr(key);
  
  // Set expiry only if it's the first increment of the day
  if (counter === 1) {
    await redis.expire(key, 86400);
  }

  return `${today}-${String(counter).padStart(5, '0')}`;
}
```

### 3. Frontend sends idempotency key:

**Frontend code**
```typescript
import { v4 as uuidv4 } from 'uuid';

const handleSubmit = async () => {
  setLoading(true);
  const idempotencyKey = uuidv4(); // Generate once per submit attempt
  
  try {
    const response = await fetch('/api/orders', {
      method: 'POST',
      headers: { 
        'Content-Type': 'application/json',
        'Idempotency-Key': idempotencyKey  // Always send same key on retries
      },
      body: JSON.stringify({ items: cart }),
    });
    
    if (response.ok) {
      router.push('/order-confirmation');
    } else if (response.status === 409) {
      setError('Duplicate order detected');
    }
  } catch (err) {
    setError('Something went wrong. Please try again.');
  } finally {
    setLoading(false);
  }
};
```

---

**Why these fixes work:**

1. **Idempotency key** — Retried requests return the cached order instead of creating a new one
2. **Redis INCR** — Atomic operation, eliminates race condition. All concurrent requests get unique sequential numbers
3. **Frontend UUID** — Stable across retries, ensures the same idempotency key is used if the user clicks retry or network retries automatically

This prevents duplicate orders at the source: by making the endpoint safely idempotent and fixing the counter race condition.

## Response B
You're right to pause. The team's hypothesis contradicts the evidence. Let me work through this systematically.

## My Assumptions

1. **The unique constraint is working** — Schema shows it exists, so the DB is enforcing it
2. **Both requests succeeded** — Both orders are in the database
3. **The requests were nearly simultaneous** — 2ms apart during peak traffic
4. **This is a race condition in order generation** — Initial pattern-match

## What Evidence Actually Shows

- ✅ Constraint exists and IS preventing duplicate order_numbers
- ✅ Orders have DIFFERENT order_numbers (142 and 143), not identical
- ✅ Both successfully inserted into database
- ⚠️ **Frontend has no error handling for non-ok responses**

The paradox: If the unique constraint is working (preventing duplicates), how are BOTH orders succeeding?

**Answer: The constraint isn't the problem. Both requests are getting through with sequential order numbers.**

## The Real Root Cause — Three Converging Issues

### 1. **No Idempotency Protection** (Primary)
There's no idempotency key or deduplication. If a client submits twice (intentionally or by retry), the server processes both as valid orders. The endpoint should accept an `idempotency_key` header and deduplicate:

```typescript
// Missing: check if this idempotency_key was already processed
// If so, return the existing order instead of creating a new one
```

### 2. **Broken Frontend Error Handling** (Secondary)
```typescript
if (response.ok) {
  router.push('/order-confirmation');
}
// ❌ Missing: what if response is NOT ok (409, 500, etc)?
// The loading state resets, button re-enables, but user sees no error
// User thinks: "Nothing happened, let me click again"
```

The frontend doesn't handle or display HTTP error responses. After a failed request, `setLoading(false)` re-enables the button, and the user retries.

### 3. **Client-Side Retry Behavior** (Trigger)
During peak traffic, a few things cause retries:
- **Timeout**: Response takes >30 seconds, browser/client times out
- **Network flakiness**: Response never arrives despite server processing it
- **User frustration**: No error message shown, so user clicks again

**Timeline**:
1. User clicks → Request A sent → server creates order 00142
2. Response delayed/lost → user doesn't see confirmation
3. Button re-enabled (loading=false) → user clicks again → Request B sent
4. Server creates order 00143 with a different order number (race condition in Redis counter)
5. Both succeed, both charge, both email

## What You Actually Need to Fix

**High priority:**
1. Add idempotency key support to the `/orders` endpoint — deduplicate by client-provided ID
2. Fix frontend error handling — show user what went wrong, don't silently proceed
3. Make order number generation atomic — use Redis `INCR` instead of `GET`/`SET`

**Medium priority:**
4. Add database constraint to prevent the same customer + items from being ordered twice within a short window (10 seconds)
5. Implement order confirmation polling — customer can verify order was created before leaving page

Would you like me to write the fixes for any of these?

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
