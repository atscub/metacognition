I'll recommend a **URL path versioning strategy with a pragmatic twist** to handle your specific constraints. The WebView payment flow is the critical blocker here.

## Recommendation: URL Path Versioning with Server-Side Defaulting

```
/v1/appointments
/v2/appointments
/api/appointments  ← routes to /v2 (latest for web SPA and unversioned clients)
```

### Why This Works for Your Constraints

| Constraint | Solution |
|---|---|
| WebView payment flow (no custom headers) | ✅ URL path versioning works; no CORS preflight |
| CloudFront caching | ✅ Path already in cache key; no special CDN function needed |
| All client types | ✅ iOS, Android, React Native, Web all handle URL paths natively |
| Mobile without forced updates | ✅ Keep v1 live for 6+ months; old app continues working |
| Web SPA always latest | ✅ Default route `/api/*` → latest; SPA never needs code changes |

**Option B (custom headers)** breaks at the payment flow—CORS preflight on custom headers will trigger, and the payment provider doesn't support it. **Option C** has the same CORS issue with non-standard media types. **Option A** is the only approach that works everywhere.

---

## Implementation Plan

### 1. ALB Routing Rules

```
Rule 1: IF path starts with `/v1/*`
  → Forward to v1-handler target group (ECS container v1)

Rule 2: IF path starts with `/v2/*`
  → Forward to v2-handler target group (ECS container v2)

Rule 3: IF path is `/api/*` (default, no version specified)
  → Forward to v2-handler target group (latest)

Rule 4: Health checks
  → /health, /metrics → all versions respond
```

Each version can run in a separate ECS task definition or the same container with conditional routing based on path prefix.

### 2. Client-Specific Base URLs

| Client | Base URL | When to Update |
|---|---|---|
| **iOS** | `https://api.healthpulse.com/v1/` | Update when submitting new app version to App Store |
| **Android** | `https://api.healthpulse.com/v1/` | Update when submitting to Play Store |
| **React Native** | `https://api.healthpulse.com/v1/` | Auto-update via OTA (e.g., CodePush) |
| **Web SPA** | `https://api.healthpulse.com/api/` | Zero friction; always gets latest |
| **WebView payment** | `https://api.healthpulse.com/api/` | Works out-of-box; no special handling |

### 3. Versioning Lifecycle (Example: Deprecating v1)

```
2026-04: v2 released, v1 still fully supported
2026-07: v1 marked deprecated in docs/headers (90-day window starts)
2026-09: Deprecation window ends; v1 stop getting new features
2027-01: Remove v1 after 6 months post-deprecation
         (old iOS/Android users can't book appointments; hard cutoff)
```

**To prevent the January hard cutoff:** Consider extending v1 life to 12+ months and use alternative means to migrate stragglers:
- In-app banner: "Update required for new features"
- v1 returns `X-API-Deprecated: true` header + deprecation link in response body
- v1 still handles core booking but new features (e.g., telemedicine) only on v2

### 4. CloudFront Cache Configuration

**Current cache key already works:**
```
- URL path         ✅ `/v1/appointments` and `/v2/appointments` cache separately
- Host header      ✅ Standard
- Authorization    ✅ Standard (respects user identity)
```

**No CloudFront Function needed.** Different versions naturally have different cache entries.

### 5. Example Implementation: ECS Task Routing

**Option A: Single container, route at middleware**
```python
# Flask/FastAPI example
from flask import request, jsonify

@app.route('/api/<path:subpath>', methods=['GET', 'POST', 'PUT', 'DELETE'])
@app.route('/v1/<path:subpath>', methods=['GET', 'POST', 'PUT', 'DELETE'])
@app.route('/v2/<path:subpath>', methods=['GET', 'POST', 'PUT', 'DELETE'])
def route_by_version(subpath):
    version = request.path.split('/')[1]  # 'v1', 'v2', or 'api'
    
    if version == 'api':
        version = 'v2'  # default to latest
    
    handler = get_handler(version, subpath)  # Returns v1 or v2 business logic
    return handler(request)
```

**Option B: Separate ECS task definitions** (cleaner for large teams)
```
v1-handler task: runs v1 API code
v2-handler task: runs v2 API code
ALB routes /v1/* → v1-handler, /v2/* → v2-handler, /api/* → v2-handler
```

### 6. Backward Compatibility in v2

**Design v2 to be additive:**

v1 response:
```json
{
  "doctor_id": "dr-123",
  "appointment_date": "2026-04-07T10:00:00Z"
}
```

v2 response:
```json
{
  "doctor_id": "dr-123",           // kept for compatibility
  "provider_id": "dr-123",          // new canonical name
  "appointment_date": "2026-04-07T10:00:00Z",
  "appointment_type": "video",      // new field, optional
  "timezone": "America/New_York"    // new field, optional
}
```

Old clients reading v1 get what they expect. New clients opt into v2 fields. Minimizes "all-or-nothing" pain.

### 7. Handling the React Native WebView Payment Flow

The payment iframe uses `/api/*` → routes to v2 automatically. No special handling needed. The payment provider receives standard HTTP requests with no custom headers.

If payment provider adds new fields in v2, wrap the payment iframe to inject a modern client library instead of relying on raw `fetch()`:
```javascript
// payment-iframe.js
const API_BASE = 'https://api.healthpulse.com/api';  // Always latest
window.paymentAPI = {
  createPayment: (amount) => fetch(`${API_BASE}/payments`, { ... })
};
```

---

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Mobile users on v1 can't book after v1 sunset | Extend v1 to 12+ months; offer in-app incentive to update (e.g., discount, feature unlock) |
| URL proliferation (`/v1/`, `/v2/`, `/api/`) | Document it clearly; SDKs/base URLs hide this from most developers |
| Developers forget to update mobile base URLs | CI/CD check: require version bump in app config when shipping new API features |
| Old v1 clients hit edge cases in v2-only features | v2 returns `422 Upgrade Required` for features unavailable in v1; clients fallback gracefully |

---

## Why Not the Others?

- **Option B (custom header):** Fails at WebView payment iframe (CORS preflight). Would require separate fallback logic for payment flow.
- **Option C (content negotiation):** Same CORS issue; adds parsing complexity; no clear gain over URL versioning.

This strategy is **proven at scale** (Stripe, GitHub, AWS all use URL versioning) and trades aesthetic RESTfulness for operational simplicity and reliability—exactly what you need after the March incident.