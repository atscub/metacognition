---
name: meta:decompose
description: "Break a problem down to its fundamental components and rebuild understanding from first principles. Use when pattern-matching keeps failing, when a problem is too complex to reason about as a whole, when inherited assumptions may be wrong, or when you need to understand *why* something works, not just *that* it works. Trigger on: /meta:decompose, 'break this down', 'first principles', 'why does this work', 'start from scratch', or when you notice yourself applying a template solution to a problem you don't fully understand."
---

# Decompose — First Principles Breakdown

## Purpose

Most reasoning is by analogy: "this looks like X, so I'll do what worked for X." That's fast and usually fine. But when it fails — when the problem is novel, when the analogy is wrong, or when you're building on inherited assumptions that nobody questions — you need to go deeper. Decomposition strips a problem to its fundamentals and rebuilds from there.

## Why AI Needs This Especially

AI agents are powerful pattern matchers. That's a strength until it isn't:

- **Template solutions**: You've seen a thousand CRUD apps, so everything looks like a CRUD app
- **Inherited complexity**: The existing code does X in a complicated way, so you assume X requires complication — maybe it doesn't
- **Abstraction leaks**: You reason about the abstraction without understanding what's underneath, then get blindsided when the abstraction breaks
- **Cargo culting**: "Best practice" applied without understanding *why* it's best in this context

## The Decomposition Process

### Step 1: State the Problem Without Jargon

Rewrite the problem using only simple, concrete language. No framework names, no design pattern labels, no acronyms.

**Before**: "We need to implement a pub/sub event-driven architecture for the notification service."

**After**: "When something happens in the system, certain other parts need to find out about it and react. Right now they don't."

This strips away assumed solutions baked into the vocabulary.

### Step 2: Identify the Atomic Components

Break the problem into its smallest independent parts:

1. **What are the inputs?** What data/signals/events enter this system?
2. **What are the outputs?** What must be produced or changed?
3. **What are the constraints?** What rules must not be violated? (Distinguish real constraints from assumed ones.)
4. **What are the dependencies?** What must exist or be true for this to work?
5. **What is the core transformation?** Input → ??? → Output. What's the ???, at its simplest?

### Step 3: Question Each Component

For each component, ask:

| Question | What It Reveals |
|----------|----------------|
| Is this actually required, or is it inherited from a previous design? | Unnecessary complexity |
| What's the simplest possible version of this component? | Whether you're over-engineering |
| What happens if I remove this entirely? | Whether it's load-bearing or vestigial |
| Why is this done *this way* and not another? | Whether the approach is principled or accidental |
| What assumption does this encode? | Hidden assumptions that may be wrong |

### Step 4: Rebuild from Fundamentals

Now reconstruct:

1. Start with the core transformation — the minimal path from input to output
2. Add constraints back one at a time, justifying each
3. Add complexity only when a simpler version demonstrably fails
4. At each step, ask: "Would I add this if I were building from zero?"

### Step 5: Compare with Current Approach

The rebuilt version may look similar to the existing approach — that's fine, it means the current design is principled. But often you'll find:
- Components that exist for historical reasons, not current ones
- Complexity that was added for a use case that no longer exists
- A simpler path that wasn't visible through the lens of the current implementation

## Quick Decompose

For smaller problems, just answer:

1. What am I actually trying to accomplish? (One sentence, no jargon)
2. What's the simplest thing that could possibly work?
3. What would I have to add to make it production-ready, and why?

## When to Use

- When you've tried two approaches and both failed — you may be solving the wrong problem
- When working with legacy code where nobody remembers why things are the way they are
- When a "simple" change keeps cascading into unexpected complexity
- When the user asks "why do we need all this?" and you can't explain it
- When you're about to import a heavy dependency for what seems like a simple task

## Anti-Patterns

- **Decomposing for its own sake**: If the problem is straightforward and your first approach works, don't decompose. This is for when you're stuck or uncertain, not for every task.
- **Ignoring practical constraints**: First principles doesn't mean ignoring reality. "In theory we could rewrite everything" is not useful. Work within real constraints while questioning assumed ones.
- **Decompose without recompose**: Breaking things down is half the skill. The value comes from rebuilding and comparing. Don't just list components — reconstruct a solution.
- **Perfectionism**: The rebuilt version doesn't need to be optimal. It needs to be *understood*. Understanding the fundamentals is the goal, not the perfect architecture.
