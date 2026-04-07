Looking at this carefully, I can identify the root cause. Let me trace through what's happening:

## Root Cause: **Non-idempotent API + Network Timeouts During Peak Traffic**

The duplicate orders have **different `order_id`s and different `order_number`s**, which tells us two separate `createOrder()` calls are succeeding. This means **the same customer is making two separate POST requests to `/orders`**.

Here's what's happening during peak traffic:

1. **Frontend sends POST /orders** (Request A)
2. **Backend starts processing** but network/backend latency causes slow response
3. **Frontend's fetch times out or never gets the response** (no explicit timeout, but browser/network might abort)
4. **Backend continues and completes** — order created, card charged, email sent, but response never reaches frontend
5. **Frontend error handler catches the network failure** → "Something went wrong"
6. **Customer retries** (or automatic retry happens) → **Second POST request** (Request B)
7. **Backend creates a new order** with a different `order_number` (counter incremented), charges card again, sends another email

The problem is **your API endpoint is not idempotent** — it has no way to detect and reject duplicate requests from the same customer.

## Why It Only Happens During Peak Traffic

- Normal traffic: responses are fast, no timeouts
- Peak traffic: slow backend response → fetch timeout → user retry → duplicate orders

## The Solution: Add Idempotency Keys

Your API needs to **accept an idempotency key** from the frontend to prevent this:

```typescript
// Frontend: generate a unique ID per order attempt
const handleSubmit = async () => {
  setLoading(true);
  const idempotencyKey = uuidv4(); // Unique per submit
  
  try {
    const response = await fetch('/api/orders', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Idempotency-Key': idempotencyKey, // Include in header
      },
      body: JSON.stringify({ items: cart }),
    });
    if (response.ok) {
      router.push('/order-confirmation');
    }
  } catch (err) {
    // If user retries, same idempotencyKey prevents duplicate
    setError('Network error. Please try again.');
  } finally {
    setLoading(false);
  }
};
```

```typescript
// Backend: store idempotency keys to prevent duplicate processing
async function createOrder(
  customerId: string, 
  items: OrderItem[], 
  idempotencyKey: string
) {
  // Check if we've already processed this key
  const existing = await db.query(
    'SELECT order_id FROM orders WHERE customer_id = $1 AND idempotency_key = $2',
    [customerId, idempotencyKey]
  );

  if (existing.rows.length > 0) {
    // Already processed — return the existing order
    return existing.rows[0];
  }

  // Create the order (new logic remains the same)
  const orderId = uuidv4();
  const orderNumber = await getNextOrderNumber();
  // ... insert order ...
  // ... insert items ...
  
  return { orderId, orderNumber, total };
}
```

## Also Add These Safeguards

1. **Add `idempotency_key` column to orders table:**
   ```sql
   ALTER TABLE orders ADD COLUMN idempotency_key VARCHAR(36) UNIQUE;
   ```

2. **Add explicit timeout to frontend fetch:**
   ```typescript
   const controller = new AbortController();
   const timeoutId = setTimeout(() => controller.abort(), 10000); // 10s timeout
   
   try {
     const response = await fetch('/api/orders', {
       signal: controller.signal,
       // ...
     });
   } finally {
     clearTimeout(timeoutId);
   }
   ```

3. **The race condition in `getNextOrderNumber()` is actually fine** — Redis handles it reasonably well during peak traffic, which is why you're getting sequential order numbers (142, 143) instead of duplicates.

**TL;DR**: You're not getting duplicate order_numbers; you're getting duplicate orders from retry requests that reach the backend after the frontend's request timed out. Fix it with idempotency keys.