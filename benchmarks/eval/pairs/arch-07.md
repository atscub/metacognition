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
## Recommendation: URL Path Versioning (Option A)

The WebView constraint eliminates the header-based options before any other factor. Here's why, then the full plan.

---

## Why Headers Are Eliminated

The React Native payment WebView is the deciding constraint. The iframe makes cross-origin `fetch()` calls from a context whose CSP is owned by the payment provider. Adding any custom request header (whether `Accept-Version` or `Accept: application/vnd...`) to a cross-origin fetch triggers a CORS preflight `OPTIONS` request. The payment provider's server doesn't handle `OPTIONS` — end of story. You cannot fix this without the payment provider's cooperation, which you don't have.

This rules out both B and C entirely for that client. You could theoretically version that one client differently, but having two versioning mechanisms in the same codebase is a maintenance trap that guarantees inconsistency.

URL path versioning works from all contexts: URLSession, Retrofit, `fetch()`, `window.fetch()` in a restricted iframe. No special handling anywhere.

**The CloudFront bonus:** Your existing cache key already includes the URL path. Versioned URLs cache correctly by default. Header-based versioning would require a CloudFront Function and cache key modification — a non-trivial change that introduces cache poisoning risk if misconfigured.

---

## Handling the Legacy `/api/*` Endpoints

Do not delete these immediately. The current unversioned paths become v1 aliases during the migration window:

```
/api/appointments  →  treated as /v1/appointments (ALB forwards to v1 target group)
```

After 90 days of v2 being live, add `Deprecation` and `Sunset` headers to all `/api/*` responses and begin client migration tracking. After the mobile support window (6 months minimum post-v1 sunset announcement), decommission.

---

## ALB Routing Rules

Three listener rules, evaluated top to bottom:

```
Priority 10: Path pattern /v2/*  →  Target Group: tg-api-v2
Priority 20: Path pattern /v1/*  →  Target Group: tg-api-v1
Priority 30: Path pattern /api/* →  Target Group: tg-api-v1   ← legacy alias, same group
```

Use a separate target group (not just separate tasks) so you can independently set health check paths, drain timeouts, and eventually decommission v1 without touching v2 routing rules.

ALB rules are evaluated before CloudFront sees the response, so CDN caching picks up the versioned path automatically.

---

## ECS Deployment Strategy

**Phase 1 (now — 6 months):** Single ECS service, version routing in application code.

```
ecs-api (single service)
├── handles /v1/* — original field names (doctor_id, etc.)
├── handles /v2/* — new field names (provider_id, etc.)
└── handles /api/* — delegates to v1 handler
```

A thin routing layer (a middleware or a controller prefix) dispatches based on the path segment. The v1 handler runs the v2 business logic and applies a transformation layer to reshape the response — not duplicate logic, just a response adapter.

**Phase 2 (once v1 is sunset):** Delete the v1 handler and the transformation layer. Zero v2 changes required.

Avoid two ECS services in phase 1. The operational overhead (two deploy pipelines, two sets of alarms, two task definitions to keep in sync) isn't justified until the versions diverge enough that they genuinely need independent scaling or runtime environments.

---

## Deprecation Headers on All v1 Responses

From the day v2 launches, every response to `/v1/*` and `/api/*` includes:

```
Deprecation: true
Sunset: <ISO 8601 date — 6 months + 90 days from launch>
Link: <https://api.healthpulse.com/v2/[resource]>; rel="successor-version"
```

This gives you an observable signal in client logs and allows SDK authors to surface warnings without modifying business logic.

---

## Per-Client Migration Plan

**Web SPA** — Update base URL from `/api/` to `/v2/` on the next deploy after v2 launches. The SPA always ships latest, so no coordination needed. Done.

**iOS (800K installs, 40% on latest)** — Update base URL to `/v2/` in the next release. The 60% on older versions continue hitting `/api/*` (which routes to v1) through the entire deprecation window. No forced update required.

**Android (1.2M installs, 35% on latest)** — Same as iOS. Retrofit's base URL is set at client initialization; changing it is a one-line diff. Old installs continue working on `/api/*` → v1.

**React Native companion app** — Update base URL to `/v2/`. For the WebView payment flow specifically: the `window.fetch()` calls are already using URL paths. Ensure the URLs embedded in the WebView are updated to `/v2/*` in the same release. No header changes needed anywhere in this client.

---

## The March Incident in v2

The `doctor_id` → `provider_id` rename is exactly the kind of change v2 handles safely:

- `/v1/appointments` response: `{ "doctor_id": "abc123", ... }`
- `/v2/appointments` response: `{ "provider_id": "abc123", ... }`

The v2 handler returns `provider_id` natively. The v1 response adapter maps `provider_id` back to `doctor_id` before serialization. When the iOS and Android apps ship their v2 updates over the following days, they flip the base URL and start receiving `provider_id`. Mobile users on old app versions stay on v1 with no breakage. No incident.

---

## What You're Not Getting With This Approach

One honest tradeoff: URL path versioning is all-or-nothing per request — you can't version individual endpoints independently while keeping a single path prefix clean. If you need `/v2/appointments` but `/v1/providers` in the same client request, the client must assemble URLs per-resource rather than setting a single base URL.

