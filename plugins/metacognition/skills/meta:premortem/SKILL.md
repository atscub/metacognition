---
name: meta:premortem
description: "Anticipate failure before committing to a plan or implementation. Use before starting a risky implementation, making an architectural decision, deploying, or any high-stakes action. Trigger on: /meta:premortem, 'what could go wrong', 'risk check', 'before we do this', or when about to commit to an approach with significant consequences."
---

# Premortem — Anticipate Failure Before It Happens

## Purpose

A premortem inverts the usual sequence: instead of analyzing what went wrong *after* failure, you imagine the project has already failed and work backwards to figure out *why*. This leverages prospective hindsight — research shows people generate 30% more reasons for failure when they imagine it has already happened vs. when they ask "what might go wrong."

## The Premortem Process

### Step 1: State the Plan

Clearly articulate:
- What you're about to do
- What success looks like
- What the key assumptions are

### Step 2: Imagine It Failed

Project forward in time. The plan was executed. It failed. Not a minor hiccup — a significant failure. Now work backwards:

**Ask these questions:**

1. **What broke?** List every way this could fail, from likely to unlikely:
   - Technical failures (bugs, edge cases, performance, compatibility)
   - Integration failures (other systems, APIs, data formats)
   - Assumption failures (things you believed that turned out wrong)
   - Scope failures (took way longer, was way more complex than expected)
   - Unintended consequences (broke something else, created a security hole)

2. **What did we miss?** Think about:
   - What information are we acting without?
   - What haven't we read/checked that we should?
   - What are we assuming is true without verification?

3. **What did we ignore?** Think about:
   - Warnings or edge cases we dismissed as unlikely
   - Complexity we hand-waved away
   - The "it'll probably be fine" assumptions

### Step 3: Assess the Risks

For each identified failure mode, evaluate:

| Risk | Likelihood | Impact | Reversibility |
|------|-----------|--------|---------------|
| *specific risk* | High/Med/Low | High/Med/Low | Easy/Hard/Impossible |

Focus attention on:
- **High likelihood + High impact**: Must mitigate before proceeding
- **Low likelihood + Impossible to reverse**: Must mitigate before proceeding
- **High likelihood + Low impact**: Accept but monitor
- **Low likelihood + Easy to reverse**: Accept

### Step 4: Mitigation Plan

For each significant risk, propose one of:
- **Prevent**: Change the plan to eliminate the risk
- **Detect**: Add a check that catches the failure early
- **Recover**: Ensure you can roll back or fix quickly
- **Accept**: Explicitly decide to proceed despite the risk (and document why)

### Step 5: Decision

Present to the user:
- Top 3-5 risks in priority order
- Recommended mitigations
- A clear recommendation: proceed, proceed with changes, or reconsider

## Quick Premortem (for smaller decisions)

Not everything needs a full analysis. For moderate decisions, just answer:

1. What's the most likely way this fails?
2. What's the worst-case way this fails?
3. What's one thing I should verify before starting?

## When to Use

- Before implementing a plan that touches multiple systems
- Before making a decision that's hard to reverse
- Before deploying to production
- When the user asks "should we do X?"
- When you notice yourself feeling very confident about a complex plan (overconfidence signal)

## Anti-Patterns

- **Going through the motions**: Actually think about failure modes specific to *this* plan. Generic risks ("the code might have bugs") are useless.
- **Analysis paralysis**: The goal is better decisions, not perfect safety. Don't premortem a one-line change.
- **Ignoring your own results**: If you identify a serious risk, don't just note it and proceed anyway. Either mitigate it or explain why you're accepting it.
