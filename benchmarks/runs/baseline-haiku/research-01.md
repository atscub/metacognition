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