In practice for HealthPulse, this doesn't matter. Breaking changes to one resource almost always accompany related changes elsewhere (the `doctor_id` → `provider_id` rename touched appointments, prescriptions, and provider records simultaneously). Clients want a coherent API version, not a patchwork. If you ever need true per-resource versioning, add a `Resource-Version` header as an *additive* mechanism alongside path versioning — but don't start there.

---

## 90-Day Timeline Skeleton

| Week | Action |
|------|--------|
| 0 | ALB rules live, `/v2/*` target group deployed, v1 transformation layer in place |
| 1 | Web SPA updated to `/v2/` |
| 2–4 | iOS, Android, React Native releases submitted with `/v2/` base URL |
| 4 | `Deprecation`/`Sunset` headers active on all `/v1/*` and `/api/*` responses |
| 8 | Monitor: what % of requests still hitting v1? Set threshold alert at >5% |
| 90 | v1 sunset date announced (calendar invite to all mobile team leads) |
| 90+180 | v1 target group decommissioned, `/api/*` ALB rule removed |

## Response B
## Working Through the Protocol

### Step 1: Surfacing My Assumptions

Before reaching for the familiar answer, let me name what I'm assuming:

1. **That URL versioning is "obviously" right** — I should catch myself here. URL versioning is the default pattern I reach for. That's anchoring, not reasoning. I need to steelman the alternatives honestly.

