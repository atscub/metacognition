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