I need to give you a straightforward answer: **I can't provide a definitive explanation without checking the actual source code of `@fastify/rate-limit`**, and the behavior you're describing suggests something non-obvious is happening that requires verification against the real implementation.

However, I can help you debug this systematically and point you toward the actual answer.

## How to get a definitive answer

**The fastest way:** Check the actual plugin source code.

```bash
# Find where it's installed
npm ls @fastify/rate-limit

# Open the source
cd node_modules/@fastify/rate-limit
cat package.json  # Check version
cat lib/index.js  # or src/index.ts
```

Look specifically for:
1. When `max` is called (at registration? per-request? per-key-per-window?)
2. How the result is cached and keyed
3. Whether there's any caching layer that could cause the first value to stick

## Debugging your specific issue

Add aggressive logging to isolate where the bug is:

```typescript
await app.register(rateLimit, {
  max: async (req: FastifyRequest) => {
    const apiKey = req.headers['x-api-key'] as string;
    const tier = await lookupTier(apiKey);
    const limit = (() => {
      switch (tier) {
        case 'enterprise': return 10000;
        case 'pro': return 1000;
        default: return 100;
      }
    })();
    
    console.log('[rate-limit] max() called:', {
      apiKey: apiKey?.slice(0, 10),
      tier,
      returnedLimit: limit,
      timestamp: new Date().toISOString(),
    });
    
    return limit;
  },
  timeWindow: '1 hour',
  keyGenerator: (req: FastifyRequest) => {
    const key = req.headers['x-api-key'] as string || req.ip;
    console.log('[rate-limit] keyGenerator():', { key: key?.slice(0, 10) });
    return key;
  },
});
```

Then test with different keys in sequence and watch the console:

```bash
curl -H "x-api-key: pk_pro_abc123" http://localhost:3000/api/data -I
curl -H "x-api-key: pk_ent_xyz789" http://localhost:3000/api/data -I
curl -H "x-api-key: pk_free_123xyz" http://localhost:3000/api/data -I
```

**Questions to answer from the logs:**
- Is `max()` called once or multiple times?
- Is it called per-request or only the first time?
- Are different tier values actually being returned?
- Is `keyGenerator` being called for each request?

## Known pattern that **does** work reliably

If the plugin has a bug with async `max`, a workaround is to move the tier lookup outside and use a cache:

```typescript
const tierCache = new Map<string, string>();

const getTier = async (apiKey: string) => {
  if (tierCache.has(apiKey)) return tierCache.get(apiKey)!;
  const tier = await lookupTier(apiKey);
  tierCache.set(apiKey, tier);
  return tier;
};

await app.register(rateLimit, {
  max: async (req: FastifyRequest) => {
    const apiKey = req.headers['x-api-key'] as string;
    const tier = await getTier(apiKey);
    return { enterprise: 10000, pro: 1000, default: 100 }[tier] ?? 100;
  },
  timeWindow: '1 hour',
  keyGenerator: (req: FastifyRequest) => req.headers['x-api-key'] as string || req.ip,
});
```

## Next steps

1. **Run the debug version** and share the console output — that will show whether `max()` is even being called on subsequent requests
2. **Check the source code** for your installed version to understand the caching behavior
3. **Check the GitHub issues** for `@fastify/rate-limit` — this specific problem may already be reported

Once you run the logging, you'll know exactly where the bug is. Reply with those logs and I can help you pinpoint the issue or build a workaround.