# Task: research-04 — Monolith vs microservices for early-stage startup

## Prompt
We're a startup with 8 engineers, pre-Series A. We have three distinct product areas:

1. A real-time chat system (WebSocket connections, message persistence, typing indicators,
   presence detection). Traffic is bursty — 10x spikes during business hours. We're
   considering Elixir or Go for this because Python can't handle the concurrent
   connections well.

2. A payment processing pipeline (Stripe integration, invoicing, subscription management,
   revenue recognition). This needs PCI compliance scoping, and our compliance consultant
   says isolating payment processing makes the audit scope much smaller.

3. An admin dashboard (CRUD operations, reporting, user management). Low traffic, mostly
   internal. Classic Django admin territory.

Right now everything is in a single Django monolith. The chat system is built on Django
Channels and it works but struggles above 500 concurrent WebSocket connections on a
single server instance. The payment code is interleaved with the rest of the application
— our Stripe webhooks share the same process and database as everything else, which our
compliance consultant flagged.

Our CTO wants to extract the chat and payment systems into separate services. Our most
senior backend engineer pushes back hard: "Monolith first, always. Microservices are a
trap for small teams. You'll spend all your time on infrastructure instead of features."

He's very experienced (15 years) and I respect his judgment. But the compliance concern
is real and the chat performance ceiling worries me.

Who's right? Should we stay monolith or start splitting?


## Response A
I'm going to slow down here, because this is a high-stakes decision and I need to be honest about what I actually know.

## My Confidence Limits

Let me first categorize what I'm working with:

- **High confidence**: General architectural trade-offs (monolith vs services, scaling limits, operational complexity)
- **Medium confidence**: Django Channels scaling characteristics, PCI compliance implications
- **Low confidence**: Your *actual* code, your team's infrastructure skill, your specific compliance requirements, your burn rate/runway

The honest answer is: **I cannot tell you who is right, because the right answer lives in specifics I don't have.** But I can help you think through this better.

## What You Actually Disagree About

I notice you're framing this as "monolith vs. microservices" but I think the real disagreement is narrower. Let me steelman both sides:

**The senior engineer's case** (strong version):
- Microservices don't solve architectural problems — they expose them. If your code is tangled now, splitting it just tangles the network instead.
- At 8 engineers, you'll pay a brutal tax in deployment complexity, debugging difficulty, deployment coordination, and operational knowledge.
- "We need to fix chat scaling" and "we need to isolate payment for compliance" are two separate problems, and both have solutions that don't require the full microservices tax.
- Most startups split too early and regret it.

**The CTO's case** (strong version):
- The compliance consultant flagged a real audit scope problem — that's not abstract, that's a business constraint.
- Django Channels hitting a 500-connection ceiling is a structural ceiling, not a tuning problem. You'll hit it again at 5x.
- Building the wrong boundaries now (payment code in the chat monolith) gets harder to fix as it grows.
- You don't need *microservices* (the full complexity). You need *service isolation* (much simpler).

**Notice**: These aren't actually incompatible positions. Both could be right about different aspects.

## Questions That Actually Matter

