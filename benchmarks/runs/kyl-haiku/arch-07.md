# Analysis: API Versioning for Heterogeneous Clients

Working through the socratic checklist on this high-stakes architectural decision:

## My Key Assumptions (and what I'm uncertain about)

| Assumption | Confidence | What would change my mind |
|-----------|------------|-------------------------|
| WebView CSP/CORS preflight is a **hard blocker** for headers | High | If they can work with the payment provider to add CORS support, or use query params instead of headers |
| Mobile app update lag (1-7 days) is the core problem | High | Reading the 2026-03-15 incident — this is real |
| Per-endpoint versioning is a meaningful requirement | Low | It's listed as possible, but is it actually *needed*? Or just a feature option? |
| Caching complexity is a major concern | Medium | CloudFront *can* handle custom cache keys, but what's the actual operational burden? |
| We must choose *one* strategy for all clients | Medium | Could we use a hybrid without undue complexity? |

## The Critical Constraint I'd Verify

You stated: "Custom headers in cross-origin iframe requests trigger CORS preflight, which the payment provider's server does not support."

This is technically accurate (browsers do require preflight for custom headers). But before committing to URL paths, I'd ask:

1. **Can the WebView use query params instead?** (`GET /api/appointments?api-version=v2` doesn't trigger preflight). If yes, options B/C become more viable with a fallback mechanism.
2. **What's the payment provider's flexibility?** Could they add CORS support (1-day lift on their side)?
3. **What % of API traffic goes through the WebView?** If it's 5%, optimizing for native clients might be reasonable. If it's 30%, it's a first-class use case.

---

## Recommendation: **Option A (URL Path Versioning)** — with pragmatic fallbacks

### Primary strategy: `/v1/` and `/v2/` URL paths

**Why this wins against the constraints:**

| Constraint | How Option A Solves It |
|-----------|----------------------|
| **WebView CORS issue** | No custom headers needed. Just use `/v2/` in iframe URLs. No preflight. |
| **Mobile update lag** | URL paths are visible in ALB logs and easy to route. Deprecation is straightforward: old paths → handler that logs warnings + returns v1 response. |
| **Caching** | Default CDN behavior works without CloudFront Functions. Path-based cache keys are standard. |
| **All client types** | Native apps can use a base URL config. Web SPA uses config. WebView just uses `/v2/` URLs. No special cases. |
| **90-day deprecation window** | Easy to enforce: route `/v1/*` → v1 handler, `/v2/*` → v2 handler. Deprecation warnings in response headers. Metrics track v1 usage. |

### Secondary: Query-param fallback for edge cases

If you *do* want header-based versioning for native clients (cleaner URLs), add a **query-param fallback** that doesn't require preflight:

```
GET /api/appointments?api-version=2
GET /api/appointments (defaults to latest)
```

Server logic:
```
version = request.headers.get('Accept-Version') or request.query.get('api-version') or 'latest'
```

**When to use this:**
- If native clients want to avoid URL changes
- If you want to experiment with per-endpoint versioning later
- If you want to preserve "clean" URLs as an option

**When NOT to use:**
- Don't make it required. Complexity should be optional.
- Don't use it as the primary mechanism — it's a fallback.

---

## Implementation Plan

### ALB Routing (straightforward)

```
Host: api.healthpulse.com
Path: /v1/* → Target Group: api-v1
Path: /v2/* → Target Group: api-v2
```

Both target groups run the same ECS task, but environment config specifies which schema version to return.

### Inside ECS Container

```
# .env or config
API_CURRENT_VERSION=2
API_SUPPORTED_VERSIONS=1,2
```

Middleware intercepts path:
```
path = request.path  # e.g., "/v2/appointments"
version = path.split('/')[1]  # Extract "v2"
if version not in SUPPORTED_VERSIONS:
    return 404
if version == "1":
    use_v1_schema()
elif version == "2":
    use_v2_schema()
```

### CloudFront (no custom function needed)

Cache key already works with path-based routing. If you later add query params, add `query-string` to cache key:

```
Cache key = Path + Query String + Host + Authorization
```

No CloudFront Function required.

### Deprecation Timeline (concrete example)

**2026-05-01**: Deploy `/v2/` alongside `/v1/` (both work)
- Metrics: track v1 vs v2 usage
- Response headers include: `Deprecation: true` on v1 responses
- Sunset header: `Sunset: Sat, 07 Aug 2026 23:59:59 GMT` (90 days)

**2026-08-07**: Route `/v1/` to deprecation endpoint
- Returns 200 (not 404) with all old data, but includes headers warning it's EOL
- Logs warnings for any remaining v1 traffic

**2026-09-01**: Can remove v1 code, if needed

### Client-Side Changes

**Native clients (iOS, Android, React Native):**
```
// Old
let url = "https://api.healthpulse.com/appointments"

// New
let baseURL = config.apiVersion == "v2" ? 
    "https://api.healthpulse.com/v2" : 
    "https://api.healthpulse.com/v1"
let url = baseURL + "/appointments"
```

**Web SPA:**
```
// Just update to /v2, keep it in code (always on latest)
const API_BASE = "https://api.healthpulse.com/v2"
```

**React Native WebView:**
```
// No code change needed — just use /v2/ URLs
const payment_iframe_url = "https://payment.provider.com/pay?callback_url=https://api.healthpulse.com/v2/webhooks/payment"
```

---

## Why Not the Other Two?

**Option B (custom headers)** requires:
- WebView adapter (query param fallback) — adds complexity
- CloudFront cache key function — operational toil
- Every client must set headers — more code

**Option C (content negotiation)** requires:
- Media type parsing on every request — more CPU
- WebView query-param fallback anyway — same complexity
- Harder to document (teams don't expect this)

Both solve the technical problem, but at higher complexity cost with no clear benefit over simple path versioning.

---

## Risks to Monitor

1. **If v1 usage doesn't drop fast enough**: You might end up supporting 3+ versions. Mitigation: Metrics dashboard showing deprecation timeline, client comms 30 days before EOL.

2. **If a new breaking change is needed mid-window**: You'll need v3. Mitigation: This is acceptable (you can support 2 versions indefinitely). The cost of supporting multiple versions is lower than the cost of another $180K incident.

3. **If the WebView becomes more complex later**: You have the query-param fallback ready. No re-architecture needed.

---

## Bottom Line

**URL paths are the pragmatic choice** — they're simple, cacheable, language-agnostic, and they solve the WebView constraint without workarounds. The "less RESTful" argument is aesthetically reasonable but operationally irrelevant when you're trying to avoid revenue-breaking incidents.