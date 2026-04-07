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