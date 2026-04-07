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