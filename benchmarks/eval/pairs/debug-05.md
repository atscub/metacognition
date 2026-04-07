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
## Root Cause Analysis

The engineering team misdiagnosed this. The unique constraint on `order_number` exists and works — the problem is that **two concurrent requests are both succeeding and producing *different* order numbers**, so the constraint never fires. There are multiple compounding bugs.

---

### Primary cause: Non-atomic counter + no idempotency

`getNextOrderNumber()` uses a read-modify-write pattern that is not atomic:

```typescript
let counter = await redis.get(key);   // Both requests read 141
counter = String(parseInt(counter) + 1); // Both compute 142... but:
await redis.set(key, counter, ...);   // A writes 142, B reads 142 next time → writes 143
```

Under concurrent load, two requests racing through this function will usually get *sequential* counters (142 and 143), not the *same* counter. The unique constraint on `order_number` only catches the same-value collision — it doesn't know that 142 and 143 both came from the same customer submitting once.

The API has **no idempotency mechanism**. Every POST creates a new order unconditionally. There is nothing to detect "this is the same logical request arriving twice."

---

### Why the request fires twice (2ms gap)

The 2ms gap is too fast for a human double-click. This is almost certainly a **load balancer or mobile client retry**. When the server takes too long under peak traffic, the client-side timeout fires, the `catch` block runs:

```typescript
} catch (err) {
  // Network error — user may retry
  setError('Something went wrong. Please try again.');
} finally {
  setLoading(false);  // ← re-enables the submit button
}
```

`setLoading(false)` runs in `finally`, so even if the server successfully processed the first request, a network timeout means the client re-enables the submit button and shows an error. The server already created order 142 and charged the customer. The retry creates order 143 and charges them again.

---

### Secondary bug: Operations are in the wrong order

```typescript
await sendConfirmationEmail(...);     // ← email sent first
await chargePayment(...);             // ← then charged
res.status(201).json(order);
```

If `chargePayment` fails, the customer already received a confirmation email for an unpaid order. Conversely, if the response is lost after charging but before the client receives it, the retry double-charges. The order should be: **charge → insert → email → respond**.

---

### Summary of bugs

| # | Bug | Impact |
|---|-----|--------|
| 1 | Non-atomic `redis.get` + increment + `redis.set` | Under heavy concurrency, could produce same order number; unique constraint is the only guard |
| 2 | No idempotency key | Two requests with different order numbers both succeed — constraint never fires |
| 3 | `finally { setLoading(false) }` re-enables submit on network error | Client retries after server already succeeded |
| 4 | Email sent before payment | Misleading confirmations for uncharged orders |

---

### Fixes

**1. Atomic counter** — replace the read-modify-write with `INCR`:
```typescript
const counter = await redis.incr(key);
await redis.expire(key, 86400);
```

**2. Idempotency key** — the client generates a UUID per checkout session and sends it as a header. The server stores it with a unique constraint:

```sql
ALTER TABLE orders ADD COLUMN idempotency_key UUID UNIQUE;
```

```typescript
// Client: generate once per checkout session, persist in sessionStorage
const idempotencyKey = sessionStorage.get('checkout_key') ?? crypto.randomUUID();

// Server: return 200 with existing order if key already exists
const existing = await db.query(
  'SELECT * FROM orders WHERE idempotency_key = $1', [idempotencyKey]
);
if (existing.rows.length) return res.status(200).json(existing.rows[0]);
```

**3. Fix frontend error handling** — don't re-enable submit on ambiguous failure:
```typescript
} catch (err) {
  // Don't re-enable the button — order may have succeeded
  setError('Something went wrong. Check your email or contact support.');
  // Do NOT call setLoading(false) here
}
```

**4. Correct the operation order**:
```typescript
await chargePayment(...);   // 1. Charge
await db.query(INSERT ...); // 2. Record
await sendEmail(...);       // 3. Confirm
res.status(201).json(...);  // 4. Respond
```

