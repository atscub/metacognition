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