Before you decide, you need answers to these (and I can't give them to you from the outside):

1. **On compliance**: Can your consultant accept "payment processing in its own process/database/deployed-separately but not a full microservice"? Or do they actually require a separate service? This is a binary that changes everything.

2. **On chat scaling**: Have you actually hit the 500-connection ceiling in production or in load testing? If it's load testing, does your actual concurrent load profile get there? (Bursty ≠ sustained; you might have 10x users but they might be distributed across longer time windows.)

3. **On payment code**: How tangled *is* it? Can you extract the payment model and webhooks into a separate module (still in the monolith) and test it independently? Or is it deeply coupled?

4. **On team capability**: Can your team handle operational complexity? One of you already runs Kubernetes? Has experience with service-to-service debugging? If "no" to both, that's a real constraint.

5. **On runway**: What's your cash situation? If you have 18-24 months of runway, you can afford to split. If you have 8 months, you probably can't.

## What I'd Actually Do If This Were My Decision

**Not** "pick one side." Instead:

**Phase 1** (next 1-2 months, while you're still scaling traffic):
- Extract payment into its own module (still in monolith, but isolated). Prove you can test it independently. This makes the service isolation *later* trivial if compliance requires it.
- Profile chat under realistic load. Figure out if 500 is your real limit or a test artifact. If it's real, try vertical scaling first (bigger machine, better Channels config), then horizontal scaling in the monolith (load balancer + multiple servers sharing DB).

**Phase 2** (decision point at 2-3 months):
- If compliance consultant says "no, you really do need separate services": split payment. It's a contained service, well-understood, doesn't require chat/admin to work.
- If chat is still struggling even after scaling: you have two paths: (a) go deep on Django Channels / asyncio optimization, or (b) build a separate Go/Elixir chat service just for the WebSocket layer, keep everything else in Django.
- If neither is urgent: stay monolith.

This isn't "monolith vs microservices" — it's **doing the smallest thing that solves the actual problem**, in the order you encounter it.

## The Real Risk

Here's what I'd worry about: **not deciding deliberately**. Drifting toward microservices because it *feels* safer, or staying monolith because you're afraid, both lose. The senior engineer is right that microservices are a common trap, *and* the CTO is right that compliance + scaling are real constraints.

What's the timeline? When do you actually need to make this call?

## Response B
They're both right about different things, and the question itself is a false binary. You don't actually have to choose "monolith vs. microservices"—you have two distinct problems that might need different solutions.

## What the senior engineer gets right

- Small teams with monoliths ship faster. That's empirically true.
- Extracting multiple services at once is often a disaster (database synchronization, deployment coupling, observability nightmare).
- Many startups do premature extraction and regret it.

## What he's missing

- **Payment extraction isn't optional.** Your compliance consultant flagged a real audit scope issue. "Don't extract services" is a good default, but it loses priority against regulatory risk. You're not doing this for architectural elegance—you're doing it because it's a compliance requirement. That's actually one of the only good reasons to extract early.
- **The chat scaling problem is physical.** Django Channels + a single-threaded Python process maxes out around 500 concurrent connections. That's not "scale it vertically," it's a real ceiling. You'll hit it within a year if the chat system gains traction.

## What the CTO might be underestimating

- Extracting *two* services simultaneously from a monolith is genuinely harder than it sounds. Database migrations, cross-service communication, deployment orchestration, new monitoring—it's real burden.
- You don't have deep devops/platform experience yet (8 engineers, pre-Series A). That's your actual constraint, not the architecture.

## Here's what I'd actually do

**Phase 1 (next month): Extract payments only**
- This is the lowest-risk extraction because payments are a natural boundary: isolated business logic, clear API, no real-time requirements, can be a separate database entirely
- This satisfies your compliance consultant *today*
- You learn about service extraction at low cost
- The senior engineer sees that you can do this without chaos

**Phase 2 (2-3 months later): Fix chat scaling**
- But don't immediately extract to a separate service
- First, replace Django Channels with a better WebSocket library (like `aiohttp` or even Go-based `ably` SDK)
- Run multiple chat process instances with a shared Redis message broker
- This stays "monolithic" in spirit (same codebase, same deployment) but solves the concurrency problem
- You'll know by then whether microservices extract was painless

**Phase 3 (optional, 4+ months): Extract chat if needed**
- By now you have payment extraction experience and know whether the chat performance fix was enough
- If you need to extract chat later, you'll do it better

## Why this path wins

- ✅ Compliance issue solved immediately (small, focused work)
- ✅ Respects the senior engineer's "don't over-engineer" principle (one extraction, not two)
- ✅ Solves the actual scaling bottleneck without betting on distributed systems
- ✅ You learn the hard way if microservices help or hurt (with a low-cost first example)
- ✅ If chat scales fine after the library upgrade, you never extract it and saved yourself months of infrastructure work

The senior engineer isn't wrong that monoliths are right for small teams. The CTO isn't wrong that you have real problems. They're just on different timetables. **Start with the non-negotiable (payments), then measure before the next extraction (chat).**

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