The idempotency key (fix #2) alone would have prevented all three production incidents. The other fixes eliminate the underlying races that make retry behavior dangerous.

## Response B
## Applying Socratic Mode Before Hypothesizing

**Pause — the engineering team's framing is already falsified by the data.**

Before explaining the root cause, let me make this explicit:

### The Team's Hypothesis is Wrong

The team believes: *"the database is missing a unique constraint."*

The data refutes this on two counts:
1. `uq_order_number` **exists** in the schema
2. The two duplicate records have **different** order numbers (`00142` vs `00143`) — a unique constraint on `order_number` would not have caught this even if one were added

This is an authority-bias trap: the team offered a diagnosis, and it's easy to accept it and look for supporting evidence. Instead, let me reason from the symptoms.

---

## What the Evidence Actually Shows

| Observation | Implication |
|---|---|
| 2ms gap between orders | Not a human action — users cannot click twice in 2ms |
| Different order numbers | `getNextOrderNumber()` was called twice and returned sequential values |
| Same customer, same total | The same HTTP request body was processed twice |
| Happens during peak traffic | Latency increases under load, triggering infrastructure timeouts |

**The 2ms gap is the critical clue.** This is not a user retry. This is infrastructure.

---

## Root Cause: Non-idempotent Endpoint + Infrastructure Retry

Under peak load, response latency increases. Load balancers (AWS ALB, nginx, etc.) have retry configurations — when a response doesn't arrive within their timeout, they retransmit the request to another upstream. Since `POST /orders` is not idempotent, both requests complete independently:

```
Client → LB → Server A: creates order 00142 (slow, LB times out)
             ↘ Server B: creates order 00143 (LB retry, succeeds fast)
              
Both inserts succeed. Two emails. Two charges.
```

The unique constraint on `order_number` cannot help here because `getNextOrderNumber()` generates a different number for each request.

---

## Secondary Bug: Non-Atomic Redis Counter

Look at `getNextOrderNumber()`:

```typescript
let counter = await redis.get(key);   // read
// ...compute new value...
await redis.set(key, counter, 'EX', 86400);  // write
```

This is a **read-modify-write without atomicity**. Under concurrent load, two requests can both read the same value and produce the same order number — in which case the `uq_order_number` constraint *would* fire a `23505` error, but the error handler returns a `409` that the client likely treats as a failure and retries again.

It should use Redis `INCR` (atomic):

```typescript
const counter = await redis.incr(key);
await redis.expire(key, 86400);
```

---

## Why the Frontend "fix" Doesn't Help

The team says the button is disabled during loading. That's irrelevant for 2ms gaps — this never reached the user. The network error path in the frontend is a *separate* problem (if the response times out, `catch` fires, `setLoading(false)` runs, and the button re-enables for user retry — seconds later, not 2ms).

---

## The Actual Fixes, in Priority Order

**1. Add idempotency keys (fixes the root cause)**

The client should send a stable `Idempotency-Key` header on submission, and the server should deduplicate on it:

```typescript
// Frontend: generate once per checkout session
const idempotencyKey = crypto.randomUUID(); // stored in component state, not regenerated on retry

fetch('/api/orders', {
  headers: { 'Idempotency-Key': idempotencyKey, ... }
})
```

```typescript
// Server: check before inserting
const existing = await redis.get(`idem:${idempotencyKey}`);
if (existing) return res.status(200).json(JSON.parse(existing));

// ... create order ...
await redis.set(`idem:${idempotencyKey}`, JSON.stringify(order), 'EX', 86400);
```

**2. Fix the Redis counter to use `INCR`** (fixes the race condition independently)

**3. Add a database-level deduplication guard** (defense in depth)

A partial unique index on `(customer_id, total, created_at::date)` won't work well, but a short-window dedup check or a `(customer_id, idempotency_key)` unique constraint would.

**4. Move payment + email inside a proper transaction or saga** — currently an order can be inserted but payment can fail, leaving an unpaid order with no rollback.

---

## What Adding a Unique Constraint Would Do

If you added `UNIQUE(customer_id, total)` or similar: it would create false positives (a customer legitimately ordering the same item twice) and still not prevent the race condition in a 2ms window depending on transaction isolation level. It treats the symptom, not the cause.

The missing primitive here is **idempotency**, not uniqueness.

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
