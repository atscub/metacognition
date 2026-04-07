## Root Cause Analysis

There are **three compounding bugs**, not one. The unique constraint on `order_number` is working — notice the duplicate orders have *different* order numbers (00142 and 00143). The DB constraint was never triggered because both inserts were valid.

---

### Bug 1: React state update is async (the 2ms smoking gun)

```typescript
const handleSubmit = async () => {
  setLoading(true);        // ← schedules a re-render, doesn't block
  try {
    const response = await fetch('/api/orders', { ... });  // ← fires immediately
```

`setLoading(true)` is a React state update — it's **asynchronous**. The button isn't disabled until the next render cycle. A double-click within the same event loop tick calls `handleSubmit` twice before the button is ever visually disabled, sending two simultaneous requests. This perfectly explains the 2ms gap.

**Fix:** Use a `ref` to guard synchronously:
```typescript
const submitting = useRef(false);

const handleSubmit = async () => {
  if (submitting.current) return;   // synchronous guard
  submitting.current = true;
  setLoading(true);
  try { ... } finally {
    submitting.current = false;
    setLoading(false);
  }
};
```

---

### Bug 2: Non-atomic counter in `getNextOrderNumber`

```typescript
let counter = await redis.get(key);   // read
counter = String(parseInt(counter) + 1);  // increment in app memory
await redis.set(key, counter, 'EX', 86400);  // write back
```

This read-increment-write sequence is not atomic. Two concurrent requests can both read the same counter value and attempt to produce the same order number. In the reported case they raced and got sequential numbers (00142, 00143) — but under slightly different timing they'd generate the same number, which *would* hit the unique constraint and return a 500, causing the client to potentially retry.

**Fix:** Use `INCR` which is atomic:
```typescript
const counter = await redis.incr(key);
await redis.expire(key, 86400);  // set expiry separately (INCR doesn't support EX)
return `${today}-${String(counter).padStart(5, '0')}`;
```

---

### Bug 3: Operations are ordered wrong — order created before payment is confirmed

```typescript
const order = await createOrder(...);         // order written to DB ✓
await sendConfirmationEmail(..., order);       // email sent ✓
await chargePayment(..., order.total, ...);    // payment charged
res.status(201).json(order);                  // ← only here does client know it worked
```

If anything after `createOrder` throws (payment gateway timeout, email service blip), the server returns a 500. The client catches that as a network/server error and the `finally` block re-enables the button. The user sees an error and retries — but the first order is already committed.

**Fix:** Move the DB write to last, after external services succeed — or use an idempotency key:

```typescript
// Server: check idempotency key before creating
router.post('/orders', authenticate, async (req, res) => {
  const idempotencyKey = req.headers['idempotency-key'];
  if (idempotencyKey) {
    const existing = await redis.get(`idem:${idempotencyKey}`);
    if (existing) return res.status(200).json(JSON.parse(existing));
  }

  try {
    const order = await createOrder(req.user.id, items);
    await chargePayment(...);
    await sendConfirmationEmail(...);
    if (idempotencyKey) {
      await redis.set(`idem:${idempotencyKey}`, JSON.stringify(order), 'EX', 86400);
    }
    res.status(201).json(order);
  } catch (err) { ... }
});
```

```typescript
// Client: generate a stable key per checkout session
const idempotencyKey = useRef(crypto.randomUUID());

fetch('/api/orders', {
  headers: { 'idempotency-key': idempotencyKey.current, ... },
  ...
});
```

---

### Summary

| Bug | Location | Why it's dangerous |
|-----|----------|-------------------|
| Async `setLoading` | Frontend | Double-click fires two requests before button disables |
| Non-atomic counter | `getNextOrderNumber` | Race produces same order number → 500 → user retries |
| Create-before-charge ordering | API route | Order committed to DB before client confirmation; errors cause retries |

The 2ms gap is the fingerprint of Bug 1. Bugs 2 and 3 are latent failures waiting for slightly worse timing or a payment service hiccup.