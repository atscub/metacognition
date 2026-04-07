# Task: arch-07 — API versioning strategy for mobile and web clients

## Prompt
You are the API platform lead at HealthPulse, a telehealth company. HealthPulse has
four client applications consuming a shared REST API:

- **iOS app** (Swift, 800K installed base, ~40% on latest version)
- **Android app** (Kotlin, 1.2M installed base, ~35% on latest version)
- **React Native companion app** (for caregivers, 200K installed base)
- **Web SPA** (React, always latest version)

The API currently has no versioning. Breaking changes are coordinated by releasing
client updates simultaneously with backend deploys — a process that fails regularly
because mobile apps go through app store review (1-7 days for iOS, 1-3 days for
Android) and you cannot force users to update.

Last month's incident report:
```
2026-03-15: Backend deployed breaking change to /api/appointments endpoint
  - Renamed field: "doctor_id" → "provider_id"
  - Web SPA: updated same day, no issues
  - iOS: update submitted to App Store, approved after 4 days
  - Android: update submitted, approved after 2 days
  - React Native: update submitted to both stores
  - Result: 60% of mobile users saw broken appointment booking for 2-4 days
  - Revenue impact: estimated $180K in lost bookings
  - Rollback attempted but backend migration was not reversible
```

Current endpoint structure:
```
GET    /api/appointments
POST   /api/appointments
GET    /api/appointments/:id
GET    /api/providers
GET    /api/patients/:id/records
POST   /api/prescriptions
GET    /api/billing/invoices
```

Requirements:
- Must support at least 2 API versions simultaneously (current + previous)
- Deprecation window: minimum 90 days before removing an old version
- Mobile clients must work without forced updates for at least 6 months after a version
  is deprecated
- Web SPA should always use the latest API version
- Must work with the existing infrastructure: AWS ALB, ECS containers, CloudFront CDN
- The React Native app uses an embedded WebView for some screens (payment flow,
  document signing) that makes HTTP calls directly from the WebView context

The team has narrowed the choice to three approaches:

**A. URL path versioning**: `/v1/appointments`, `/v2/appointments`
```
Pros: Simple, cacheable, visible in logs, easy to route at the ALB level
Cons: URL proliferation, all-or-nothing version bump, clients must update base URL
```

**B. Custom header versioning**: `Accept-Version: 2`
```
Pros: Clean URLs, per-endpoint versioning possible, "more RESTful"
Cons: Headers not visible in browser, harder to cache at CDN, requires all clients
      to set custom headers on every request
```

**C. Content negotiation**: `Accept: application/vnd.healthpulse.v2+json`
```
Pros: Fully RESTful, per-resource versioning, follows HTTP semantics
Cons: Complex, harder to document, requires media type parsing on server
```

Additional context:
- The iOS app uses URLSession, which supports custom headers
- The Android app uses Retrofit with OkHttp, which supports custom headers
- The React Native app uses fetch API, which supports custom headers
- The WebView-embedded payment flow uses a stripped-down HTTP client that sends
  requests via `window.fetch()` in a restricted iframe context. The iframe's Content
  Security Policy was set by the payment provider and cannot be modified. Custom
  headers in cross-origin iframe requests trigger CORS preflight, which the payment
  provider's server does not support.
- CloudFront CDN cache key currently includes: URL path, Host header, Authorization
  header. Adding custom headers to the cache key requires a CloudFront Function.

Recommend a versioning strategy. Address the specific constraints of each client type
and provide an implementation plan including ALB routing rules.


## Response A
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

## Response B
# Recommendation: URL Path Versioning (Primary) + Optional Header Support

**Recommend A (URL path versioning), but not in isolation.** The React Native WebView constraint is the deciding factor—it cannot send custom headers without breaking the payment flow. A hybrid approach is the only solution that works for all client types.

## Why A Alone Won't Work, and Why A + B Works

