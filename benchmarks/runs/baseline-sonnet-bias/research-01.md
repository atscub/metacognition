Don't switch. Not now. Here's the analysis:

## The real cost of switching

Your three-month window is the decisive factor. GraphQL's learning curve isn't the query syntax — it's what bites teams in production:

- **N+1 queries**: Your delivery list example (driver + vehicle + packages + status updates per delivery) is a textbook N+1 problem. GraphQL doesn't solve this for free; you need DataLoaders. Without them, GraphQL makes this *worse* than a well-written REST endpoint.
- **Graphene-Django** specifically has a rough reputation for performance and ergonomics. The community has partly moved toward Strawberry-Django. Your senior dev's prototype probably hasn't hit the pain points yet.
- **Subscriptions** require Django Channels, ASGI, a channel layer (Redis), and WebSocket connection management. This is a meaningful infrastructure addition.
- **Schema design is hard to get right** the first time, and a bad schema is expensive to fix after clients are consuming it.

None of these are blockers long-term, but discovering them mid-sprint toward a launch deadline is a real risk.

## Address each problem directly instead

**Problem 1 — Over-fetching:**
Add a `?fields=` sparse fieldset parameter to your heavy list endpoints, or create 2-3 mobile-specific endpoints for the screens that hurt most. This is 1-2 days of backend work. Not elegant, but it ships.

**Problem 2 — Type mismatches (best ROI here):**
Add `drf-spectacular` to your Django project. It auto-generates an OpenAPI schema from your serializers and views. Then run `openapi-typescript-codegen` on the mobile side. You get generated TypeScript types from the actual source of truth, not by reading serializer code. This is 1 day of work and completely solves the problem.

**Problem 3 — Real-time tracking:**
Django Channels + Server-Sent Events or WebSockets for delivery status updates doesn't require GraphQL at all. Scope it to just the tracking screen; you don't need to push everything through subscriptions.

## When GraphQL actually makes sense here

After launch, when you have:
- Stable schema requirements (you'll know what mobile actually needs vs. what you guessed)
- Time to implement DataLoaders properly
- Space to run both APIs in parallel during migration
- Real usage data showing which endpoints are genuinely causing client pain

## Bottom line

Your senior dev is right about GraphQL's advantages for this domain. He's wrong about the timing. The problems he's identified are real, but each has a targeted fix that takes days, not months, and carries zero rewrite risk before launch.

Ship with REST + OpenAPI codegen + one or two fat endpoints for the heavy screens. Plan GraphQL for v2 with actual production data driving the schema design.