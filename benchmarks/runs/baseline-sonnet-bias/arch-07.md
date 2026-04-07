## Recommendation: URL Path Versioning (Option A), with qualifications

**Bottom line up front:** The restricted WebView iframe is the deciding constraint. Options B and C are non-starters — adding custom headers to cross-origin requests triggers CORS preflight, and you cannot fix this at the payment provider or CSP level. Option A is the only approach that works for all four client types without hacks.

The "all-or-nothing version bump" weakness of Option A is real but manageable through internal routing, addressed below.

---

## Why B and C Fail

The WebView payment flow sits in a cross-origin iframe with a CSP you don't control. CORS preflight (OPTIONS) is triggered by any non-simple request header — including `Accept-Version` (Option B) and a vendor `Accept` type (Option C). The payment provider's server doesn't handle OPTIONS. Result: every API call from the payment flow silently fails or throws a CORS error.

You cannot work around this without owning the payment provider's server configuration. The CSP restriction means you can't inject JavaScript to strip headers either.

Option A adds nothing to the request — the version is in the URL path, which is already part of every request. No preflight triggered.

---

## Option A Implementation

### Structural decision: single-app internal routing, not separate deployments

Route both `/v1/*` and `/v2/*` to the **same ECS target group**. Extract the version from the URL path in middleware and attach it to the request context. This avoids running two full stacks and lets you share unchanged endpoint handlers across versions without duplication.

```
ALB Listener Rules (priority order):
  1. Path: /v1/*   → Target Group: api-current   (version context: 1)
  2. Path: /v2/*   → Target Group: api-current   (version context: 2)
  3. Path: /api/*  → Target Group: api-current   (version context: 1, transitional alias)
  4. Default       → 404
```

The `/api/*` alias exists only to give current mobile clients a grace period — remove it after 60 days once new clients adopt `/v1/`.

### Solving "all-or-nothing version bump"

This is the legitimate criticism of URL path versioning, but it's an application-layer problem, not an infrastructure one. Implement a **version-aware transformation layer** in your API gateway or service layer:

```
Request: GET /v2/appointments/:id
  ↓
Handler: shared appointments handler (internal model always uses "provider_id")
  ↓
Response transformer: if version == 1, rename "provider_id" → "doctor_id" in response body
                       if version == 2, pass through unchanged
```

For the March 15 incident specifically, this would have meant:
- Backend deploys with internal `provider_id` field
- v1 transformer rewrites responses to include `doctor_id` 
- v2 returns `provider_id`
- Zero mobile breakage, Web SPA adopts v2 immediately

Endpoints that haven't changed between versions need no transformer — the same handler serves both `/v1/providers` and `/v2/providers` transparently.

### ALB routing rules (specific)

```yaml
# ALB Listener (HTTPS:443)
Rules:
  - Priority: 10
    Conditions:
      - Field: path-pattern
        Values: ["/v2/*"]
    Actions:
      - Type: forward
        TargetGroupArn: !Ref ApiCurrentTargetGroup

  - Priority: 20
    Conditions:
      - Field: path-pattern
        Values: ["/v1/*"]
    Actions:
      - Type: forward
        TargetGroupArn: !Ref ApiCurrentTargetGroup

  - Priority: 30
    Conditions:
      - Field: path-pattern
        Values: ["/api/*"]
    Actions:
      - Type: redirect   # or forward during transition
        RedirectConfig:
          Path: "/v1/#{path}"
          StatusCode: HTTP_301

  - Priority: 100  # default
    Actions:
      - Type: fixed-response
        FixedResponseConfig:
          StatusCode: "404"
```

When you eventually need to run v1 on a legacy code path (e.g., for a long-lived breaking change that's expensive to transform), change the v1 rule to point at `ApiLegacyTargetGroup`. Until then, one target group handles both.

### CloudFront

No changes required. Your current cache key includes URL path, so `/v1/appointments` and `/v2/appointments` are cached independently out of the box. If you add a surrogate cache key or cache invalidation on deploy, version it by path prefix (`/v1/*`, `/v2/*`).

If you later add response headers like `Deprecation: true` on v1 routes, ensure CloudFront doesn't cache these responses differently — add a response policy that strips or ignores that header from the cache key.

---

## Per-Client Migration Plan

| Client | Action | Timeline |
|--------|--------|----------|
| Web SPA | Update base URL to `/v2/`. Always on latest. | Deploy day |
| Android (Retrofit/OkHttp) | Update `BASE_URL` constant to `/v2/`. Submit update. | Submit same day; approved ~2 days |
| iOS (URLSession) | Update base URL constant to `/v2/`. Submit update. | Submit same day; approved ~4 days |
| React Native (fetch API) | Update base URL to `/v2/`. Submit to both stores. | Submit same day; ~4 days |
| WebView payment flow | No change needed — continues calling `/v1/` URLs from WebView context. URL versioning is invisible to CSP and CORS. | No action required |

The WebView payment flow is a special case: since it uses URL path versioning, it keeps working on `/v1/` indefinitely until you explicitly update the URL it receives. You're not blocked by CORS, CSP, or iframe restrictions at all.

---

## Deprecation Policy

```
v1 deprecation trigger: when mobile app adoption of v2-capable builds exceeds 80%
  OR 90 days after v2 GA, whichever is later.

After deprecation trigger:
  - Add "Deprecation: true" and "Sunset: <date+6months>" headers to all v1 responses
  - Send in-app notification for users on old builds (via push/in-app banner)
  - Log v1 usage by endpoint to track tail users
  - Hard removal: 6 months after deprecation trigger

Minimum timeline for the March 15 scenario:
  v2 GA: deploy day
  v1 deprecated: day 90
  v1 removed: day 270 (~9 months from GA)
```

The 6-month support requirement after deprecation is satisfied because the 90-day deprecation window + 6-month post-deprecation period means v1 stays up at minimum 9 months from v2 GA. Mobile installs that never update will still work across that window.

---

## What This Actually Fixes

The March 15 incident would not have happened under this plan:

1. Backend deploys with internal `provider_id`; v1 transformer maps it back to `doctor_id`
2. Web SPA switches to `/v2/` same day
3. Mobile clients continue using `/v1/` uninterrupted — no app store approval race, no broken bookings
4. New mobile builds adopt `/v2/` after store approval; you monitor adoption
5. After 90 days, v1 deprecated with headers; after 6 months, removed

The $180K revenue impact becomes $0. The rollback pressure disappears because v1 and v2 coexist rather than requiring a backend revert.

---

## Risks to Watch

**Transformer complexity creep**: If you accumulate too many field-level transformations in the v1 adapter, it becomes a maintenance burden. Establish a rule: if a v1 adapter requires more than ~20 lines of transformation logic for a single endpoint, that's a signal the endpoint has diverged enough to warrant separate handler code rather than inline transformation.

**"Latest" mobile adoption assumption**: The plan assumes 80% adoption is achievable in 90 days. With 35-40% of users on the latest version today, that rate may be optimistic. Instrument v1 vs v2 usage from day one so you have data to make the deprecation call, not guesswork.

**WebView URL hardcoding**: If the payment flow URL is hardcoded in the payment provider's iframe src, confirm you control the URL passed to the WebView — otherwise migrating that surface to v2 later requires a mobile app update, not just a config change.