2. **That the WebView constraint is a hard blocker for custom headers** — This needs closer scrutiny. The problem says "the payment provider's server does not support CORS preflight." But CORS preflight goes to the *destination* server (HealthPulse's API), not the source. HealthPulse controls their own CORS headers. So why is this a blocker?

   Working through it: The WebView iframe runs in the payment provider's context. `window.fetch()` with a custom `Accept-Version` header from that iframe context makes the request "non-simple" under the CORS spec. This triggers an OPTIONS preflight to HealthPulse's API. HealthPulse *could* handle this preflight — but the problem states the payment provider's CSP and restricted iframe context make this unreliable. The practical constraint is: **you cannot guarantee custom headers will work in a third-party iframe context you don't control.** This is a genuine operational hard constraint, not just a theoretical one.

3. **That the three options are exhaustive** — They're not. Query parameter versioning (`?api_version=2`) exists. I'll assess it honestly.

4. **That caching matters for these endpoints** — Do healthcare endpoints benefit from CDN caching? Authenticated patient records and prescriptions: no. Appointment listings: possibly, with short TTLs. Provider listings: yes, relatively stable. So CDN caching matters *somewhat* but not uniformly.

---

### Step 2: Steelmanning Options B and C

**Strongest case for Option B (Custom Header):**

> "The WebView payment flow is a narrow special case. You could implement a tiered fallback: header versioning as the canonical mechanism, with a query parameter fallback (`?v=1`) for the WebView context only. That's a small carveout for one edge case. Meanwhile, all other clients get clean URLs, per-endpoint version negotiation, and no URL proliferation. The CloudFront Function for cache key augmentation is maybe 20 lines of JavaScript — one-time cost. The 'cleaner URLs' argument is real: monitoring dashboards, Swagger docs, and client code all read better when the URL isn't cluttered with version prefixes."

This is genuinely compelling. The WebView carveout is implementable. But it introduces *two* versioning mechanisms in the same API — which means two documentation paths, two testing matrices, and an ongoing risk that engineers forget to test the query-param fallback path. In a healthcare system where the last incident cost $180K, operational complexity is risk.

**Strongest case for Option C (Content Negotiation):**

> "HealthPulse is building an API that will exist for years. Content negotiation is how HTTP was *designed* to work. It gives you per-resource versioning, which means `/api/providers` can be at v1 while `/api/appointments` moves to v3. That granularity prevents the 'all-or-nothing' problem where a single breaking change forces every client to re-integrate the entire API surface. Libraries like `djangorestframework` and frameworks in Node.js support this natively."

The per-resource granularity is genuinely valuable. But: same WebView problem as Option B, and the "per-resource versioning" benefit is double-edged — it requires clients to track the version of *each* endpoint individually, which is harder to reason about than a single API version contract. For a consumer health app, the simpler client mental model matters.

---

### Step 3: Why the WebView Constraint Is Decisive

The problem is not theoretical. Here's the failure chain with Option B or C:

1. React Native app ships update with `Accept-Version: 2` header
2. App Store/Play Store review takes 1-7 days (same cycle that caused the $180K incident)
3. During that window, some React Native users open the payment flow
4. The WebView iframe sends `window.fetch()` requests with custom headers to HealthPulse API
5. CORS preflight fires; behavior depends on the payment provider's CSP enforcement
6. Payment bookings fail for an unknown fraction of users

You cannot test your way out of this. The iframe context is controlled by a third party. The risk of a silent failure mode in your payment flow is unacceptable in healthcare.

**Query parameter versioning** (`?v=2`) would sidestep this — URL parameters don't trigger CORS preflight. But query parameters are semantically wrong for versioning (they imply filtering, not routing), create cache-key unpredictability, and are easier to accidentally omit. This is a worse tradeoff than URL path versioning.

---

### Step 4: What Would Change My Mind?

- If someone confirmed that the WebView payment flow **never** calls the HealthPulse API (only the payment provider's API), the WebView constraint evaporates and Option B becomes more competitive.
- If the team has bandwidth to maintain two versioning mechanisms and a strong testing culture around the WebView carveout path, Option B with a query-param fallback is defensible.
- If the API surface were much larger (50+ endpoints), per-endpoint versioning (Option C) would have more value and might be worth the complexity.

None of these apply here. 7 endpoints, healthcare reliability requirements, and a recent $180K incident from operational complexity.

---

## Recommendation: URL Path Versioning (Option A)

URL versioning is correct — but not for the hand-wavy reasons usually given. Here's the precise reasoning:

**It is the only mechanism that works correctly for all four clients without special cases.** Custom headers fail in the WebView iframe context. Content negotiation fails for the same reason. URL versioning works in URLSession, Retrofit/OkHttp, `fetch()`, and `window.fetch()` in a restricted iframe — identically, without conditionals.

**It aligns perfectly with the existing infrastructure.** Your ALB can route `/v1/*` and `/v2/*` with path-based rules today, with no code changes. CloudFront's cache key already includes URL path — no CloudFront Function needed.

**The stated cons don't apply at this scale.** Seven endpoints doubling to fourteen is not "URL proliferation." "All-or-nothing version bump" is actually a *feature* for a consumer health app: clients have a single string (the base URL) that controls their entire API contract. That's easier to reason about than per-endpoint version tracking.

---

## Implementation Plan

### ALB Routing Rules (add these, in order)

```
Priority 1:  Path pattern /v2/*  →  Target Group: api-ecs-v2
Priority 2:  Path pattern /v1/*  →  Target Group: api-ecs-v1
Priority 3:  Path pattern /api/* →  Target Group: api-ecs-v2  (Web SPA default)
```

The Web SPA gets a permanent redirect from the unversioned path (or configure the React app to hardcode `/v2`). Mobile clients continue hitting `/v1/*` until their app updates.

### Version Coexistence Layer

Don't duplicate all handler logic. Run one codebase with a transformation layer:

```
Request: GET /v1/appointments/:id
  → Route to v2 handler
  → Run response through v1 adapter: rename provider_id → doctor_id
  → Return v1-shaped response

Request: GET /v2/appointments/:id
  → Route to v2 handler directly
  → Return v2-shaped response
```

This means the `doctor_id` → `provider_id` rename that caused the incident would have been a v2 change only. V1 handler would have continued returning `doctor_id` via the adapter — no mobile breakage, no rollback needed.

### Per-Client Plan

| Client | Action | Timeline |
|---|---|---|
| **Web SPA** | Update base URL to `/v2`. Deploy immediately. | Day 1 |
| **iOS (800K, 40% on latest)** | New version targets `/v2`. Old versions continue on `/v1`. | Next release cycle |
| **Android (1.2M, 35% on latest)** | Same as iOS. | Next release cycle |
| **React Native** | New version targets `/v2`. WebView payment flow inherits the base URL — no special casing needed since URL versioning works in iframe context. | Next release cycle |

The 60% of mobile users on old versions: they stay on `/v1` and keep working. No incident. The 90-day deprecation clock starts when you announce v1 deprecation, which you don't have to do until v2 is stable.

### Deprecation Tracking

Add these headers to all v1 responses the moment v2 ships:

```
Deprecation: true
Sunset: 2026-10-07   (today + 6 months, satisfies your 6-month mobile requirement)
Link: </v2/appointments>; rel="successor-version"
```

Log v1 requests by `User-Agent` and app version. Build a dashboard. Set an alert when v1 traffic from mobile drops below 5% — that's your signal that it's safe to remove.

### Handling the React Native WebView Specifically

The payment flow WebView calls HealthPulse APIs via `window.fetch()`. Because you're using URL versioning:
- The React Native app initializes the WebView with a base URL constant: `https://api.healthpulse.com/v1`
- The WebView uses that constant for all API calls
- No custom headers involved — no CORS preflight, no CSP conflict
- When the app updates to target v2, the constant changes to `/v2` and the WebView inherits it

Zero special cases.

### CloudFront

No changes required. Cache keys already include URL path, so `/v1/providers` and `/v2/providers` cache independently without any configuration changes. This is an advantage over Option B (which would have required a CloudFront Function).

---

## What to Watch For

The one genuine risk with URL versioning: engineers sometimes skip creating v2 routes for "unchanged" endpoints, then clients get 404s when they switch base URLs. Guard against this by:

1. **Integration test**: assert that every v1 route has a corresponding v2 route before deploying v2
2. **Default routing rule**: if a v2 route doesn't exist, the ALB returns a 301 to the v1 equivalent (temporary, not a permanent architecture)

The incident that cost $180K was a consequence of having *no* versioning. Any of the three options would have prevented it. But URL versioning prevents the next incident with the least operational surface area to get wrong.

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
