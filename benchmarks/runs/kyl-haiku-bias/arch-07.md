I'm going to work through the Socratic checklist before recommending, because this decision carries high cost ($180K incident, compound downstream effects).

## What I'm Assuming vs. What I've Verified

| Assumption | Confidence | Verification Needed |
|-----------|-----------|-------------------|
| WebView payment flow *calls HealthPulse's API* (not just payment provider's API) | **LOW** — I inferred this from context | Critical — need clarification |
| Custom headers trigger CORS preflight in cross-origin iframes | **HIGH** — this is HTTP spec | N/A |
| Payment provider doesn't support CORS preflight | **MEDIUM** — user stated it, but haven't seen evidence | Matters only if WebView calls HealthPulse |
| All native clients can update headers on every request | **HIGH** — URLSession, Retrofit, fetch all support this | N/A |
| CloudFront cache key concerns are real but solvable | **MEDIUM** — plausible, but depends on current CDN function support | Needs investigation |

## Critical Uncertainties

Before I recommend, I need to clarify **one specific constraint** because it's the pivot point:

**Does the React Native WebView actually call HealthPulse's API, or only the payment provider's API?**

- **If WebView-only calls payment provider**: The payment flow constraint doesn't block header/content-negotiation versioning for HealthPulse's API. The constraint is isolated.
- **If WebView calls HealthPulse's API directly**: Custom header/content-negotiation versioning is genuinely blocked, and you're forced to URL path versioning.

This distinction changes the recommendation. Can you clarify what the WebView payment flow actually calls?

---

## Assuming WebView Calls HealthPulse API — My Recommendation

If the WebView constraint is real (it calls HealthPulse's API and cannot send custom headers), here's my analysis:

### **I recommend: URL Path Versioning (`/v1/...`, `/v2/...`)** 

**Rationale:**

1. **The WebView constraint is a hard blocker for headers/content-negotiation.** CORS preflight on custom headers in a payment iframe is a real problem you can't work around without modifying the payment provider's server (impossible) or moving the payment call outside the WebView (expensive re-architecture).

2. **URL path versioning is the only option that works for all four clients without workarounds:**
   - iOS, Android, React Native, Web all handle URL changes natively
   - The payment WebView can make requests to new URLs without header tricks
   - No CORS issues, no CDN cache key complications

3. **The "all-or-nothing" con is overstated in your context:** Yes, you must version all endpoints together, but:
   - Your last incident killed appointments *across endpoints* anyway (one breaking field rename)
   - Coordinating a full version bump is operationally simpler than per-endpoint versioning
   - You can deprecate old versions gradually without forcing simultaneous migration

4. **The client base URL update is a solved problem:**
   - iOS/Android: ship a config change in one release, no code change needed
   - React Native: same
   - Web SPA: rebuild and deploy same day (non-issue)
   - The 6-month grace period allows old clients to keep working on `/v1/` while you deprecate

### Implementation Plan

**ALB Routing (simplest, most visible):**

```
IF path matches /v2/* → route to ECS task group "api-v2"
IF path matches /v1/* → route to ECS task group "api-v1"
IF path matches /api/* (no version) → route to "api-v1" (default) OR return 410 Gone
```

This makes version visible in logs, ALB metrics, and during incidents.

**CloudFront Cache Key:**
- Include path in cache key (already done)
- No custom header handling needed
- `/v1/appointments` and `/v2/appointments` are separate cache entries (good)

**Deprecation Window:**
1. Deploy `/v2/` endpoints (new logic)
2. Web SPA switches to `/v2/` immediately
3. Native apps receive `/v2/` URL config in next release (no app store review needed for config)
4. Support `/v1/` for full 180 days (double the 90-day minimum)
5. Telemetry shows when `/v1/` traffic drops below 5% → retire `/v1/` in v3 planning

**Handling the Last-Mile Mobile Delay:**
- Publish a *configuration* change (not code), shipped out-of-band to old clients
- Old clients get new base URL from config service before next app store release
- Falls back to old URL if config unreachable (safe default)

### What About the REST Purist Argument?

Content negotiation and custom headers are "more RESTful," but REST is a style guide, not a law. The cost here is:
- Operational simplicity (won in favor of URL versioning)
- Client implementation (won in favor of URL versioning)
- Reliability under constraints (won decisively in favor of URL versioning)

Purity loses when it costs $180K and affects 1.2M+ users.

---

## Final Question

Before I write this up formally: **Is my understanding of the WebView constraint correct?** If the payment flow doesn't actually call HealthPulse's API, or if there's a way to proxy through the app backend, that changes the recommendation.