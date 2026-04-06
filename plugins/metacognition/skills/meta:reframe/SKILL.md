---
name: meta:reframe
description: "Try different angles when the current approach is not working. Use when stuck, when the first solution feels wrong, when debugging hits a wall, or when you need to shift perspective on a design decision. Trigger on: /meta:reframe, 'think about this differently', 'other approaches', 'what am I missing', 'step back'. Only for significant decisions where a wrong framing costs real rework."
---

# Reframe — Multiple Perspectives Before Commitment

## Purpose

Your first framing of a problem determines your solution space. If you frame "the API is slow" as a caching problem, you'll only consider caching solutions — and miss that the real issue is an N+1 query. This skill forces you to deliberately re-frame the problem from multiple angles before committing to any one.

## The Reframing Process

### Step 1: State Your Current Framing

Write down how you're currently thinking about the problem:
- "This is a [type of problem] that needs [type of solution]"
- What mental model are you using?
- What category have you implicitly placed it in?

### Step 2: Apply Reframing Lenses

Work through at least 3 of these lenses:

#### The Inversion Lens
Instead of "how do I make X work?", ask "what would guarantee X fails?" Then avoid those things. Often reveals constraints you weren't thinking about.

#### The Simplicity Lens
What if this is simpler than you think? What if the "obvious" solution is actually correct? Strip away complexity: what's the minimal version of this problem? Sometimes we over-engineer because we pattern-match to harder problems.

If stripping to fundamentals reveals the problem is genuinely novel and pattern-matching is the core failure, consider handing off to `/meta:decompose` for a full first-principles breakdown.

#### The Zoom Out Lens
You're looking at a component. Zoom out to the system. Is this really the right place to solve this? Maybe the problem should be solved upstream, downstream, or at a completely different layer.

#### The Zoom In Lens
You're looking at the system. Zoom into the specific failure. What exactly is happening, byte by byte, line by line? Sometimes abstract thinking obscures a concrete, simple issue.

#### The User Lens
Forget the code. What is the *user* actually trying to do? Is there a way to give them what they need that doesn't require solving this technical problem at all?

#### The Time Lens
What does this look like in 6 months? Will this solution still make sense? What will have changed? Alternatively: what's the quick fix for now, and is that actually fine?

#### The Novice Lens
Explain the problem to someone who doesn't know the codebase. When you have to explain from first principles, you often spot assumptions you've been taking for granted.

If explaining from first principles reveals that you don't actually understand the fundamentals, hand off to `/meta:decompose`.

#### The Adversarial Lens
If someone was trying to break this solution, how would they? What edge cases, race conditions, or unexpected inputs would cause problems?

#### The Constraint Lens
What constraints are you assuming that might not actually exist? "We have to use this library" — do we? "This has to be real-time" — does it? Question every constraint.

#### The Precedent Lens
Has this problem been solved elsewhere in the codebase? In a well-known open source project? What did they do, and why?

### Step 3: Compare Framings

After generating alternative framings:
1. Which framing leads to the simplest solution?
2. Which framing best matches what's actually happening?
3. Which framing reveals risks the others don't?
4. Do multiple framings converge on the same solution? (Strong signal)
5. Do they diverge completely? (You need more information)

### Step 4: Choose and Proceed

Pick the framing that best fits. Briefly explain to the user:
- How you're thinking about the problem
- What other framings you considered
- Why this one seems right

Then proceed. Don't get lost in analysis.

## Quick Reframe (When Stuck)

If you're going in circles, just answer these three:
1. What am I assuming is true?
2. What if the opposite were true?
3. What would a senior engineer who knows this codebase well look at first?

## When to Use

- When your first approach doesn't work and you're not sure why
- Before making an architectural decision with long-term consequences
- When the user and you seem to be talking past each other
- When a bug defies your mental model
- When you catch yourself saying "this should work" but it doesn't

## Anti-Patterns

- **Reframing as procrastination**: The goal is *better* action, not *delayed* action. Don't use this to avoid committing.
- **Collecting framings without choosing**: You must converge. Pick one and go.
- **Only using comfortable lenses**: The most useful reframe is often the one that challenges your current approach the most.
