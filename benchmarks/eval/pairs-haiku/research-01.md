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
## Socratic Analysis: GraphQL vs. REST for 3-Month Launch

Running through the framework. Here are my key uncertainties first:

### 1. What You're Actually Optimizing For

**Hidden assumption**: You're assuming this decision is primarily about architecture quality. But your real constraint is *shipping a working product in 3 months with a team that has no GraphQL experience*.

**The question that matters**: Is the current REST API *breaking the launch*, or is it *suboptimal*? 

- "Over-fetching" and "manual TS interfaces" sound like *friction problems* (dev experience), not *blockers*.
- "Polling instead of subscriptions" is a feature gap, but is it critical to launch?
- Which of these three things would actually cause users to not download the app or abandon it?

If the answer is "none of them — it all works, just not elegantly," then you have a different decision than if you're saying "mobile UX is unacceptable as-is."

### 2. What You're Not Considering

The senior dev's prototype probably covers the happy path. What's harder:

- **Authorization & security**: REST has predictable auth patterns. GraphQL + Django needs careful thought on field-level permissions. Have you modeled this?
- **Production N+1 prevention**: GraphQL makes it *easy* to write queries that hit the database dozens of times. Django ORM + DataLoader isn't magic — did the prototype handle this?
- **Real-time subscriptions**: Did the prototype actually implement WebSocket subscriptions? That's where a lot of GraphQL projects hit friction (connection management, scaling, debugging).
- **Debugging in production**: REST errors are simple. GraphQL errors can be tangled. Do you have observability for that?
- **Client-side complexity**: React Native + GraphQL client (Apollo? Relay?) adds tooling complexity. The mobile dev now needs to learn GraphQL patterns, not just call an API.

### 3. The Crux Question

**Can you do both**: Ship the mobile app in 3 months with REST, *and* migrate to GraphQL post-launch?

The senior dev might say "that's rework," but is it? If REST gets you to market and you migrate when you're not under deadline pressure, you've:
- De-risked the launch
- Kept the team focused
- Given everyone time to actually learn GraphQL instead of learning-while-shipping
- Proven what the real performance bottleneck is (maybe it's not what you think)

**Counter-consideration**: If subscriptions are genuinely critical to the app's behavior (real-time delivery tracking that affects UX), you can't retrofit that easily. This is worth testing now.

---

## My Take (with my uncertainty flagged):

**Confidence: Medium** (I'm reasoning about team dynamics and timeline risk, not reading your actual codebase or performance data)

**My recommendation: Stick with REST for launch**, with caveats:

### If you stick with REST:

✅ **Now:**
- Use OpenAPI schema + code generation instead of manual TS interfaces (solves the typing problem without GraphQL complexity)
- Implement a BFF (Backend For Frontend) layer or use field selection in your REST endpoints to address over-fetching (simpler than GraphQL)
- Validate whether subscriptions are actually needed pre-launch, or if polling is acceptable MVE
- Ship in 3 months

❌ **What you're deferring:**
- Cleaner GraphQL schema (migration debt)
- Proper subscription support (polling has worse UX but works)

### If you switch to GraphQL:

✅ **What you gain:**
- Better architecture for a 3-year old mobile app
- Subscription support
- Team learns a valuable skill

❌ **What you risk:**
- **Likely**: Ship late, or ship with bugs because you're learning in production
- **Possible**: Hit N+1 queries in production because no one understood Django ORM + DataLoader
- **Possible**: Mobile auth/permission problems surface mid-project
- **Outcome**: The app ships, but the team is burned out and the code quality is compromised

### The Steel-Manning Argument for GraphQL

The senior dev isn't wrong to want this — he's thinking about the next 3 *years*, not the next 3 months. If you're building a product you'll maintain for years, getting the architecture right upfront matters. And learning GraphQL as a team now, under deadline pressure with a prototype, is hard — but it's also the only way to actually learn it.

**But** that's a strategic choice, not a technical one. It requires accepting that the launch might slip, or the first version might be rough. Does your business allow for that?

---

## What Would Change My Mind

1. **Show me the prototype's scope**: How much of the 40 endpoints did it cover? Especially authentication and subscriptions.
2. **Show me the team's velocity**: If you've shipped complex features in 2 months before, maybe 3 months for GraphQL is realistic. If 3 months is tight even for normal work, it's unrealistic.
3. **Show me the mobile UX impact**: Metrics on over-fetching (how many extra bytes? How much slower?). Is it noticeable to users?
4. **Show me the real dependency**: Which of the three benefits (over-fetching reduction, typing, subscriptions) is actually blocking your launch? Or are they all nice-to-haves?

What does the data say?

## Response B
**My recommendation: Don't switch to GraphQL for launch.** But fix the real problems it would solve.

Here's the honest take:

## What's Real in His Arguments

1. **Over-fetching is a real problem** — mobile bandwidth matters, and your "custom fat endpoints" pattern is a maintenance nightmare. Valid concern.
2. **Type safety gap is painful** — mobile devs reverse-engineering Django serializers is error-prone. Valid pain point.
3. **Real-time tracking would be nice** — but polling works; it's not breaking the app.

## What's Underestimated

**You'd be learning GraphQL under deadline pressure:**
- GraphQL schema design is **not intuitive** if you're coming from REST. You'll make mistakes that are expensive to fix post-launch (like query complexity explosions, N+1 problems that look different than in REST).
- A small team with no production GraphQL experience is likely to ship something that "works" but has operational surprises (query costs, caching behavior, monitoring gaps).
- 3 months is tight for: schema design → Graphene setup → mobile code generation → testing → deployment stability validation. That's real pressure.

**The switching cost is higher than it looks:**
- You're not just adding GraphQL; you're maintaining both REST and GraphQL initially (or you're cutting off REST support and stranding existing mobile apps).
- Your 2 backend developers are now context-switching to learn a different query paradigm while supporting the REST API.

## The Pragmatic Path Forward

**Solve the problems without GraphQL:**

1. **Over-fetching** → Use REST query parameters for field selection (like a lightweight GraphQL):
   ```python
   GET /deliveries?fields=id,driver.name,vehicle.info,packages_count,status_updates[0:3]
   ```
   This is a 2-week feature. It's boring. It solves the problem.

2. **Type safety** → Generate TypeScript from Django serializers (OpenAPI/Swagger):
   ```bash
   python manage.py generateschema > schema.yaml
   npx openapi-typescript schema.yaml > types.ts
   ```
   This is a weekend setup. Mobile devs stop reverse-engineering.

3. **Real-time tracking** → Keep polling for launch; add WebSocket subscriptions in v2 if you need it. Your users aren't waiting for real-time; they're waiting for the app to launch.

## Why This Matters for Your Situation

- **Reduce risk**: You're launching a delivery service. The business succeeds if orders move reliably, not if the backend is architecturally pure.
- **Ship faster**: 3 months is already tight. Adding a new querying paradigm adds risk without adding launch value.
- **Keep options open**: If GraphQL becomes clearly necessary after launch, you can add it alongside REST. You have real usage data and pain points to justify the effort.

## When GraphQL Becomes the Right Call

- After launch, if you have 5+ mobile clients with divergent data needs, or real-time becomes mission-critical.
- When your team has shipped a v1 and knows what you actually need.
- When you have time to do it right.

---

**The key question for your senior dev:** *"Which of these three problems would GraphQL actually solve that we can't solve in REST in the next 3 weeks?"* The answers are all "not really — REST can solve them for the launch timeline."

Want me to help think through the field-selection REST design, or work through a premortem on why GraphQL might still make sense for your specific case?

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
