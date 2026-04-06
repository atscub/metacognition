---
name: ops:handoff
description: "Prepare context for another person or a future session to continue work seamlessly. Use when stopping mid-task, handing off to a teammate, or when the next session will need to pick up where this one left off. Trigger on: /ops:handoff, 'hand this off', 'someone else will continue', 'pick this up later', 'context for next session'. Only when context is complex enough that git log alone won't suffice."
---

# Handoff — Context for Continuity

## Purpose

When work transfers between people or sessions, context is lost. The next person (or future you) wastes time reconstructing what was done, why, and what's next. A good handoff compresses the essential context into something actionable.

## The Handoff Process

### Step 1: State of Work

Summarize the current state clearly:

**What was the goal?**
- What problem were we solving?
- What was the user's original request?

**What was done?**
- List the changes made (files modified, features added, bugs fixed)
- What approach was taken and why?
- Any alternatives that were considered and rejected (and why — so the next person doesn't re-explore them)

**What's the current state?**
- Does it build? Do tests pass?
- Is it deployed? To what environment?
- Is there a PR open? What's its status?

### Step 2: What's Left

Be specific about remaining work:

**Unfinished items:**
- What still needs to be done?
- What's blocked and on what?
- Are there known bugs or edge cases not yet addressed?

**Open decisions:**
- What choices remain unmade?
- What information is needed to make them?
- Who should make them?

### Step 3: Gotchas and Context

Things the next person needs to know that aren't obvious from the code:

- **Surprising discoveries**: "The API doesn't actually support X despite the docs saying it does"
- **Workarounds in place**: "We're using Y because Z doesn't work in this version"
- **Sensitive areas**: "Don't touch file X without understanding Y first — it's load-bearing in a non-obvious way"
- **Environment specifics**: "This only reproduces with flag X enabled" or "requires database migration first"

### Step 4: Entry Points

Tell the next person where to start:
- Key files to read first
- Commands to run to get up to speed
- Links to relevant PRs, issues, docs, or discussions

### Step 5: Persist the Handoff

Choose the right format based on audience:
- **Same person, next session**: Save to memory or a handoff note in the repo
- **Teammate**: PR description, issue comment, or message
- **Future unknown person**: Documentation in the repo

## Quick Handoff

For simple cases:
1. What did I do?
2. What's left?
3. What's the one thing the next person needs to know?

## When to Use

- When stopping work mid-task
- When another developer will take over
- Before a long break from the project
- When context is complex enough that git log alone won't be enough

## Anti-Patterns

- **Assuming the code speaks for itself**: It doesn't. Not for the *why*.
- **Including every detail**: A handoff is not a transcript. Compress to what matters.
- **Skipping the gotchas**: The obvious stuff is in the code. The handoff's value is the non-obvious context.
