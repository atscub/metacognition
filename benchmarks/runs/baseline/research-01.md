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