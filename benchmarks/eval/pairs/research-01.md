# Task: research-01 — GraphQL migration for mobile delivery app

## Prompt
We're building a mobile app for a delivery service (iOS and Android, React Native).
Our backend is a Python Django REST API with about 40 endpoints. A senior developer
on our team is pushing us to switch to GraphQL. His main arguments are:

1. Reducing over-fetching on mobile. We have many list views with nested data — for
   example, a delivery list screen that shows the driver name, vehicle info, current
   package count, and the last three status updates per delivery. Right now we either
   make multiple REST calls per screen or have custom "fat" endpoints that return
   everything.

2. Getting a typed schema that the mobile team can use for code generation. Currently
   the mobile devs are manually writing TypeScript interfaces based on reading the
   Django serializer source code, which leads to subtle type mismatches.

3. Subscription support for real-time delivery tracking instead of our current polling
   approach.

Our team is 4 developers: 2 backend (Django), 1 mobile (React Native), and 1 full-stack.
None of us have used GraphQL in production before. The senior dev has done a few tutorials
and built a small prototype with Graphene-Django.

We're targeting a launch in 3 months. Current REST API is stable and working, just
inefficient for the mobile client.

Should we switch to GraphQL?


## Response A
## Socratic Analysis: GraphQL vs. REST Decision

Let me work through this carefully before giving you a recommendation.

---

### Epistemic check: what do I actually know here?

**High confidence** (well-established patterns): GraphQL's N+1 query problem, Graphene-Django's reputation, pre-launch tech switch risk profiles, OpenAPI codegen as a REST alternative.