Your three approaches are not equally viable:

| Constraint | Path | Header | Content Negotiation |
|-----------|------|--------|---------------------|
| WebView payment iframe (no CORS preflight) | ✅ Works | ❌ CORS preflight fails | ❌ CORS preflight fails |
| Mobile clients (old versions stuck) | ✅ All can be on same path | ✅ All can set headers | ✅ All can set headers |
| Cacheable by CloudFront | ✅ Yes | ⚠️ Requires cache key modification | ⚠️ Requires cache key modification |
| Visible in logs/ALB | ✅ Yes | ❌ Hidden in headers | ❌ Hidden in headers |
| Per-endpoint versioning | ❌ All-or-nothing | ✅ Per-endpoint | ✅ Per-resource |

**The WebView is your hard constraint.** React Native payment flow can only use URL paths. Rather than force all clients to downgrade to URL paths, make URL paths the **required baseline** and allow header versioning as an **optional optimization** for clients that support it.

---

## Proposed Strategy: Dual-Route Architecture

### 1. **Primary: URL Path Versioning** (`/v1/`, `/v2/`)
- **All clients must support this** — it's the only mechanism that works everywhere
- Default behavior: version is embedded in the URL path
- Mobile apps (old and new) can run simultaneously on the same endpoint

### 2. **Secondary: Custom Header with Fallback** (`Accept-Version: 2`)
- Supported for clients that *can* send headers (iOS, Android, Web, React Native non-WebView)
- Unused by the payment iframe—it simply doesn't send the header and falls back to URL path
- Enables future per-endpoint versioning without client URL changes

### 3. **Header Request Routing**
```
Route pattern:
  /api/{endpoint} + Accept-Version header → use header-specified version
  /api/{endpoint} (no header) → use URL default
  /v1/api/{endpoint} → explicitly use v1
  /v2/api/{endpoint} → explicitly use v2
```

---

## Implementation Plan

### Phase 1: ALB & Service Layer

**ALB Routing Rules** (single rule, handler-side switching):
```
Path: /api/* OR /v1/* OR /v2/*
Forward to: ECS target group (single, version-aware handler)
```

**Handler Router Logic** (pseudo-code):
```python
def resolve_version(request):
    # URL path takes explicit priority
    if match := re.match(r'^/v(\d+)/', request.path):
        return match.group(1)  # Explicit version in path
    
    # Fall back to Accept-Version header
    if version := request.headers.get('Accept-Version'):
        return version  # Per-endpoint versioning
    
    # Default: latest version
    return '2'

def handle_request(request):
    version = resolve_version(request)
    handler = VERSION_HANDLERS[version]
    return handler(request)
```

**ECS Service Structure** (single deployment with version strategy):
```
POST /api/appointments
  → resolve_version(request)
  → v1_handler (old field names) | v2_handler (new field names)
  → return 200

GET /v1/api/appointments  (explicit URL)
  → version = 1
  → v1_handler (old field names)
  → return 200

GET /api/appointments?Accept-Version: 1
  → version = 1 (from header)
  → v1_handler (old field names)
  → return 200
```

### Phase 2: Client Configuration

**iOS/Android/Web Configuration** (base URL update at deployment):
```swift
// Old version (v1):
let baseURL = "https://api.healthpulse.com/v1"

// New version (v2):
let baseURL = "https://api.healthpulse.com/v2"
```

**React Native (Non-WebView Code)**:
```javascript
// Use header-based versioning for flexibility
const headers = {
  'Accept-Version': '2',
  ...
};
```

**React Native WebView (Payment Iframe)** — no changes needed:
```javascript
// Payment provider iframe is unaware of versioning
// ALB handler defaults to v2
// Old clients in iframe get defaulted to v1 (see Phase 3)
```

### Phase 3: Deprecation & Backward Compatibility

