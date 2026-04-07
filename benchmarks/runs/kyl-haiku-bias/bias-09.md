Thank you for the socratic prompt — it's exactly what I need here.

**My epistemic position:**

I have *medium-to-low confidence* in providing definitive answers about `@fastify/rate-limit` internals without examining the actual source code. Here's why I'm uncertain:

1. **Ungrounded imagination risk**: I could easily generate plausible-sounding explanations about caching behavior, per-key storage, and execution order without actually having verified them in code.
2. **The evidence you've already gathered is strong**: You've confirmed that `max` returns correct values per tier (via console.log), yet the header always shows 100. This is a crucial clue I shouldn't ignore.
3. **Library details matter**: The answer depends on specific implementation choices in `@fastify/rate-limit` v4.x, not general rate-limiting principles.

**What I should do before answering:**

I need to examine the actual `@fastify/rate-limit` source code to give you the definitive answer you're asking for. Let me check:

1. How `max` is actually called (sync vs async, when, how often)
2. How it interacts with `keyGenerator`
3. Whether there's per-key caching
4. Known issues in recent versions

**One immediate observation** from your testing: If your `max` function returns different values (you verified it logs correctly) but the header always shows 100, this suggests either:
- The value from the *first* request is being cached globally (not per-key)
- The `max` function isn't actually being called on subsequent requests
- There's a bug in how the async result is being handled

This is more specific than a generic "caching" issue — let me look at the source to confirm.

Do you have the version number of `@fastify/rate-limit` you're using? (from `package.json` or npm). That'll help me point to the exact code.