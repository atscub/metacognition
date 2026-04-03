---
name: ops:pr-feedback
description: "Systematically address PR review feedback — read, understand, respond, and fix. Use when a PR has review comments that need to be addressed. Trigger on: /ops:pr-feedback, 'address PR comments', 'fix review feedback', 'PR review', or when the user shares a PR URL with unresolved comments."
disable-model-invocation: true
---

# PR Feedback — Systematic Review Response

## Purpose

PR review feedback is a conversation, not a todo list. Each comment deserves understanding before action. This skill ensures you address feedback systematically — understanding the reviewer's concern, responding thoughtfully, and making changes that actually resolve the issue.

## The PR Feedback Process

### Step 1: Read All Comments First

Before changing anything:
1. Fetch all review comments on the PR
2. Read every comment in full — don't start fixing after the first one
3. Identify themes: are multiple comments pointing at the same underlying issue?
4. Note which comments are blocking vs. suggestions vs. questions

### Step 2: Categorize Each Comment

For each piece of feedback, classify it:

| Type | Action |
|------|--------|
| **Bug / Correctness** | Must fix. The reviewer found something wrong. |
| **Design / Architecture** | Discuss. May require rethinking the approach, not just a local fix. |
| **Style / Convention** | Fix if the project has established conventions. Discuss if it's preference. |
| **Clarification request** | Respond with explanation. May also indicate the code needs to be clearer. |
| **Suggestion / Nice-to-have** | Evaluate. Accept if it improves things without scope creep. Defer if it's out of scope. |
| **Nit** | Fix quickly. Don't argue about nits. |

### Step 3: Understand Before Fixing

For each non-trivial comment, ask:
- **What is the reviewer actually concerned about?** The surface comment may not be the real issue.
- **Are they right?** Check their claim. Don't assume they're wrong because you wrote the code.
- **Is there a deeper problem?** A comment about one line might indicate a pattern issue throughout the PR.
- **What would fully address this?** A minimal fix might not resolve the underlying concern.

### Step 4: Make Changes

Work through the comments systematically:
1. Group related changes — if three comments point at the same issue, fix the root cause once
2. Make each change in a way that clearly maps to the feedback
3. Don't sneak in unrelated changes — keep the diff focused on review response
4. If a comment requires significant rework, flag it to the user before proceeding

### Step 5: Respond to Comments

For each comment, respond appropriately:
- **Accepted and fixed**: "Fixed — [brief explanation of what you changed]"
- **Accepted with different approach**: "Agreed with the concern. Addressed it by [approach] instead because [reason]"
- **Respectfully disagreed**: "I see the concern, but I think the current approach is better because [reason]. Happy to discuss."
- **Deferred**: "Good point — I've created an issue for this since it's out of scope for this PR: [link]"
- **Clarified**: Answer the question, and if the code should be self-explanatory, improve the code too

### Step 6: Verify and Push

1. Run tests to make sure fixes didn't break anything
2. Review the full diff of your changes — do they make sense as a cohesive response?
3. Commit with a clear message referencing the review
4. Push and notify the reviewer

## Quick PR Feedback

For PRs with just a few comments:
1. Read all comments
2. Fix what needs fixing
3. Reply to each one
4. Push

## When to Use

- When a PR has review comments to address
- When the user shares a PR link and asks to handle the feedback
- After a re-review with new comments

## Anti-Patterns

- **Fixing without understanding**: Applying the reviewer's literal suggestion without understanding *why* they suggested it. The suggestion may be wrong while the concern is valid.
- **Defensive responses**: "It works fine" is not a response to design feedback. Engage with the concern.
- **Bundling unrelated changes**: Don't refactor surrounding code while addressing feedback. It makes re-review harder.
- **Ignoring comments you disagree with**: Respond to every comment, even if you disagree. Silence reads as dismissal.