**Medium confidence** (haven't verified in this session): Graphene-Django's current maintenance status vs. alternatives like Strawberry; specific Django Channels complexity for subscriptions.

**Assumption I'm examining**: That the senior dev's framing of the problems is accurate. Let me verify that before accepting it.

---

### Steelmanning the "switch now" position

The senior dev's arguments are technically *correct*. GraphQL was designed for exactly this use case — nested mobile data, typed schemas, real-time. React Native + Apollo Client is a mature, well-trodden path. Code generation from a GraphQL schema genuinely eliminates type drift. Subscriptions are GraphQL's native model for real-time. If the team pulls this off, they'll have a better architecture *and* won't face a painful migration later.

This is not a false pattern match. The technology fits the problem.

---

### Now the hard questions

**1. Are these problems actually blocking launch, or just annoying?**

You said the REST API is "stable and working, just inefficient." That's not a crisis. Inefficiency is fixable with targeted interventions. The question isn't "would GraphQL be better?" — it's "is the cost of switching worth the benefit *before launch*?"

**2. What's the N+1 trap?**

Your specific example — delivery list with nested driver, vehicle info, package count, and last 3 status updates — is precisely the scenario where Graphene-Django will generate catastrophically inefficient database queries by default. Every item in the list will trigger separate queries for each nested field. A team new to GraphQL will almost certainly ship this. Fixing it requires explicit DataLoader implementation, which is non-trivial. This isn't theoretical — it's the most documented pitfall of Graphene-Django specifically.

**3. Subscriptions are the hard part, not the easy part**

The senior dev lists subscriptions as an argument *for* switching, but subscriptions are actually the riskiest piece. Django Channels + Redis + WebSocket management is a significant infrastructure lift. Building this correctly, with reconnection logic, auth, and error handling, under time pressure, by a team new to the technology, is where projects slip. Don't let "subscriptions" appear as a checkbox on a list of benefits — it's a separate project in itself.

**4. A prototype is not production**

There's a specific gap between "tutorial + prototype" and "production GraphQL":
- Query depth/complexity limits (malicious or accidental)
- Field-level authorization (not just endpoint-level)
- Partial failure semantics (GraphQL returns 200 even on errors)
- Caching (REST caching is trivial; GraphQL requires persisted queries)
- Performance monitoring (standard APM tools don't understand GraphQL queries well)

None of these are blockers if you have time. All of them are landmines at launch.

**5. What's the cost of being wrong in each direction?**

| Direction | Succeeds | Fails |
|-----------|----------|-------|
| Switch to GraphQL | Better architecture, no future migration | Miss launch, or ship a buggy, poorly-understood backend |
| Stay with REST | Ship on time, optimize later | Slightly inefficient UX at launch |

The downside of switching and failing is far worse than the downside of staying. This is asymmetric risk, and asymmetric risk should bias you toward the conservative choice.

---

### Are the senior dev's problems actually solvable with REST?

This is where I want to push back on the framing. Each argument has a targeted REST-based answer:

**Over-fetching on mobile nested views:**
- Add 2-3 screen-specific aggregate endpoints for your worst screens. Ugly, but ships in days.
- Or add sparse fieldsets (`?fields=driver_name,vehicle_info,package_count`) to existing endpoints — DRF supports this natively.

**Typed schema / TypeScript type mismatches:**
- Install `drf-spectacular`, generate an OpenAPI schema, run `openapi-typescript-codegen`. This is 1-2 days of work, solves the problem completely, and the mobile team gets types automatically from the spec.

**Real-time tracking:**
- Polling with a short interval is acceptable for delivery tracking at launch — users don't perceive the difference between 5-second polling and true real-time.
- If polling is genuinely unacceptable, a lightweight WebSocket "ping to refresh" channel (just "hey, reload delivery #123") is far simpler than full GraphQL subscriptions and doesn't require a full stack change.

---

### Where I'm being careful about my own biases

I'm checking myself for **complexity bias** in the opposite direction — sometimes the simple answer is too conservative. But I don't think that's happening here. The REST alternatives I'm proposing are genuinely simpler *and* solve the stated problems. The simplest thing that could work, here, is actually simple.

I'm also checking for **authority bias** — am I dismissing the senior dev too quickly because he's a relative newcomer to GraphQL? No: my concern isn't "GraphQL is bad," it's "3 months before launch, with no production experience, is the wrong time."

---

### My recommendation

**Don't switch before launch.** Here's what to do instead:

1. **This week**: Set up `drf-spectacular` → OpenAPI schema → TypeScript codegen. Type mismatch problem gone.
2. **Over the next 2-3 weeks**: Add aggregate endpoints or sparse fieldsets for the 3-4 worst mobile screens. Over-fetching problem reduced substantially.
3. **For launch**: Keep polling. Measure whether users actually notice.
4. **Post-launch (month 4+)**: Now evaluate GraphQL seriously. You'll have real production traffic data to understand actual query patterns. You can migrate incrementally. The senior dev can build real production experience without a launch deadline overhead.

The senior dev is right that GraphQL fits your use case. He's wrong about the timing. Three months before launch is when you reduce risk, not when you introduce it.

---

**Confidence in this recommendation: high.** The specific REST alternatives I named (drf-spectacular, openapi-typescript-codegen, sparse fieldsets) are real tools — verify them before committing, but they exist and are mature. The N+1 and subscription complexity concerns are well-documented, not speculative.

## Response B
## Don't switch. Address the actual problems instead.

Your senior dev has correctly diagnosed three real problems, but GraphQL is not the only solution to any of them — and switching introduces compounding risk against your timeline.

### The core constraint is decisive

3 months to launch, zero production GraphQL experience on the team. GraphQL has real operational complexity that tutorials don't cover:

- **N+1 queries** hit you immediately on list views. You need DataLoader or similar to batch database calls. Graphene-Django makes this easy to get wrong and hard to debug.
- **Authorization** moves from resource-level (REST) to field-level. Every resolver needs auth checks. Missing one is a security hole.
- **Caching** breaks. REST gets HTTP caching for free. GraphQL (POST-based) gets none. You'll need to implement it explicitly.
- **Error handling** is counterintuitive — GraphQL returns HTTP 200 even for errors, which surprises everyone the first time.

A Graphene-Django prototype that works for happy-path demos is not evidence that the production path is clear.

### Each problem has a targeted fix

**Over-fetching on list views**

Add 2-3 purpose-built mobile endpoints instead of 40 generic ones. A `GET /deliveries/summary/` that returns exactly what the delivery list screen needs is faster to build, easier to cache, and simpler to reason about than a GraphQL schema migration. DRF supports this trivially.

**Typed schema and code generation**

This is solved by [drf-spectacular](https://github.com/tfranzel/drf-spectacular) + [openapi-typescript](https://github.com/openapi-ts/openapi-typescript). You get:
- Auto-generated OpenAPI 3 schema from your existing serializers
- TypeScript types generated from that schema
- Zero migration cost

Your mobile dev stops reading Django source code. This is a one-day setup, not a 3-month migration.

**Real-time tracking**

GraphQL subscriptions on Django require Django Channels + Redis + a WebSocket layer — the same infrastructure you'd need to add WebSockets to REST. There's no infrastructure savings. Use Django Channels with a plain WebSocket or Server-Sent Events endpoint for the tracking screen. Simpler, well-documented, solves exactly one problem.

### When GraphQL would make sense here

Post-launch, if your mobile surface area grows to many heterogeneous clients with genuinely different data needs, the trade-off shifts. After launch you'll also have real profiling data instead of architectural intuition, and the team will have bandwidth to learn it properly.

### What to tell your senior dev

His diagnosis is right; his solution is the wrong tool for this stage. The question isn't "is GraphQL good?" — it's "does the value of switching exceed the cost of switching *right now*?" The answer is no, because drf-spectacular + targeted endpoints gets you 80% of the benefit at 5% of the risk, and you ship on time.

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
