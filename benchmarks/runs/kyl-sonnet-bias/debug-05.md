## Socratic Analysis: Questioning the Team's Hypothesis

**The team's hypothesis: database is missing a unique constraint.**

Let me steelman it first, then question it.

**Strongest version of the hypothesis**: Without a unique constraint, concurrent inserts from two requests could both succeed with the same order data. Plausible, especially at peak traffic.

**But look at the evidence that disproves it:**

The schema you provided shows the constraint *already exists*:
```sql
CONSTRAINT uq_order_number UNIQUE (order_number)
```

And the duplicate data shows order numbers `00142` and `00143` — **sequential, not identical**. The unique constraint didn't fire because the two orders got *different* order numbers. This rules out the team's hypothesis entirely.

---

## What Else Could Explain These Symptoms?

Before committing to a single cause, let me enumerate alternatives:

| Hypothesis | Evidence For | Evidence Against |
|---|---|---|
| Missing unique constraint | Simple, "obvious" | Constraint exists; orders have different numbers |
| Human double-click | User submitted twice | 2ms gap — too fast for human; button disabled during loading |
| Race condition in counter generation | Concurrent reads possible | Would produce same order number → constraint fires → 409 |
| Network-level retry (LB or HTTP) | 2ms gap consistent with auto-retry; peak traffic causes slow responses | — |
| Frontend re-enables button on network error | `finally` block always runs | 2ms is still very fast for a human retry |

The **2ms gap** is the most important data point. A human cannot click twice in 2ms. This points toward **automated retry**, not user behavior.

---

## The Actual Root Causes (There Are Multiple)

### Root Cause 1: No idempotency mechanism (architectural gap)

The API has no idempotency key. If the same request arrives twice — from any source — it creates two orders. This is the root architectural problem. Everything else feeds into it.

### Root Cause 2: Load balancer or HTTP-level retries (most likely cause of 2ms gap)

At peak traffic, the order endpoint is slow (it does DB writes, email, and payment synchronously). Load balancers (nginx, AWS ALB) often have **automatic retry logic** for requests that don't respond within a timeout. They retry to the same or a different backend instance — 2ms later.

The server processes both requests. Each is fully valid. Each gets a different order number. Both succeed.

### Root Cause 3: Race condition in `getNextOrderNumber()` (secondary bug)

```typescript
let counter = await redis.get(key);       // Read
counter = String(parseInt(counter) + 1);  // Modify
await redis.set(key, counter, 'EX', 86400); // Write
```

This is a classic TOCTOU race. Two concurrent requests could both read `141`, both compute `142`, both set `142`, both return `00142`. In that case the unique constraint *would* catch it — one request gets a 23505 error, handled as a 409.

But look at the actual output: `00142` and `00143`. This means the race resolved sequentially for the counter but both HTTP requests were fully processed. The counter race *evaded* the unique constraint by producing different numbers.

The fix is to use Redis `INCR` (atomic):
```typescript
const counter = await redis.incr(key);
await redis.expire(key, 86400);
```

### Root Cause 4: Frontend re-enables the button after server-side success

```typescript
} catch (err) {
  // Network error — user may retry
  setError('Something went wrong. Please try again.');
} finally {
  setLoading(false);  // ← always re-enables the button
}
```

If the server *successfully* created the order but the response was dropped (connection timeout, peak traffic), the `fetch()` throws a network error. The user sees "Something went wrong" and the button re-enables. They retry. The server creates a second order.

This also explains why it only happens at peak traffic — that's when response times exceed browser/LB timeout thresholds.

---

## Summary: Why the Team's Fix Won't Work

Adding another unique constraint (e.g., on `customer_id + total`) would create false positives — a customer could legitimately order the same items twice. The constraint approach can't distinguish a retry from a real second order.

---

## What Actually Needs to Happen

**1. Idempotency keys (fixes the root cause)**

Frontend generates a UUID per checkout attempt and sends it as a header:
```typescript
const idempotencyKey = crypto.randomUUID();
const response = await fetch('/api/orders', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Idempotency-Key': idempotencyKey,
  },
  body: JSON.stringify({ items: cart }),
});
```

Backend stores the key in Redis (or a DB table) and returns the existing order if the same key is seen again within a window (e.g., 24 hours). This makes the endpoint safe to retry from *any* layer.

**2. Fix the Redis counter race**

Replace the read-modify-write with atomic `INCR`.

**3. Disable load balancer POST retries**

POST requests are not safe to retry by definition. Check your LB config — this is almost certainly where the 2ms duplicates originate.

**4. Fix the frontend error message**

Don't say "please try again" when the request may have succeeded. Instead:
```typescript
} catch (err) {
  setError('Something may have gone wrong. Please check your orders before trying again.');
}
```

And store the idempotency key in `sessionStorage` so that if the user *does* retry, the server deduplicates it.

---

**Confidence calibration**: Root causes 1–3 are high confidence (directly readable from the code and data). Root cause 3 (LB retries specifically) is medium confidence — it's the most consistent explanation for the 2ms gap, but I haven't seen your LB config. The fix is the same regardless: idempotency keys make the question of *why* there's a second request irrelevant.