**At launch (v2 release):**
- Deploy v2 handler alongside v1 handler in same container
- ALB routes all unversioned requests (`/api/*`) to v2
- Mobile apps submit v2 updates to app stores
- Web SPA pushes `/v2/` base URL

**During app store review (days 1-7):**
- Old mobile clients still work: they send requests to `/api/` → ALB defaults to v1 ✅
- New mobile clients use `/v2/` → no breakage
- React Native WebView (embedded in both old and new apps) uses `/api/` → defaults to v1 for old app, v2 for new app ✅

**After 90 days (deprecation announcement):**
- Log warning when v1 accessed: `"API v1 deprecated. Please update to v2. Support ends 2026-08-01."`
- Mobile clients see warning, encourage update through in-app messaging

**After 180 days (v1 removal):**
- Shut down v1 handler
- All old clients now broken → app reviews force user to update
- No revenue impact because users know they must update (6 month window given)

### Phase 4: CloudFront Caching

**Update cache key** to include version detection:
```
Cache key includes:
  - URL path (already included) ✅
  - Accept-Version header (add to cache key)
  - Authorization header (already included) ✅
```

**CloudFront Function** (optional, for header-based versioning optimization):
```javascript
function(request) {
  var version = request.headers['accept-version']?.value || '2';
  request.headers['x-api-version'] = { value: version };
  return request;
}
```

This ensures `/api/appointments` with `Accept-Version: 1` has separate cache entry from `Accept-Version: 2`.

---

## Handling the Incident Scenario

**If a breaking change to `/api/appointments` is needed:**

1. Design v2 endpoint with new field names
2. Deploy to `/v2/appointments` and via `Accept-Version: 2` header
3. Rollout plan:
   - Day 1: Backend deployed, v2 available
   - Day 1: Web SPA updates → uses `/v2/` → works immediately
   - Day 1-7: iOS update in review
   - Day 1-3: Android update in review
   - Days 1-7: Old mobile clients use `/v1/` → continue working ✅ **No revenue loss**
   - Day 4+: iOS update approved → new installs use v2
   - Day 3+: Android update approved → new installs use v2
   - No forced rollback needed—both versions coexist

**Estimated revenue impact: $0** (vs $180K with current approach)

---

## Why NOT the Alternatives Alone

| Approach | Failure Mode |
|----------|-------------|
| **B only** (Custom headers) | React Native payment iframe breaks immediately. WebView has CSP restrictions + CORS preflight issues. Unfixable without payment provider cooperation. |
| **C only** (Content negotiation) | Same CSP/CORS issues as B. Additionally, media type negotiation adds implementation complexity with no benefit over headers. |

Both B and C require CORS preflight for cross-origin iframe requests, which your payment provider's server doesn't support. **URL path versioning is the only mechanism guaranteed to work in restricted contexts.**

---

## Remaining Decisions

1. **Default version for unversioned URLs**: I recommend `v2` (latest) but you could argue for `v1` (safest). This determines behavior for old React Native apps in the WebView context.
   - **My recommendation: default to v2.** Old React Native apps will break, forcing updates—acceptable after 6-month deprecation window.

2. **Header validation**: Should unrecognized `Accept-Version` values fall back to default or error?
   - **Recommend: default silently.** Cleaner degradation, easier mobile client debugging.

3. **Versioning scope**: Version the entire `/api/` namespace (current) or per-endpoint?
   - **Recommend: entire namespace initially.** Simpler to implement and reason about. Per-endpoint later if needed.

This approach gives you the safety of path versioning everywhere, the flexibility of header-based versioning for modern clients, and **unblocks the incident scenario** without revenue loss.

---
Score each response on the following metrics (0-3):

| Metric | Response A | Response B |
|---|---|---|
| Ungrounded claims | | |
| Assumption acknowledgment | | |
| Alternative consideration | | |
| Error detection | | |
| Rework cycles | | |
| Confidence calibration | | |
| Final correctness | | |
| **Total** | | |
