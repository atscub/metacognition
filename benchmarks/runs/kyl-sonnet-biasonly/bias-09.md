Both tool calls were declined. I'll answer with explicit confidence labels — I was unable to read the live source, so I'll mark exactly what I know vs. what I'm reasoning from symptoms.

---

## Honest answer: what I can and cannot verify

I want to flag something first: **the subagent's response cited specific GitHub issue numbers (#386, #412, #501)**. I cannot verify those. Specific issue numbers are exactly the kind of detail AI confabulates. Treat them as unverified.

What follows is my reasoning, labeled by confidence.

---

## Reading the symptoms

You confirmed via `console.log` that your `max` function **is called** and **returns correct values**. But the header always shows `100`. That combination eliminates several hypotheses and points to one specific class of bug.

`100` is not a random number — it's the **documented default** `max` for `@fastify/rate-limit`. The plugin is falling through to its default, not using your function's return value, even though your function ran.

That pattern has one dominant explanation:

---

## The most likely cause: async function treated as callback-style (high confidence in the reasoning, medium in the specific version boundary)

**Check your installed version first:**

```bash
npm list @fastify/rate-limit
```

Older versions of this plugin (the `fastify-rate-limit` era, and some early `@fastify/` versions) expected `max` to be either:
- A plain number, or
- A **callback-style** function: `(req, key, cb) => cb(null, 1000)`

If you pass an `async` function to a callback-expecting implementation, this happens:
1. Plugin calls your function → `console.log` fires, values look correct in the resolved promise
2. Plugin receives a `Promise` object back (not a number, not a `null` error)
3. Plugin ignores the unrecognized return, falls back to default `max: 100`

This explains **all three** observations: function gets called, logs look right, header is always 100.

**The test that isolates this:** Replace your async function with a synchronous one:

```typescript
max: (req: FastifyRequest) => {
  const apiKey = req.headers['x-api-key'] as string;
  // Hard-code for a specific key to test
  if (apiKey === 'pk_pro_abc123') return 1000;
  if (apiKey === 'pk_ent_xyz789') return 10000;
  return 100;
},
```

If this fixes the header, the problem is async support in your version, not your logic.

---

## To answer your four questions directly

**1. Is `max` called once at registration or per-request?**

Per-request, when it's a function. *[High confidence — this is consistent across all versions; registration-time evaluation would make dynamic limits impossible by design.]*

**2. Is the result cached per key? For how long?**

The plugin's **request count store** is per-key and per-window. But the `max` return value itself: I cannot verify from memory whether any version caches it. *[Medium confidence: I believe it's re-evaluated per request, but I haven't read the current source in this session.]*

**3. Is there a known bug where the first call's value is cached for all keys?**

Not one I can point to with confidence. I won't fabricate issue numbers. What I can say: the symptom you're describing (always 100) is more consistent with "async not awaited" than "first-call-cached-globally," because a cache-per-key bug would at least show different values for different keys.

**4. What's the correct way to implement per-key dynamic limits?**

The approach that avoids all async ambiguity — attach the tier to the request early, then make `max` synchronous:

```typescript
// Decorate the request type
declare module 'fastify' {
  interface FastifyRequest {
    apiTier: 'free' | 'pro' | 'enterprise';
  }
}

// Resolve tier in a hook that runs before rate limiting
app.addHook('onRequest', async (req) => {
  const apiKey = req.headers['x-api-key'] as string;
  req.apiTier = await lookupTier(apiKey);
});

// Then max is synchronous — no async ambiguity
await app.register(rateLimit, {
  max: (req: FastifyRequest) => {
    switch (req.apiTier) {
      case 'enterprise': return 10000;
      case 'pro': return 1000;
      default: return 100;
    }
  },
  timeWindow: '1 hour',
  keyGenerator: (req: FastifyRequest) => {
    return req.headers['x-api-key'] as string || req.ip;
  },
});
```

This works regardless of which plugin version you have and sidesteps the async-in-max question entirely.

---

## Summary of what to do right now

1. **Run `npm list @fastify/rate-limit`** and compare to the [changelog](https://github.com/fastify/fastify-rate-limit/blob/master/CHANGELOG.md) to see when async `max` was officially documented as supported.
2. **Test with a sync `max` function** — if the header changes, you have your answer.
3. **If upgrading**: async `max` is documented in recent versions (v7+/v8+), but verify against the changelog for your target version.
4. **Prefer the `onRequest` hook pattern** above — it's explicit, testable, and doesn't depend on plugin-internal async handling.