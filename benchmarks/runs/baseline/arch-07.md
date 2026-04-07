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